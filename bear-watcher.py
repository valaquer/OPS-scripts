#!/usr/bin/env python3
"""Bear note change watcher -- polls iMac Bear DB for changes, posts to Aether.

Write constraint: reads via SQLite, writes via ssh imac "open 'bear://x-callback-url/...'" ONLY.
Detection: polls iMac DB directly via SSH (fastest -- no sync delay).
Tag resolution: reads Mini's local Bear DB (synced copy, no SSH escaping issues for complex joins).
Session-based notifications: queues changes while Bear is frontmost on iMac, flushes when
Boss switches to Aether (Safari tab active).
Attribution: MCP writes logged to a write ledger; unmatched changes attributed to Boss.
"""

import subprocess
import sqlite3
import json
import time
import urllib.request
import os
import sys

POLL_INTERVAL = 2
AETHER_URL = "http://localhost:51820"
WRITE_LEDGER_PATH = "/var/tmp/bear-write-ledger.json"

IMAC_SSH_OPTS = [
    "ssh",
    "-o", "ControlMaster=auto",
    "-o", "ControlPath=/tmp/bear-watcher-ssh",
    "-o", "ControlPersist=300",
    "-o", "ConnectTimeout=3",
    "-o", "BatchMode=yes",
    "imac",
]

IMAC_BEAR_DB = r"~/Library/Group\ Containers/9K33E3U3T4.net.shinyfrog.bear/Application\ Data/database.sqlite"
MINI_BEAR_DB = os.path.expanduser(
    "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
)

PROJECT_ROOMS = ["manhattan", "onyx", "rev", "spark", "lighthouse", "honeybloom"]
TEAM_HOSTS = {
    "ops": "rio",
    "studio": "dante",
    "re-team": "hana",
    "marketing": "kirby",
    "intel": "juno",
    "finance": "felix",
}
TEAMMATES = [
    "gunnar", "fable", "felix", "jake", "rio", "chica", "natalie",
    "dante", "sierra", "cindy", "hana", "klara", "wyatt", "kirby",
    "ananya", "nora", "andrea", "juno", "pike", "jukka", "claire",
    "burt", "jeh",
]


