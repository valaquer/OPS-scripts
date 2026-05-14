#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Markwhen
# @raycast.mode silent

if ! curl -s -o /dev/null http://localhost:51730 2>/dev/null; then
    lsof -ti :51730 | xargs kill -9 2>/dev/null || true
    nohup bash -c 'cd /Users/d.patnaik/honeybloom/natalie/Facade && exec npm run dev -- --port 51730' > /tmp/facade-dev.log 2>&1 &
    echo $! > /tmp/facade.pid
    WAIT=0
    while [ $WAIT -lt 30 ]; do
        curl -s -o /dev/null http://localhost:51730 2>/dev/null && break
        sleep 1
        WAIT=$((WAIT + 1))
    done
fi
open -a Safari http://localhost:51730/markwhen-fork.html
