#!/bin/bash
# Reminder agent — checks all REMINDERS.md files, fires /api/pulse for matches
# Runs via launchd every 60 seconds

set -uo pipefail

HONEYBLOOM="/Users/deepak-macmini/honeybloom"
ORG_FILE="$HONEYBLOOM/library/ORG.md"
STATE_DIR="$HONEYBLOOM/library/aether/reminders-state"
AETHER_URL="http://localhost:51730"

# Current time components
NOW_HOUR=$(date +%H)
NOW_MIN=$(date +%M)
NOW_DOM=$(date +%d)        # day of month (01-31)
NOW_DOW=$(date +%a | tr '[:upper:]' '[:lower:]')  # mon, tue, wed, ...

# Extract teammate names from ORG.md Roster section
get_teammates() {
    grep '^Teammate:' "$ORG_FILE" | sed 's/^Teammate: *//' | tr '[:upper:]' '[:lower:]'
}

# Check if a schedule matches right now
schedule_matches() {
    local schedule="$1" time_field="$2"
    local sched_hour="${time_field%%:*}"
    local sched_min="${time_field##*:}"

    # Time must match
    [[ "$sched_hour" == "$NOW_HOUR" && "$sched_min" == "$NOW_MIN" ]] || return 1

    # Check schedule type
    if [[ "$schedule" == "daily" ]]; then
        return 0
    fi

    # Day of month (e.g. "30th", "1st", "15th")
    local dom_num="${schedule%%[a-z]*}"
    if [[ "$dom_num" =~ ^[0-9]+$ ]]; then
        local now_dom_num=$((10#$NOW_DOM))
        [[ "$dom_num" -eq "$now_dom_num" ]] && return 0
        return 1
    fi

    # Day names (e.g. "mon,wed,fri" or "mon")
    IFS=',' read -ra days <<< "$schedule"
    for day in "${days[@]}"; do
        [[ "${day// /}" == "$NOW_DOW" ]] && return 0
    done

    return 1
}

# Generate a short hash for a reminder line (for unique pending file names)
line_hash() {
    echo -n "$1" | md5 -q | head -c 8
}

# Check if Facade is running
if ! curl -s -o /dev/null --max-time 2 "$AETHER_URL/api/pulse"; then
    exit 0  # Facade not up, try next minute
fi

# Process each teammate
while IFS= read -r teammate; do
    [[ -z "$teammate" ]] && continue
    reminders_file="$HONEYBLOOM/$teammate/REMINDERS.md"
    [[ -f "$reminders_file" ]] || continue

    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" == \#* ]] && continue

        # Parse: {schedule} {HH:MM} | {reason}
        if [[ "$line" =~ ^([^|]+)\|(.+)$ ]]; then
            local_sched="${BASH_REMATCH[1]}"
            reason="${BASH_REMATCH[2]}"
            reason="${reason## }"  # trim leading space
            reason="${reason%% }"  # trim trailing space

            # Split schedule part into schedule and time
            local_sched="${local_sched%% }"  # trim trailing
            local_sched="${local_sched## }"  # trim leading
            time_field="${local_sched##* }"  # last word = HH:MM
            schedule="${local_sched% *}"     # everything before = schedule

            hash=$(line_hash "$schedule $time_field $reason")
            pending_file="$STATE_DIR/${teammate}-${hash}.pending"

            if [[ -f "$pending_file" ]]; then
                # Already pending — re-pulse to keep it alive
                curl -s -o /dev/null --max-time 3 -X POST "$AETHER_URL/api/pulse" \
                    -H 'Content-Type: application/json' \
                    -d "{\"teammate\":\"$teammate\",\"reason\":\"$reason\"}"
            elif schedule_matches "$schedule" "$time_field"; then
                # New match — create pending and fire
                printf 'fired:%s\nreason:%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$reason" > "$pending_file"
                curl -s -o /dev/null --max-time 30 -X POST "$AETHER_URL/api/pulse" \
                    -H 'Content-Type: application/json' \
                    -d "{\"teammate\":\"$teammate\",\"reason\":\"$reason\"}"
            fi
        fi
    done < "$reminders_file"
done <<< "$(get_teammates)"
