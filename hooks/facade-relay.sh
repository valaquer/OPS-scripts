#!/bin/bash
# PostToolUse hook: relay tool activity to Facade for live mirror.
# Zero cost when inactive — checks flag file and exits immediately if absent.

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[[ -z "$CWD" ]] && CWD="$PWD"

TEAMMATE=""
if [[ -n "$CWD" ]]; then
    TEAMMATE=$(basename "$CWD")
fi

# Check if live mirror is active globally (persists across restart/reboot)
GLOBAL_FLAG="/Users/d.patnaik/honeybloom/library/facade/livemirror-global"
[[ ! -f "$GLOBAL_FLAG" ]] && exit 0
ROOM="global"

# Extract tool call data from stdin JSON
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
[[ "$TOOL_NAME" == *"post_to_facade"* ]] && exit 0
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}' 2>/dev/null)
TOOL_OUTPUT=$(echo "$INPUT" | jq -r '.tool_output // empty' 2>/dev/null)

# POST to Facade — fire and forget
curl -s -o /dev/null -X POST http://localhost:51730/api/tool-activity \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
        --arg sender "$TEAMMATE" \
        --arg room "$ROOM" \
        --arg toolName "$TOOL_NAME" \
        --argjson toolInput "$TOOL_INPUT" \
        --arg toolOutput "$TOOL_OUTPUT" \
        --arg status "success" \
        '{sender: $sender, room: $room, toolName: $toolName, toolInput: $toolInput, toolOutput: $toolOutput, status: $status}'
    )" &

exit 0
