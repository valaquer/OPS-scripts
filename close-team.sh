#!/bin/bash
# Close all Kitty tabs for a team by leader name.
# Inverse of open-team.sh. Uses close-tabs.py for the heavy lifting.
#
# Usage: close-team.sh <leader>
# Example: close-team.sh rio    → closes rio, chica, natalie

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ORG_PATH="/Users/deepak-macmini/honeybloom/library/wiki/Organization/ORG.md"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <leader>" >&2
    exit 1
fi

LEADER="$(echo "$1" | tr '[:upper:]' '[:lower:]')"

if ! echo "$LEADER" | grep -qE '^[a-z0-9-]+$'; then
    echo "Invalid leader name: $LEADER" >&2
    exit 1
fi

if grep -qE "\(host: *${LEADER}\)" "$ORG_PATH"; then
    echo "Closing team: $LEADER"
elif grep -qiE "^Teammate: *${LEADER} *$" "$ORG_PATH" && \
     python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('ct', '$SCRIPT_DIR/close-tabs.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.exit(0 if mod.is_solo_operator('$LEADER') else 1)
" 2>/dev/null; then
    echo "Closing solo: $LEADER"
else
    echo "Not a team leader or solo operator in ORG.md: $LEADER" >&2
    exit 1
fi
python3 "$SCRIPT_DIR/close-tabs.py" "$LEADER"

AETHER_URL="${AETHER_URL:-http://localhost:51730}"
ROOM_ID=$(curl -s "$AETHER_URL/api/rooms" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for h in data.get('huddles', []):
    if h.get('name') == '$LEADER' and h.get('active', False):
        print(h['id'])
        break
" 2>/dev/null)

if [ -n "$ROOM_ID" ]; then
    curl -s -X POST "$AETHER_URL/api/archive-huddle" \
        -H "Content-Type: application/json" \
        -d "{\"roomId\":\"$ROOM_ID\"}" >/dev/null 2>&1
    echo "Archived huddle: $ROOM_ID"
fi
