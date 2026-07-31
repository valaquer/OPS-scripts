#!/bin/bash
# Emergency failover destination: OpenCode (v4 combo).
# Single command, no prompts.

set -euo pipefail

HOMEDIR="/Users/deepak-macmini/honeybloom"
ORG_MD="${ORG_MD_OVERRIDE:-$HOMEDIR/library/wiki/Organization/ORG.md}"
CANONICAL_JANUS_CSV="$HOMEDIR/library/scripts/janus-config.csv"
JANUS_CSV="${JANUS_CSV_OVERRIDE:-$CANONICAL_JANUS_CSV}"
KITTEN="/opt/homebrew/bin/kitten"
LAUNCH_SCRIPT="$HOMEDIR/library/scripts/open-team.sh"
BACKUP_DIR="$HOMEDIR/library/scripts/.failover-backup"

# Legacy Natalie exception preserves her current row pending Boss's failover-policy decision.
SKIP_TEAMMATES="natalie"

# --- Read ORG.md roster (excluding the deferred legacy exception) ---
get_roster() {
    grep -i "^Teammate:" "$ORG_MD" | sed 's/^Teammate: *//I' | tr '[:upper:]' '[:lower:]' | grep -vwF "$SKIP_TEAMMATES"
}

# --- Socket Discovery (same as open-team.sh) ---
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
# Returns one host per validated current group.
# This avoids duplicate launches when iterating the roster.
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
            printf '%s,%s,V4 Flash,OpenCode,OpenCode Go,%s,%s,deepseek-v4-flash,%s\n' "$teammate" "$role" "$api_key" "$effort_level" "$machine" >> "$tmpcsv"
        fi
    done < <(tail -n +2 "$csv_path")
    mv "$tmpcsv" "$csv_path"
}

main() {
validate_org_and_print_hosts >/dev/null
validate_csv

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
echo "All $(get_roster | wc -l | tr -d ' ') MCP configs verified."

# --- Backup CSV ---
mkdir -p "$BACKUP_DIR"
cp "$JANUS_CSV" "$BACKUP_DIR/janus-config.csv.pre-v4-$(date +%Y%m%d-%H%M%S)"
echo "CSV backed up."

# --- Rewrite CSV atomically ---
echo "Rewriting janus-config.csv..."
rewrite_csv "$JANUS_CSV"
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
    bash "$LAUNCH_SCRIPT" --solo "$name" &
    sleep 1
done <<< "$(get_launch_names)"

# Wait for all background launches
wait

echo ""
echo "=== FAILOVER COMPLETE ==="
echo "The other 25 teammates now use OpenCode / V4 Flash; Natalie's row is unchanged pending Boss's failover-policy decision."
echo "Restoration to the Codex/Sol baseline is not automated and requires separately gated work."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
