#!/bin/bash
#
# transfer-to-drive.sh — Collect honeybloom system onto external drive
# Usage: ./transfer-to-drive.sh [/Volumes/DriveName]
#

set -euo pipefail

# --- Drive detection ---

if [[ $# -ge 1 ]]; then
    DRIVE="$1"
else
    echo "Available external volumes:"
    echo ""
    found=0
    for vol in /Volumes/*/; do
        vol="${vol%/}"
        name="$(basename "$vol")"
        # Skip system volumes
        [[ "$name" == "Macintosh HD" || "$name" == "Macintosh HD - Data" ]] && continue
        size=$(df -h "$vol" 2>/dev/null | tail -1 | awk '{print $2}')
        avail=$(df -h "$vol" 2>/dev/null | tail -1 | awk '{print $4}')
        echo "  $vol  (${size} total, ${avail} available)"
        found=1
    done
    if [[ $found -eq 0 ]]; then
        echo "  No external volumes found."
        exit 1
    fi
    echo ""
    read -rp "Enter drive path: " DRIVE
fi

if [[ ! -d "$DRIVE" ]]; then
    echo "Error: $DRIVE does not exist or is not a directory."
    exit 1
fi

DEST="$DRIVE/honeybloom-transfer"
echo ""
echo "Transfer destination: $DEST"
echo ""

# --- Check available space ---

avail_kb=$(df -k "$DRIVE" | tail -1 | awk '{print $4}')
avail_gb=$((avail_kb / 1048576))
echo "Available space on drive: ${avail_gb} GB"

if [[ $avail_gb -lt 100 ]]; then
    echo "WARNING: Workspace is ~86 GB. Available space (${avail_gb} GB) may not be enough."
    read -rp "Continue anyway? [y/N] " answer
    [[ "${answer,,}" != "y" ]] && exit 1
fi

# --- Collect items ---

mkdir -p "$DEST"

transfer_item() {
    local label="$1"
    local src="$2"
    local dest_subdir="$3"

    if [[ ! -e "$src" ]]; then
        echo "  SKIP: $label — $src not found"
        return
    fi

    echo "  Transferring: $label"
    mkdir -p "$DEST/$dest_subdir"

    if [[ -d "$src" ]]; then
        rsync -a --info=progress2 "$src/" "$DEST/$dest_subdir/" 2>&1 | tail -1
    else
        rsync -a "$src" "$DEST/$dest_subdir/"
    fi
}

echo "Collecting 7 items..."
echo ""

# 1. Workspace
transfer_item "honeybloom workspace (this will take a while)" \
    "/Users/d.patnaik/honeybloom" \
    "workspace"

# 2. Claude Code config directory
transfer_item "~/.claude/ config directory" \
    "/Users/d.patnaik/.claude" \
    "claude-config"

# 3. Claude Code global config
transfer_item "~/.claude.json (MCP servers)" \
    "/Users/d.patnaik/.claude.json" \
    "claude-global"

# 4. Snap.app
transfer_item "Snap.app" \
    "/Applications/Snap.app" \
    "apps/Snap.app"

# 5. managed-settings.json
transfer_item "managed-settings.json" \
    "/Library/Application Support/ClaudeCode/managed-settings.json" \
    "system"

# 6. Kitty config
transfer_item "Kitty config (kitty.conf + session files)" \
    "/Users/d.patnaik/.config/kitty" \
    "kitty-config"

# 7. LaunchAgent plists
echo "  Transferring: LaunchAgent plists"
mkdir -p "$DEST/launchagents"
for plist in /Users/d.patnaik/Library/LaunchAgents/com.honeybloom.*.plist; do
    if [[ -f "$plist" ]]; then
        rsync -a "$plist" "$DEST/launchagents/"
        echo "    $(basename "$plist")"
    fi
done

echo ""

# --- Generate manifest ---

echo "Generating manifest..."
{
    echo "# Honeybloom Transfer Manifest"
    echo "# Generated: $(date)"
    echo "# Source machine: $(hostname)"
    echo "# macOS: $(sw_vers -productVersion)"
    echo ""

    for item in workspace claude-config claude-global apps system kitty-config launchagents; do
        path="$DEST/$item"
        if [[ -e "$path" ]]; then
            size=$(du -sh "$path" 2>/dev/null | cut -f1)
            count=$(find "$path" -type f 2>/dev/null | wc -l | tr -d ' ')
            echo "$item: $size ($count files)"
        else
            echo "$item: MISSING"
        fi
    done

    echo ""
    total=$(du -sh "$DEST" 2>/dev/null | cut -f1)
    echo "TOTAL: $total"
} > "$DEST/manifest.txt"

cat "$DEST/manifest.txt"

echo ""
echo "Transfer complete: $DEST"
echo ""
