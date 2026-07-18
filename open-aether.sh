#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Aether
# @raycast.mode silent

MINI_IP="192.168.0.186"
AETHER_URL="http://${MINI_IP}:51730"
SSH_CMD="ssh -T -o BatchMode=yes -i /Users/d.patnaik/.ssh/id_hanover -o StrictHostKeyChecking=no -o ConnectTimeout=3 deepak-macmini@${MINI_IP}"

# Restart Aether via launchd (kill + auto-revive via KeepAlive)
$SSH_CMD "sudo launchctl kickstart -k system/com.honeybloom.aether; rm -f /Users/deepak-macmini/honeybloom/library/aether-app/db/mongod.lock; true"

# Wait for it to come up (up to 30s)
WAIT=0
while [ $WAIT -lt 30 ]; do
    curl -s -o /dev/null --max-time 2 "$AETHER_URL" 2>/dev/null && break
    sleep 1
    WAIT=$((WAIT + 1))
done

open -a Safari "$AETHER_URL"
