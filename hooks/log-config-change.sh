#!/bin/bash
# Log all Claude Code config changes to a local file.
# Registered as ConfigChange hook, matcher "*".
# Never blocks — exit 0 always.

LOG="/tmp/claude-config-changes.log"
TEAMMATE=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
INPUT=$(cat)

echo "[$TIMESTAMP] [$TEAMMATE] $INPUT" >> "$LOG"
exit 0
