#!/usr/bin/env python3
"""Extract the next 100 words from a text file using session state. Jeh passes only the session ID."""
import sys
import os
import json

WORD_COUNT = 100
STATE_DIR = "/tmp"

def main():
    if len(sys.argv) < 2:
        print("Usage: speed-reader-continuer.py <session_id>", file=sys.stderr)
        sys.exit(1)

    session_id = sys.argv[1]
    state_file = os.path.join(STATE_DIR, f"speed-reader-{session_id}.state")

    try:
        with open(state_file) as f:
            state = json.load(f)
    except FileNotFoundError:
        print(f"No state found for session: {session_id}", file=sys.stderr)
        sys.exit(1)

    file_path = state["file_path"]
    offset = state["offset"]
    total = state["total"]

    if offset >= total:
        print("END", file=sys.stderr)
        sys.exit(0)

    with open(file_path, encoding="utf-8") as f:
        text = f.read()

    words = text.split()
    chunk = words[offset:offset + WORD_COUNT]
    new_offset = min(offset + WORD_COUNT, total)

    # Update state
    state["offset"] = new_offset
    with open(state_file, "w") as f:
        json.dump(state, f)

    print(f"Jeh, Boss says, do prosodic chunking of this and throw it up in the speed reader. Session: {session_id}")
    print("")
    print(" ".join(chunk))

    remaining = total - new_offset
    if remaining <= 0:
        print("END", file=sys.stderr)
    else:
        print(f"words:{offset}-{new_offset}/{total} remaining:{remaining}", file=sys.stderr)

if __name__ == "__main__":
    main()
