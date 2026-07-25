#!/bin/bash
# Hourly auto-commit for honeybloom-vault repo.
# Commits all changes and pushes to valaquer/honeybloom-vault.

set -euo pipefail

VAULT_DIR="/Users/deepak-macmini/honeybloom"
LOG="/var/tmp/vault-auto-commit.log"

cd "$VAULT_DIR"

if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
    exit 0
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)

git add -A 2>>"$LOG"
git commit -m "Auto-commit $TIMESTAMP" --no-gpg-sign 2>>"$LOG" || {
    echo "$(date): FAILED -- git commit failed" >> "$LOG"
    exit 1
}

GIT_SSH_COMMAND="ssh -i /Users/deepak-macmini/.ssh/id_mini -o StrictHostKeyChecking=no" git push origin main 2>>"$LOG" || {
    echo "$(date): FAILED -- git push failed" >> "$LOG"
    exit 1
}

echo "$(date): vault auto-commit done" >> "$LOG"
