#!/bin/bash
# Sync screenshots from iMac to Mini (one-way pull)
# Runs via launchd every 5s

IMAC_USER="d.patnaik"
IMAC_IP="192.168.0.153"
SSH_KEY="/Users/deepak-macmini/.ssh/id_mini"
LOCAL_DIR="/Users/deepak-macmini/screenshots/"

rsync -a --delete \
  -e "ssh -i $SSH_KEY -o ConnectTimeout=3 -o StrictHostKeyChecking=no" \
  "${IMAC_USER}@${IMAC_IP}:~/screenshots/" \
  "$LOCAL_DIR" 2>/dev/null
