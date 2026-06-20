#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Start
# @raycast.mode silent

# Opens 9 teammates. No auto-huddles — Boss starts huddles manually.
# All on Mac Mini (cryo reduction Jun 17 2026).

LAUNCH="/Users/deepak-macmini/honeybloom/library/scripts/kitty-open-teammate.sh"

open_tab() {
    "$LAUNCH" --solo "$1" &
}

# OPS
open_tab rio
open_tab chica

# Product
open_tab sierra
open_tab daksh

# R&D
open_tab juno

# Growth
open_tab ananya
open_tab andrea

# Knowledge
open_tab claire

# Finance
open_tab felix

wait
