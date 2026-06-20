#!/bin/bash
# Emergency failover: switch entire org from OpenCode (v4 combo) back to Claude Code (4.6 combo).
# Single command, no prompts. Run after Anthropic outage is resolved.

set -euo pipefail

HOMEDIR="/Users/deepak-macmini/honeybloom"
ORG_MD="$HOMEDIR/library/ORG.md"
JANUS_CSV_LINK="$HOMEDIR/rio/janus-config.csv"
JANUS_CSV="$(readlink -f "$JANUS_CSV_LINK" 2>/dev/null || echo "$JANUS_CSV_LINK")"
KITTEN="/opt/homebrew/bin/kitten"
CLAUDE="/Users/deepak-macmini/.local/bin/claude"
LAUNCH_SCRIPT="$HOMEDIR/library/scripts/kitty-open-teammate.sh"
BACKUP_DIR="$HOMEDIR/library/scripts/.failover-backup"

# Natalie excluded — stays on Claude Code as safety net for Boss
SKIP_TEAMMATES="natalie"

# --- Read ORG.md Roster (excluding safety net) ---
get_roster() {
    grep -i "^Teammate:" "$ORG_MD" | sed 's/^Teammate: *//I' | tr '[:upper:]' '[:lower:]' | grep -vwF "$SKIP_TEAMMATES"
}

# --- Socket Discovery ---
discover_socket() {
    for path in /tmp/honeybloom-kitty-*.sock; do
        [ -S "$path" ] || continue
        local uri="unix:$path"
        if $KITTEN @ --to "$uri" ls >/dev/null 2>&1; then
            echo "$uri"
            return 0
        fi
    done
    return 1
}

# --- Get unique group representatives for launch ---
get_launch_names() {
    local seen_groups=""
    while IFS= read -r name; do
        local group_line
        group_line="$(grep -i "^Group:.*\b${name}\b" "$ORG_MD" 2>/dev/null | head -1)" || true
        if [ -z "$group_line" ]; then
            echo "$name"
        else
            local group_key
            group_key="$(echo "$group_line" | sed 's/^Group: *//' | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
            if [[ "$seen_groups" != *"|${group_key}|"* ]]; then
                seen_groups="${seen_groups}|${group_key}|"
                echo "$name"
            fi
        fi
    done <<< "$(get_roster)"
}

echo "=== FAILOVER TO 4.6 COMBO ==="
echo ""

# --- Preflight: check Claude Code auth ---
echo "Checking Claude Code auth..."
if ! "$CLAUDE" --version >/dev/null 2>&1; then
    echo "WARNING: 'claude --version' failed. Claude Code may not be functional."
    echo "If Anthropic is still down, this failover will produce auth errors."
    echo "Press Ctrl+C within 5 seconds to abort, or wait to continue..."
    sleep 5
fi
echo "Claude Code check passed."

# --- Backup CSV ---
mkdir -p "$BACKUP_DIR"
cp "$JANUS_CSV" "$BACKUP_DIR/janus-config.csv.pre-46-$(date +%Y%m%d-%H%M%S)"
echo "CSV backed up."

# --- Rewrite CSV atomically ---
echo "Rewriting janus-config.csv..."
TMPCSV="$(mktemp)"
head -1 "$JANUS_CSV" > "$TMPCSV"
tail -n +2 "$JANUS_CSV" | while IFS=',' read -r teammate role model harness provider api_key effort_level model_api_id; do
    local_name="$(echo "$teammate" | tr '[:upper:]' '[:lower:]')"
    if echo "$SKIP_TEAMMATES" | grep -qwF "$local_name"; then
        # Preserve safety net teammate's row unchanged
        echo "${teammate},${role},${model},${harness},${provider},${api_key},${effort_level},${model_api_id}" >> "$TMPCSV"
    else
        echo "${teammate},${role},Opus 4.6,Claude Code,Anthropic,${api_key},high," >> "$TMPCSV"
    fi
done
mv "$TMPCSV" "$JANUS_CSV"
echo "CSV updated: all teammates (except $SKIP_TEAMMATES) -> Claude Code / Opus 4.6."

# --- Restore hooks to opencode.json files ---
echo "Restoring shell hooks to opencode.json files..."
if [ -d "$BACKUP_DIR/hooks" ]; then
    while IFS= read -r name; do
        config="$HOMEDIR/$name/.opencode/opencode.json"
        hooks_backup="$BACKUP_DIR/hooks/${name}.json"
        if [ -f "$hooks_backup" ] && [ -f "$config" ]; then
            # Only restore if hooks are currently absent
            if ! jq -e '.hooks' "$config" >/dev/null 2>&1; then
                jq --argjson hooks "$(cat "$hooks_backup")" '. + {hooks: $hooks}' "$config" > "${config}.tmp" && mv "${config}.tmp" "$config"
                echo "  Restored hooks for $name"
            fi
        fi
    done <<< "$(get_roster)"
    echo "Hooks restored."
else
    echo "No hooks backup found — skipping restore."
fi

# --- Kill all teammate tabs ---
echo "Killing all teammate tabs..."
SOCKET="$(discover_socket)" || true
if [ -n "$SOCKET" ]; then
    while IFS= read -r name; do
        $KITTEN @ --to "$SOCKET" close-tab --match "var:teammate=$name" 2>/dev/null || true
    done <<< "$(get_roster)"
    echo "Tabs closed."
    sleep 2
else
    echo "No Kitty socket found — skipping tab close."
fi

# --- Relaunch via group-aware launch script ---
echo "Relaunching all teammates..."
while IFS= read -r name; do
    echo "  Launching $name..."
    bash "$LAUNCH_SCRIPT" "$name" &
    sleep 1
done <<< "$(get_launch_names)"

# Wait for all background launches
wait

echo ""
echo "=== FAILOVER COMPLETE ==="
echo "All teammates now on Claude Code / Opus 4.6 (Anthropic)."
echo "To reverse: bash $HOMEDIR/library/scripts/failover-to-v4.sh"
