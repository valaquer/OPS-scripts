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
    if ! grep -qi "^Teammate: ${input}$" "$ORG_CACHE" 2>/dev/null; then
        echo ""
        return
    fi
    local group_line
    group_line="$(grep -i "^Group:.*\b${input}\b" "$ORG_CACHE" 2>/dev/null | head -1)"
    if [ -z "$group_line" ]; then
        echo "SINGLE $input"
        return
    fi
    local host=""
    if echo "$group_line" | grep -q "(host:"; then
        host="$(echo "$group_line" | sed 's/.*host: *\([a-z]*\).*/\1/')"
    fi
    local members_raw
    members_raw="$(echo "$group_line" | sed 's/^Group: *//; s/ *(host:.*//')"
    local members
    members="$(echo "$members_raw" | tr ',' ' ' | tr -s ' ' | tr '[:upper:]' '[:lower:]' | xargs)"
    local count
    count="$(echo "$members" | wc -w | tr -d ' ')"
    if [ "$count" -ge 3 ]; then
        echo "TRIO $host $members"
    else
        echo "$members"
    fi
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

# --- Main ---

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
    if ! echo "$EXISTING" | grep -qx "$INPUT"; then
        launch_tab "$SOCKET" "$INPUT" "$INPUT" "no" ""
        apply_tab_color "$SOCKET" "$INPUT"
    fi
else
    MODE="$(echo "$PAIR_INFO" | awk '{print $1}')"

    if [ "$MODE" = "SINGLE" ]; then
        NAME="$(echo "$PAIR_INFO" | awk '{print $2}')"
        if ! echo "$EXISTING" | grep -qx "$NAME"; then
            launch_tab "$SOCKET" "$NAME" "$NAME" "no" ""
            apply_tab_color "$SOCKET" "$NAME"
        fi
    elif [ "$MODE" = "TRIO" ]; then
        HOST="$(echo "$PAIR_INFO" | awk '{print $2}')"
        MEMBERS="$(echo "$PAIR_INFO" | cut -d' ' -f3-)"
        PREV=""
        for NAME in $MEMBERS; do
            if ! echo "$EXISTING" | grep -qx "$NAME"; then
                NEEDS_GROUP="no"
                [ -z "$PREV" ] && NEEDS_GROUP="yes"
                launch_tab "$SOCKET" "$NAME" "$NAME" "$NEEDS_GROUP" "$PREV"
                apply_tab_color "$SOCKET" "$NAME"
            fi
            PREV="$NAME"
        done
        # Auto-start huddle
        PARTICIPANTS_JSON="$(echo "$MEMBERS" | awk '{for(i=1;i<=NF;i++) printf "\"%s\"%s", $i, (i<NF?",":"")}')"
        curl -s -o /dev/null "${AETHER_URL}/api/huddle" \
            -X POST -H "Content-Type: application/json" \
            -d "{\"action\":\"start\",\"host\":\"$HOST\",\"participants\":[$PARTICIPANTS_JSON]}" &
    else
        # Paired teammates (duo)
        LEFT_NAME="$(echo "$PAIR_INFO" | awk '{print $1}')"
        RIGHT_NAME="$(echo "$PAIR_INFO" | awk '{print $2}')"
        LEFT_EXISTS=false
        RIGHT_EXISTS=false
        echo "$EXISTING" | grep -qx "$LEFT_NAME" && LEFT_EXISTS=true
        echo "$EXISTING" | grep -qx "$RIGHT_NAME" && RIGHT_EXISTS=true

        if $LEFT_EXISTS && $RIGHT_EXISTS; then
            :
        elif ! $LEFT_EXISTS && ! $RIGHT_EXISTS; then
            launch_tab "$SOCKET" "$LEFT_NAME" "$LEFT_NAME" "yes" ""
            apply_tab_color "$SOCKET" "$LEFT_NAME"
            launch_tab "$SOCKET" "$RIGHT_NAME" "$RIGHT_NAME" "no" "$LEFT_NAME"
            apply_tab_color "$SOCKET" "$RIGHT_NAME"
        else
            if ! $LEFT_EXISTS; then
                launch_tab "$SOCKET" "$LEFT_NAME" "$LEFT_NAME" "no" "$RIGHT_NAME"
                apply_tab_color "$SOCKET" "$LEFT_NAME"
            else
                launch_tab "$SOCKET" "$RIGHT_NAME" "$RIGHT_NAME" "no" "$LEFT_NAME"
                apply_tab_color "$SOCKET" "$RIGHT_NAME"
            fi
        fi
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
