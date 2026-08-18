#!/usr/bin/env python3
"""
Whiteboard watcher -- detects canvas changes and posts notifications to Aether.
Polls the whiteboard server every 5s, hashes element IDs + versions.
20s debounce: queues changes, posts only after 20s of quiet.
Attribution via write ledger (MCP writes → teammate, unmatched → Boss).
"""

import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error

WHITEBOARD_URL = "http://127.0.0.1:51850"
AETHER_URL = "http://localhost:51820"
POLL_INTERVAL = 5
ACTIVE_FILE = "/Users/deepak-macmini/honeybloom/library/whiteboard/.active"
WRITE_LEDGER = "/var/tmp/whiteboard-write-ledger.json"


def get_elements_hash():
    try:
        req = urllib.request.Request(f"{WHITEBOARD_URL}/api/elements")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        elements = data.get("elements", [])
        id_versions = sorted(f"{e['id']}:{e.get('version', 0)}" for e in elements)
        h = hashlib.md5("|".join(id_versions).encode()).hexdigest()
        return h, len(elements)
    except Exception:
        return None, 0


def get_active_canvas():
    try:
        with open(ACTIVE_FILE) as f:
            return f.read().strip()
    except Exception:
        return "canvas"


def consume_ledger():
    """Read and clear the write ledger. Returns list of teammate names."""
    try:
        with open(WRITE_LEDGER) as f:
            entries = json.load(f)
        with open(WRITE_LEDGER, "w") as f:
            json.dump([], f)
        return [e.get("teammate", "unknown") for e in entries if e.get("teammate")]
    except Exception:
        return []


def get_ops_huddle_id():
    try:
        req = urllib.request.Request(f"{AETHER_URL}/api/active-rooms?teammate=rio")
        with urllib.request.urlopen(req, timeout=5) as resp:
            rooms = json.loads(resp.read())
        for room in rooms:
            if room.startswith("huddle-rio-"):
                return room
    except Exception:
        pass
    return "direct-chica"


def post_notification(canvas_name, teammates):
    if teammates:
        unique = list(dict.fromkeys(teammates))
        who = ", ".join(unique)
    else:
        who = "Boss"

    body = f"{who} edited the whiteboard canvas '{canvas_name}'."
    room = get_ops_huddle_id()

    payload = json.dumps({"sender": "system", "body": body, "room": room}).encode()
    req = urllib.request.Request(
        f"{AETHER_URL}/api/message",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Failed to post notification: {e}", file=sys.stderr)


def main():
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Whiteboard watcher started", flush=True)

    last_hash = None
    last_count = 0

    last_hash, last_count = get_elements_hash()
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Initial state: {last_count} elements, hash {last_hash}", flush=True)

    while True:
        time.sleep(POLL_INTERVAL)

        current_hash, current_count = get_elements_hash()
        if current_hash is None:
            continue

        if current_hash != last_hash:
            teammates = consume_ledger()
            canvas_name = get_active_canvas()
            # post_notification(canvas_name, teammates)
            print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] Change detected: canvas '{canvas_name}', {len(teammates)} teammate edits", flush=True)
            last_hash = current_hash
            last_count = current_count


if __name__ == "__main__":
    main()
