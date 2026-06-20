#!/bin/bash
# Calendar auto-wake — 6 AM daily via launchd.
# 1. Always wake Felix (daily briefing duty)
# 2. Check both calendars, wake teammates with events due today
# Only runs if Kitty is already running (socket guard).

KITTEN="/opt/homebrew/bin/kitten"
LAUNCHER="/Users/deepak-macmini/honeybloom/library/scripts/kitty-open-teammate.sh"
OFFICE_CAL="/Users/deepak-macmini/honeybloom/library/office-calendar.json"
PERSONAL_CAL="/Users/deepak-macmini/honeybloom/library/personal-calendar.json"

# Socket guard — exit silently if no Kitty
SOCKET=""
for path in /tmp/honeybloom-kitty-*.sock; do
    [ -S "$path" ] || continue
    SOCKET="unix:$path"
    break
done
[ -z "$SOCKET" ] && exit 0

# Get already-open teammates
OPEN_TEAMMATES=$($KITTEN @ --to "$SOCKET" ls 2>/dev/null | /usr/bin/python3 -c "
import json, sys
data = json.load(sys.stdin)
for os_win in data:
    for tab in os_win.get('tabs', []):
        for window in tab.get('windows', []):
            val = window.get('user_vars', {}).get('teammate', '')
            if val:
                print(val)
" 2>/dev/null)

wake_teammate() {
    local name="$1"
    if echo "$OPEN_TEAMMATES" | grep -qx "$name"; then
        return  # already open
    fi
    "$LAUNCHER" --solo "$name" 2>/dev/null
}

# 1. Always wake Felix
wake_teammate "felix"

# 2. Check both calendars for events due today
TEAMMATES_TO_WAKE=$(python3 -c "
import json, sys, os
from datetime import date, timedelta

today = date.today()
to_wake = set()

for cal_path in ['$OFFICE_CAL', '$PERSONAL_CAL']:
    if not os.path.isfile(cal_path):
        continue
    try:
        with open(cal_path) as f:
            cal = json.load(f)
    except:
        continue

    for event in cal.get('events', []):
        eid = event.get('id', '')
        targets = event.get('targets', [])
        schedule = event.get('schedule', {})
        advance = event.get('advance_days', 0)
        stype = schedule.get('type', '')

        if not all([eid, targets, stype]):
            continue

        check_dates = [today]
        if advance > 0:
            check_dates.append(today + timedelta(days=advance))

        fires = False
        for d in check_dates:
            if stype == 'weekly':
                if d.strftime('%A').lower() == schedule.get('day', '').lower():
                    fires = True
            elif stype == 'monthly':
                if d.day == schedule.get('day_of_month', 0):
                    fires = True
            elif stype == 'biweekly':
                anchor = schedule.get('anchor', '')
                day_name = schedule.get('day', '').lower()
                if anchor and d.strftime('%A').lower() == day_name:
                    delta = (d - date.fromisoformat(anchor)).days
                    if delta >= 0 and delta % 14 == 0:
                        fires = True
            elif stype == 'interval':
                anchor = schedule.get('anchor', '')
                interval = schedule.get('days', 0)
                if anchor and interval > 0:
                    delta = (d - date.fromisoformat(anchor)).days
                    if delta >= 0 and delta % interval == 0:
                        fires = True
            elif stype == 'once':
                if d.isoformat() == schedule.get('date', ''):
                    fires = True
            if fires:
                break

        if fires:
            if 'all' in targets:
                # Can't wake 'all' — skip, these fire via prompt injection... wait, no.
                # 'all' targets don't map to specific teammates to wake.
                # Skip 'all' — those teammates will get the reminder when they wake naturally.
                pass
            else:
                for t in targets:
                    to_wake.add(t)

for name in sorted(to_wake):
    print(name)
" 2>/dev/null)

# Wake each teammate with events due today
for name in $TEAMMATES_TO_WAKE; do
    wake_teammate "$name"
done