def query_imac_mods() -> dict[str, tuple[str, str]]:
    """Query iMac Bear DB for note modification dates. Returns {uid: (mod_date, title)}."""
    sql = "SELECT ZUNIQUEIDENTIFIER, ZMODIFICATIONDATE, ZTITLE FROM ZSFNOTE WHERE ZTRASHED = 0"
    try:
        result = subprocess.run(
            IMAC_SSH_OPTS + [f'sqlite3 {IMAC_BEAR_DB} "{sql}"'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {}
        mods = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                mods[parts[0]] = (parts[1], parts[2])
        return mods
    except (subprocess.TimeoutExpired, Exception):
        return {}


def is_bear_frontmost() -> bool:
    """Check if Bear is the frontmost app on the iMac."""
    try:
        result = subprocess.run(
            IMAC_SSH_OPTS + ['osascript -e \'tell application "System Events" to get name of first application process whose frontmost is true\''],
            capture_output=True, text=True, timeout=5,
        )
        return "Bear" in result.stdout.strip()
    except Exception:
        return False


def get_tags_for_note(uid: str) -> list[str]:
    """Read tags for a note from the iMac Bear DB via SSH."""
    sql = (
        "SELECT t.ZTITLE FROM ZSFNOTETAG t "
        "JOIN Z_5TAGS jt ON jt.Z_13TAGS = t.Z_PK "
        "JOIN ZSFNOTE n ON n.Z_PK = jt.Z_5NOTES "
        f"WHERE n.ZUNIQUEIDENTIFIER = '{uid}'"
    )
    try:
        result = subprocess.run(
            IMAC_SSH_OPTS + [f'sqlite3 {IMAC_BEAR_DB} "{sql}"'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log(f"Tag lookup failed for {uid}: {result.stderr.strip()}")
            return []
        tags = [t.strip().lower() for t in result.stdout.strip().split("\n") if t.strip()]
        return tags
    except Exception as e:
        log(f"Tag lookup failed for {uid}: {e}")
        return []


def resolve_room(tags: list[str]) -> "str | None":
    """Route notification based on tag priority: project > team > person."""
    for project in PROJECT_ROOMS:
        if project in tags:
            return get_huddle_room(project, "work")

    for team, host in TEAM_HOSTS.items():
        if team in tags:
            return get_huddle_room(host, "team")

    for name in TEAMMATES:
        if name in tags:
            return f"direct-{name}"

    return None


def get_huddle_room(name: str, kind: str) -> "str | None":
    """Find an active huddle room by name."""
    try:
        req = urllib.request.urlopen(f"{AETHER_URL}/api/rooms", timeout=5)
        data = json.loads(req.read())
        for h in data.get("huddles", []):
            hid = h.get("id", "").lower()
            project = h.get("project", "").lower()
            if kind == "work" and project == name:
                return h["id"]
            if kind == "team" and f"huddle-{name}" in hid:
                return h["id"]
    except Exception:
        pass
    return None


LEDGER_EXPIRY_SECONDS = 120


def read_write_ledger() -> dict[str, dict]:
    """Read the MCP write ledger. Returns {uid: {teammate, ts}}."""
    try:
        with open(WRITE_LEDGER_PATH) as f:
            raw = json.load(f)
        now = time.time()
        fresh = {}
        for uid, entry in raw.items():
            if isinstance(entry, dict) and now - entry.get("ts", 0) < LEDGER_EXPIRY_SECONDS:
                fresh[uid] = entry
            elif isinstance(entry, str):
                fresh[uid] = {"teammate": entry, "ts": 0}
        return fresh
    except Exception:
        return {}


def clear_ledger_entries(uids: set[str]) -> None:
    """Remove consumed entries from the write ledger."""
    try:
        ledger = read_write_ledger()
        for uid in uids:
            ledger.pop(uid, None)
        with open(WRITE_LEDGER_PATH, "w") as f:
            json.dump(ledger, f)
    except Exception:
        pass


def attribute_change(uid: str) -> str:
    """Determine who made the change. MCP writes are logged; everything else is Boss."""
    ledger = read_write_ledger()
    entry = ledger.get(uid)
    if entry and isinstance(entry, dict):
        return entry.get("teammate", "Boss")
    return "Boss"


def post_to_aether(room: str, author: str, title: str) -> None:
    """Post a change notification to Aether."""
    payload = json.dumps({
        "sender": "system",
        "body": f"{author} edited the **{title}** note in the Bear app.",
        "room": room,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{AETHER_URL}/api/message",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    last_mods: dict[str, str] = {}
    pending_changes: dict[str, str] = {}  # uid -> title
    first_run = True
    was_bear_frontmost = False

    log("Bear watcher started")

    while True:
        time.sleep(POLL_INTERVAL)

        current = query_imac_mods()
        if not current:
            continue

        for uid, (mod, title) in current.items():
            prev = last_mods.get(uid)
            if prev is not None and mod != prev and not first_run:
                pending_changes[uid] = title
                log(f"Change detected: {title}")
            last_mods[uid] = mod

        if first_run:
            log(f"Initial snapshot: {len(current)} notes")
        first_run = False

        bear_front = is_bear_frontmost()

        if was_bear_frontmost and not bear_front and pending_changes:
            log(f"Bear lost focus -- flushing {len(pending_changes)} changes")
            ledger_uids = set()
            for uid, title in pending_changes.items():
                tags = get_tags_for_note(uid)
                room = resolve_room(tags) if tags else None
                if room:
                    author = attribute_change(uid)
                    post_to_aether(room, author, title)
                    log(f"Posted: {author} edited {title} -> {room}")
                    ledger_uids.add(uid)
                else:
                    log(f"No route for {title} (tags={tags})")

            if ledger_uids:
                clear_ledger_entries(ledger_uids)
            pending_changes.clear()

        if not bear_front and pending_changes and not was_bear_frontmost:
            log(f"Immediate flush: {len(pending_changes)} changes (Bear not frontmost)")
            ledger_uids = set()
            for uid, title in pending_changes.items():
                tags = get_tags_for_note(uid)
                room = resolve_room(tags) if tags else None
                if room:
                    author = attribute_change(uid)
                    post_to_aether(room, author, title)
                    log(f"Posted: {author} edited {title} -> {room}")
                    ledger_uids.add(uid)
                else:
                    log(f"No route for {title} (tags={tags})")

            if ledger_uids:
                clear_ledger_entries(ledger_uids)
            pending_changes.clear()

        was_bear_frontmost = bear_front


if __name__ == "__main__":
    main()
