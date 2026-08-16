#!/bin/bash
set -euo pipefail

ENV_FILE="/Users/deepak-macmini/honeybloom/library/bavaria-app/.env.local"
LOG_FILE="/var/tmp/bavaria-staging-keepalive.log"

if [ ! -f "$ENV_FILE" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR .env.local not found" >> "$LOG_FILE"
    exit 1
fi

source "$ENV_FILE"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "${SUPABASE_URL}/rest/v1/" \
    -H "apikey: ${SUPABASE_ANON_KEY}" \
    --connect-timeout 10 \
    --max-time 30)

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) keepalive status=$STATUS" >> "$LOG_FILE"

if [ "$STATUS" = "000" ]; then
    exit 1
fi
exit 0
