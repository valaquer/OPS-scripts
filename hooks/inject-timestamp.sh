#!/bin/bash
# Global hook: per-turn current time.

TIMESTAMP=$(date "+%H:%M %a %b %d %Y")
MSG="Current time: ${TIMESTAMP}."


jq -n --arg msg "$MSG" '{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": $msg
  }
}'
