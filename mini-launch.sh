#!/bin/bash
# Launcher script for Mac Mini. Executed via SSH from iMac.
# Usage: mini-launch.sh <name>
# All config reading (harness, model, wakeup) happens locally on Mini.

NAME="$1"
[ -z "$NAME" ] && echo "Usage: mini-launch.sh <name>" && exit 1

HOMEDIR="/Users/deepak-macmini/honeybloom"
JANUS_CSV="$HOMEDIR/library/skills/runbook-janus/janus-config.csv"

# Ensure Homebrew is in PATH (SSH non-login shell)
export PATH="$HOMEDIR/library/scripts:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

CLAUDE="/opt/homebrew/bin/claude"
OPENCODE="/opt/homebrew/bin/opencode"

# Unlock Keychain for SSH session (macOS locks it for remote connections)
MINI_PASS=$(ssh -i /Users/deepak-macmini/.ssh/id_mini -o ConnectTimeout=3 d.patnaik@192.168.0.153 "cat ~/.secrets/hanover-keychain" 2>/dev/null)
[ -n "$MINI_PASS" ] && security unlock-keychain -p "$MINI_PASS" 2>/dev/null

# Read field from janus-config.csv
get_field() {
    awk -F',' -v name="$1" -v col="$2" 'tolower($1) == name { print $col }' "$JANUS_CSV"
}

HARNESS="$(get_field "$NAME" 4)"
PROVIDER="$(get_field "$NAME" 5)"
MODEL_API_ID="$(get_field "$NAME" 8)"

[ -z "$HARNESS" ] && echo "Error: $NAME not found in janus-config.csv" && exit 1

# Build wakeup message
build_wakeup_message() {
    local name="$1"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
    local cap_name greeting
    cap_name="$(echo "$name" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')"
    greeting="$cap_name"
    local item1
    if [[ "$HARNESS" == *"OpenCode"* ]]; then
        # Parse @-imports from the teammate's own CLAUDE.md
        local claude_file="$HOMEDIR/$name/CLAUDE.md"
        local imports=""
        if [ -f "$claude_file" ]; then
            imports="$(grep '^@' "$claude_file" | sed "s|^@||" 2>/dev/null)"
        fi
        if [ -n "$imports" ]; then
            local file_list=""
            while IFS= read -r line; do
                file_list="${file_list}
- ${line}"
            done <<< "$imports"
            item1="[1] Your CLAUDE is loaded. The following files are @-referenced in your CLAUDE.md but NOT auto-loaded on OpenCode. Read them all manually at wakeup:${file_list}
You have a generous 1M context window so internalize the files."
        else
            item1="[1] Your CLAUDE, PLAYBOOK AND LOGBOOK are already loaded into context. No need to call Read on them again. You have a generous 1M context window so internalize the files."
        fi
    else
        item1="[1] Your CLAUDE, PLAYBOOK AND LOGBOOK are already loaded into context. No need to call Read on them again. You have a generous 1M context window so internalize the files."
    fi
    local boss_title="Boss"
    local body="${greeting}, hi.
${item1}
[2] Your knowledge cutoff is nearly a year old. Keep this in mind
[3] This is the start of a new session. Use judgement to determine the time that has elapsed between the end of the last session and the start of this session.
[4] In every turn, you will receive the current timestamp and a directive to be succinct and productive.
[5] Aether is the only prescribed way to communicate with ${boss_title} and other teammates. Do not output text directly because then it only shows up in the terminal and no one can read it there. ${boss_title} and all your teammates are in the Aether software, therefore use the Aether MCP to send your messages.
Bring your A-game!"
    printf 'sender: boss\nroom: direct-%s\ntimestamp: %s\nbody: %s' "$name" "$ts" "$body"
}

# Change to teammate directory
cd "$HOMEDIR/$NAME" || exit 1

# Build wakeup
WAKEUP="$(build_wakeup_message "$NAME")"

# Notify Aether that this teammate is activating
curl -s -o /dev/null -X POST "http://localhost:51730/api/rooms/activate" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$NAME\"}" 2>/dev/null || true

# Launch harness
if [[ "$HARNESS" == *"OpenCode"* ]]; then
    export OPENCODE_DISABLE_AUTOUPDATE=true
    MODEL_FLAG=""
    model_prefix="opencode-go"
    [[ "$PROVIDER" == *"Zen"* ]] && model_prefix="opencode"
    [ -n "$MODEL_API_ID" ] && MODEL_FLAG="-m $model_prefix/$MODEL_API_ID"
    exec $OPENCODE $MODEL_FLAG --prompt "$WAKEUP"
else
    exec $CLAUDE --dangerously-skip-permissions "$WAKEUP"
fi
