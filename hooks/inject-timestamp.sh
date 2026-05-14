#!/bin/bash
# Global hook: per-turn current time + succinct language directive.
# For OpenCode teammates (klara, natalie): first-turn wakeup prompt via OPENCODE_SESSION_ID.

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

# OpenCode wakeup prompt — first turn only (klara and natalie, not sandbox)
if [[ "$TEAMMATE" == "klara" || "$TEAMMATE" == "natalie" ]]; then
    WAKEUP_FLAG="/tmp/.opencode-wakeup-${TEAMMATE}"
    SESSION_ID="${OPENCODE_SESSION_ID:-}"
    STORED_SESSION=""
    [ -f "$WAKEUP_FLAG" ] && STORED_SESSION=$(cat "$WAKEUP_FLAG")
    if [[ -n "$SESSION_ID" && "$STORED_SESSION" != "$SESSION_ID" ]]; then
        echo "$SESSION_ID" > "$WAKEUP_FLAG"
        TITLE_NAME="$(echo "${TEAMMATE:0:1}" | tr '[:lower:]' '[:upper:]')${TEAMMATE:1}"
        WAKEUP="${TITLE_NAME}, hi. A few important announcements.
[1] Read your CLAUDE, LOGBOOK and OJT skill.
[2] You have a knowledge cutoff. Keep this in mind.
[3] This is the start of a new session. Use judgement to determine the time that has elapsed between the end of the last session and the start of this session.
Bring your A-game!"
        MSG="${WAKEUP}"$'\n\n'"${MSG}"
    fi
fi

# Per-turn succinctness directive injection.
# Source: library canonical, read at hook runtime. Single source of truth —
# edits to the canonical propagate to every turn automatically.
# Fail-loud if unreadable: Boss sees the broken turn, we fix it.
SUCCINCT_CANONICAL="/Users/d.patnaik/honeybloom/library/output-styles/honeybloom-succinct-language.md"
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
