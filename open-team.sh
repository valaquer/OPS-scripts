#!/bin/bash
# Open a team: wake all members, create huddle, unpin old leader huddle, pin new one.
# Usage: open-team.sh <leader>
# Example: open-team.sh kirby

set -euo pipefail

LEADER="${1:-}"
if [[ -z "$LEADER" ]]; then
    echo "Usage: $0 <leader>"
    exit 1
fi

LEADER="$(echo "$LEADER" | tr '[:upper:]' '[:lower:]')"
ORG_MD="/Users/deepak-macmini/honeybloom/library/ORG.md"
# Wake must run on the iMac — kitty-open-teammate.sh is iMac-runtime code
# (iMac-only SSH key path, local Kitty socket). Route via reverse SSH.
IMAC_KEY="/Users/deepak-macmini/.ssh/id_mini"
IMAC_HOST="d.patnaik@192.168.0.153"
IMAC_LAUNCH="/Users/d.patnaik/raycast-scripts/kitty-open-teammate.sh"
AETHER_URL="${AETHER_URL:-http://localhost:51730}"
HUDDLE_URL="$AETHER_URL/api/huddle"
PINNED_URL="$AETHER_URL/api/pinned-rooms"

# --- Parse ORG.md Groups for leader's team ---

group_line="$(grep -i "(host: *${LEADER})" "$ORG_MD" 2>/dev/null | head -1)"
if [[ -z "$group_line" ]]; then
    echo "Error: no group found for host '$LEADER' in ORG.md"
    exit 1
fi

# Extract members (everything before "(host:")
members_raw="$(echo "$group_line" | sed 's/ *(host:.*//')"
# Split on comma, trim, lowercase
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

# --- Wake all members ---

echo "Waking ${#members[@]} members..."
for m in "${members[@]}"; do
    ssh -o BatchMode=yes -o ConnectTimeout=5 -i "$IMAC_KEY" "$IMAC_HOST" \
        "$IMAC_LAUNCH --solo $m" &
done
wait
echo "All members launched."

# --- Create huddle ---

# Build participants JSON array
participants="[$(printf '"%s",' "${members[@]}" | sed 's/,$//')]"

echo "Creating huddle with host=$LEADER..."
response="$(curl -s -X POST "$HUDDLE_URL" \
    -H "Content-Type: application/json" \
    -d "{\"action\":\"start\",\"host\":\"$LEADER\",\"participants\":$participants}")"

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
