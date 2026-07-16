#!/usr/bin/env python3
"""Houston poller — REQ-4.
Polls vendor APIs on interval, detects anomalies, fires alerts.
Runs as launchd agent every 2 minutes.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

CREDS_DIR = os.path.expanduser("~/.secrets/houston")
STATE_FILE = os.path.expanduser("~/.secrets/houston/poller-state.json")
AETHER_URL = os.environ.get("AETHER_URL", "http://localhost:51730")
ALERT_URL = f"{AETHER_URL}/api/houston-alert"
HUDDLE_URL = f"{AETHER_URL}/api/huddle"
WATCHTOWER_ROOM = "huddle-houston-watchtower"
SUPABASE_REF = "rdsgujuyoumygpvsmzaq"
UA = "Houston/1.0"

# --- Helpers ---

def read_cred(filename):
    path = os.path.join(CREDS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fire_alert(vendor, message, deep_link=None):
    """Post alert to Aether + watchtower room + auto-add Guru's team."""
    # 1. Create alert (triggers cop car LED via SSE)
    data = json.dumps({"vendor": vendor, "message": message, "deep_link": deep_link or ""}).encode()
    req = urllib.request.Request(ALERT_URL, data=data, headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    # 2. Post to watchtower room
    msg = f"🚨 {vendor.upper()}: {message}"
    if deep_link:
        msg += f"\nFix: {deep_link}"
    post_data = json.dumps({"body": msg, "room": WATCHTOWER_ROOM}).encode()
    req = urllib.request.Request(f"{AETHER_URL}/api/message", data=post_data, headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    # 3. Auto-add Guru's team to watchtower
    add_data = json.dumps({"action": "add", "roomId": WATCHTOWER_ROOM, "participants": ["guru", "daksh", "ines"]}).encode()
    req = urllib.request.Request(HUDDLE_URL, data=add_data, headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


# --- Vendor checks ---

def check_vercel():
    lines = read_cred("vercel-token")
    if not lines:
        return "skip", "no credentials"
    token = lines[0]
    team_id = lines[1] if len(lines) > 1 else None

    url = "https://api.vercel.com/v7/deployments?limit=1"
    if team_id:
        url += f"&teamId={team_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    deploys = body.get("deployments", [])
    if not deploys:
        return "healthy", "no deployments"
    latest = deploys[0]
    state = latest.get("state", "UNKNOWN")
    if state in ("READY", "BUILDING", "QUEUED"):
        return "healthy", f"latest: {state}"
    return "unhealthy", f"latest deployment {state}", f"https://vercel.com/deployments/{latest.get('uid', '')}"


def check_supabase():
    lines = read_cred("supabase-pat")
    if not lines:
        return "skip", "no credentials"
    pat = lines[0]

    # Health check
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/health?services=auth,db,pooler,realtime,rest,storage"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {pat}", "User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=10)
    services = json.loads(resp.read())
    unhealthy = [s["name"] for s in services if not s.get("healthy", True)]
    if unhealthy:
        return "unhealthy", f"services down: {', '.join(unhealthy)}", f"https://supabase.com/dashboard/project/{SUPABASE_REF}"

    # Readonly check
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/readonly"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {pat}", "User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=10)
    ro = json.loads(resp.read())
    if ro.get("enabled"):
        return "unhealthy", "database in READONLY mode (disk full)", f"https://supabase.com/dashboard/project/{SUPABASE_REF}"

    return "healthy", "all services healthy"


def check_resend():
    lines = read_cred("resend-key")
    if not lines:
        return "skip", "no credentials"
    key = lines[0]

    url = "https://api.resend.com/api-keys"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=10)
    return "healthy", f"API reachable (HTTP {resp.status})"


def check_openrouter():
    lines = read_cred("openrouter-key")
    if not lines:
        return "skip", "no credentials"
    key = lines[0]

    url = "https://openrouter.ai/api/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=15)
    body = json.loads(resp.read())
    count = len(body.get("data", []))
    if count == 0:
        return "unhealthy", "zero models available", "https://openrouter.ai/models"
    return "healthy", f"{count} models available"


def check_cloudflare():
    lines = read_cred("cloudflare-token")
    if not lines:
        return "skip", "no credentials"
    token = lines[0]
    zone_id = lines[1] if len(lines) > 1 else None
    if not zone_id:
        return "skip", "no zone_id"

    query = '{ viewer { zones(filter: {zoneTag: "%s"}) { httpRequests1dGroups(limit: 1, filter: {date_gt: "2025-01-01"}) { sum { requests } } } } }' % zone_id
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/graphql", data=data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    if body.get("errors"):
        return "unhealthy", f"GraphQL errors: {body['errors'][0].get('message', 'unknown')}", "https://dash.cloudflare.com"
    return "healthy", "API reachable"


# --- Main ---

def main():
    state = load_state()
    checks = [
        ("vercel", check_vercel),
        ("supabase", check_supabase),
        ("resend", check_resend),
        ("openrouter", check_openrouter),
        ("cloudflare", check_cloudflare),
    ]

    for vendor, check_fn in checks:
        try:
            result = check_fn()
            status = result[0]
            message = result[1]
            deep_link = result[2] if len(result) > 2 else None
        except Exception as e:
            status = "unhealthy"
            message = f"check failed: {e}"
            deep_link = None

        if status == "skip":
            continue

        prev_status = state.get(vendor, "healthy")

        # State-change detection: only alert on transition
        if status == "unhealthy" and prev_status != "unhealthy":
            fire_alert(vendor, message, deep_link)

        state[vendor] = status

    save_state(state)


if __name__ == "__main__":
    main()
