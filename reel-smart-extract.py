#!/usr/bin/env python3
"""Smart frame extraction — extracts sharp frames from reel videos.

Takes a video, extracts candidate frames via FFmpeg (I-frames + scene detection),
scores each frame using grid-based Laplacian variance, outputs only sharp frames.
"""

import sys
import os
import subprocess
import tempfile
import shutil
import atexit
import argparse
import cv2


def extract_candidates(video_path, tmp_dir, scene_threshold=0.05):
    """Extract candidate frames using FFmpeg scene detection + I-frames."""
    pattern = os.path.join(tmp_dir, "candidate_%04d.png")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='eq(pict_type,I)+gt(scene,{scene_threshold})',showinfo",
        "-vsync", "vfr",
        "-frame_pts", "1",
        pattern
    ]
    subprocess.run(cmd, capture_output=True)
    candidates = sorted(f for f in os.listdir(tmp_dir) if f.startswith("candidate_") and f.endswith(".png"))
    return [os.path.join(tmp_dir, f) for f in candidates]


def score_frame_grid(path, grid_size=6):
    """Score a frame using grid-based Laplacian variance.

    Returns (score, all_block_scores) where score is the 25th percentile
    of center block Laplacian variances. This avoids a single featureless
    patch (smooth skin, plain wall) from killing the score while still
    catching widespread or localized blur across multiple blocks.
    """
    img = cv2.imread(path)
    if img is None:
        return None, []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    block_h = h // grid_size
    block_w = w // grid_size

    scores = []
    for row in range(grid_size):
        for col in range(grid_size):
            y1 = row * block_h
            y2 = (row + 1) * block_h if row < grid_size - 1 else h
            x1 = col * block_w
            x2 = (col + 1) * block_w if col < grid_size - 1 else w
            block = gray[y1:y2, x1:x2]
            variance = cv2.Laplacian(block, cv2.CV_64F).var()
            scores.append((row, col, variance))

    # Center-weighted: only inner blocks trigger rejection
    # For 6x6 grid: rows 1-4, cols 1-4 (inner 4x4 = 16 blocks)
    center_scores = []
    for row, col, variance in scores:
        if 0 < row < grid_size - 1 and 0 < col < grid_size - 1:
            center_scores.append(variance)

    if not center_scores:
        return 0.0, scores

    # 25th percentile of center blocks — robust against single featureless patches
    center_sorted = sorted(center_scores)
    p25_idx = max(0, len(center_sorted) // 4 - 1)
    p25_score = center_sorted[p25_idx]
    return p25_score, scores


def main():
    parser = argparse.ArgumentParser(description="Smart frame extraction from reel videos")
    parser.add_argument("video", help="Path to MP4 video")
    parser.add_argument("--threshold", type=float, default=0,
                        help="Min Laplacian variance per center block. 0 = score-only mode (default)")
    parser.add_argument("--grid", type=int, default=6, help="Grid divisions (default: 6 = 6x6)")
    parser.add_argument("--scene", type=float, default=0.05, help="FFmpeg scene detection threshold (default: 0.05)")
    args = parser.parse_args()

    if not os.path.isfile(args.video):
        print(f"Error: File not found: {args.video}")
        sys.exit(1)

    basename = os.path.splitext(os.path.basename(args.video))[0]
    output_dir = os.path.join(os.path.expanduser("~"), "honeybloom/sierra/reels/frames", basename)
    os.makedirs(output_dir, exist_ok=True)

    # Temp directory with cleanup
    tmp_dir = tempfile.mkdtemp(prefix="reel-extract-")
    atexit.register(lambda: shutil.rmtree(tmp_dir, ignore_errors=True))

    # Stage 1: FFmpeg extraction
    print(f"Extracting candidates from: {args.video}")
    candidates = extract_candidates(args.video, tmp_dir, args.scene)
    print(f"Candidates extracted: {len(candidates)}")

    if not candidates:
        print("No candidates found. Try lowering --scene threshold.")
        sys.exit(0)

    # Stage 2: Grid-based scoring
    results = []
    for path in candidates:
        min_score, block_scores = score_frame_grid(path, args.grid)
        if min_score is not None:
            results.append((path, min_score, block_scores))

    results.sort(key=lambda x: x[1], reverse=True)

    # Print scores
    print(f"\n{'Frame':<25} {'P25 Center Score':>16}")
    print("-" * 43)
    for path, min_score, _ in results:
        name = os.path.basename(path)
        marker = ""
        if args.threshold > 0 and min_score < args.threshold:
            marker = "  << REJECT"
        print(f"{name:<25} {min_score:>16.1f}{marker}")

    # Filter and copy
    if args.threshold > 0:
        kept = 0
        for i, (path, min_score, _) in enumerate(results):
            if min_score >= args.threshold:
                dst = os.path.join(output_dir, f"frame_{i:04d}.png")
                shutil.copy2(path, dst)
                kept += 1

        rejected = len(results) - kept
        print(f"\nThreshold: {args.threshold}")
        print(f"Extracted {len(candidates)} candidates, {kept} passed scoring, {rejected} rejected")
        print(f"Output: {output_dir}")
    else:
        print(f"\nScore-only mode (--threshold 0). No frames copied.")
        print(f"Set --threshold to enable filtering.")


if __name__ == "__main__":
    main()
