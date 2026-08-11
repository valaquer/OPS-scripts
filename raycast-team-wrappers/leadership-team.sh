#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title leadership-team
# @raycast.mode silent

HUDDLE_URL="http://localhost:51730/api/huddle"
PARTICIPANTS='["gunnar","fable","felix","rio","dante","hana","guru","kirby","juno"]'

curl -s -X POST "$HUDDLE_URL" \
    -H "Content-Type: application/json" \
    -d "{\"action\":\"start\",\"host\":\"gunnar\",\"participants\":$PARTICIPANTS}" \
    > /dev/null 2>&1
