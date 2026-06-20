#!/bin/bash
# Global hook: per-turn current time + succinct language directive.

# Read stdin to get cwd (Claude Code passes JSON on stdin; OpenCode does not)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[[ -z "$CWD" ]] && CWD="$PWD"

# Extract teammate name from cwd
TEAMMATE=""
if [[ -n "$CWD" ]]; then
    TEAMMATE=$(basename "$CWD")
fi

TIMESTAMP=$(date "+%H:%M %a %b %d %Y")

MSG="Current time: ${TIMESTAMP}."

# Active room injection — fetch the teammate's current Aether rooms
if [ -n "$TEAMMATE" ]; then
	ACTIVE_JSON=$(curl -s --connect-timeout 1 "${AETHER_URL:-http://localhost:51730}/api/rooms/active-room?name=$TEAMMATE" 2>/dev/null)
	if [ -n "$ACTIVE_JSON" ]; then
		ROOMS=$(echo "$ACTIVE_JSON" | jq -r '.rooms // [] | join(", ")')
		if [ -n "$ROOMS" ]; then
			MSG="${MSG}"$'\n'"Active in: ${ROOMS}."
		fi
	fi
fi

# Per-turn succinctness directive injection.
# Source: library canonical, read at hook runtime. Single source of truth —
# edits to the canonical propagate to every turn automatically.
# Fail-loud if unreadable: Boss sees the broken turn, we fix it.
SUCCINCT_CANONICAL="/Users/deepak-macmini/honeybloom/library/output-styles/honeybloom-succinct-language.md"
if [ -r "$SUCCINCT_CANONICAL" ]; then
    # Strip YAML frontmatter (everything up to and including the second ---)
    DIRECTIVE_BODY=$(awk '/^---$/{c++; next} c>=2' "$SUCCINCT_CANONICAL")
    if [ -n "$DIRECTIVE_BODY" ]; then
        MSG="${MSG}"$'\n'"${DIRECTIVE_BODY}"
    fi
fi

jq -n --arg msg "$MSG" '{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": $msg
  }
}'
