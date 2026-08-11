#!/usr/bin/env python3
"""
Nudge hook: remind Juno to delegate research to Pike instead of doing it himself.
Non-blocking -- surfaces a prompt but doesn't prevent the tool call.
"""

import json
import os
import sys


def main():
    cwd = os.getcwd()
    if "/honeybloom/juno" not in cwd:
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("WebSearch", "WebFetch"):
        sys.exit(0)

    msg = (
        "Juno, is this a genuine quick ask from Boss or an official request "
        "from the org? If official, follow the research RUNBOOK -- delegate "
        "to Pike with Jukka's pre-mortem. No direct research on official requests."
    )
    print(msg, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
