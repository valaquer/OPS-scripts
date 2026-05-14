#!/bin/bash
# SessionStart hook: record session start timestamp and clear stale state.
SUBDIR=$(basename "$PWD")
date +%s > "/tmp/.claude-session-start-${SUBDIR}"
rm -f "/tmp/.claude-context-${SUBDIR}"
