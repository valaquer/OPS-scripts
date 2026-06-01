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
    # Fallback: read buffered tool input from PreToolUse hook (env var is always {})
    if [[ "$TOOL_INPUT" == '{}' ]]; then
        BUFFERED=$(cat "/tmp/facade-tool-input-${TEAMMATE}" 2>/dev/null || echo "")
        if [[ -n "$BUFFERED" && "$BUFFERED" != '{}' ]]; then
            TOOL_INPUT="$BUFFERED"
        fi
    fi
else
    # Claude Code: read stdin JSON
    INPUT=$(cat)
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
    [[ -z "$CWD" ]] && CWD="$PWD"
    TEAMMATE=$(echo "$CWD" | sed -n 's|.*/honeybloom/\([^/]*\).*|\1|p')
    [[ -z "$TEAMMATE" ]] && TEAMMATE=$(basename "$CWD")
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
    # Skip Honeybloom MCP tools + ToolSearch (allow external MCP like Playwright, Reddit)
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


# FP-12 Credential Relay filter — line-level redaction for sensitive file paths and raw keys
# Keychain subshell expansion is the primary defense. This filter redacts matching lines, not entire cards.
CRED_REGEX='auth\.json|credentials\.json|\.env[^a-z]|tokens/|\.keys|\.pem|\.p12|(sk|pk|key|tok|ghp|gho)[-_][A-Za-z0-9_-]{20,}|find-generic-password|add-generic-password|delete-generic-password'
TOOL_INPUT=$(echo "$TOOL_INPUT" | sed -E "s#.*($CRED_REGEX).*#[credential redacted]#g")
TOOL_OUTPUT=$(echo "$TOOL_OUTPUT" | sed -E "s#.*($CRED_REGEX).*#[credential redacted]#g")

# Generate summary for read-only tool activity
# OpenCode passes lowercase tool names and TOOL_INPUT is always {} (env var limitation).
# Use generic summaries since file/pattern details aren't available via env vars.
SUMMARY=""
case "$TOOL_NAME" in
  [Rr]ead)
    # Try tool_input first (Claude Code), fall back to tool_output parsing
    FP=$(echo "$TOOL_INPUT" | jq -r '.file_path // ""' 2>/dev/null)
    if [[ -z "$FP" ]]; then
      FP=$(echo "$TOOL_OUTPUT" | sed -n 's/.*<path>\([^<]*\)<\/path>.*/\1/p' | head -1)
    fi
    if [[ -n "$FP" ]]; then
      # Show last 2 path segments for context (e.g. "server/harness-reader.ts")
      FN=$(echo "$FP" | awk -F/ '{if(NF>1) print $(NF-1)"/"$NF; else print $NF}')
      if echo "$TOOL_OUTPUT" | grep -qE '\(Showing lines [0-9]+[-–][0-9]+ of [0-9]+'; then
        SUMMARY="Read $FN (partial)"
      else
        SUMMARY="Read $FN"
      fi
    else
      SUMMARY="Read files"
    fi
    ;;
  [Gg]rep)
    PT=$(echo "$TOOL_INPUT" | jq -r '.pattern // ""' 2>/dev/null)
    GP=$(echo "$TOOL_INPUT" | jq -r '.path // ""' 2>/dev/null)
    if [[ -n "$GP" ]]; then
      GP=$(echo "$GP" | awk -F/ '{if(NF>1) print $(NF-1)"/"$NF; else print $NF}')
    fi
    if [[ -n "$PT" && -n "$GP" ]]; then
      SUMMARY="Grep '$PT' in $GP"
    elif [[ -n "$PT" ]]; then
      SUMMARY="Grep '$PT'"
    else
      SUMMARY="Grep search"
    fi
    ;;
  [Gg]lob)
    PAT=$(echo "$TOOL_INPUT" | jq -r '.pattern // ""' 2>/dev/null)
    MATCH_COUNT=$(echo "$TOOL_OUTPUT" | grep -c '^/' 2>/dev/null || echo 0)
    if [[ -n "$PAT" && "$MATCH_COUNT" -gt 0 ]]; then
      SUMMARY="Glob $PAT ($MATCH_COUNT matches)"
    elif [[ -n "$PAT" ]]; then
      SUMMARY="Glob $PAT"
    elif [[ "$MATCH_COUNT" -gt 0 ]]; then
      SUMMARY="Found $MATCH_COUNT matching files"
    else
      SUMMARY="Found matching files"
    fi
    ;;
  [Bb]ash|[Ww]rite|[Ee]dit|[Nn]otebook[Ee]dit)
    # Write tools: no summary — full input + output sent for QA
    SUMMARY=""
    ;;
  *[Rr]eddit*)
    URL=$(echo "$TOOL_INPUT" | jq -r '.url // ""' 2>/dev/null)
    QUERY=$(echo "$TOOL_INPUT" | jq -r '.query // ""' 2>/dev/null)
    SR=$(echo "$TOOL_INPUT" | jq -r '.subreddit // ""' 2>/dev/null)
    if [[ -n "$URL" ]]; then SUMMARY="Fetched Reddit thread"
    elif [[ -n "$QUERY" ]]; then SUMMARY="Searched Reddit for '$QUERY'"
    elif [[ -n "$SR" ]]; then SUMMARY="Listed r/$SR posts"
    else SUMMARY="Reddit query"
    fi
    ;;
  *[Vv]ision*|*vision*)
    SUMMARY="Analyzed image"
    ;;
  [Ss]kill)
    SK=$(echo "$TOOL_INPUT" | jq -r '.skill // .name // ""' 2>/dev/null)
    if [[ -n "$SK" ]]; then
      SUMMARY="Loaded skill: $SK"
    else
      SUMMARY="Loaded skill"
    fi
    ;;
esac

# Determine room — use active huddle room if teammate is in one, otherwise direct room
ROOM="direct-${TEAMMATE}"

# POST to Facade — env vars + temp file to avoid shell arg limits on large output
export RELAY_SENDER="$TEAMMATE"
export RELAY_ROOM="$ROOM"
export RELAY_TOOL_NAME="$TOOL_NAME"
export RELAY_TOOL_INPUT="$TOOL_INPUT"
export RELAY_TOOL_OUTPUT="$TOOL_OUTPUT"
export RELAY_SUMMARY="$SUMMARY"

TMPFILE=$(mktemp)
jq -n '{
    sender: env.RELAY_SENDER,
    room: env.RELAY_ROOM,
    toolName: env.RELAY_TOOL_NAME,
    toolInput: (env.RELAY_TOOL_INPUT | try fromjson catch .),
    toolOutput: env.RELAY_TOOL_OUTPUT,
    status: "success",
    summary: env.RELAY_SUMMARY
}' > "$TMPFILE" 2>/dev/null

curl -s -o /dev/null -X POST http://localhost:51730/api/tool-activity \
    -H "Content-Type: application/json" \
    --data @"$TMPFILE"

rm -f "$TMPFILE"
exit 0
