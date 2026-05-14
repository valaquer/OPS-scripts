#!/bin/bash
#
# setup-from-drive.sh — Deploy honeybloom system from transfer drive onto laptop
# Usage: ./setup-from-drive.sh [/Volumes/DriveName/honeybloom-transfer]
#
# Safe to run multiple times (idempotent).
#

set -euo pipefail

# --- Locate transfer directory ---

if [[ $# -ge 1 ]]; then
    SRC="$1"
else
    # Auto-detect: look for honeybloom-transfer/ on any external volume
    SRC=""
    for vol in /Volumes/*/; do
        vol="${vol%/}"
        name="$(basename "$vol")"
        [[ "$name" == "Macintosh HD" || "$name" == "Macintosh HD - Data" ]] && continue
        if [[ -d "$vol/honeybloom-transfer" ]]; then
            SRC="$vol/honeybloom-transfer"
            break
        fi
    done
    if [[ -z "$SRC" ]]; then
        echo "Error: Could not find honeybloom-transfer/ on any external volume."
        echo "Usage: $0 /Volumes/DriveName/honeybloom-transfer"
        exit 1
    fi
fi

if [[ ! -f "$SRC/manifest.txt" ]]; then
    echo "Error: $SRC/manifest.txt not found. Is this a valid transfer directory?"
    exit 1
fi

echo "Transfer source: $SRC"
echo ""
echo "Manifest:"
cat "$SRC/manifest.txt"
echo ""

# --- Pre-flight: check for existing configs ---

preflight_check() {
    local path="$1"
    local label="$2"
    local backup="${path}.pre-transfer-backup"

    if [[ -e "$path" ]]; then
        if [[ -e "$backup" ]]; then
            echo "  WARNING: $label exists at $path (backup already made)"
        else
            echo "  WARNING: $label exists at $path"
            read -rp "  Back up and overwrite? [y/N] " answer
            if [[ "${answer,,}" == "y" ]]; then
                mv "$path" "$backup"
                echo "  Backed up to $backup"
            else
                echo "  SKIPPING $label"
                return 1
            fi
        fi
    fi
    return 0
}

echo "Pre-flight checks..."

skip_workspace=0
skip_claude=0
skip_snap=0

preflight_check "/Users/d.patnaik/honeybloom" "Honeybloom workspace" || skip_workspace=1
preflight_check "/Users/d.patnaik/.claude" "Claude Code config" || skip_claude=1
preflight_check "/Applications/Snap.app" "Snap.app" || skip_snap=1

echo ""

# --- Deploy items ---

deploy_item() {
    local label="$1"
    local src="$2"
    local dest="$3"
    local skip="${4:-0}"

    if [[ "$skip" -eq 1 ]]; then
        echo "  SKIP: $label (user chose not to overwrite)"
        return
    fi

    if [[ ! -e "$src" ]]; then
        echo "  SKIP: $label — not in transfer directory"
        return
    fi

    echo "  Deploying: $label"
    local dest_dir
    dest_dir="$(dirname "$dest")"
    mkdir -p "$dest_dir"

    if [[ -d "$src" ]]; then
        rsync -a --info=progress2 "$src/" "$dest/" 2>&1 | tail -1
    else
        rsync -a "$src" "$dest"
    fi
}

echo "Deploying 7 items..."
echo ""

# 1. Workspace
deploy_item "honeybloom workspace (this will take a while)" \
    "$SRC/workspace" \
    "/Users/d.patnaik/honeybloom" \
    "$skip_workspace"

# 2. Claude Code config directory
deploy_item "~/.claude/ config directory" \
    "$SRC/claude-config" \
    "/Users/d.patnaik/.claude" \
    "$skip_claude"

# 3. Claude Code global config
if [[ -f "$SRC/claude-global/.claude.json" ]]; then
    if [[ -f "/Users/d.patnaik/.claude.json" && ! -f "/Users/d.patnaik/.claude.json.pre-transfer-backup" ]]; then
        mv "/Users/d.patnaik/.claude.json" "/Users/d.patnaik/.claude.json.pre-transfer-backup"
        echo "  Backed up existing ~/.claude.json"
    fi
    echo "  Deploying: ~/.claude.json (MCP servers)"
    cp "$SRC/claude-global/.claude.json" "/Users/d.patnaik/.claude.json"
fi

# 4. Snap.app
deploy_item "Snap.app" \
    "$SRC/apps/Snap.app" \
    "/Applications/Snap.app" \
    "$skip_snap"

# 5. Kitty config
deploy_item "Kitty config (kitty.conf + session files)" \
    "$SRC/kitty-config" \
    "/Users/d.patnaik/.config/kitty"

# 6. LaunchAgent plists
if [[ -d "$SRC/launchagents" ]]; then
    echo "  Deploying: LaunchAgent plists"
    mkdir -p "/Users/d.patnaik/Library/LaunchAgents"
    for plist in "$SRC/launchagents"/com.honeybloom.*.plist; do
        if [[ -f "$plist" ]]; then
            name="$(basename "$plist")"
            cp "$plist" "/Users/d.patnaik/Library/LaunchAgents/"
            echo "    $name"
        fi
    done

    echo "  Loading daemons..."
    local uid
    uid="$(id -u)"
    for plist in /Users/d.patnaik/Library/LaunchAgents/com.honeybloom.*.plist; do
        if [[ -f "$plist" ]]; then
            name="$(basename "$plist")"
            # Bootout first in case already loaded (idempotent)
            launchctl bootout "gui/$uid/$name" 2>/dev/null || true
            launchctl bootstrap "gui/$uid" "$plist" 2>/dev/null && echo "    Loaded: $name" || echo "    FAILED: $name"
        fi
    done
fi

echo ""

# 7. Reconcile skill symlinks
echo "Reconciling skill symlinks..."
if [[ -f "/Users/d.patnaik/honeybloom/samara/reconcile-skills.py" ]]; then
    python3 /Users/d.patnaik/honeybloom/samara/reconcile-skills.py 2>&1 && echo "  Symlinks rebuilt." || echo "  WARNING: reconcile-skills.py failed"
else
    echo "  WARNING: reconcile-skills.py not found — skill symlinks may be broken"
fi

echo ""
echo "================================================"
echo "  DEPLOYMENT COMPLETE"
echo "================================================"
echo ""

# --- Sudo commands for Boss ---

echo "SUDO COMMANDS (run these in a separate Terminal window):"
echo ""
echo "  sudo mkdir -p '/Library/Application Support/ClaudeCode'"
echo "  sudo cp '$SRC/system/managed-settings.json' '/Library/Application Support/ClaudeCode/'"
echo ""

# --- Manual steps checklist ---

echo "MANUAL STEPS:"
echo ""
echo "  Apps to install (if not already present):"
for app in "Kitty" "Obsidian" "Raycast" "1Password" "Yoink"; do
    if [[ -d "/Applications/$app.app" ]]; then
        echo "    [x] $app (already installed)"
    else
        echo "    [ ] $app"
    fi
done
echo ""

echo "  CLI tools to install:"
for cmd in python3 node brew bw; do
    if command -v "$cmd" &>/dev/null; then
        echo "    [x] $cmd ($(command -v "$cmd"))"
    else
        echo "    [ ] $cmd"
    fi
done
echo "    [ ] Claude Code (npm install -g @anthropic-ai/claude-code)"
echo ""

echo "  Permissions to grant:"
echo "    [ ] Snap.app → Accessibility (System Preferences > Privacy & Security)"
echo "    [ ] Snap.app → Screen Recording (System Preferences > Privacy & Security)"
echo ""

echo "  Credentials to enter:"
echo "    [ ] Bitwarden auth (bw login)"
echo "    [ ] 1Password login"
echo "    [ ] iCloud sign-in"
echo ""

echo "  After all steps:"
echo "    [ ] Quit and reopen Kitty (picks up config + managed-settings)"
echo "    [ ] Launch Snap.app, grant permissions, test Ctrl+1/Ctrl+2"
echo "    [ ] Note: 8 GB RAM — limit to 2-3 concurrent teammate sessions"
echo ""
