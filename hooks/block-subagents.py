#!/usr/bin/env python3
import os, sys

tool_name = os.environ.get("OPENCODE_TOOL_NAME", "").lower()
on_opencode = "OPENCODE_HOOK_TYPE" in os.environ

if tool_name == "task":
    print("deny")
    sys.exit(0 if on_opencode else 2)

sys.exit(0)
