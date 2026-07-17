#!/usr/bin/env python3
"""Search Aether conversations and session transcripts for keyword matches."""

import argparse
import json
import glob
import os
import sqlite3
import sys


PROJECT_BASE = os.path.expanduser("~/.claude/projects")
DIR_PREFIX = "-Users-d-patnaik-honeybloom-"
AETHER_DB = "/Users/deepak-macmini/honeybloom/library/aether/aether.db"


def resolve_project_dir(teammate):
    return os.path.join(PROJECT_BASE, f"{DIR_PREFIX}{teammate}")


def teammate_from_cwd():
    cwd = os.getcwd()
    basename = os.path.basename(cwd)
    if os.path.isdir(resolve_project_dir(basename)):
        return basename
    return None


def extract_text(entry):
    """Extract searchable text from a user or assistant transcript entry."""
    msg = entry.get("message", {})
    content = msg.get("content")
    if content is None:
        return ""
    # user: content is a string
    if isinstance(content, str):
        return content
    # assistant: content is a list of blocks
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def make_snippet(text, match_start, match_end, width=120):
    """Create a snippet centered on the match position."""
    # Collapse whitespace for display
    text = " ".join(text.split())
    # Re-find match position in collapsed text
    query_text = text[match_start:match_end] if match_start < len(text) else ""
    # Search in collapsed text since positions may have shifted
    lower_text = text.lower()
    lower_query = query_text.lower()
    pos = lower_text.find(lower_query) if lower_query else match_start
    if pos == -1:
        pos = 0

    # Center around match
    half = (width - len(lower_query)) // 2
    start = max(0, pos - half)
    end = min(len(text), start + width)
    if end - start < width:
        start = max(0, end - width)

    snippet = text[start:end]
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def search_file(filepath, query_lower, results, limit):
    """Search a single .jsonl file, appending matches to results."""
    with open(filepath, "r", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            if len(results) >= limit:
                return
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue

            text = extract_text(entry)
            if not text:
                continue

            text_lower = text.lower()
            match_pos = text_lower.find(query_lower)
            if match_pos == -1:
                continue

            timestamp = entry.get("timestamp", "unknown")
            # Trim timestamp to minutes
            if len(timestamp) > 16:
                timestamp = timestamp[:16] + "Z"

            snippet = make_snippet(text, match_pos, match_pos + len(query_lower))
            results.append(f"{filepath}:{line_num}  [{timestamp}]  {snippet}")


def resolve_aether_rooms(teammate, cursor):
    """Return list of conversationIds the teammate belongs to."""
    rooms = []
    # Direct rooms — messages sent by or to this teammate
    like_pattern = f"direct-{teammate}-%"
    cursor.execute(
        "SELECT DISTINCT conversationId FROM messages WHERE conversationId LIKE ?",
        (like_pattern,)
    )
    for row in cursor.fetchall():
        rooms.append(row[0])
    # Huddle rooms — teammate is in the participants JSON array
    cursor.execute(
        "SELECT id, participants FROM rooms WHERE type = 'huddle'"
    )
    for row in cursor.fetchall():
        try:
            parts = json.loads(row[1])
            if teammate in parts:
                rooms.append(row[0])
        except (json.JSONDecodeError, TypeError):
            continue
    return rooms


def search_aether(query_lower, limit, teammate, room=None):
    """Search Aether messages, returning results list."""
    results = []
    if not os.path.isfile(AETHER_DB):
        print(f"Aether DB not found at {AETHER_DB}", file=sys.stderr)
        return results

    conn = None
    try:
        conn = sqlite3.connect(AETHER_DB)
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.cursor()
        if room:
            conv_ids = [room]
        else:
            conv_ids = resolve_aether_rooms(teammate, cursor)

        if not conv_ids:
            return results

        for cid in conv_ids:
            if len(results) >= limit:
                break
            cursor.execute(
                "SELECT rowid, sender, content, createdAt FROM messages WHERE conversationId = ? AND content IS NOT NULL AND sender != 'system' ORDER BY createdAt ASC",
                (cid,)
            )
            for row in cursor.fetchall():
                if len(results) >= limit:
                    break
                rowid, sender, content, created = row
                if not content:
                    continue
                text_lower = content.lower()
                match_pos = text_lower.find(query_lower)
                if match_pos == -1:
                    continue
                ts = created
                if len(ts) > 16:
                    ts = ts[:16] + "Z"
                snippet = make_snippet(content, match_pos, match_pos + len(query_lower))
                results.append(f"aether:{rowid}  [{ts}]  {sender}: {snippet}")
    except sqlite3.Error as e:
        print(f"Aether DB error: {e}", file=sys.stderr)
    finally:
        if conn:
            conn.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="Search Aether conversations and session transcripts for keywords.")
    parser.add_argument("query", help="Search keyword or phrase")
    parser.add_argument("--teammate", "-t", help="Teammate name (default: from cwd)")
    parser.add_argument("--room", "-r", help="Room ID to search (e.g. direct-chica-20260527)")
    parser.add_argument("--limit", "-l", type=int, default=50, help="Max results (default 50)")
    parser.add_argument("--source", choices=["aether", "jsonl", "all"], default="aether",
                        help="Source to search (default: aether)")
    args = parser.parse_args()

    teammate = args.teammate
    if not teammate:
        teammate = teammate_from_cwd()
        if not teammate:
            print("Could not determine teammate from cwd. Use --teammate.", file=sys.stderr)
            sys.exit(1)

    caller = teammate_from_cwd() or ""
    if teammate == "burt" and caller != "burt":
        print("Access to Burt's transcripts is restricted.", file=sys.stderr)
        sys.exit(1)

    query_lower = args.query.lower()
    results = []

    if args.source in ("aether", "all"):
        results = search_aether(query_lower, args.limit, teammate, args.room)

    if args.source in ("jsonl", "all") and len(results) < args.limit:
        project_dir = resolve_project_dir(teammate)
        if os.path.isdir(project_dir):
            files = sorted(glob.glob(os.path.join(project_dir, "*.jsonl")))
            for filepath in files:
                search_file(filepath, query_lower, results, args.limit)
                if len(results) >= args.limit:
                    break

    if not results:
        print("No matches found.")
        sys.exit(0)

    for line in results:
        print(line)

    print(f"\n{len(results)} match(es) found.", file=sys.stderr)


if __name__ == "__main__":
    main()
