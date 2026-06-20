#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Aether
# @raycast.mode silent

SSH_CMD="ssh -T -o BatchMode=yes -i /Users/d.patnaik/.ssh/id_hanover -o StrictHostKeyChecking=no -o ConnectTimeout=3 deepak-macmini@192.168.0.186"

# Check if Aether is already running on Mini
if curl -s -o /dev/null --max-time 3 http://192.168.0.186:51730 2>/dev/null; then
    open -a Safari http://192.168.0.186:51730
    exit 0
fi

# Kill any stale vite process on Mini
$SSH_CMD "pkill -f 'vite dev' 2>/dev/null || true"
sleep 1

# Start Aether on Mini
$SSH_CMD "cd /Users/deepak-macmini/honeybloom/library/aether-app && nohup npx vite dev --port 51730 --host 0.0.0.0 > /tmp/aether.log 2>&1 &"

# Wait for it to come up
WAIT=0
while [ $WAIT -lt 30 ]; do
    curl -s -o /dev/null --max-time 2 http://192.168.0.186:51730 2>/dev/null && break
    sleep 1
    WAIT=$((WAIT + 1))
done

open -a Safari http://192.168.0.186:51730
