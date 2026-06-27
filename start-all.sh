#!/bin/bash

# NOTE: This is NOT the Raycast-active copy.
# Raycast reads from iMac: /Users/d.patnaik/raycast-scripts/start-all.sh
# That copy uses iMac LAUNCH path + LAN IP for huddle API.
# Update BOTH copies when changing this script.

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Start
# @raycast.mode silent

# Opens 21 teammates + 6 auto-huddles (pairs/trios/groups).
# All on Mac Mini (Jun 26 2026 update).

LAUNCH="/Users/deepak-macmini/honeybloom/library/scripts/kitty-open-teammate.sh"

open_tab() {
    "$LAUNCH" --solo "$1" &
}

# --- Individuals (no auto-huddle) ---

# Strategy
open_tab gunnar

# Finance
open_tab felix

# UI & UX
open_tab andrea

# Knowledge
open_tab claire

# Credential Security
open_tab burt

# Cohen
open_tab cohen

# --- Groups (auto-huddle after tabs open) ---

# Ops
open_tab rio
open_tab chica
open_tab natalie

# Visual + Chat AI
open_tab dante
open_tab sierra
open_tab cindy

# Visual Pipeline
open_tab hana
open_tab wyatt
open_tab klara

# Product Engineering (Prague)
open_tab guru
open_tab daksh
open_tab ines

# Growth
open_tab kirby
open_tab ananya
open_tab nora

# R&D
open_tab juno
open_tab pike

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

wait
