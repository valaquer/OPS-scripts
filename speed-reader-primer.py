#!/usr/bin/env python3
"""Extract the first 100 words from a text file, generate session ID, and write state for the continuer."""
import sys
import os
import time
import random
import json

WORD_COUNT = 100
STATE_DIR = "/tmp"

def generate_session_id():
    t = int(time.time() * 1000)
    r = random.randint(0, 0xFFFFFF)
    return f"{t:x}-{r:06x}"

def main():
    if len(sys.argv) < 2:
        print("Usage: speed-reader-primer.py <file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = os.path.abspath(sys.argv[1])

    try:
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    words = text.split()
    total = len(words)
    primer = words[:WORD_COUNT]
    session_id = generate_session_id()
    offset = min(WORD_COUNT, total)

    # Write state for continuer
    state_file = os.path.join(STATE_DIR, f"speed-reader-{session_id}.state")
    with open(state_file, "w") as f:
        json.dump({"file_path": file_path, "offset": offset, "total": total}, f)

    print(session_id)
    print(" ".join(primer))
    print(f"words:{offset}/{total}", file=sys.stderr)

if __name__ == "__main__":
    main()
