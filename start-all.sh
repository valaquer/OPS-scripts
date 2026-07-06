#!/bin/bash

# NOTE: This is NOT the Raycast-active copy.
# Raycast reads from iMac: /Users/d.patnaik/raycast-scripts/start-all.sh
# That copy uses iMac LAUNCH path + LAN IP for huddle API.
# Update BOTH copies when changing this script.

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Start
# @raycast.mode silent

# Opens 24 teammates (staggered) + 6 auto-huddles.
# All on Mac Mini. 7 batches with 60s gaps to avoid API rate limits.
# Each group's huddle starts as soon as its batch lands.

LAUNCH="/Users/deepak-macmini/honeybloom/library/scripts/kitty-open-teammate.sh"
HUDDLE_URL="http://localhost:51730/api/huddle"

open_tab() {
    # Skip if teammate already has an active Kitty tab
    if kitten @ ls 2>/dev/null | grep -q "\"title\": \"$1\""; then
        return
    fi
    "$LAUNCH" --solo "$1" &
}

start_huddle() {
    local host="$1"
    shift
    local participants="[$(printf '"%s",' "$@" | sed 's/,$//')]"
    curl -s -X POST "$HUDDLE_URL" \
        -H "Content-Type: application/json" \
        -d "{\"action\":\"start\",\"host\":\"$host\",\"participants\":$participants}" \
        > /dev/null 2>&1 &
}

# --- Batch 1: TBD, Finance, Credentials, UI/UX, Analyst ---
open_tab gunnar
open_tab felix
open_tab burt
open_tab andrea
open_tab jeh
wait
sleep 60

# --- Batch 2: Ops ---
open_tab rio
open_tab chica
open_tab natalie
wait
start_huddle rio rio chica natalie
sleep 60

# --- Batch 3: Studio ---
open_tab dante
open_tab sierra
open_tab cindy
wait
start_huddle dante dante sierra cindy
sleep 60

# --- Batch 4: Chat Engine ---
open_tab hana
open_tab wyatt
open_tab klara
wait
start_huddle hana hana wyatt klara
sleep 60

# --- Batch 5: Engineering ---
open_tab guru
open_tab daksh
open_tab ines
wait
start_huddle guru guru daksh ines
sleep 60

# --- Batch 6: Growth ---
open_tab kirby
open_tab ananya
open_tab nora
wait
start_huddle kirby kirby ananya nora
sleep 60

# --- Batch 7: Intel, Skills ---
open_tab juno
open_tab pike
open_tab jukka
open_tab claire
wait
start_huddle juno juno pike jukka

wait
