#!/bin/bash
# Bear note change watcher -- polls iMac Bear DB, posts notifications to Aether
# Write constraint: reads via SQLite, writes via ssh imac "open 'bear://x-callback-url/...'" ONLY

IMAC_SSH="ssh -o ControlMaster=auto -o ControlPath=/tmp/bear-watcher-ssh -o ControlPersist=300 -o ConnectTimeout=3 -o BatchMode=yes imac"
IMAC_BEAR_DB="~/Library/Group\\ Containers/9K33E3U3T4.net.shinyfrog.bear/Application\\ Data/database.sqlite"
AETHER_URL="http://localhost:51820"
POLL_INTERVAL=2

declare -A LAST_MODS

query_mods() {
	$IMAC_SSH "sqlite3 $IMAC_BEAR_DB \"SELECT n.ZUNIQUEIDENTIFIER, n.ZMODIFICATIONDATE, n.ZTITLE, group_concat(t.ZTITLE, ',') FROM ZSFNOTE n LEFT JOIN Z_5TAGS jt ON jt.Z_5NOTES = n.Z_PK LEFT JOIN ZSFNOTETAG t ON t.Z_PK = jt.Z_13TAGS WHERE n.ZTRASHED = 0 GROUP BY n.ZUNIQUEIDENTIFIER HAVING group_concat(t.ZTITLE, ',') IS NOT NULL\"" 2>/dev/null
}

resolve_room() {
	local tags="$1"

	for project in manhattan onyx rev spark lighthouse honeybloom; do
		if echo ",$tags," | grep -qi ",${project},"; then
			local rooms_json
			rooms_json=$(curl -s "${AETHER_URL}/api/rooms" 2>/dev/null) || continue
			local room
			room=$(echo "$rooms_json" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for h in data.get('huddles', []):
        if '${project}' in h.get('id', '').lower():
            print(h['id']); break
except: pass
" 2>/dev/null)
			if [ -n "$room" ]; then echo "$room"; return; fi
		fi
	done

	for team in ops studio re-team marketing intel finance; do
		if echo ",$tags," | grep -qi ",${team},"; then
			local host=""
			case "$team" in
				ops) host="rio" ;;
				studio) host="dante" ;;
				re-team) host="hana" ;;
				marketing) host="kirby" ;;
				intel) host="juno" ;;
				finance) host="felix" ;;
			esac
			if [ -n "$host" ]; then
				local rooms_json
				rooms_json=$(curl -s "${AETHER_URL}/api/rooms" 2>/dev/null) || continue
				local room
				room=$(echo "$rooms_json" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for h in data.get('huddles', []):
        if 'huddle-${host}' in h.get('id', ''):
            print(h['id']); break
except: pass
" 2>/dev/null)
				if [ -n "$room" ]; then echo "$room"; return; fi
			fi
		fi
	done

	local names="gunnar fable felix jake rio chica natalie dante sierra cindy hana klara wyatt kirby ananya nora andrea juno pike jukka claire burt jeh"
	for name in $names; do
		if echo ",$tags," | grep -qi ",${name},"; then
			echo "direct-${name}"
			return
		fi
	done
}

while true; do
	sleep "$POLL_INTERVAL"

	RESULT=$(query_mods)
	if [ -z "$RESULT" ]; then continue; fi

	while IFS='|' read -r uid mod title tags; do
		[ -z "$uid" ] && continue
		prev="${LAST_MODS[$uid]}"
		if [ -n "$prev" ] && [ "$mod" != "$prev" ]; then
			room=$(resolve_room "$tags")
			if [ -n "$room" ]; then
				curl -s -X POST "${AETHER_URL}/api/message" \
					-H "Content-Type: application/json" \
					-d "{\"sender\":\"system\",\"body\":\"Bear note changed: ${title}\",\"room\":\"${room}\"}" \
					> /dev/null 2>&1 || true
			fi
		fi
		LAST_MODS[$uid]="$mod"
	done <<< "$RESULT"
done
