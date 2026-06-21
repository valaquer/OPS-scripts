#!/bin/bash

# NOTE: This is NOT the Raycast-active copy.
# Raycast reads from iMac: /Users/d.patnaik/raycast-scripts/start-all.sh
# That copy uses iMac LAUNCH path + LAN IP for huddle API.
# Update BOTH copies when changing this script.

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Start
# @raycast.mode silent

# Opens 14 teammates + 9 auto-huddles (5 pairs + 4 solos).
# All on Mac Mini (Jun 21 2026 restructure).

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

# --- Groups (auto-huddle after tabs open) ---

# Ops
open_tab rio
open_tab chica

# Visual + Chat AI
open_tab dante
open_tab sierra

# Product Engineering (Prague)
open_tab guru
open_tab daksh

# Growth
open_tab kirby
open_tab ananya

# R&D + Knowledge
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

start_huddle gunnar gunnar
start_huddle felix felix
start_huddle andrea andrea
start_huddle claire claire
start_huddle rio rio chica
start_huddle dante dante sierra
start_huddle guru guru daksh
start_huddle kirby kirby ananya
start_huddle juno juno pike

wait
