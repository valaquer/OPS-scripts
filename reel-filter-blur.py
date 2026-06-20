#!/usr/bin/env python3
"""Score and filter extracted reel frames by sharpness (Laplacian variance)."""

import sys
import os
import shutil
import cv2

def laplacian_variance(path):
    img = cv2.imread(path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def main():
    if len(sys.argv) < 2:
        print("Usage: reel-filter-blur.py <frames-dir> [threshold]")
        print("  If threshold is omitted, prints scores only (no filtering).")
        sys.exit(1)

    frames_dir = sys.argv[1]
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else None

    if not os.path.isdir(frames_dir):
        print(f"Error: Directory not found: {frames_dir}")
        sys.exit(1)

    pngs = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not pngs:
        print("No PNG files found.")
        sys.exit(0)

    scores = []
    for f in pngs:
        path = os.path.join(frames_dir, f)
        score = laplacian_variance(path)
        if score is not None:
            scores.append((f, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    print(f"{'Frame':<25} {'Laplacian Variance':>18}")
    print("-" * 45)
    for name, score in scores:
        marker = "" if threshold is None or score >= threshold else "  << BLUR"
        print(f"{name:<25} {score:>18.1f}{marker}")

    if threshold is not None:
        rejected_dir = os.path.join(frames_dir, "rejected")
        os.makedirs(rejected_dir, exist_ok=True)
        rejected = 0
        for name, score in scores:
            if score < threshold:
                shutil.move(os.path.join(frames_dir, name), os.path.join(rejected_dir, name))
                rejected += 1
        kept = len(scores) - rejected
        print(f"\nThreshold: {threshold}")
        print(f"Kept: {kept} | Rejected: {rejected} (moved to rejected/)")

if __name__ == "__main__":
    main()
