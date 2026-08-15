#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title leadership-team
# @raycast.mode silent

HUDDLE_URL="http://localhost:51820/api/huddle"
PARTICIPANTS='["fable","felix","rio","dante","hana","kirby","juno"]'

curl -s -X POST "$HUDDLE_URL" \
    -H "Content-Type: application/json" \
    -d "{\"action\":\"start\",\"host\":\"fable\",\"participants\":$PARTICIPANTS,\"project\":\"Honeybloom\"}" \
    > /dev/null 2>&1
