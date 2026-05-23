#!/bin/bash
# Red Mist — QA toggle for principal execution lock
# Usage: red-mist plan <teammate>  — lock to plan mode
#        red-mist build <teammate> — unlock to build mode
#        red-mist status           — show all active flags

ACTION="$1"
TEAMMATE="$2"

case "$ACTION" in
  plan)
    if [ -z "$TEAMMATE" ]; then
      echo "Usage: red-mist plan <teammate>" >&2
      exit 1
    fi
    echo "plan" > "/tmp/red-mist-${TEAMMATE}"
    echo "RED MIST: ${TEAMMATE} locked to plan mode."
    ;;
  build)
    if [ -z "$TEAMMATE" ]; then
      echo "Usage: red-mist build <teammate>" >&2
      exit 1
    fi
    echo "build" > "/tmp/red-mist-${TEAMMATE}"
    /opt/homebrew/bin/kitten @ send-text --match "title:(?i)${TEAMMATE}" "You are now unlocked.\n"
    echo "RED MIST: ${TEAMMATE} unlocked to build mode."
    ;;
  status)
    echo "RED MIST status:"
    for f in /tmp/red-mist-*; do
      if [ -f "$f" ]; then
        name=$(basename "$f" | sed 's/red-mist-//')
        mode=$(cat "$f")
        echo "  ${name}: ${mode}"
      fi
    done
    if ! ls /tmp/red-mist-* >/dev/null 2>&1; then
      echo "  No flags set. All principals in default plan mode."
    fi
    ;;
  *)
    echo "Usage: red-mist {plan|build|status} [teammate]" >&2
    exit 1
    ;;
esac
