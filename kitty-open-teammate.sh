#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Open Teammate (Kitty)
# @raycast.mode silent
# @raycast.argument1 { "type": "text", "placeholder": "Teammate name" }

KITTEN="/opt/homebrew/bin/kitten"

# Mac Mini SSH constants
SSH_KEY="/Users/d.patnaik/.ssh/id_hanover"
MINI_USER="deepak-macmini"
MINI_HOST="192.168.0.186"
MINI_LAUNCH="/Users/deepak-macmini/honeybloom/library/scripts/mini-launch.sh"
AETHER_URL="http://192.168.0.186:51730"

# --- Socket Discovery ---

discover_socket() {
    local env_sock="${KITTY_LISTEN_ON:-}"
    if [ -n "$env_sock" ]; then
        local path="${env_sock#unix:}"
        if [ -S "$path" ] && $KITTEN @ --to "$env_sock" ls >/dev/null 2>&1; then
            echo "$env_sock"
            return 0
        fi
    fi
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

# --- Tab Existence Check ---

get_existing_teammates() {
    local socket="$1"
    $KITTEN @ --to "$socket" ls 2>/dev/null | /usr/bin/python3 -c "
import json, sys
data = json.load(sys.stdin)
for os_win in data:
    for tab in os_win.get('tabs', []):
        for window in tab.get('windows', []):
            val = window.get('user_vars', {}).get('teammate', '')
            if val:
                print(val)
"
}

# --- Group Mapping (SSH-read ORG.md from Mini) ---

ORG_CACHE="/tmp/honeybloom-org.md"

cache_org_md() {
    ssh -o BatchMode=yes -o ConnectTimeout=3 -i "$SSH_KEY" "${MINI_USER}@${MINI_HOST}" \
        "cat /Users/deepak-macmini/honeybloom/library/ORG.md" > "$ORG_CACHE" 2>/dev/null
}

get_group_info() {
    local input="$1"
    /usr/bin/python3 - "$ORG_CACHE" "$input" <<'PY'
import re, sys

path, requested = sys.argv[1], sys.argv[2].lower()
lines = open(path).read().splitlines()
roster = [m.group(1).lower() for line in lines if (m := re.fullmatch(r"Teammate:\s*([a-z0-9-]+)", line.strip(), re.I))]
if not roster or len(roster) != len(set(roster)):
    raise SystemExit("Invalid ORG roster")
groups, in_groups = [], False
for raw in lines:
    line = raw.strip()
    if line == "## Groups":
        in_groups = True
        continue
    if in_groups and line.startswith("## "):
        break
    if not in_groups or not line or "(host:" not in line.lower():
        continue
    match = re.fullmatch(r"(.+?)\s*\(host:\s*([a-z0-9-]+)\)", line, re.I)
    if not match:
        raise SystemExit(f"Malformed ORG group: {line}")
    members = [item.strip().lower() for item in match.group(1).split(",") if item.strip()]
    host = match.group(2).lower()
    if not members or len(members) != len(set(members)) or host not in members:
        raise SystemExit(f"Invalid ORG group: {line}")
    groups.append((host, members))
assigned = [member for _, members in groups for member in members]
if set(assigned) != set(roster) or len(assigned) != len(set(assigned)):
    raise SystemExit("ORG groups do not cover the unique roster")
if requested not in roster:
    raise SystemExit(f"Unknown teammate: {requested}")
for host, members in groups:
    if requested in members:
        print("GROUP", host, *members)
        break
PY
}

# --- Launch Tab ---

launch_tab() {
    local socket="$1" name="$2" title="$3" keep_focus="$4" match_near="$5"
    local args=("$KITTEN" "@" "--to" "$socket" "launch" "--type=tab"
                "--tab-title" "$title" "--title" "$title"
                "--var" "teammate=$name")

    if [ -n "$match_near" ]; then
        args+=("--location" "after" "--match" "var:teammate=$match_near")
    fi

    if [ "$keep_focus" = "yes" ]; then
        args+=("--keep-focus")
    fi

    args+=("/bin/zsh" "-l" "-c"
           "trap 'curl -s -o /dev/null --max-time 3 ${AETHER_URL}/api/tab-closed?teammate=$name' EXIT; ssh -t -i $SSH_KEY ${MINI_USER}@${MINI_HOST} $MINI_LAUNCH $name")

    "${args[@]}"
}

# --- Tab Colors ---

get_tab_colors() {
    local name="$1"
    case "$name" in
        rio|ananya|claire|felix|jake)
            echo "#8B0000 #5C0000" ;;
        juno)
            echo "#2E7D32 #1B5E20" ;;
        chica|sierra|daksh)
            echo "#1565C0 #0D47A1" ;;
        andrea)
            echo "#008080 #006060" ;;
    esac
}

apply_tab_color() {
    local socket="$1" name="$2"
    local colors active_bg inactive_bg
    colors="$(get_tab_colors "$name")"
    [ -z "$colors" ] && return
    active_bg="$(echo "$colors" | awk '{print $1}')"
    inactive_bg="$(echo "$colors" | awk '{print $2}')"
    $KITTEN @ --to "$socket" set-tab-color --match "var:teammate=$name" \
        active_bg="$active_bg" inactive_bg="$inactive_bg" 2>/dev/null
}

