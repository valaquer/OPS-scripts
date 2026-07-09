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

# iMac has Safari with Instagram login — SSH for cookie-dependent operations
IMAC_SSH="ssh -i /Users/deepak-macmini/.ssh/id_mini d.patnaik@192.168.0.153"
IMAC_YTDLP="~/bin/yt-dlp"

# Combined SSH call: extract shortcode + download in one session, clean up iMac /tmp
IMAC_TMP="/tmp/ig-reel-dl-$$"
RESULT=$($IMAC_SSH "
  set -e
  SHORTCODE=\$($IMAC_YTDLP --cookies-from-browser safari --print id '$URL' 2>/dev/null) || true
  if [ -z \"\$SHORTCODE\" ]; then
    echo 'ERROR: Could not extract shortcode'
    exit 1
  fi
  mkdir -p $IMAC_TMP
  $IMAC_YTDLP --cookies-from-browser safari --merge-output-format mp4 --output '$IMAC_TMP/raw.mp4' '$URL' >&2
  echo \"\$SHORTCODE\"
" 2>&1) || true

SHORTCODE=$(echo "$RESULT" | tail -1)
if [ -z "${SHORTCODE:-}" ] || [[ "$SHORTCODE" == ERROR:* ]]; then
  echo "Error: Could not extract shortcode from $URL"
  echo "$RESULT"
  exit 1
fi

OUTPUT_PATH="$OUTPUT_DIR/${SHORTCODE}.mp4"

if [ -f "$OUTPUT_PATH" ]; then
  echo "Already exists: $OUTPUT_PATH"
  $IMAC_SSH "rm -rf $IMAC_TMP" 2>/dev/null || true
  exit 0
fi

# SCP raw file from iMac, then clean up iMac /tmp
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"; '"$IMAC_SSH"' "rm -rf '"$IMAC_TMP"'" 2>/dev/null || true' EXIT

scp -i /Users/deepak-macmini/.ssh/id_mini "d.patnaik@192.168.0.153:$IMAC_TMP/raw.mp4" "$TMPDIR/raw.mp4"

# Re-encode locally on Mini (H.264 for QuickTime compatibility)
ffmpeg -i "$TMPDIR/raw.mp4" -c:v libx264 -crf 18 -c:a aac -movflags +faststart -y "$OUTPUT_PATH" 2>/dev/null

echo "Downloaded to: $OUTPUT_PATH"