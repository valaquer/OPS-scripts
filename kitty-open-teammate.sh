#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Open Teammate (Kitty)
# @raycast.mode silent
# @raycast.argument1 { "type": "text", "placeholder": "Teammate name" }

# Boss's wakeup prompt — {NAME} is substituted with the teammate's title-case name at launch.

KITTEN="/opt/homebrew/bin/kitten"
CLAUDE="/Users/d.patnaik/.local/bin/claude"
OPENCODE="/Users/d.patnaik/.opencode/bin/opencode"
HOMEDIR="/Users/d.patnaik/honeybloom"
JANUS_CSV="/Users/d.patnaik/honeybloom/rio/janus-config.csv"
WAKEUP_PROMPT_TEMPLATE='{NAME}, hi. A few important announcements.
[1] Your CLAUDE, PLAYBOOK AND LOGBOOK are already loaded into context. No need to call Read on them again. You have a generous 1M context window so internalize the files.
[2] Your knowledge cutoff is nearly a year old. Keep this in mind
[3] This is the start of a new session. Use judgement to determine the time that has elapsed between the end of the last session and the start of this session.
[4] In every turn, you will receive the current timestamp and a directive to be succinct and productive.
Bring your A-game!'

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

# --- Harness Detection ---
# Reads harness from janus-config.csv. CSV is the single source of truth.

get_harness() {
    awk -F',' -v name="$1" 'tolower($1) == name { print $4 }' "$JANUS_CSV"
}

# --- Launch Tab ---

launch_tab() {
    local socket="$1" name="$2" title="$3" keep_focus="$4" match_near="$5"
    local args=("$KITTEN" "@" "--to" "$socket" "launch" "--type=tab"
                "--tab-title" "$title" "--title" "$title"
                "--var" "teammate=$name"
                "--cwd" "$HOMEDIR/$name")

    if [ -n "$match_near" ]; then
        args+=("--location" "after" "--match" "var:teammate=$match_near")
    fi

    if [ "$keep_focus" = "yes" ]; then
        args+=("--keep-focus")
    fi

    local harness
    harness="$(get_harness "$name")"
    if [ -z "$harness" ]; then
        echo "Error: $name not found in janus-config.csv"
        return 1
    fi

    if [[ "$harness" == *"OpenCode"* ]]; then
        args+=("/bin/zsh" "-l" "-c"
               "$OPENCODE")
    else
        local wakeup_prompt="${WAKEUP_PROMPT_TEMPLATE//\{NAME\}/$title}"
        args+=("/bin/zsh" "-l" "-c"
               "$CLAUDE --dangerously-skip-permissions \"$wakeup_prompt\"")
    fi

    "${args[@]}"
}

# --- Focus Tab ---

focus_tab() {
    local socket="$1" name="$2"
    $KITTEN @ --to "$socket" focus-tab --match "var:teammate=$name" 2>/dev/null
}

# --- Tab Colors ---
# Per-tab accent colors applied via set-tab-color after launch.
# Background only — text colors come from kitty.conf defaults.

get_tab_colors() {
    local name="$1"
    case "$name" in
        dante|rio|gunnar|kirby|guru|ananya|claire|felix|hana|samara|zara|noah|katja)
            echo "#8B0000 #5C0000" ;;
        ezra|theo|juno|vera|isa)
            echo "#2E7D32 #1B5E20" ;;
        chica|lea|sierra|nash|pike|eva|daksh|quinn|wyatt|omar|edgar)
            echo "#1565C0 #0D47A1" ;;
        richie)
            echo "#B8860B #8B6914" ;;
        natalie|klara|ines)
            echo "#008080 #006060" ;;
        sandbox)
            echo "#808080 #606060" ;;
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

# --- Pair Mapping ---
# LEFT = first in pair (principal or first-listed). RIGHT = second (partner).
# Focus lands on RIGHT tab.

get_pair() {
    local input="$1"
    case "$input" in
        chica|rio)      echo "chica Chica rio Rio" ;;
        edgar|isa)      echo "edgar Edgar isa Isa" ;;
        lea|theo)       echo "lea Lea theo Theo" ;;
        sierra|dante)   echo "sierra Sierra dante Dante" ;;
        eva|kirby)      echo "eva Eva kirby Kirby" ;;
        daksh|guru)     echo "daksh Daksh guru Guru" ;;
        ines)           echo "SINGLE ines Ines" ;;
        nash|ezra)      echo "nash Nash ezra Ezra" ;;
        pike|juno)      echo "pike Pike juno Juno" ;;
        quinn|vera)     echo "quinn Quinn vera Vera" ;;
        wyatt|hana)     echo "wyatt Wyatt hana Hana" ;;
        omar|zara)      echo "omar Omar zara Zara" ;;
        ananya)         echo "SINGLE ananya Ananya" ;;
        claire)         echo "SINGLE claire Claire" ;;
        felix)          echo "SINGLE felix Felix" ;;
        gunnar)         echo "SINGLE gunnar Gunnar" ;;
        richie)         echo "SINGLE richie Richie" ;;
        katja)          echo "SINGLE katja Katja" ;;

        noah)           echo "SINGLE noah Noah" ;;
        natalie)        echo "SINGLE natalie Natalie" ;;
        klara)          echo "SINGLE klara Klara" ;;
        sandbox)        echo "SINGLE sandbox sandbox" ;;
        samara)         echo "SINGLE samara Samara" ;;
        *)              echo "" ;;
    esac
}

