#!/bin/bash
# PostResponse hook: capture terminal chatter (plain model text, no MCP) to Facade.
# Reads response text from stdin, determines teammate from CWD, POSTs to /api/tool-activity.
# Room is pinned to direct room — terminal chatter is Boss-only, no huddle fan-out.

RESPONSE_TEXT=$(cat)
[[ -z "$RESPONSE_TEXT" ]] && exit 0

# Junk filter: ≤10 words and contains sit-out keywords → skip
WORD_COUNT=$(echo "$RESPONSE_TEXT" | wc -w | tr -d ' ')
if [[ "$WORD_COUNT" -le 10 ]]; then
  if echo "$RESPONSE_TEXT" | grep -qiE '[[:<:]](queue|acknowledged|holding|waiting|standing|token)[[:>:]]|nothing to add'; then
    exit 0
  fi
fi

TEAMMATE=$(basename "$PWD")

curl -s -o /dev/null -X POST http://localhost:51730/api/tool-activity \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg sender "$TEAMMATE" --arg room "direct-${TEAMMATE}" --arg body "$RESPONSE_TEXT" '{sender: $sender, room: $room, body: $body}')" &

exit 0
