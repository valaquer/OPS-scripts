#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Bavaria
# @raycast.mode silent

if ! curl -s -o /dev/null http://localhost:51740 2>/dev/null; then
    lsof -ti :51740 | xargs kill -9 2>/dev/null || true
    nohup bash -c 'cd /Users/d.patnaik/honeybloom/library/workbench && exec npm run dev' > /tmp/workbench-dev.log 2>&1 &
    echo $! > /tmp/workbench.pid
    WAIT=0
    while [ $WAIT -lt 30 ]; do
        curl -s -o /dev/null http://localhost:51740 2>/dev/null && break
        sleep 1
        WAIT=$((WAIT + 1))
    done
fi
open -a Safari http://localhost:51740/bavaria
