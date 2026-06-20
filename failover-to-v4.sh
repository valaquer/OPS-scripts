#!/bin/bash
# Emergency failover: switch entire org from Claude Code (4.6 combo) to OpenCode (v4 combo).
# Single command, no prompts. Designed for Anthropic outage scenarios.

set -euo pipefail

HOMEDIR="/Users/deepak-macmini/honeybloom"
ORG_MD="$HOMEDIR/library/ORG.md"
JANUS_CSV_LINK="$HOMEDIR/rio/janus-config.csv"
JANUS_CSV="$(readlink -f "$JANUS_CSV_LINK" 2>/dev/null || echo "$JANUS_CSV_LINK")"
KITTEN="/opt/homebrew/bin/kitten"
LAUNCH_SCRIPT="$HOMEDIR/library/scripts/kitty-open-teammate.sh"
BACKUP_DIR="$HOMEDIR/library/scripts/.failover-backup"

# Natalie excluded — stays on Claude Code as safety net for Boss
SKIP_TEAMMATES="natalie"

# --- Read ORG.md Roster (excluding safety net) ---
get_roster() {
    grep -i "^Teammate:" "$ORG_MD" | sed 's/^Teammate: *//I' | tr '[:upper:]' '[:lower:]' | grep -vwF "$SKIP_TEAMMATES"
}

# --- Socket Discovery (same as kitty-open-teammate.sh) ---
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
# Returns one name per group (the first member), plus all SINGLEs.
# This avoids duplicate launches when iterating the roster.
get_launch_names() {
    local seen_groups=""
    while IFS= read -r name; do
        local group_line
        group_line="$(grep -i "^Group:.*\b${name}\b" "$ORG_MD" 2>/dev/null | head -1)" || true
        if [ -z "$group_line" ]; then
            # SINGLE — launch directly
            echo "$name"
        else
            # Part of a group — only launch if we haven't seen this group yet
            local group_key
            group_key="$(echo "$group_line" | sed 's/^Group: *//' | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
            if [[ "$seen_groups" != *"|${group_key}|"* ]]; then
                seen_groups="${seen_groups}|${group_key}|"
                echo "$name"
            fi
        fi
    done <<< "$(get_roster)"
}

echo "=== FAILOVER TO V4 COMBO ==="
echo ""

# --- Preflight: check OpenCode binary ---
if [ ! -x "$HOMEDIR/../.opencode/bin/opencode" ] && [ ! -x "/Users/deepak-macmini/.opencode/bin/opencode" ]; then
    echo "ABORT: OpenCode binary not found at ~/.opencode/bin/opencode"
    exit 1
fi

# --- Preflight: check Medusa plugin ---
if [ ! -f "/Users/deepak-macmini/.config/opencode/plugins/medusa.ts" ]; then
    echo "ABORT: Medusa plugin not found at ~/.config/opencode/plugins/medusa.ts"
    exit 1
fi

# --- Preflight: check MCP config parity ---
echo "Checking MCP configs..."
MISSING_MCP=""
while IFS= read -r name; do
    config="$HOMEDIR/$name/.opencode/opencode.json"
    if [ ! -f "$config" ]; then
        MISSING_MCP="${MISSING_MCP}  $name: opencode.json missing\n"
    elif ! grep -q "honeybloom-aether" "$config" 2>/dev/null; then
        MISSING_MCP="${MISSING_MCP}  $name: honeybloom-aether MCP missing\n"
    fi
done <<< "$(get_roster)"

if [ -n "$MISSING_MCP" ]; then
    echo "ABORT: MCP config issues found:"
    echo -e "$MISSING_MCP"
    exit 1
fi
echo "All 23 MCP configs verified."

# --- Backup CSV ---
mkdir -p "$BACKUP_DIR"
cp "$JANUS_CSV" "$BACKUP_DIR/janus-config.csv.pre-v4-$(date +%Y%m%d-%H%M%S)"
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
        echo "${teammate},${role},V4 Flash,OpenCode,OpenCode Go,${api_key},${effort_level},deepseek-v4-flash" >> "$TMPCSV"
    fi
done
mv "$TMPCSV" "$JANUS_CSV"
echo "CSV updated: all teammates (except $SKIP_TEAMMATES) -> OpenCode / V4 Flash."

# --- Strip hooks from opencode.json files ---
echo "Stripping shell hooks from opencode.json files..."
mkdir -p "$BACKUP_DIR/hooks"
while IFS= read -r name; do
    config="$HOMEDIR/$name/.opencode/opencode.json"
    if jq -e '.hooks' "$config" >/dev/null 2>&1; then
        # Back up the hooks section for restoration
        jq '.hooks' "$config" > "$BACKUP_DIR/hooks/${name}.json"
        # Strip hooks
        jq 'del(.hooks)' "$config" > "${config}.tmp" && mv "${config}.tmp" "$config"
        echo "  Stripped hooks from $name"
    fi
done <<< "$(get_roster)"
echo "Hooks stripped."

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
echo "All teammates now on OpenCode / V4 Flash (OpenCode Go)."
echo "To reverse: bash $HOMEDIR/library/scripts/failover-to-46.sh"
