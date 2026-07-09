#!/bin/bash
set -euo pipefail

TITLE="${1:-}"
BODY="${2:-}"

if [ -z "$TITLE" ]; then
  echo "Usage: write-to-notes.sh \"title\" \"body\""
  echo "Body supports plain text with newlines (converted to <br> for Notes)."
  exit 1
fi

# Convert newlines to <br> for Notes HTML body
BODY=$(printf '%s' "$BODY" | sed 's/$/<br>/g')

# Base64 encode to survive all quoting layers
B64_TITLE=$(printf '%s' "$TITLE" | base64)
B64_BODY=$(printf '%s' "$BODY" | base64)

IMAC_SSH="ssh -i /Users/deepak-macmini/.ssh/id_mini d.patnaik@192.168.0.153"

# Write a temp AppleScript on iMac, execute it, delete it — avoids quote hell
IMAC_TMP="/tmp/write-to-notes-$$.scpt"
RESULT=$($IMAC_SSH "
  TITLE=\$(printf '%s' '$B64_TITLE' | base64 -d)
  BODY=\$(printf '%s' '$B64_BODY' | base64 -d)
  cat > $IMAC_TMP <<'SCPT'
on run argv
  set theTitle to item 1 of argv
  set theBody to item 2 of argv
  tell application \"Notes\"
    tell account \"iCloud\"
      make new note at folder \"Notes\" with properties {name:theTitle, body:theBody}
    end tell
  end tell
end run
SCPT
  osascript $IMAC_TMP \"\$TITLE\" \"\$BODY\"
  rm -f $IMAC_TMP
" 2>&1)

if [[ "$RESULT" == *"note id"* ]]; then
  echo "Note created: $TITLE"
else
  echo "Error creating note: $RESULT"
  exit 1
fi
