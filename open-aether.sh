#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Aether
# @raycast.mode silent

MINI_IP="192.168.0.186"
AETHER_URL="http://${MINI_IP}:51730"
SSH_CMD="ssh -T -o BatchMode=yes -i /Users/d.patnaik/.ssh/id_hanover -o StrictHostKeyChecking=no -o ConnectTimeout=3 deepak-macmini@${MINI_IP}"

# Check if Aether is already running
if curl -s -o /dev/null --max-time 3 "$AETHER_URL" 2>/dev/null; then
    open -a Safari "$AETHER_URL"
    exit 0
fi

# Kill any stale process on Mini (vite + mongod lock)
$SSH_CMD "pkill -f 'vite.*aether' 2>/dev/null; pkill -f 'node.*aether' 2>/dev/null; pkill -f 'mongod.*aether-app' 2>/dev/null; rm -f /Users/deepak-macmini/honeybloom/library/aether-app/db/mongod.lock; true"
sleep 1

# Start Aether on Mini with full PATH
$SSH_CMD "export PATH=/opt/homebrew/bin:/usr/local/bin:\$PATH; cd /Users/deepak-macmini/honeybloom/library/aether-app && nohup npm run dev > /tmp/aether.log 2>&1 &"

# Wait for it to come up (up to 30s)
WAIT=0
while [ $WAIT -lt 30 ]; do
    curl -s -o /dev/null --max-time 2 "$AETHER_URL" 2>/dev/null && break
    sleep 1
    WAIT=$((WAIT + 1))
done

open -a Safari "$AETHER_URL"