should_start_huddle() {
    local member_count="$1" launched_count="$2"
    [ "$member_count" -gt 1 ] && [ "$launched_count" -gt 0 ]
}

start_group_huddle() {
    local host="$1" members="$2" participants_json
    participants_json="$(echo "$members" | awk '{for(i=1;i<=NF;i++) printf "\"%s\"%s", $i, (i<NF?",":"")}')"
    curl -s -o /dev/null "${AETHER_URL}/api/huddle" \
        -X POST -H "Content-Type: application/json" \
        -d "{\"action\":\"start\",\"host\":\"$host\",\"participants\":[$participants_json]}" &
}

launch_solo() {
    local socket="$1" name="$2" existing="$3"
    if ! echo "$existing" | grep -qx "$name"; then
        launch_tab "$socket" "$name" "$name" "no" ""
        apply_tab_color "$socket" "$name"
    fi
}

launch_group() {
    local socket="$1" host="$2" members="$3" existing="$4"
    local previous="" launched_count=0 name needs_group
    for name in $members; do
        if ! echo "$existing" | grep -qx "$name"; then
            needs_group="no"
            [ -z "$previous" ] && needs_group="yes"
            launch_tab "$socket" "$name" "$name" "$needs_group" "$previous"
            apply_tab_color "$socket" "$name"
            launched_count=$((launched_count + 1))
        fi
        previous="$name"
    done
    if should_start_huddle "$(echo "$members" | wc -w | tr -d ' ')" "$launched_count"; then
        start_group_huddle "$host" "$members"
    fi
}

# --- Main ---

main() {

SOLO=false
if [ "$1" = "--solo" ]; then
    SOLO=true
    shift
fi

INPUT="$(echo "$1" | tr '[:upper:]' '[:lower:]')"

# Cache ORG.md from Mini (only needed for group logic in non-solo mode)
if ! $SOLO; then
    cache_org_md
fi

# For solo mode, create a minimal ORG cache so validation works
if $SOLO; then
    # Validate teammate exists via SSH
    if ! ssh -o BatchMode=yes -o ConnectTimeout=3 -i "$SSH_KEY" "${MINI_USER}@${MINI_HOST}" \
        "grep -qi '^Teammate: ${INPUT}$' /Users/deepak-macmini/honeybloom/library/ORG.md" 2>/dev/null; then
        echo "Unknown teammate: $1"
        exit 1
    fi
else
    PAIR_INFO="$(get_group_info "$INPUT")"
    if [ -z "$PAIR_INFO" ]; then
        echo "Unknown teammate: $1"
        exit 1
    fi
fi

# Ensure Kitty is running and socket is available
WE_LAUNCHED=false
SOCKET="$(discover_socket)"
if [ -z "$SOCKET" ]; then
    open -a kitty
    WE_LAUNCHED=true
    ATTEMPTS=0
    while [ $ATTEMPTS -lt 20 ]; do
        sleep 0.5
        SOCKET="$(discover_socket)"
        [ -n "$SOCKET" ] && break
        ATTEMPTS=$((ATTEMPTS + 1))
    done
    if [ -z "$SOCKET" ]; then
        echo "Kitty launched but socket not found after 10s"
        exit 1
    fi
fi

# Capture frontmost app before any Kitty operations
FRONT_APP="$(osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' 2>/dev/null)"

EXISTING="$(get_existing_teammates "$SOCKET")"

if $SOLO; then
    # Solo mode — open only the named teammate
    launch_solo "$SOCKET" "$INPUT" "$EXISTING"
else
    MODE="$(echo "$PAIR_INFO" | awk '{print $1}')"

    if [ "$MODE" = "GROUP" ]; then
        HOST="$(echo "$PAIR_INFO" | awk '{print $2}')"
        MEMBERS="$(echo "$PAIR_INFO" | cut -d' ' -f3-)"
        launch_group "$SOCKET" "$HOST" "$MEMBERS" "$EXISTING"
    else
        echo "Invalid group data for $INPUT" >&2
        exit 1
    fi
fi

# Restore frontmost app
if [ -n "$FRONT_APP" ]; then
    osascript -e "tell application \"$FRONT_APP\" to activate" 2>/dev/null || true
fi

# Close the default blank tab that Kitty opens on launch
if $WE_LAUNCHED; then
    DEFAULT_WINDOWS=$($KITTEN @ --to "$SOCKET" ls 2>/dev/null | /usr/bin/python3 -c "
import json, sys
data = json.load(sys.stdin)
for os_win in data:
    for tab in os_win.get('tabs', []):
        has_teammate = False
        first_window_id = None
        for window in tab.get('windows', []):
            if first_window_id is None:
                first_window_id = window['id']
            if window.get('user_vars', {}).get('teammate', ''):
                has_teammate = True
                break
        if not has_teammate and first_window_id is not None:
            print(first_window_id)
")
    for WIN_ID in $DEFAULT_WINDOWS; do
        $KITTEN @ --to "$SOCKET" close-tab --match "id:$WIN_ID" 2>/dev/null
    done
fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
