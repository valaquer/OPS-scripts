#!/bin/bash
# PostResponse hook: capture terminal chatter (plain model text, no MCP) to Facade.
# Reads response text from stdin, determines teammate from CWD, POSTs to /api/tool-activity.
# Room is pinned to direct room — terminal chatter is Boss-only, no huddle fan-out.

RESPONSE_TEXT=$(cat)
[[ -z "$RESPONSE_TEXT" ]] && exit 0

TEAMMATE=$(basename "$PWD")

curl -s -o /dev/null -X POST http://localhost:51730/api/tool-activity \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg sender "$TEAMMATE" --arg room "direct-${TEAMMATE}" --arg body "$RESPONSE_TEXT" '{sender: $sender, room: $room, body: $body}')" &

exit 0
