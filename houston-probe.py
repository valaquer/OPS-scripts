#!/usr/bin/env python3
"""Houston probe script — REQ-1.
Hits vendor APIs with real tokens from Burt, dumps raw responses.
Validates Juno's research against what our accounts actually return.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

CREDS_DIR = os.path.expanduser("~/.secrets/houston")
OUTPUT_FILE = "/tmp/houston-probe-results.json"

# --- Config ---
SUPABASE_REF = "rdsgujuyoumygpvsmzaq"

# --- Helpers ---

def read_cred(filename):
    """Read credential file from Burt's temp dir. Returns list of lines."""
    path = os.path.join(CREDS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def probe(name, func):
    """Run a probe function, capture result or error with timing."""
    start = time.time()
    try:
        result = func()
        elapsed = round(time.time() - start, 3)
        return {
            "vendor": name,
            "status": "ok",
            "latency_s": elapsed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": result
        }
    except Exception as e:
        elapsed = round(time.time() - start, 3)
        return {
            "vendor": name,
            "status": "error",
            "latency_s": elapsed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }


# --- Vendor probes ---

def probe_supabase():
    import urllib.request
    import urllib.error

    lines = read_cred("supabase-pat")
    if not lines:
        raise RuntimeError("No supabase-pat credential file")
    pat = lines[0]

    results = {}

    # Health check
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/health?services=auth,db,pooler,realtime,rest,storage"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {pat}", "User-Agent": "Houston/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        results["health"] = {"http_status": resp.status, "body": json.loads(resp.read())}

    # Readonly check
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/readonly"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {pat}", "User-Agent": "Houston/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        results["readonly"] = {"http_status": resp.status, "body": json.loads(resp.read())}

    return results


def probe_resend():
    import urllib.request

    lines = read_cred("resend-key")
    if not lines:
        raise RuntimeError("No resend-key credential file")
    key = lines[0]

    url = "https://api.resend.com/api-keys"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": "Houston/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
        key_count = len(body.get("data", []))
        return {"http_status": resp.status, "api_key_count": key_count, "endpoint_used": "/api-keys"}


def probe_openrouter():
    import urllib.request

    lines = read_cred("openrouter-key")
    if not lines:
        raise RuntimeError("No openrouter-key credential file")
    key = lines[0]

    url = "https://openrouter.ai/api/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": "Houston/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
        model_count = len(body.get("data", []))
        # Don't dump all models — just count + first 3 names
        sample = [m.get("id") for m in body.get("data", [])[:3]]
        return {"http_status": resp.status, "model_count": model_count, "sample_models": sample}


def probe_vercel():
    import urllib.request

    lines = read_cred("vercel-token")
    if not lines:
        raise RuntimeError("No vercel-token credential file — Boss needs to provision")
    token = lines[0]
    team_id = lines[1] if len(lines) > 1 else None

    results = {}

    # Deployments list
    url = "https://api.vercel.com/v7/deployments?limit=3"
    if team_id:
        url += f"&teamId={team_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "Houston/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
        deploys = body.get("deployments", [])
        results["deployments"] = {
            "http_status": resp.status,
            "count": len(deploys),
            "latest": {
                "uid": deploys[0].get("uid") if deploys else None,
                "state": deploys[0].get("state") if deploys else None,
                "created": deploys[0].get("created") if deploys else None
            } if deploys else None
        }

    # Build logs for latest deploy
    if deploys:
        deploy_id = deploys[0]["uid"]
        url = f"https://api.vercel.com/v3/deployments/{deploy_id}/events"
        if team_id:
            url += f"?teamId={team_id}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "Houston/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            event_count = len(body) if isinstance(body, list) else 0
            results["build_logs"] = {"http_status": resp.status, "event_count": event_count}

    return results


def probe_cloudflare():
    import urllib.request

    lines = read_cred("cloudflare-token")
    if not lines:
        raise RuntimeError("No cloudflare-token credential file — Boss needs to provision")
    token = lines[0]
    zone_id = lines[1] if len(lines) > 1 else None

    if not zone_id:
        raise RuntimeError("No zone_id in cloudflare-token file (expected on line 2)")

    # GraphQL query for HTTP traffic
    query = """{
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(limit: 1, filter: {date_gt: "2025-01-01"}) {
            sum { requests bytes }
            dimensions { date }
          }
        }
      }
    }""" % zone_id

    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
        return {"http_status": resp.status, "graphql_response": body}


# --- Main ---

def main():
    print(f"Houston probe — {datetime.now(timezone.utc).isoformat()}")
    print(f"Credentials dir: {CREDS_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    results = []

    # Probe available vendors
    for name, func in [
        ("supabase", probe_supabase),
        ("resend", probe_resend),
        ("openrouter", probe_openrouter),
        ("vercel", probe_vercel),
        ("cloudflare", probe_cloudflare),
    ]:
        print(f"Probing {name}...", end=" ", flush=True)
        result = probe(name, func)
        print(result["status"])
        results.append(result)

    # Write results
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to {OUTPUT_FILE}")

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"Summary: {ok} ok, {err} errors")


if __name__ == "__main__":
    main()
