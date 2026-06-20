#!/bin/bash
# Launcher script for Mac Mini. Lives on NFS share, executed via SSH.
# Usage: mini-launch.sh <name> <harness> [model_id]

NAME="$1"
HARNESS="$2"
MODEL_ID="$3"

HOMEDIR="/Users/deepak-macmini/honeybloom"
TMP="$HOMEDIR/.tmp"

# Ensure Homebrew is in PATH (SSH non-login shell doesn't load profile)
export PATH="$HOMEDIR/library/scripts:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

CLAUDE="/opt/homebrew/bin/claude"
OPENCODE="$HOME/.opencode/bin/opencode"

# Unlock Keychain (password from temp file, written by kitty-open-teammate.sh)
PW_FILE="$TMP/.pw-$NAME"
if [ -f "$PW_FILE" ]; then
    PW=$(cat "$PW_FILE")
    rm -f "$PW_FILE"
    security unlock-keychain -p "$PW" "$HOME/Library/Keychains/login.keychain-db" 2>/dev/null
    unset PW
fi

# Read wakeup prompt
WAKEUP_FILE="$TMP/wakeup-$NAME.txt"
WAKEUP=""
if [ -f "$WAKEUP_FILE" ]; then
    WAKEUP=$(cat "$WAKEUP_FILE")
    rm -f "$WAKEUP_FILE"
fi

# Change to teammate directory (NFS path parity)
cd "$HOMEDIR/$NAME" || exit 1

# Set Aether URL for shell hooks (LAN IP instead of localhost)
export AETHER_URL="http://localhost:51730"

# Launch harness
if [ "$HARNESS" = "opencode" ]; then
    MODEL_FLAG=""
    [ -n "$MODEL_ID" ] && MODEL_FLAG="-m opencode-go/$MODEL_ID"
    exec $OPENCODE $MODEL_FLAG --prompt "$WAKEUP"
else
    exec $CLAUDE --dangerously-skip-permissions "$WAKEUP"
fi
