#!/bin/bash
# Sync postal mail from iMac to Felix's directory on Mini (one-way pull, non-destructive)
# Runs via launchd every 5s

IMAC_USER="d.patnaik"
IMAC_IP="192.168.0.153"
SSH_KEY="/Users/deepak-macmini/.ssh/id_mini"
LOCAL_DIR="/Users/deepak-macmini/honeybloom/felix/postal-mail/"

# iMac → Mini (Boss puts file, Felix sees it)
rsync -a \
  -e "ssh -i $SSH_KEY -o ConnectTimeout=3 -o StrictHostKeyChecking=no" \
  "${IMAC_USER}@${IMAC_IP}:~/postal-mail/" \
  "$LOCAL_DIR" 2>/dev/null

# Mini → iMac (Felix puts file, Boss sees it)
rsync -a --delete \
  -e "ssh -i $SSH_KEY -o ConnectTimeout=3 -o StrictHostKeyChecking=no" \
  "$LOCAL_DIR" \
  "${IMAC_USER}@${IMAC_IP}:~/postal-mail/" 2>/dev/null
