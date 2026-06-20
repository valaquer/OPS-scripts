#!/bin/bash
# iTerm2 Status Bar Script: Shows meeting indicator if session is hosting a meeting
# Outputs: "📊 MEETING IN PROGRESS" if active, empty otherwise
# iTerm2 polls this script periodically

MEETINGS_FILE="$HOME/.claude/meetings/active.json"

# Get current session's profile name from iTerm2 environment
# iTerm2 sets ITERM_PROFILE for shell scripts
PROFILE="${ITERM_PROFILE:-}"

if [ -z "$PROFILE" ]; then
    exit 0
fi

PROFILE_LOWER=$(echo "$PROFILE" | tr '[:upper:]' '[:lower:]')

# Check if this profile is hosting a meeting
if [ -f "$MEETINGS_FILE" ]; then
    IS_HOST=$(python3 -c "
import json
import sys
try:
    with open('$MEETINGS_FILE', 'r') as f:
        state = json.load(f)
    if '$PROFILE_LOWER' in state:
        print('yes')
    else:
        print('no')
except:
    print('no')
" 2>/dev/null)

    if [ "$IS_HOST" = "yes" ]; then
        echo "📊 MEETING IN PROGRESS"
    fi
fi
