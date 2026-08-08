#!/usr/bin/env python3
"""Bavaria CSV009 watchdog. Alerts Dante's huddles when assets exist without CSV009 entries."""

import csv
import json
import os
import re
import urllib.request
import urllib.error

BAVARIA_DIR = "/Users/deepak-macmini/honeybloom/library/bavaria"
CSV009_PATH = "/Users/deepak-macmini/honeybloom/library/ip/prompt-engineer-v8/CSV009-outputs.csv"
AETHER_URL = "http://localhost:51730"
ASSET_CODE_RE = re.compile(r"0{3}\d{3}")


def get_dante_huddles():
    try:
        req = urllib.request.Request(f"{AETHER_URL}/api/active-rooms?teammate=dante")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return [r["id"] for r in data.get("rooms", []) if r["id"].startswith("huddle-") or r["id"].startswith("work-")]
    except Exception:
        return []


def get_filesystem_codes():
    codes = set()
    for root, dirs, files in os.walk(BAVARIA_DIR):
        for f in files:
            match = ASSET_CODE_RE.search(f)
            if match:
                codes.add(match.group())
    return codes


def get_csv009_codes():
    codes = set()
    try:
        with open(CSV009_PATH, newline="") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row and row[0].strip():
                    codes.add(row[0].strip())
    except FileNotFoundError:
        pass
    return codes


def post_alert(room, message):
    payload = json.dumps({"sender": "system", "body": message, "room": room}).encode()
    req = urllib.request.Request(
        f"{AETHER_URL}/api/message",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def main():
    huddles = get_dante_huddles()
    if not huddles:
        return

    fs_codes = get_filesystem_codes()
    csv_codes = get_csv009_codes()
    unlogged = sorted(fs_codes - csv_codes)

    if not unlogged:
        return

    msg = f"CSV009 watchdog: {len(unlogged)} asset(s) not logged -- {', '.join(unlogged)}"
    for huddle in huddles:
        post_alert(huddle, msg)


if __name__ == "__main__":
    main()
