#!/bin/bash
# Bidirectional postal-mail sync between Mini and iMac via Unison
# Runs via launchd every 5s

LOCAL_DIR="/Users/deepak-macmini/honeybloom/felix/postal-mail"
REMOTE_HOST="192.168.0.153"
REMOTE_USER="d.patnaik"
REMOTE_DIR="ssh://${REMOTE_USER}@${REMOTE_HOST}/postal-mail"
SSH_KEY="/Users/deepak-macmini/.ssh/id_mini"
SSH_OPTS="-i $SSH_KEY -o ConnectTimeout=3 -o StrictHostKeyChecking=no"

PATH=/opt/homebrew/bin:$PATH
export UNISONLOCALHOSTNAME=honeybloom-mini

run_sync() {
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
    -servercmd "env UNISONLOCALHOSTNAME=honeybloom-display /opt/homebrew/bin/unison" \
    -sshargs "$SSH_OPTS"
}

run_sync
exit_code=$?

if [ $exit_code -eq 3 ]; then
  echo "$(date): Archive inconsistency (exit 3), clearing archives and retrying" >&2

  rm -f "$HOME/Library/Application Support/Unison/"ar* "$HOME/Library/Application Support/Unison/"fp*

  ssh $SSH_OPTS "${REMOTE_USER}@${REMOTE_HOST}" \
    'rm -f "$HOME/Library/Application Support/Unison/"ar* "$HOME/Library/Application Support/Unison/"fp*'

  run_sync
  exit $?
fi

exit $exit_code
