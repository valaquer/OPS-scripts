#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Workbench
# @raycast.mode silent

# Workbench dev server runs on Mac Mini. Safari on iMac hits it over LAN.

SSH_KEY="/Users/deepak-macmini/.ssh/id_hanover"
MINI_USER="deepak-macmini"
MINI_HOST="192.168.0.186"
MINI_URL="http://${MINI_HOST}:51740"

# Kill any local iMac process on :51740 (prevent shadowing)
lsof -ti :51740 | xargs kill -9 2>/dev/null || true

# Kill any existing Workbench process on Mini
ssh -i "$SSH_KEY" -o ConnectTimeout=3 "${MINI_USER}@${MINI_HOST}" \
    "lsof -ti :51740 | xargs kill -9 2>/dev/null || true" 2>/dev/null

# Start Workbench dev server on Mini via SSH
ssh -i "$SSH_KEY" -o ConnectTimeout=3 "${MINI_USER}@${MINI_HOST}" \
    "nohup bash -c 'cd /Users/deepak-macmini/honeybloom/library/workbench && PATH=/opt/homebrew/bin:\$PATH exec npm run dev' > /tmp/workbench-dev.log 2>&1 &" 2>/dev/null

# Wait for Mini's server to be reachable from iMac
WAIT=0
while [ $WAIT -lt 30 ]; do
    curl -s -o /dev/null "$MINI_URL" 2>/dev/null && break
    sleep 1
    WAIT=$((WAIT + 1))
done

open -a Safari "${MINI_URL}/styleguide"
open -a Safari "${MINI_URL}/bavaria"
open -a Safari "${MINI_URL}/lisbon"
