#!/usr/bin/env python3
"""
Honeybloom Bear — Read/write MCP server for Bear note collaboration.
Reads from iMac Bear DB via SSH (no iCloud sync delay).
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
IMAC_BEAR_DB = r"~/Library/Group\ Containers/9K33E3U3T4.net.shinyfrog.bear/Application\ Data/database.sqlite"
IMAC_SSH_OPTS = [
    "ssh",
    "-o", "ControlMaster=auto",
    "-o", "ControlPath=/tmp/bear-watcher-ssh",
    "-o", "ControlPersist=300",
    "-o", "ConnectTimeout=3",
    "-o", "BatchMode=yes",
    "imac",
]
WRITE_LEDGER_PATH = "/var/tmp/bear-write-ledger.json"

mcp = FastMCP("honeybloom-bear")


def ssh_query(sql: str) -> str:
    result = subprocess.run(
        IMAC_SSH_OPTS + [f'sqlite3 {IMAC_BEAR_DB} "{sql}"'],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def get_db():
    return sqlite3.connect(f"file:{BEAR_DB}?mode=ro", uri=True)


def get_teammate_name():
    cwd = os.getcwd()
    parts = cwd.split("/honeybloom/")
    if len(parts) > 1:
        return parts[1].split("/")[0]
    return "unknown"


def log_write(uid: str, teammate: str):
    import time
    try:
        ledger = {}
        if os.path.exists(WRITE_LEDGER_PATH):
            with open(WRITE_LEDGER_PATH) as f:
                ledger = json.load(f)
        ledger[uid] = {"teammate": teammate, "ts": time.time()}
        with open(WRITE_LEDGER_PATH, "w") as f:
            json.dump(ledger, f)
    except Exception:
        pass


def find_note_by_title(title: str) -> "str | None":
    """Find a note by exact title (case-insensitive). Returns UID or None."""
    safe_title = title.replace("'", "''")
    sql = f"SELECT ZUNIQUEIDENTIFIER FROM ZSFNOTE WHERE ZTITLE = '{safe_title}' COLLATE NOCASE AND ZTRASHED = 0 LIMIT 1"
    try:
        output = ssh_query(sql).strip()
        return output if output else None
    except Exception:
        return None


@mcp.tool()
def bear_read(title: str = "", uid: str = "") -> str:
    """Read a Bear note by title or unique identifier.

    Args:
        title: Note title to search for (case-insensitive)
        uid: Note unique identifier (takes priority over title)
    """
    if not uid and not title:
        return "Provide either title or uid."

    if uid:
        sql = f"SELECT ZTITLE, ZTEXT FROM ZSFNOTE WHERE ZUNIQUEIDENTIFIER = '{uid}' AND ZTRASHED = 0"
    else:
        safe_title = title.replace("'", "''")
        sql = f"SELECT ZTITLE, ZTEXT FROM ZSFNOTE WHERE ZTITLE LIKE '%{safe_title}%' AND ZTRASHED = 0"

    try:
        output = ssh_query(sql)
        if not output.strip():
            return f"Note not found: {title or uid}"
        parts = output.split("|", 1)
        if len(parts) == 2:
            return f"# {parts[0]}\n\n{parts[1]}"
        return output
    except Exception as e:
        return f"Read failed: {e}"


@mcp.tool()
def bear_list(tag: str = "") -> str:
    """List Bear notes, optionally filtered by tag.

    Args:
        tag: Filter by tag name (e.g. 'manhattan', 'klara')
    """
    if tag:
        safe_tag = tag.lower().replace("'", "''")
        sql = (
            "SELECT DISTINCT n.ZUNIQUEIDENTIFIER, n.ZTITLE "
            "FROM ZSFNOTE n "
            "JOIN Z_5TAGS jt ON jt.Z_5NOTES = n.Z_PK "
            "JOIN ZSFNOTETAG t ON t.Z_PK = jt.Z_13TAGS "
            f"WHERE n.ZTRASHED = 0 AND LOWER(t.ZTITLE) LIKE '%{safe_tag}%' "
            "ORDER BY n.ZMODIFICATIONDATE DESC"
        )
    else:
        sql = "SELECT ZUNIQUEIDENTIFIER, ZTITLE FROM ZSFNOTE WHERE ZTRASHED = 0 ORDER BY ZMODIFICATIONDATE DESC"

    try:
        output = ssh_query(sql)
        if not output.strip():
            return "No notes found."
        lines = []
        for line in output.strip().split("\n"):
            parts = line.split("|", 1)
            if len(parts) == 2:
                lines.append(f"- {parts[1]} (id: {parts[0]})")
        return "\n".join(lines) if lines else "No notes found."
    except Exception as e:
        return f"List failed: {e}"


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
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "imac", f"open -g '{url}'"],
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
    """Create a new Bear note via x-callback-url. If a note with the same title
    already exists, appends to it instead of creating a duplicate.

    Args:
        title: Note title
        text: Note content
        tag: Tag to apply (e.g. 'manhattan')
    """
    existing_uid = find_note_by_title(title)
    if existing_uid:
        if not text:
            return f"Note '{title}' already exists (id: {existing_uid}). No text to append."
        result = bear_write(existing_uid, text, mode="append")
        tag_note = f" Tag '{tag}' not applied -- check existing note's tags." if tag else ""
        return f"Note '{title}' already exists -- appended to existing note (id: {existing_uid}).{tag_note}"

    params = {"title": title}
    if text:
        params["text"] = text
    if tag:
        params["tags"] = tag

    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"bear://x-callback-url/create?{query}"

    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", "imac", f"open -g '{url}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"Create failed: {result.stderr.strip()}"
        return f"Note '{title}' created."
    except subprocess.TimeoutExpired:
        return "Create failed: SSH timeout."
    except Exception as e:
        return f"Create failed: {e}"


@mcp.tool()
def bear_delete(uid: str) -> str:
    """Trash a Bear note (recoverable from Bear's trash).

    Args:
        uid: Note unique identifier
    """
    url = f"bear://x-callback-url/trash?id={uid}"
    try:
        result = subprocess.run(
            IMAC_SSH_OPTS + [f"open -g '{url}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"Delete failed: {result.stderr.strip()}"
        teammate = get_teammate_name()
        log_write(uid, teammate)
        return f"Note {uid} moved to trash."
    except subprocess.TimeoutExpired:
        return "Delete failed: SSH timeout."
    except Exception as e:
        return f"Delete failed: {e}"


@mcp.tool()
def bear_edit(uid: str, old_text: str, new_text: str) -> str:
    """Surgically edit a Bear note by replacing old_text with new_text.

    Args:
        uid: Note unique identifier
        old_text: Text to find in the note
        new_text: Replacement text
    """
    try:
        sql = f"SELECT ZTEXT FROM ZSFNOTE WHERE ZUNIQUEIDENTIFIER = '{uid}' AND ZTRASHED = 0"
        output = ssh_query(sql).strip()
        if not output:
            return f"Note not found: {uid}"

        if old_text not in output:
            return f"old_text not found in note."

        updated = output.replace(old_text, new_text, 1)
        encoded = urllib.parse.quote(updated, safe="")
        url = f"bear://x-callback-url/add-text?id={uid}&text={encoded}&mode=replace_all"

        result = subprocess.run(
            IMAC_SSH_OPTS + [f"open -g '{url}'"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"Edit failed: {result.stderr.strip()}"

        teammate = get_teammate_name()
        log_write(uid, teammate)
        return f"Note {uid} edited."
    except subprocess.TimeoutExpired:
        return "Edit failed: SSH timeout."
    except Exception as e:
        return f"Edit failed: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
