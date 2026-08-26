#!/bin/bash
set -uo pipefail

ENV_FILE="/Users/deepak-macmini/honeybloom/library/bavaria-app/.env.local"
LOG_FILE="/var/tmp/bavaria-staging-keepalive.log"
STATUS_FILE="/var/tmp/bavaria-staging-keepalive-status"

if [ ! -f "$ENV_FILE" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR .env.local not found" >> "$LOG_FILE"
    echo "FAILED $(date -u +%Y-%m-%dT%H:%M:%SZ) .env.local not found" > "$STATUS_FILE"
    exit 1
fi

source "$ENV_FILE"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "${SUPABASE_URL}/storage/v1/bucket" \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    --connect-timeout 10 \
    --max-time 30)
CURL_EXIT=$?

if [ "$CURL_EXIT" -ne 0 ] || [ "$STATUS" = "000" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) FAILED curl_exit=$CURL_EXIT status=$STATUS -- project unreachable" >> "$LOG_FILE"
    echo "FAILED $(date -u +%Y-%m-%dT%H:%M:%SZ) curl_exit=$CURL_EXIT status=$STATUS" > "$STATUS_FILE"
    exit 1
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) keepalive status=$STATUS" >> "$LOG_FILE"
echo "OK $(date -u +%Y-%m-%dT%H:%M:%SZ) status=$STATUS" > "$STATUS_FILE"
exit 0
