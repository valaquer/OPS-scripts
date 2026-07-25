#!/usr/bin/env python3
"""
Block write access to the Aether database for all teammates.
PreToolUse hook — blocks Bash/Write/Edit targeting aether.db, aether.db-wal, aether.db-shm.
Read tool and MCP tools are unaffected.
"""

import json
import os
import sys

AETHER_DB = os.path.realpath("/Users/deepak-macmini/honeybloom/library/aether/aether.db")
DB_BASENAME = "aether.db"

DENY_MSG = "Write access to the Aether database is blocked. Use the Read tool or MCP read_room for access."


def resolve_and_match(path: str) -> bool:
    expanded = os.path.expanduser(path)
    try:
        resolved = os.path.realpath(expanded)
    except (OSError, ValueError):
        resolved = expanded
    if DB_BASENAME in os.path.basename(resolved):
        return True
    if resolved == AETHER_DB or resolved.startswith(AETHER_DB):
        return True
    return False


def command_targets_db(command: str) -> bool:
    if DB_BASENAME in command:
        return True
    return False


def deny(on_opencode: bool):
    print(DENY_MSG, file=sys.stderr)
    if on_opencode:
        print("deny")
        sys.exit(0)
    else:
        sys.exit(2)


def main():
    on_opencode = "OPENCODE_HOOK_TYPE" in os.environ

    if on_opencode:
        tool_name = os.environ.get("OPENCODE_TOOL_NAME", "").lower()
        tool_input_raw = os.environ.get("OPENCODE_TOOL_INPUT", "")
        tool_input = {}
        command = tool_input_raw
    else:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            sys.exit(0)
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")

    if tool_name == "Bash" or (on_opencode and command):
        if command_targets_db(command):
            deny(on_opencode)

    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if file_path and resolve_and_match(file_path):
            deny(on_opencode)

    sys.exit(0)


if __name__ == "__main__":
    main()
