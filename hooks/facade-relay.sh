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
    TOOL_INPUT="${OPENCODE_TOOL_INPUT:-}"
    [[ -z "$TOOL_INPUT" ]] && TOOL_INPUT='{}'
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
    TOOL_OUTPUT=$(echo "$INPUT" | jq -r '
      .tool_response // empty |
      if type == "array" then map(.text // empty) | join("\n")
      elif type == "object" then (.file.content // .stdout // .text // tostring)
      else tostring
      end
    ' 2>/dev/null)
fi

# FP-12 Credential Relay filter — suppress relay for sensitive file paths and raw keys
# Keychain subshell expansion is the primary defense. This filter catches file reads and raw key patterns.
COMBINED="${TOOL_INPUT}"
if echo "$COMBINED" | grep -qiE 'auth\.json|credentials\.json|\.env[^a-z]|tokens/|\.keys|\.pem|\.p12|[a-f0-9]{32,}|(sk|pk|key|tok|ghp|gho)[-_][A-Za-z0-9]{20,}'; then
    exit 0
fi

# Generate summary for read-only tool activity
SUMMARY=""
case "$TOOL_NAME" in
  Read)
    FP=$(echo "$TOOL_INPUT" | jq -r '.filePath // (.filePaths // [])[0] // ""' 2>/dev/null)
    if [[ -n "$FP" ]]; then SUMMARY="Read $FP"; else SUMMARY="Read files"; fi
    ;;
  Grep)
    PT=$(echo "$TOOL_INPUT" | jq -r '.pattern // ""' 2>/dev/null)
    if [[ -n "$PT" ]]; then SUMMARY="Searched for '$PT'"; else SUMMARY="Searched file contents"; fi
    ;;
  Glob)
    PT=$(echo "$TOOL_INPUT" | jq -r '.pattern // ""' 2>/dev/null)
    if [[ -n "$PT" ]]; then SUMMARY="Matched '$PT'"; else SUMMARY="Found matching files"; fi
    ;;
  *reddit*)
    URL=$(echo "$TOOL_INPUT" | jq -r '.url // ""' 2>/dev/null)
    QUERY=$(echo "$TOOL_INPUT" | jq -r '.query // ""' 2>/dev/null)
    SR=$(echo "$TOOL_INPUT" | jq -r '.subreddit // ""' 2>/dev/null)
    if [[ -n "$URL" ]]; then SUMMARY="Fetched Reddit thread"
    elif [[ -n "$QUERY" ]]; then SUMMARY="Searched Reddit for '$QUERY'"
    elif [[ -n "$SR" ]]; then SUMMARY="Listed r/$SR posts"
    else SUMMARY="Reddit query"
    fi
    ;;
  *[Vv]ision*)
    SUMMARY="Analyzed image"
    ;;
esac

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
        --arg summary "$SUMMARY" \
        '{sender: $sender, room: $room, toolName: $toolName, toolInput: $toolInput, toolOutput: $toolOutput, status: $status, summary: $summary}'
    )" &

exit 0
