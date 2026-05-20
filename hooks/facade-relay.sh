#!/bin/bash
# PostToolUse hook: relay tool activity to Facade for live mirror.
# Zero cost when inactive — checks flag file and exits immediately if absent.

# Global live mirror flag — if absent, exit immediately
GLOBAL_FLAG="/Users/d.patnaik/honeybloom/library/facade/livemirror-global"
[[ ! -f "$GLOBAL_FLAG" ]] && exit 0

# OpenCode sets OPENCODE_HOOK_TYPE env var. Use env vars directly, skip stdin.
if [[ -n "${OPENCODE_HOOK_TYPE:-}" ]]; then
    TEAMMATE=$(basename "$PWD")
    TOOL_NAME="${OPENCODE_TOOL_NAME:-}"
    [[ "$TOOL_NAME" == *"honeybloom-facade"* || "$TOOL_NAME" == *"honeybloom-huddle"* || "$TOOL_NAME" == "ToolSearch" ]] && exit 0
    TOOL_INPUT='{}'
    TOOL_OUTPUT="${OPENCODE_TOOL_OUTPUT:-}"
else
    # Claude Code: read stdin JSON
    INPUT=$(cat)
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
    [[ -z "$CWD" ]] && CWD="$PWD"
    TEAMMATE=$(basename "$CWD")
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
    [[ "$TOOL_NAME" == *"honeybloom-facade"* || "$TOOL_NAME" == *"honeybloom-huddle"* || "$TOOL_NAME" == "ToolSearch" ]] && exit 0
    TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}' 2>/dev/null)
    TOOL_OUTPUT=$(echo "$INPUT" | jq -r '.tool_output // empty' 2>/dev/null)
fi

# FP-12 Credential Relay filter — suppress relay for sensitive file paths
COMBINED="${TOOL_INPUT} ${TOOL_OUTPUT}"
if echo "$COMBINED" | grep -qiE 'auth\.json|credentials\.json|\.env|tokens/|\.keys|secret|apikey|api_key|api-key|\.pem|\.p12|password|bitwarden|keychain|bearer|authorization'; then
    exit 0
fi

# Determine room — use active huddle room if teammate is in one, otherwise direct room
ROOM="direct-${TEAMMATE}"

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
