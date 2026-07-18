#!/usr/bin/env python3
"""Houston poller — REQ-4 + REQ-9 logbook.
Polls vendor APIs on interval, detects anomalies, fires alerts.
Runs as launchd agent every 2 minutes.
All activity logged to append-only SQLite DB (no UPDATE, no DELETE).
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

CREDS_DIR = "/Users/houston/.secrets"
STATE_FILE = "/var/tmp/houston-poller-state.json"
HOUSTON_DB = "/Users/deepak-macmini/honeybloom/library/houston-app/houston.db"
AETHER_URL = os.environ.get("AETHER_URL", "http://localhost:51730")
ALERT_URL = f"{AETHER_URL}/api/houston-alert"
SUPABASE_REF = "rdsgujuyoumygpvsmzaq"
UA = "Houston/1.0"

# --- Logbook ---

def init_db():
    conn = sqlite3.connect(HOUSTON_DB, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS check_log (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            vendor TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            response_ms INTEGER
        );
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            vendor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT,
            deep_link TEXT
        );
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            detail TEXT
        );
    """)
    conn.close()


def log_check(vendor, status, message, response_ms):
    try:
        conn = sqlite3.connect(HOUSTON_DB, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            "INSERT INTO check_log (ts, vendor, status, message, response_ms) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), vendor, status, message, response_ms)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[HOUSTON] log_check failed: {e}", file=sys.stderr)


def log_alert(vendor, event_type, message, deep_link=None):
    try:
        conn = sqlite3.connect(HOUSTON_DB, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            "INSERT INTO alert_log (ts, vendor, event_type, message, deep_link) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), vendor, event_type, message, deep_link)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[HOUSTON] log_alert failed: {e}", file=sys.stderr)


def log_action(action, result, detail=None):
    try:
        conn = sqlite3.connect(HOUSTON_DB, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(
            "INSERT INTO action_log (ts, action, result, detail) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), action, result, detail)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[HOUSTON] log_action failed: {e}", file=sys.stderr)


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


def ensure_aether():
    """Check Aether is running (LaunchDaemon keeps it alive)."""
    try:
        req = urllib.request.Request(f"{AETHER_URL}/api/houston-alert", headers={"User-Agent": UA})
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception as e:
        log_action("ensure_aether", "failure", str(e))
        return False


def fire_alert(vendor, message, deep_link=None, alert_type="incident"):
    """Post alert to Aether — server handles watchtower huddle lifecycle."""
    log_alert(vendor, alert_type, message, deep_link)

    if not ensure_aether():
        return

    data = json.dumps({"vendor": vendor, "message": message, "deep_link": deep_link or "", "type": alert_type}).encode()
    req = urllib.request.Request(ALERT_URL, data=data, headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
        log_action("fire_alert", "success", f"{vendor}: {message}")
    except Exception as e:
        log_action("fire_alert", "failure", f"{vendor}: {e}")


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

    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    query = '{ viewer { zones(filter: {zoneTag: "%s"}) { httpRequests1dGroups(limit: 1, filter: {date_gt: "%s"}) { sum { requests } } } } }' % (zone_id, since)
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/graphql", data=data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    if body.get("errors"):
        return "unhealthy", f"GraphQL errors: {body['errors'][0].get('message', 'unknown')}", "https://dash.cloudflare.com"
    return "healthy", "API reachable"


def check_prague_app():
    url = "https://prague-navy.vercel.app"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=10)
    if resp.status == 200:
        return "healthy", f"app serving (HTTP {resp.status})"
    return "unhealthy", f"app returned HTTP {resp.status}", "https://prague-navy.vercel.app"


def check_prague_supabase():
    url = f"https://{SUPABASE_REF}.supabase.co/auth/v1/health"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return "healthy", f"project endpoint alive (HTTP {resp.status})"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "healthy", f"project endpoint alive (HTTP {e.code})"
        return "unhealthy", f"project endpoint HTTP {e.code}", f"https://supabase.com/dashboard/project/{SUPABASE_REF}"


# --- Main ---

def main():
    init_db()

    state = load_state()
    checks = [
        ("vercel", check_vercel),
        ("supabase", check_supabase),
        ("resend", check_resend),
        ("openrouter", check_openrouter),
        ("cloudflare", check_cloudflare),
        ("prague_app", check_prague_app),
        ("prague_supabase", check_prague_supabase),
    ]

    for vendor, check_fn in checks:
        t0 = time.time()
        try:
            result = check_fn()
            status = result[0]
            message = result[1]
            deep_link = result[2] if len(result) > 2 else None
        except Exception as e:
            status = "unhealthy"
            message = f"check failed: {e}"
            deep_link = None
        response_ms = int((time.time() - t0) * 1000)

        if status == "skip":
            continue

        # Supabase retry-before-alert: one 5s retry on any unhealthy outcome
        if vendor == "supabase" and status == "unhealthy":
            time.sleep(5)
            try:
                retry_result = check_fn()
                retry_status = retry_result[0]
            except Exception:
                retry_status = "unhealthy"
            if retry_status == "healthy" and state.get(vendor, "healthy") == "healthy":
                log_check(vendor, "recovered-on-retry", f"transient: {message}", response_ms)
                status = "healthy"
                message = "recovered on retry"
                state[vendor] = status
                continue
            elif retry_status == "healthy":
                status = "healthy"
                message = "recovered on retry"

        log_check(vendor, status, message, response_ms)

        prev_status = state.get(vendor, "healthy")

        # State-change detection: only alert on transition
        if status == "unhealthy" and prev_status != "unhealthy":
            fire_alert(vendor, message, deep_link)
        elif status == "healthy" and prev_status == "unhealthy":
            fire_alert(vendor, f"recovered — {message}", alert_type="recovery")

        state[vendor] = status

    save_state(state)

    try:
        hb_data = json.dumps({"state": state}).encode()
        hb_req = urllib.request.Request(
            f"{AETHER_URL}/api/houston-heartbeat",
            data=hb_data,
            headers={"Content-Type": "application/json", "User-Agent": UA},
            method="POST"
        )
        urllib.request.urlopen(hb_req, timeout=5)
        log_action("heartbeat", "success")
    except Exception as e:
        log_action("heartbeat", "failure", str(e))


if __name__ == "__main__":
    main()
