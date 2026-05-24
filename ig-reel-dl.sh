#!/bin/bash
set -euo pipefail

URL="${1:-}"
if [ -z "$URL" ]; then
  echo "Usage: ig-reel-dl.sh <instagram-reel-url>"
  echo "Example: ig-reel-dl.sh https://www.instagram.com/p/DYg7gtolQ7z/"
  exit 1
fi

OUTPUT_DIR="$HOME/honeybloom/sierra/reels"
mkdir -p "$OUTPUT_DIR"

SHORTCODE=$(yt-dlp --cookies-from-browser safari --print id "$URL" 2>/dev/null) || true
if [ -z "${SHORTCODE:-}" ]; then
  echo "Error: Could not extract shortcode from $URL"
  exit 1
fi

OUTPUT_PATH="$OUTPUT_DIR/${SHORTCODE}.mp4"

if [ -f "$OUTPUT_PATH" ]; then
  echo "Already exists: $OUTPUT_PATH"
  exit 0
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

yt-dlp \
  --cookies-from-browser safari \
  --merge-output-format mp4 \
  --output "$TMPDIR/raw.mp4" \
  "$URL"

ffmpeg -i "$TMPDIR/raw.mp4" -c:v libx264 -crf 18 -c:a aac -movflags +faststart -y "$OUTPUT_PATH" 2>/dev/null

echo "Downloaded to: $OUTPUT_PATH"