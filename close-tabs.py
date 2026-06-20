#!/usr/bin/env python3
"""Close a teammate's Kitty tab and their pair partner's tab.

Single purpose: tab closing only. No ledger, no huddle cleanup.

Usage: close-tabs.py <teammate_name>
"""

import csv
import glob as glob_mod
import os
import subprocess
import sys
import urllib.request
import json

KITTEN = "/opt/homebrew/bin/kitten"

ORG_PATH = "/Users/deepak-macmini/honeybloom/library/ORG.md"
JANUS_CSV = "/Users/deepak-macmini/honeybloom/library/skills/gestalt-layer-3-janus/janus-config.csv"
SSH_KEY = "/Users/deepak-macmini/.ssh/id_hanover"
MINI_USER = "deepak-macmini"
MINI_HOST = "192.168.0.186"


def parse_groups():
    groups = []
    with open(ORG_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("Group:"):
                raw = line[len("Group:"):].strip()
                # Strip optional (host: X) suffix
                if "(" in raw:
                    raw = raw[:raw.index("(")].strip()
                members = [m.strip().lower() for m in raw.split(",") if m.strip()]
                if members:
                    groups.append(members)
    return groups


def find_group(groups, teammate):
    for group in groups:
        if teammate in group:
            return group
    return None


def discover_socket():
    env_sock = os.environ.get("KITTY_LISTEN_ON", "")
    if env_sock:
        path = env_sock.replace("unix:", "")
        if os.path.exists(path):
            return env_sock
    for path in glob_mod.glob("/tmp/honeybloom-kitty-*.sock"):
        if os.path.exists(path):
            return f"unix:{path}"
    return None


def is_tab_alive(socket, teammate):
    result = subprocess.run(
        [KITTEN, "@", "--to", socket, "ls",
         "--match", f"var:teammate={teammate}"],
        capture_output=True, timeout=5, text=True,
    )
    return result.returncode == 0 and result.stdout.strip()


def close_tab(socket, teammate):
    subprocess.run(
        [KITTEN, "@", "--to", socket, "close-tab",
         "--match", f"var:teammate={teammate}"],
        capture_output=True, timeout=10,
    )


def get_machine(teammate):
    try:
        with open(JANUS_CSV) as f:
            reader = csv.reader(f)
            header = next(reader)
            machine_idx = header.index("machine") if "machine" in header else -1
            if machine_idx < 0:
                return "imac"
            for row in reader:
                if len(row) > machine_idx and row[0].strip().lower() == teammate:
                    return row[machine_idx].strip().lower() or "imac"
    except Exception:
        pass
    return "imac"


def close_mini_tab(teammate):
    try:
        result = subprocess.run(
            ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=3",
             f"{MINI_USER}@{MINI_HOST}",
             f"for p in $(pgrep -x claude); do "
             f"lsof -p $p -d cwd -Fn 2>/dev/null | grep -q 'honeybloom/{teammate}$' && kill $p && echo killed && exit 0; "
             f"done; echo none"],
            capture_output=True, timeout=10, text=True,
        )
        return "killed" in result.stdout
    except Exception:
        return False


def unmount_safe(teammate):
    """Unmount encrypted safe if mounted. Best-effort — never blocks close flow."""
    try:
        safe_script = "/Users/deepak-macmini/honeybloom/library/scripts/safe.sh"
        if os.path.exists(safe_script):
            subprocess.run([safe_script, "unmount", teammate],
                           capture_output=True, timeout=10)
    except Exception:
        pass


def notify_aether(name):
    try:
        data = json.dumps({"name": name}).encode()
        req = urllib.request.Request(
            "http://localhost:51730/api/rooms/deactivate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <teammate>", file=sys.stderr)
        sys.exit(1)

    teammate = sys.argv[1].strip().lower()

    socket = discover_socket()

    def close_one(name):
        machine = get_machine(name)
        if machine == "mini":
            if close_mini_tab(name):
                notify_aether(name)
                unmount_safe(name)
                print(f"Closed {name}'s process on Mini.")
            elif socket and is_tab_alive(socket, name):
                close_tab(socket, name)
                notify_aether(name)
                unmount_safe(name)
                print(f"Closed {name}'s tab locally (not on Mini).")
            else:
                print(f"No process found for {name} on Mini or locally.")
        else:
            if not socket:
                print(f"No Kitty socket — cannot close {name}.", file=sys.stderr)
                return
            if is_tab_alive(socket, name):
                close_tab(socket, name)
                notify_aether(name)
                unmount_safe(name)
                print(f"Closed {name}'s tab.")
            else:
                print(f"No tab open for {name}.")

    close_one(teammate)

    groups = parse_groups()
    group = find_group(groups, teammate)
    if group:
        for member in group:
            if member == teammate:
                continue
            close_one(member)


if __name__ == "__main__":
    main()
