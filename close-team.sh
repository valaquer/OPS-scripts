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

if ! grep -qE "\(host: *${LEADER}\)" "$ORG_PATH"; then
    echo "Not a team leader in ORG.md: $LEADER" >&2
    exit 1
fi

echo "Closing team: $LEADER"
python3 "$SCRIPT_DIR/close-tabs.py" "$LEADER"
