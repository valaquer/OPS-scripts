#!/bin/bash
# Unlock login Keychain at boot
# Runs via launchd RunAtLoad

PASS_FILE="/Users/deepak-macmini/.keychain-pass"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

if [ -f "$PASS_FILE" ]; then
    security unlock-keychain -p "$(cat "$PASS_FILE")" "$KEYCHAIN" 2>/dev/null
    security set-keychain-settings "$KEYCHAIN" 2>/dev/null
fi
