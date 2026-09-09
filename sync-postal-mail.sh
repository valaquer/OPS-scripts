#!/bin/bash
# Bidirectional postal-mail sync between Mini and iMac via Unison
# Runs via launchd every 5s

LOCAL_DIR="/Users/deepak-macmini/honeybloom/felix/postal-mail"
REMOTE_DIR="ssh://d.patnaik@192.168.0.153/postal-mail"

PATH=/opt/homebrew/bin:$PATH

unison "$LOCAL_DIR" "$REMOTE_DIR" \
  -batch -auto -silent -dumbtty \
  -perms 0 -dontchmod \
  -ignore "Name .DS_Store" \
  -ignore "Name .venv*" \
  -ignore "Name .opencode*" \
  -ignore "Name .playwright*" \
  -ignore "Name .claude" \
  -ignore "Name .accounts.json" \
  -ignore "Name .gauth.json" \
  -ignore "Name .mcp.json" \
  -ignore "Name .oauth2*" \
  -servercmd /opt/homebrew/bin/unison \
  -sshargs "-i /Users/deepak-macmini/.ssh/id_mini -o ConnectTimeout=3 -o StrictHostKeyChecking=no" \
  2>/dev/null
