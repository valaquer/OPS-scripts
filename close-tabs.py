#!/usr/bin/env python3
"""Close a teammate's Kitty tab and their pair partner's tab.

Single purpose: tab closing only. No ledger, no huddle cleanup.

Usage: close-tabs.py <teammate_name>
"""

import glob as glob_mod
import os
import subprocess
import sys
import urllib.request
import json

KITTEN = "/opt/homebrew/bin/kitten"

PAIRS = {
    "chica": "rio", "rio": "chica",
    "lea": "theo", "theo": "lea",
    "sierra": "dante", "dante": "sierra",
    "eva": "kirby", "kirby": "eva",
    "daksh": "guru", "guru": "daksh",
    "nash": "ezra", "ezra": "nash",
    "pike": "juno", "juno": "pike",
    "quinn": "vera", "vera": "quinn",
    "wyatt": "hana", "hana": "wyatt",
    "omar": "zara", "zara": "omar",
    "isa": "edgar", "edgar": "isa",
}


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


def close_tab(socket, teammate):
    subprocess.run(
        [KITTEN, "@", "--to", socket, "close-tab",
         "--match", f"var:teammate={teammate}"],
        capture_output=True, timeout=10,
    )


def notify_facade(name):
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
    if not socket:
        print("No Kitty socket found.", file=sys.stderr)
        sys.exit(1)

    close_tab(socket, teammate)
    notify_facade(teammate)
    print(f"Closed {teammate}'s tab.")

    partner = PAIRS.get(teammate)
    if partner:
        close_tab(socket, partner)
        notify_facade(partner)
        print(f"Closed {partner}'s tab (pair).")


if __name__ == "__main__":
    main()
