#!/bin/bash
# Mirror system config files into ~/honeybloom/chica/system-config-mirror/
# Google Drive syncs ~/honeybloom/ — this gets external configs into that sync path.
# Runs hourly via launchd. Idempotent. Missing sources skipped silently.

MIRROR="/Users/deepak-macmini/honeybloom/chica/system-config-mirror"

# Single files — cp -p (preserve timestamps)
[ -f "$HOME/.claude/settings.json" ] && cp -p "$HOME/.claude/settings.json" "$MIRROR/claude-settings.json"
[ -f "$HOME/.claude.json" ] && cp -p "$HOME/.claude.json" "$MIRROR/claude-json.json"
[ -f "/Library/Application Support/ClaudeCode/managed-settings.json" ] && cp -p "/Library/Application Support/ClaudeCode/managed-settings.json" "$MIRROR/managed-settings.json"
[ -f "$HOME/.config/kitty/kitty.conf" ] && cp -p "$HOME/.config/kitty/kitty.conf" "$MIRROR/kitty.conf"
[ -f "$HOME/.claude/gmail-credentials.json" ] && cp -p "$HOME/.claude/gmail-credentials.json" "$MIRROR/gmail-credentials.json"

# Directories — rsync (sync, don't accumulate stale files)
if ls "$HOME/Library/LaunchAgents"/com.honeybloom.*.plist 1>/dev/null 2>&1; then
    rsync -a --delete --include='com.honeybloom.*.plist' --exclude='*' "$HOME/Library/LaunchAgents/" "$MIRROR/launchagents/"
fi
if [ -d "$HOME/.claude/gmail-tokens" ]; then
    rsync -a --delete "$HOME/.claude/gmail-tokens/" "$MIRROR/gmail-tokens/"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') mirror complete"