# --- Main ---

# Notify Facade that these teammates' tabs are open
notify_facade() {
    local name="$1"
    curl -s -X POST "http://localhost:51730/api/rooms/activate" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$name\"}" >/dev/null 2>&1 || true
}

SOLO=false
if [ "$1" = "--solo" ]; then
    SOLO=true
    shift
fi

INPUT="$(echo "$1" | tr '[:upper:]' '[:lower:]')"

# Validate teammate name before doing anything else
PAIR_INFO="$(get_pair "$INPUT")"
if [ -z "$PAIR_INFO" ]; then
    echo "Unknown teammate: $1"
    exit 1
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

EXISTING="$(get_existing_teammates "$SOCKET")"

if [ "$(echo "$PAIR_INFO" | awk '{print $1}')" = "SINGLE" ]; then
    # Single teammate
    NAME="$(echo "$PAIR_INFO" | awk '{print $2}')"
    TITLE="$(echo "$PAIR_INFO" | awk '{print $3}')"

    if echo "$EXISTING" | grep -qx "$NAME"; then
        focus_tab "$SOCKET" "$NAME"
    else
        launch_tab "$SOCKET" "$NAME" "$TITLE" "no" ""
        apply_tab_color "$SOCKET" "$NAME"
        notify_facade "$NAME"
    fi
else
    # Paired teammates
    LEFT_NAME="$(echo "$PAIR_INFO" | awk '{print $1}')"
    LEFT_TITLE="$(echo "$PAIR_INFO" | awk '{print $2}')"
    RIGHT_NAME="$(echo "$PAIR_INFO" | awk '{print $3}')"
    RIGHT_TITLE="$(echo "$PAIR_INFO" | awk '{print $4}')"

    if $SOLO; then
        # Solo mode — open only the named teammate, skip their partner
        if [ "$INPUT" = "$LEFT_NAME" ]; then
            SOLO_NAME="$LEFT_NAME"; SOLO_TITLE="$LEFT_TITLE"
        else
            SOLO_NAME="$RIGHT_NAME"; SOLO_TITLE="$RIGHT_TITLE"
        fi
        if echo "$EXISTING" | grep -qx "$SOLO_NAME"; then
            focus_tab "$SOCKET" "$SOLO_NAME"
        else
            launch_tab "$SOCKET" "$SOLO_NAME" "$SOLO_TITLE" "no" ""
            apply_tab_color "$SOCKET" "$SOLO_NAME"
            notify_facade "$SOLO_NAME"
        fi
    else
        LEFT_EXISTS=false
        RIGHT_EXISTS=false
        echo "$EXISTING" | grep -qx "$LEFT_NAME" && LEFT_EXISTS=true
        echo "$EXISTING" | grep -qx "$RIGHT_NAME" && RIGHT_EXISTS=true

        if $LEFT_EXISTS && $RIGHT_EXISTS; then
            # Both exist — focus the one Boss typed
            focus_tab "$SOCKET" "$INPUT"
        elif ! $LEFT_EXISTS && ! $RIGHT_EXISTS; then
            # Neither exists — open both
            launch_tab "$SOCKET" "$LEFT_NAME" "$LEFT_TITLE" "yes" ""
            apply_tab_color "$SOCKET" "$LEFT_NAME"
            notify_facade "$LEFT_NAME"
            launch_tab "$SOCKET" "$RIGHT_NAME" "$RIGHT_TITLE" "no" "$LEFT_NAME"
            apply_tab_color "$SOCKET" "$RIGHT_NAME"
            notify_facade "$RIGHT_NAME"
        else
            # One exists — open only the missing one
            if ! $LEFT_EXISTS; then
                launch_tab "$SOCKET" "$LEFT_NAME" "$LEFT_TITLE" "no" "$RIGHT_NAME"
                apply_tab_color "$SOCKET" "$LEFT_NAME"
                notify_facade "$LEFT_NAME"
            else
                launch_tab "$SOCKET" "$RIGHT_NAME" "$RIGHT_TITLE" "no" "$LEFT_NAME"
                apply_tab_color "$SOCKET" "$RIGHT_NAME"
                notify_facade "$RIGHT_NAME"
            fi
        fi
    fi
fi

# Close the default blank tab that Kitty opens on launch
# Only when WE launched Kitty — never touch pre-existing tabs
if $WE_LAUNCHED; then
    rm -f /tmp/kitty-huddles.json
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
