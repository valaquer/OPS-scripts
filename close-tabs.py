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
import re

KITTEN = "/opt/homebrew/bin/kitten"

ORG_PATH = "/Users/deepak-macmini/honeybloom/library/ORG.md"
JANUS_CSV = "/Users/deepak-macmini/honeybloom/library/scripts/janus-config.csv"
SSH_KEY = "/Users/deepak-macmini/.ssh/id_hanover"
MINI_USER = "deepak-macmini"
MINI_HOST = "192.168.0.186"


def parse_groups(org_path=None):
    path = org_path or ORG_PATH
    roster = []
    groups = []
    in_groups = False
    with open(path) as f:
        for line in f:
            teammate_match = re.match(r"^Teammate:\s*([a-z0-9-]+)\s*$", line.strip(), re.I)
            if teammate_match:
                roster.append(teammate_match.group(1).lower())
            line = line.strip()
            if line == "## Groups":
                in_groups = True
                continue
            if in_groups and line.startswith("## "):
                break
            if not in_groups or "(host:" not in line:
                continue
            match = re.fullmatch(r"(.+?)\s*\(host:\s*([a-z0-9-]+)\)", line, re.I)
            if not match:
                raise ValueError(f"Malformed ORG group line: {line}")
            raw, host = match.group(1).strip(), match.group(2).lower()
            members = [m.strip().lower() for m in raw.split(",") if m.strip()]
            if not members or len(set(members)) != len(members):
                raise ValueError(f"Empty or duplicate ORG group members: {line}")
            if host not in members:
                raise ValueError(f"ORG group host is not a member: {line}")
            groups.append({"host": host, "members": members})
    if not roster or len(set(roster)) != len(roster):
        raise ValueError("ORG roster is empty or contains duplicates")
    assigned = [member for group in groups for member in group["members"]]
    unknown = sorted(set(assigned) - set(roster))
    missing = sorted(set(roster) - set(assigned))
    duplicates = sorted({member for member in assigned if assigned.count(member) > 1})
    if unknown or missing or duplicates:
        raise ValueError(f"Invalid ORG groups: unknown={unknown}, missing={missing}, duplicates={duplicates}")
    return groups


def find_group(groups, teammate):
    for group in groups:
        if teammate in group["members"]:
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


