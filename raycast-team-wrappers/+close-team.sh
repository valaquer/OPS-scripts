#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title +close-team
# @raycast.mode compact
# @raycast.argument1 { "type": "text", "placeholder": "leader name (e.g. rio)" }

ssh -o BatchMode=yes -o ConnectTimeout=5 -i ~/.ssh/id_hanover deepak-macmini@192.168.0.186 \
    "bash /Users/deepak-macmini/honeybloom/library/scripts/close-team.sh $1"
