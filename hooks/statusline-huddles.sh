#!/bin/bash
# Status line huddle detection for Claude Code.
# Called by settings.json statusLine command.
# Args: $1 = teammate name (lowercase)
# Output: "{HOST}'S HUDDLE - {P1}, {P2}, ..." for hosts, empty otherwise.
# Exit 0 always — errors must never break the status line.

TEAMMATE="${1:-}"
[ -z "$TEAMMATE" ] && exit 0
TEAMMATE=$(echo "$TEAMMATE" | tr '[:upper:]' '[:lower:]')

[ ! -f /tmp/kitty-huddles.json ] && exit 0

python3 -c "
import json, sys
t = '$TEAMMATE'
try:
    s = json.load(open('/tmp/kitty-huddles.json'))
    # Check if teammate is a host
    if t in s:
        host_data = s[t]
        participants = host_data.get('participants', [])
        # Convert to uppercase and sort
        participants_upper = [p.upper() for p in participants]
        participants_upper.sort()
        # Format host name (uppercase + possessive)
        host_upper = t.upper()
        host_possessive = host_upper + \"'S\"
        # Build participant list string
        if participants_upper:
            participants_str = \", \".join(participants_upper)
            result = f\"{host_possessive} HUDDLE - {participants_str}\"
        else:
            result = f\"{host_possessive} HUDDLE\"
        print(result)
    # If not a host, print nothing (participants and non-huddle teammates get empty)
except:
    pass
" 2>/dev/null
