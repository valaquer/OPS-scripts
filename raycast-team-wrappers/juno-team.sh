#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title juno-team
# @raycast.mode silent

ssh -o BatchMode=yes -o ConnectTimeout=5 -i ~/.ssh/id_hanover deepak-macmini@192.168.0.186     "bash /Users/deepak-macmini/honeybloom/library/scripts/open-team.sh juno" &
