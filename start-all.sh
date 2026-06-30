#!/bin/bash

# NOTE: This is NOT the Raycast-active copy.
# Raycast reads from iMac: /Users/d.patnaik/raycast-scripts/start-all.sh
# That copy uses iMac LAUNCH path + LAN IP for huddle API.
# Update BOTH copies when changing this script.

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Start
# @raycast.mode silent

# Opens 23 teammates (staggered) + 9 auto-huddles.
# All on Mac Mini. 7 batches with 60s gaps to avoid API rate limits.

LAUNCH="/Users/deepak-macmini/honeybloom/library/scripts/kitty-open-teammate.sh"

open_tab() {
    # Skip if teammate already has an active Kitty tab
    if kitten @ ls 2>/dev/null | grep -q "\"title\": \"$1\""; then
        return
    fi
    "$LAUNCH" --solo "$1" &
}

# --- Batch 1: Strategy, Finance, Credentials, Investor, UI/UX ---
open_tab gunnar
open_tab felix
open_tab burt
open_tab cohen
open_tab andrea
wait
sleep 60

# --- Batch 2: Ops ---
open_tab rio
open_tab chica
open_tab natalie
wait
sleep 60

# --- Batch 3: Studio ---
open_tab dante
open_tab sierra
open_tab cindy
wait
sleep 60

# --- Batch 4: Chat Engine ---
open_tab hana
open_tab wyatt
open_tab klara
wait
sleep 60

# --- Batch 5: Engineering ---
open_tab guru
open_tab daksh
open_tab ines
wait
sleep 60

# --- Batch 6: Growth ---
open_tab kirby
open_tab ananya
open_tab nora
wait
sleep 60

# --- Batch 7: Intel, Skills ---
open_tab juno
open_tab pike
open_tab claire
wait

# Auto-huddles for each group
sleep 10

HUDDLE_URL="${FACADE_URL:-http://localhost:51730}/api/huddle"

start_huddle() {
    local host="$1"
    shift
    local participants="[$(printf '"%s",' "$@" | sed 's/,$//')]"
    curl -s -X POST "$HUDDLE_URL" \
        -H "Content-Type: application/json" \
        -d "{\"action\":\"start\",\"host\":\"$host\",\"participants\":$participants}" \
        > /dev/null 2>&1 &
}

start_huddle rio rio chica natalie
start_huddle dante dante sierra cindy
start_huddle hana hana wyatt klara
start_huddle guru guru daksh ines
start_huddle kirby kirby ananya nora
start_huddle juno juno pike

# Solo huddles
start_huddle felix felix
start_huddle burt burt

# Strategy + Cohen
start_huddle gunnar gunnar cohen

wait
