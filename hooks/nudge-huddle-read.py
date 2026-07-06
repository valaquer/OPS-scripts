#!/usr/bin/env python3
"""
Nudge hook: deny Read on /tmp/room-huddle-* files.
Huddle messages are delivered via sendToKitty -- reading the room file
is redundant and burns tokens.
"""

import json
import os
import sys


def main():
    on_opencode = "OPENCODE_HOOK_TYPE" in os.environ

    if on_opencode:
        tool_name = os.environ.get("OPENCODE_TOOL_NAME", "").lower()
        file_path = os.environ.get("OPENCODE_TOOL_INPUT", "")
    else:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            sys.exit(0)
        tool_name = input_data.get("tool_name", "")
        if tool_name != "Read":
            sys.exit(0)
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")

    if "/tmp/room-huddle-" in file_path:
        msg = (
            "Huddle messages are delivered to your tab automatically. "
            "Reading the room file is unnecessary and burns tokens. "
            "If Boss explicitly asked you to read a huddle, use the read_room MCP tool directly."
        )
        print(msg, file=sys.stderr)
        if on_opencode:
            print("deny")
            sys.exit(0)
        else:
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
