#!/bin/bash
# Emergency failover destination: Claude Code (4.6 combo).
# Single command, no prompts.

set -euo pipefail

HOMEDIR="/Users/deepak-macmini/honeybloom"
ORG_MD="${ORG_MD_OVERRIDE:-$HOMEDIR/library/ORG.md}"
CANONICAL_JANUS_CSV="$HOMEDIR/library/wiki/project-runbooks/runbook-janus-coding/janus-config.csv"
JANUS_CSV="${JANUS_CSV_OVERRIDE:-$CANONICAL_JANUS_CSV}"
KITTEN="/opt/homebrew/bin/kitten"
CLAUDE="/Users/deepak-macmini/.local/bin/claude"
LAUNCH_SCRIPT="$HOMEDIR/library/scripts/kitty-open-teammate.sh"
BACKUP_DIR="$HOMEDIR/library/scripts/.failover-backup"

# Legacy Natalie exception preserves her current row pending Boss's failover-policy decision.
SKIP_TEAMMATES="natalie"

# --- Read ORG.md roster (excluding the deferred legacy exception) ---
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
    validate_org_and_print_hosts
}

validate_org_and_print_hosts() {
    /usr/bin/python3 - "$ORG_MD" <<'PY'
import re, sys
lines = open(sys.argv[1]).read().splitlines()
roster = [m.group(1).lower() for line in lines if (m := re.fullmatch(r"Teammate:\s*([a-z0-9-]+)", line.strip(), re.I))]
if not roster or len(roster) != len(set(roster)): raise SystemExit("invalid ORG roster")
groups=[]; active=False
for raw in lines:
    line=raw.strip()
    if line == "## Groups": active=True; continue
    if active and line.startswith("## "): break
    if not active or not line or "(host:" not in line.lower(): continue
    m=re.fullmatch(r"(.+?)\s*\(host:\s*([a-z0-9-]+)\)", line, re.I)
    if not m: raise SystemExit(f"malformed ORG group: {line}")
    members=[x.strip().lower() for x in m.group(1).split(",") if x.strip()]; host=m.group(2).lower()
    if not members or len(members)!=len(set(members)) or host not in members: raise SystemExit(f"invalid ORG group: {line}")
    groups.append((host,members))
assigned=[x for _,members in groups for x in members]
if set(assigned)!=set(roster) or len(assigned)!=len(set(assigned)): raise SystemExit("ORG groups do not cover unique roster")
for host,_ in groups: print(host)
PY
}

validate_csv() {
    local csv_path="${1:-$JANUS_CSV}"
    /usr/bin/python3 - "$ORG_MD" "$csv_path" <<'PY'
import csv, re, sys
org_path, csv_path = sys.argv[1:]
roster = [m.group(1).lower() for line in open(org_path) if (m := re.fullmatch(r"Teammate:\s*([a-z0-9-]+)\s*", line.strip(), re.I))]
rows = list(csv.reader(open(csv_path)))
expected = ["teammate","role","model","harness","provider","api_key","effort_level","model_api_id","machine"]
if not rows or rows[0] != expected or any(len(row) != 9 for row in rows[1:]): raise SystemExit("invalid Janus nine-column schema")
names = [row[0].strip().lower() for row in rows[1:]]
if len(names) != len(set(names)) or set(names) != set(roster): raise SystemExit("Janus teammate set differs from ORG roster")
PY
}

rewrite_csv() {
    local csv_path="${1:?rewrite_csv requires an explicit CSV path}"
    if [ "${HONEYBLOOM_TEST_MODE:-0}" = 1 ] && [ "$csv_path" = "$CANONICAL_JANUS_CSV" ]; then
        echo "ABORT: test mode refuses the canonical Janus CSV." >&2
        return 1
    fi
    local tmpcsv
    tmpcsv="$(mktemp "${csv_path}.tmp.XXXXXX")"
    head -1 "$csv_path" > "$tmpcsv"
    while IFS=',' read -r teammate role model harness provider api_key effort_level model_api_id machine; do
        local local_name
        local_name="$(echo "$teammate" | tr '[:upper:]' '[:lower:]')"
        if echo "$SKIP_TEAMMATES" | grep -qwF "$local_name"; then
            printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$teammate" "$role" "$model" "$harness" "$provider" "$api_key" "$effort_level" "$model_api_id" "$machine" >> "$tmpcsv"
        else
            printf '%s,%s,Opus 4.6,Claude Code,Anthropic,%s,high,,%s\n' "$teammate" "$role" "$api_key" "$machine" >> "$tmpcsv"
        fi
    done < <(tail -n +2 "$csv_path")
    mv "$tmpcsv" "$csv_path"
}

main() {
validate_org_and_print_hosts >/dev/null
validate_csv

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
rewrite_csv "$JANUS_CSV"
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
echo "The other 25 teammates now use Claude Code / Opus 4.6; Natalie's row is unchanged pending Boss's failover-policy decision."
echo "Restoration to the Codex/Sol baseline is not automated and requires separately gated work."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