def build_mini_close_command(teammate):
    if not re.fullmatch(r"[a-z0-9-]+", teammate, re.I):
        raise ValueError(f"Invalid teammate name: {teammate}")
    expected_cwd = f"/Users/deepak-macmini/honeybloom/{teammate}"
    return f"""expected_cwd='{expected_cwd}'
cwd_of() {{ lsof -p "$1" -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p'; }}
is_live() {{ kill -0 "$1" 2>/dev/null || return 1; state=$(ps -o stat= -p "$1" 2>/dev/null | tr -d ' '); case "$state" in Z*) return 1 ;; esac; return 0; }}
command_of() {{ ps -o command= -p "$1" 2>/dev/null || true; }}
birth_of() {{ ps -o lstart= -p "$1" 2>/dev/null | awk '{{$1=$1; print}}'; }}
fingerprint_of() {{ command=$(command_of "$1"); birth=$(birth_of "$1"); [ -n "$command" ] && [ -n "$birth" ] || return 1; printf '%s\n%s' "$command" "$birth" | cksum | awk '{{print $1 ":" $2}}'; }}
add_target() {{ pid="$1"; role="$2"; [ "$(cwd_of "$pid")" = "$expected_cwd" ] || return; fingerprint=$(fingerprint_of "$pid") || return; case " $targets " in *" $pid "*) return ;; esac; targets="$targets $pid"; eval fp_$pid=$fingerprint; eval role_$pid=$role; }}
still_target() {{ pid="$1"; is_live "$pid" || return 1; [ "$(cwd_of "$pid")" = "$expected_cwd" ] || return 1; eval expected_fp=\\$fp_$pid; eval role=\\$role_$pid; [ -n "$expected_fp" ] && [ "$(fingerprint_of "$pid")" = "$expected_fp" ] || return 1; command=$(command_of "$pid"); case "$role" in descendant) case "$command" in */codex-code-mode-host|*/bin/codex\\ *) ;; *) return 1 ;; esac ;; native) [ "$(ps -o comm= -p "$pid" 2>/dev/null | sed 's#.*/##' | tr -d ' ')" = codex ] || return 1 ;; launcher) case "$command" in node\\ /opt/homebrew/bin/codex\\ *) ;; *) return 1 ;; esac ;; claude) [ "$(ps -o comm= -p "$pid" 2>/dev/null | sed 's#.*/##' | tr -d ' ')" = claude ] || return 1 ;; *) return 1 ;; esac; }}
record_descendants() {{ for child in $(pgrep -P "$1" 2>/dev/null || true); do child_cmd=$(command_of "$child"); case "$child_cmd" in */codex-code-mode-host|*/bin/codex\\ *) ;; *) continue ;; esac; if [ "$(cwd_of "$child")" = "$expected_cwd" ]; then record_descendants "$child"; add_target "$child" descendant; fi; done; }}
targets=""
for native in $(pgrep -x codex 2>/dev/null || true); do
  [ "$(cwd_of "$native")" = "$expected_cwd" ] || continue
  launcher=$(ps -o ppid= -p "$native" 2>/dev/null | tr -d ' ')
  launcher_cmd=$(ps -o command= -p "$launcher" 2>/dev/null || true)
  case "$launcher_cmd" in node\\ /opt/homebrew/bin/codex\\ *) ;; *) launcher="" ;; esac
  [ -z "$launcher" ] || [ "$(cwd_of "$launcher")" = "$expected_cwd" ] || launcher=""
  record_descendants "$native"
  add_target "$native" native
  [ -z "$launcher" ] || add_target "$launcher" launcher
done
for claude in $(pgrep -x claude 2>/dev/null || true); do
  [ "$(cwd_of "$claude")" = "$expected_cwd" ] || continue
  add_target "$claude" claude
done
for pid in $targets; do still_target "$pid" && kill -TERM "$pid" 2>/dev/null || true; done
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  survivors=""
  for pid in $targets; do still_target "$pid" && survivors="$survivors $pid"; done
  [ -z "$survivors" ] && {{ [ -n "$targets" ] && echo killed || echo none; exit 0; }}
  sleep 0.2
done
for pid in $survivors; do still_target "$pid" && kill -9 "$pid" 2>/dev/null || true; done
sleep 0.2
remaining=""
for pid in $survivors; do still_target "$pid" && remaining="$remaining $pid"; done
[ -z "$remaining" ] || {{ echo "surviving teammate processes:$remaining" >&2; exit 1; }}
[ -n "$targets" ] && echo killed || echo none"""


def close_mini_tab(teammate):
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=3",
         f"{MINI_USER}@{MINI_HOST}",
         build_mini_close_command(teammate)],
        capture_output=True, timeout=10, text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"remote exit {result.returncode}"
        raise RuntimeError(f"Mini process cleanup failed for {teammate}: {detail}")
    status = result.stdout.strip()
    if status not in {"killed", "none"}:
        raise RuntimeError(f"Mini process cleanup returned invalid status for {teammate}: {status!r}")
    return status


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
    if not re.fullmatch(r"[a-z0-9-]+", teammate):
        print(f"Invalid teammate: {teammate}", file=sys.stderr)
        sys.exit(1)

    # Validate the complete roster/group contract before closing anything.
    groups = parse_groups()
    group = find_group(groups, teammate)
    if group is None:
        print(f"Teammate is missing from ORG groups: {teammate}", file=sys.stderr)
        sys.exit(1)

    socket = discover_socket()

    def close_one(name):
        machine = get_machine(name)
        if machine == "mini":
            cleanup_status = close_mini_tab(name)
            if cleanup_status == "killed":
                notify_aether(name)
                unmount_safe(name)
                print(f"Closed {name}'s process on Mini.")
            elif cleanup_status == "none" and socket and is_tab_alive(socket, name):
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

    if group:
        for member in group["members"]:
            if member == teammate:
                continue
            close_one(member)


if __name__ == "__main__":
    main()
