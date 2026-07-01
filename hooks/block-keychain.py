#!/usr/bin/env python3
"""
Block Keychain access for all teammates except Burt.
PreToolUse hook — inspects Bash commands for `security` CLI calls.
"""

import json
import os
import re
import sys

def get_teammate_from_cwd(cwd: str) -> str:
    m = re.search(r'/honeybloom/([^/]+)', cwd)
    return m.group(1).lower() if m else ""

def main():
    on_opencode = "OPENCODE_HOOK_TYPE" in os.environ

    if on_opencode:
        tool_name = os.environ.get("OPENCODE_TOOL_NAME", "").lower()
        command = os.environ.get("OPENCODE_TOOL_INPUT", "")
        cwd = os.getcwd()
    else:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            sys.exit(0)
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Bash":
            sys.exit(0)
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")
        cwd = input_data.get("cwd", os.getcwd())

    if not command:
        sys.exit(0)

    teammate = get_teammate_from_cwd(cwd)

    if teammate == "burt":
        sys.exit(0)

    if re.search(r'\bsecurity\s', command):
        msg = "Keychain access blocked. Request credentials through Burt at direct-burt."
        print(msg, file=sys.stderr)
        if on_opencode:
            print("deny")
            sys.exit(0)
        else:
            sys.exit(2)

    sys.exit(0)

if __name__ == "__main__":
    main()
