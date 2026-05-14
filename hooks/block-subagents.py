#!/usr/bin/env python3
"""
Sub-Agent Prevention Hook — PreToolUse hook for Task tool.
Blocks all sub-agent spawning team-wide. Boss directive, Mar 14.
"""

import json
import sys


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")

    if tool_name != "Task":
        sys.exit(0)

    print(
        "BLOCKED: Sub-agents are disabled team-wide.\n"
        "The Task tool is not available. Work within your own session.",
        file=sys.stderr
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
