#!/usr/bin/env python3
"""
Outbox Protection Hook — PreToolUse hook for Bash commands.
Blocks rm/mv/rmdir on the outbox folder (~/honeybloom/mailbox/outbox/) and its contents.
"""

import json
import os
import re
import sys
from typing import Optional

HOME = os.path.expanduser("~")
PROTECTED_DIR = os.path.join(HOME, "honeybloom", "mailbox", "outbox")

DANGEROUS_COMMANDS = {"rm", "mv", "rmdir"}


def extract_paths_from_command(command: str) -> list[str]:
    """Extract potential file paths from a shell command."""
    paths = []
    token_pattern = r"""'([^']*)'|"([^"]*)"|(\S+)"""
    for match in re.finditer(token_pattern, command):
        token = match.group(1) or match.group(2) or match.group(3)
        if token:
            expanded = os.path.expanduser(token)
            paths.append(expanded)
    return paths


def is_protected_path(path: str) -> bool:
    """Check if a path is the outbox directory or a file within it."""
    normalized = os.path.normpath(path)
    protected = os.path.normpath(PROTECTED_DIR)
    return normalized == protected or normalized.startswith(protected + os.sep)


def get_base_command(command: str) -> Optional[str]:
    """Extract the base command from a shell command."""
    tokens = command.strip().split()
    for token in tokens:
        if "=" in token and not token.startswith("-"):
            continue
        if token == "sudo":
            continue
        return token
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    base_cmd = get_base_command(command)
    if base_cmd not in DANGEROUS_COMMANDS:
        sys.exit(0)

    paths = extract_paths_from_command(command)
    for path in paths:
        if is_protected_path(path):
            print(
                f"BLOCKED: Cannot {base_cmd} outbox contents.\n"
                f"Path '{path}' is in the protected outbox directory.\n"
                f"The outbox (~/honeybloom/mailbox/outbox/) is protected from deletion.",
                file=sys.stderr
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
