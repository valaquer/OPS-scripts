#!/bin/bash
# Open a teammate or team on Mac Mini's local Kitty.
# Usage: open-team.sh --solo <name>     # one teammate
#        open-team.sh <leader>          # full team + huddle

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KITTEN="/opt/homebrew/bin/kitten"
MINI_LAUNCH="$SCRIPT_DIR/mini-launch.sh"
ORG_MD="/Users/deepak-macmini/honeybloom/library/wiki/Organization/ORG.md"
AETHER_URL="${AETHER_URL:-http://localhost:51820}"
HUDDLE_URL="$AETHER_URL/api/huddle"
PINNED_URL="$AETHER_URL/api/pinned-rooms"

# --- Kitty Socket Discovery ---

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

# --- Check if teammate tab already exists ---

has_tab() {
    local socket="$1" name="$2"
    $KITTEN @ --to "$socket" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for os_win in data:
    for tab in os_win.get('tabs', []):
        for window in tab.get('windows', []):
            if window.get('user_vars', {}).get('teammate', '') == '$name':
                sys.exit(0)
sys.exit(1)
" 2>/dev/null
}

# --- Launch a single teammate tab ---

launch_tab() {
    local socket="$1" name="$2"

    if has_tab "$socket" "$name"; then
        echo "Tab already exists: $name"
        return 0
    fi

    $KITTEN @ --to "$socket" launch --type=tab \
        --tab-title "$name" --title "$name" \
        --var "teammate=$name" \
        --keep-focus \
        /bin/zsh -l -c "$MINI_LAUNCH $name"

    curl -s -o /dev/null -X POST "$AETHER_URL/api/rooms/activate" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$name\"}" 2>/dev/null || true

    echo "Launched: $name"
}

# --- Ensure Kitty is running ---

ensure_kitty() {
    local socket
    socket="$(discover_socket 2>/dev/null || true)"
    if [ -n "$socket" ]; then
        echo "$socket"
        return 0
    fi
    open -a kitty
    local attempts=0
    while [ $attempts -lt 20 ]; do
        sleep 0.5
        socket="$(discover_socket 2>/dev/null || true)"
        if [ -n "$socket" ]; then
            echo "$socket"
            return 0
        fi
        attempts=$((attempts + 1))
    done
    echo "Kitty launched but socket not found after 10s" >&2
    return 1
}

# --- Parse mode ---

SOLO=false
if [[ "${1:-}" == "--solo" ]]; then
    SOLO=true
    shift
fi

INPUT="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
if [[ -z "$INPUT" ]]; then
    echo "Usage: $0 [--solo] <name>"
    exit 1
fi

SOCKET="$(ensure_kitty)"

if $SOLO; then
    # Solo mode -- launch one teammate, no huddle
    launch_tab "$SOCKET" "$INPUT"
    exit 0
fi

# --- Team mode ---

LEADER="$INPUT"

group_line="$(grep -i "(host: *${LEADER})" "$ORG_MD" 2>/dev/null | head -1)"
if [[ -z "$group_line" ]]; then
    echo "Error: no group found for host '$LEADER' in ORG.md"
    exit 1
fi

members_raw="$(echo "$group_line" | sed 's/ *(host:.*//')"
IFS=',' read -ra member_arr <<< "$members_raw"
members=()
for m in "${member_arr[@]}"; do
    cleaned="$(echo "$m" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
    [[ -n "$cleaned" ]] && members+=("$cleaned")
done

if [[ ${#members[@]} -eq 0 ]]; then
    echo "Error: no members parsed for '$LEADER'"
    exit 1
fi

echo "Team $LEADER: ${members[*]}"

# --- Wake all members locally ---

echo "Waking ${#members[@]} members..."
for m in "${members[@]}"; do
    launch_tab "$SOCKET" "$m" &
done
wait
echo "All members launched."

# --- Create huddle ---

participants="[$(printf '"%s",' "${members[@]}" | sed 's/,$//')]"

# If LEADER is a virtual group name (not a teammate), use first member as huddle host
HUDDLE_HOST="$LEADER"
if [[ ! -d "/Users/deepak-macmini/honeybloom/$LEADER" ]]; then
    HUDDLE_HOST="${members[0]}"
fi

echo "Creating huddle with host=$HUDDLE_HOST..."
response="$(curl -s -X POST "$HUDDLE_URL" \
    -H "Content-Type: application/json" \
    -d "{\"action\":\"start\",\"host\":\"$HUDDLE_HOST\",\"participants\":$participants}")"

room_id="$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('roomId',''))" 2>/dev/null || echo "")"

if [[ -z "$room_id" ]]; then
    echo "Warning: could not extract roomId from huddle response: $response"
    exit 0
fi

echo "Huddle created: $room_id"

# --- Unpin old leader huddles ---

echo "Checking for old pinned huddles..."
pinned="$(curl -s "$PINNED_URL")"
old_rooms="$(echo "$pinned" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('rooms', []):
    rid = r if isinstance(r, str) else r.get('roomId', '')
    if rid.startswith('huddle-$LEADER-') and rid != '$room_id':
        print(rid)
" 2>/dev/null || true)"

if [[ -n "$old_rooms" ]]; then
    while IFS= read -r old_id; do
        echo "Unpinning: $old_id"
        curl -s -X POST "$PINNED_URL" \
            -H "Content-Type: application/json" \
            -d "{\"action\":\"unpin\",\"roomId\":\"$old_id\"}" > /dev/null 2>&1
    done <<< "$old_rooms"
fi

# --- Pin new huddle ---

echo "Pinning: $room_id"
curl -s -X POST "$PINNED_URL" \
    -H "Content-Type: application/json" \
    -d "{\"action\":\"pin\",\"roomId\":\"$room_id\"}" > /dev/null 2>&1

echo "Done. Team $LEADER is live in $room_id."
