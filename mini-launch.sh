#!/bin/bash
# Launcher script for Mac Mini. Executed via SSH from iMac.
# Usage: mini-launch.sh <name>
# All config reading (harness, model, wakeup) happens locally on Mini.

NAME="$1"
[ -z "$NAME" ] && echo "Usage: mini-launch.sh <name>" && exit 1

HOMEDIR="/Users/deepak-macmini/honeybloom"
JANUS_CSV="$HOMEDIR/library/scripts/janus-config.csv"

# Ensure Homebrew is in PATH (SSH non-login shell)
export PATH="$HOMEDIR/library/scripts:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

CLAUDE="/opt/homebrew/bin/claude"
OPENCODE="/opt/homebrew/bin/opencode"
CODEX="/opt/homebrew/bin/codex"

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

build_wakeup_message() {
    echo "Boss and teammates are all in Aether, not in the terminal; use the post_to_aether tool of the honeybloom_aether MCP; to initiate a new conversation, post to direct-{teammate} or huddle-{host}."
}

# Change to teammate directory
cd "$HOMEDIR/$NAME" || exit 1

# Build wakeup
WAKEUP="$(build_wakeup_message "$NAME")"

# Notify Aether that this teammate is activating
curl -s -o /dev/null -X POST "http://localhost:51730/api/rooms/activate" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$NAME\"}" 2>/dev/null || true

# Launch harness (only pass WAKEUP when non-empty)
if [[ "$HARNESS" == *"OpenCode"* ]]; then
    export OPENCODE_DISABLE_AUTOUPDATE=true
    MODEL_FLAG=""
    model_prefix="opencode-go"
    [[ "$PROVIDER" == *"Zen"* ]] && model_prefix="opencode"
    [ -n "$MODEL_API_ID" ] && MODEL_FLAG="-m $model_prefix/$MODEL_API_ID"
    if [ -n "$WAKEUP" ]; then
        exec $OPENCODE $MODEL_FLAG --prompt "$WAKEUP"
    else
        exec $OPENCODE $MODEL_FLAG
    fi
elif [[ "$HARNESS" == *"Codex"* ]]; then
    CODEX_ARGS=(--dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust)
    if [ -n "$MODEL_API_ID" ]; then
        CODEX_ARGS+=(--model "$MODEL_API_ID")
    fi
    if [ -n "$WAKEUP" ]; then
        exec "$CODEX" "${CODEX_ARGS[@]}" "$WAKEUP"
    else
        exec "$CODEX" "${CODEX_ARGS[@]}"
    fi
else
    CLAUDE_ARGS=(--dangerously-skip-permissions)
    [ -n "$MODEL_API_ID" ] && CLAUDE_ARGS+=(--model "$MODEL_API_ID")
    if [ -n "$WAKEUP" ]; then
        exec $CLAUDE "${CLAUDE_ARGS[@]}" "$WAKEUP"
    else
        exec $CLAUDE "${CLAUDE_ARGS[@]}"
    fi
fi
