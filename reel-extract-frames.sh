#!/bin/bash
set -euo pipefail

VIDEO="${1:-}"
if [ -z "$VIDEO" ]; then
  echo "Usage: reel-extract-frames.sh <video-path>"
  echo "Extracts structurally sharp frames (I-frames + scene changes) as PNGs."
  exit 1
fi

if [ ! -f "$VIDEO" ]; then
  echo "Error: File not found: $VIDEO"
  exit 1
fi

BASENAME=$(basename "$VIDEO" .mp4)
OUTPUT_DIR="$HOME/honeybloom/sierra/reels/frames/$BASENAME"
mkdir -p "$OUTPUT_DIR"

SCENE_THRESHOLD="${2:-0.3}"

echo "Extracting sharp frames from: $VIDEO"
echo "Output: $OUTPUT_DIR"
echo "Scene threshold: $SCENE_THRESHOLD"

ffmpeg -i "$VIDEO" \
  -vf "select='eq(pict_type,I)+gt(scene,$SCENE_THRESHOLD)',showinfo" \
  -vsync vfr \
  -frame_pts 1 \
  "$OUTPUT_DIR/frame_%04d.png" \
  2>&1 | grep -c "^frame" || true

COUNT=$(ls "$OUTPUT_DIR"/frame_*.png 2>/dev/null | wc -l | tr -d ' ')
echo "Extracted $COUNT frames to $OUTPUT_DIR"
