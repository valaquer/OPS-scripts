#!/usr/bin/env python3
"""
Nudge teammates to use huddles instead of DMs for cross-team communication.
PreToolUse hook for mcp__honeybloom-aether__post_to_aether.
Non-blocking -- warns but does not deny.
"""

import json
import sys

EXCEPTIONS = {"direct-burt", "direct-jeh", "direct-boss"}

try:
    input_data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

tool_input = input_data.get("tool_input", {})
room = tool_input.get("room", "")

if room.startswith("direct-") and room not in EXCEPTIONS:
    print("Are you sure? Shouldn't you be messaging their huddle instead?", file=sys.stderr)

sys.exit(0)
