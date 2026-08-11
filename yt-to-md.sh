#!/bin/bash
set -euo pipefail

# REQ-141: YouTube video -> Markdown file
# Extracts title, description, upload date, and transcript (auto-captions)
# Writes to library/video-summaries/{date}-{video_id}.md

URL="${1:-}"
if [ -z "$URL" ]; then
  echo "Usage: yt-to-md.sh <youtube-url>"
  echo "Example: yt-to-md.sh https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  exit 1
fi

OUTPUT_DIR="$HOME/honeybloom/library/video-summaries"
mkdir -p "$OUTPUT_DIR"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

VIDEO_ID=$(yt-dlp --print id "$URL" 2>/dev/null) || true
TITLE=$(yt-dlp --print title "$URL" 2>/dev/null) || true
UPLOAD_DATE=$(yt-dlp --print upload_date "$URL" 2>/dev/null) || true
DESCRIPTION=$(yt-dlp --print description "$URL" 2>/dev/null) || true

if [ -z "${VIDEO_ID:-}" ]; then
  echo "Error: Could not extract video ID from $URL"
  exit 1
fi

OUTPUT_FILE="$OUTPUT_DIR/${UPLOAD_DATE:-unknown}-${VIDEO_ID}.md"

# Download auto-captions if available
TRANSCRIPT_TEXT=""
yt-dlp --write-auto-sub --sub-lang en --sub-format vtt --skip-download \
  --output "$TMPDIR/sub" "$URL" >/dev/null 2>&1 || true

SUB_FILE=$(ls "$TMPDIR"/*.vtt 2>/dev/null || true)
if [ -n "${SUB_FILE:-}" ] && [ -s "$SUB_FILE" ]; then
  TRANSCRIPT_TEXT=$(awk '
    /^WEBVTT|^Kind:|^Language:/ { next }
    /-->/ { next }
    /^[[:space:]]*$/ { next }
    {
      gsub(/<[^>]*>/, "")
      gsub(/align:[^ ]* ?/, "")
      gsub(/position:[0-9]*% ?/, "")
      gsub(/^[[:space:]]+/, "")
      gsub(/[[:space:]]+$/, "")
      if (length($0) > 0) print
    }
  ' "$SUB_FILE" | awk '!seen[$0]++')
fi

# Write to file
{
  echo "# ${TITLE:-Untitled}"
  echo ""
  echo "URL: $URL"
  echo "Uploaded: ${UPLOAD_DATE:-(unknown)}"
  echo ""
  echo "## Description"
  echo ""
  if [ -n "${DESCRIPTION:-}" ]; then
    echo "$DESCRIPTION"
  else
    echo "(no description available)"
  fi
  echo ""
  echo "## Transcript"
  echo ""
  if [ -n "${TRANSCRIPT_TEXT:-}" ]; then
    echo "$TRANSCRIPT_TEXT"
  else
    echo "(no transcript available)"
  fi
} > "$OUTPUT_FILE"

echo "Written to: $OUTPUT_FILE"
