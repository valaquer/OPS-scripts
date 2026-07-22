#!/usr/bin/env python3
"""Block subagent/agent spawning on both Claude Code and OpenCode."""
import os, sys, json

# Claude Code: reads tool info from stdin JSON
# OpenCode: reads from OPENCODE_TOOL_NAME env var
on_opencode = "OPENCODE_HOOK_TYPE" in os.environ

if on_opencode:
    tool_name = os.environ.get("OPENCODE_TOOL_NAME", "").lower()
    if tool_name == "task":
        print("deny")
        sys.exit(0)
else:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
    except Exception:
        tool_name = ""
    BLOCKED = {
        "Agent", "Workflow", "TaskCreate",
        "ScheduleWakeup", "CronCreate", "CronDelete", "CronList",
    }
    if tool_name in BLOCKED:
        print(f"{tool_name} is disabled by org policy.", file=sys.stderr)
        sys.exit(2)

sys.exit(0)
