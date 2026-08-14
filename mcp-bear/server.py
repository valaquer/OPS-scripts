#!/usr/bin/env python3
"""
Honeybloom Bear — Read/write MCP server for Bear note collaboration.
Reads from Mini's local Bear DB (SQLite, read-only).
Writes via x-callback-url on iMac (SSH) to keep Bear's cache in sync.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.2.0"]
# ///

import json
import os
import sqlite3
import subprocess
import urllib.parse
from mcp.server.fastmcp import FastMCP

BEAR_DB = os.path.expanduser(
    "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
)
WRITE_LEDGER_PATH = "/var/tmp/bear-write-ledger.json"

mcp = FastMCP("honeybloom-bear")


def get_db():
    return sqlite3.connect(f"file:{BEAR_DB}?mode=ro", uri=True)


def get_teammate_name():
    cwd = os.getcwd()
    parts = cwd.split("/honeybloom/")
    if len(parts) > 1:
        return parts[1].split("/")[0]
    return "unknown"


def log_write(uid: str, teammate: str):
    try:
        ledger = {}
        if os.path.exists(WRITE_LEDGER_PATH):
            with open(WRITE_LEDGER_PATH) as f:
                ledger = json.load(f)
        ledger[uid] = teammate
        with open(WRITE_LEDGER_PATH, "w") as f:
            json.dump(ledger, f)
    except Exception:
        pass


@mcp.tool()
def bear_read(title: str = "", uid: str = "") -> str:
    """Read a Bear note by title or unique identifier.

    Args:
        title: Note title to search for (case-insensitive)
        uid: Note unique identifier (takes priority over title)
    """
    conn = get_db()
    try:
        if uid:
            cursor = conn.execute(
                "SELECT ZTITLE, ZTEXT FROM ZSFNOTE WHERE ZUNIQUEIDENTIFIER = ? AND ZTRASHED = 0",
                (uid,),
            )
        elif title:
            cursor = conn.execute(
                "SELECT ZTITLE, ZTEXT FROM ZSFNOTE WHERE ZTITLE LIKE ? AND ZTRASHED = 0",
                (f"%{title}%",),
            )
        else:
            return "Provide either title or uid."

        row = cursor.fetchone()
        if not row:
            return f"Note not found: {title or uid}"
        return f"# {row[0]}\n\n{row[1]}"
    finally:
        conn.close()


@mcp.tool()
def bear_list(tag: str = "") -> str:
    """List Bear notes, optionally filtered by tag.

    Args:
        tag: Filter by tag name (e.g. 'manhattan', 'klara')
    """
    conn = get_db()
    try:
        if tag:
            cursor = conn.execute(
                """SELECT DISTINCT n.ZUNIQUEIDENTIFIER, n.ZTITLE
                   FROM ZSFNOTE n
                   JOIN Z_5TAGS jt ON jt.Z_5NOTES = n.Z_PK
                   JOIN ZSFNOTETAG t ON t.Z_PK = jt.Z_13TAGS
                   WHERE n.ZTRASHED = 0 AND LOWER(t.ZTITLE) LIKE ?
                   ORDER BY n.ZMODIFICATIONDATE DESC""",
                (f"%{tag.lower()}%",),
            )
        else:
            cursor = conn.execute(
                "SELECT ZUNIQUEIDENTIFIER, ZTITLE FROM ZSFNOTE WHERE ZTRASHED = 0 ORDER BY ZMODIFICATIONDATE DESC"
            )

        rows = cursor.fetchall()
        if not rows:
            return "No notes found."
        return "\n".join(f"- {row[1]} (id: {row[0]})" for row in rows)
    finally:
        conn.close()


@mcp.tool()
def bear_write(uid: str, text: str, mode: str = "append") -> str:
    """Write to a Bear note via x-callback-url (safe, keeps Bear cache in sync).

    Args:
        uid: Note unique identifier
        text: Text to add
        mode: 'append' (add to end) or 'prepend' (add to beginning)
    """
    if mode not in ("append", "prepend"):
        return "Mode must be 'append' or 'prepend'."

    encoded_text = urllib.parse.quote(text, safe="")
    url = f"bear://x-callback-url/add-text?id={uid}&text={encoded_text}&mode={mode}"

    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "imac", f"open '{url}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"Write failed: {result.stderr.strip()}"

        teammate = get_teammate_name()
        log_write(uid, teammate)
        return f"Written to note {uid} ({mode})."
    except subprocess.TimeoutExpired:
        return "Write failed: SSH timeout."
    except Exception as e:
        return f"Write failed: {e}"


@mcp.tool()
def bear_create(title: str, text: str = "", tag: str = "") -> str:
    """Create a new Bear note via x-callback-url.

    Args:
        title: Note title
        text: Note content
        tag: Tag to apply (e.g. 'manhattan')
    """
    params = {"title": title}
    if text:
        params["text"] = text
    if tag:
        params["tags"] = tag

    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"bear://x-callback-url/create?{query}"

    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "imac", f"open '{url}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"Create failed: {result.stderr.strip()}"
        return f"Note '{title}' created."
    except subprocess.TimeoutExpired:
        return "Create failed: SSH timeout."
    except Exception as e:
        return f"Create failed: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
