#!/usr/bin/env python3
"""
Transcript Protection Hook — PreToolUse hook for Bash commands.
Blocks rm/mv on sacred transcript files (~/.claude/projects/-Users-d-patnaik-honeybloom-*/*.jsonl).
"""

import json
import os
import re
import sys
from fnmatch import fnmatch
from typing import Optional

# Protected path pattern (expanded)
HOME = os.path.expanduser("~")
PROTECTED_PATTERN = os.path.join(HOME, ".claude/projects/-Users-d-patnaik-honeybloom-*/*.jsonl")

# Commands that can delete/move files
DANGEROUS_COMMANDS = {"rm", "mv"}


def extract_paths_from_command(command: str) -> list[str]:
    """Extract potential file paths from a shell command.

    Handles:
    - Unquoted paths
    - Single-quoted paths
    - Double-quoted paths
    - Tilde expansion
    """
    paths = []

    # Match quoted strings (single or double) and unquoted tokens
    # This regex captures: 'path', "path", or unquoted-path
    token_pattern = r"""'([^']*)'|"([^"]*)"|(\S+)"""

    for match in re.finditer(token_pattern, command):
        # Get whichever group matched
        token = match.group(1) or match.group(2) or match.group(3)
        if token:
            # Expand tilde
            expanded = os.path.expanduser(token)
            paths.append(expanded)

    return paths


def is_protected_path(path: str) -> bool:
    """Check if a path matches the protected pattern."""
    # Normalize the path
    normalized = os.path.normpath(path)

    # Pattern: ~/.claude/projects/-Users-d-patnaik-honeybloom-*/*.jsonl
    # Break it down for fnmatch
    pattern_dir = os.path.join(HOME, ".claude/projects")

    # Check if path is under the projects dir and matches pattern
    if not normalized.startswith(pattern_dir):
        return False

    # Get relative path from projects dir
    rel_path = os.path.relpath(normalized, pattern_dir)
    parts = rel_path.split(os.sep)

    # Must be: -Users-d-patnaik-honeybloom-*/something.jsonl
    if len(parts) < 2:
        return False

    dir_part = parts[0]
    file_part = parts[-1]

    # Check directory matches -Users-d-patnaik-honeybloom-*
    if not fnmatch(dir_part, "-Users-d-patnaik-honeybloom-*"):
        return False

    # Check file is a .jsonl
    if not file_part.endswith(".jsonl"):
        return False

    return True


def get_base_command(command: str) -> Optional[str]:
    """Extract the base command (rm, mv, etc.) from a shell command."""
    # Strip leading whitespace and get first token
    command = command.strip()

    # Handle common prefixes: sudo, env vars, etc.
    # Skip env var assignments (VAR=value)
    tokens = command.split()

    for token in tokens:
        # Skip env var assignments
        if "=" in token and not token.startswith("-"):
            continue
        # Skip sudo
        if token == "sudo":
            continue
        # This should be the command
        return token

    return None


def main():
    try:
        # Read JSON from stdin
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        # Not valid JSON, allow (shouldn't happen)
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")

    # Only care about Bash commands
    if tool_name != "Bash":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    # Get the base command
    base_cmd = get_base_command(command)

    if base_cmd not in DANGEROUS_COMMANDS:
        sys.exit(0)

    # Extract all paths from the command
    paths = extract_paths_from_command(command)

    # Check if any path matches protected pattern
    for path in paths:
        if is_protected_path(path):
            print(
                f"BLOCKED: Cannot {base_cmd} transcript file.\n"
                f"Path '{path}' matches protected pattern.\n"
                f"Transcript files (~/.claude/projects/-Users-d-patnaik-honeybloom-*/*.jsonl) are sacred.",
                file=sys.stderr
            )
            sys.exit(2)

    # No protected paths found, allow
    sys.exit(0)


if __name__ == "__main__":
    main()
