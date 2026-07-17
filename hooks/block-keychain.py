#!/usr/bin/env python3
"""
Block credential access for all teammates except Burt.
PreToolUse hook — blocks Keychain (`security` CLI) and ~/.secrets/ reads.
Handles both Bash and Read tool calls.
"""

import json
import os
import re
import sys

SECRETS_DIR = os.path.expanduser("~/.secrets")
BURT_TRANSCRIPT_DIR = os.path.expanduser("~/.claude/projects/-Users-deepak-macmini-honeybloom-burt")

SECRETS_PATTERNS = [
    re.compile(r'~/.secrets'),
    re.compile(re.escape(SECRETS_DIR)),
    re.compile(r'\$HOME/.secrets'),
    re.compile(re.escape(BURT_TRANSCRIPT_DIR)),
    re.compile(r'honeybloom-burt'),
]

DENY_MSG = "Credential access blocked. Request credentials through Burt at direct-burt."

def get_teammate_from_cwd(cwd: str) -> str:
    m = re.search(r'/honeybloom/([^/]+)', cwd)
    return m.group(1).lower() if m else ""

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
        cwd = os.getcwd()
        tool_input = {}
        command = tool_input_raw
    else:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            sys.exit(0)
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        cwd = input_data.get("cwd", os.getcwd())
        command = tool_input.get("command", "")

    teammate = get_teammate_from_cwd(cwd)

    if teammate == "burt":
        sys.exit(0)

    if tool_name == "Bash" or (on_opencode and command):
        if re.search(r'\bsecurity\s', command):
            deny(on_opencode)
        for pattern in SECRETS_PATTERNS:
            if pattern.search(command):
                deny(on_opencode)

    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        resolved = os.path.expanduser(file_path)
        if resolved.startswith(SECRETS_DIR + "/") or resolved == SECRETS_DIR:
            deny(on_opencode)
        if resolved.startswith(BURT_TRANSCRIPT_DIR + "/") or resolved == BURT_TRANSCRIPT_DIR:
            deny(on_opencode)

    sys.exit(0)

if __name__ == "__main__":
    main()
