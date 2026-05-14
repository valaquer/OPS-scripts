#!/usr/bin/env python3
"""Search raw session transcript files (.jsonl) for keyword matches."""

import argparse
import json
import glob
import os
import sys


PROJECT_BASE = os.path.expanduser("~/.claude/projects")
DIR_PREFIX = "-Users-d-patnaik-honeybloom-"


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


def main():
    parser = argparse.ArgumentParser(description="Search session transcripts for keywords.")
    parser.add_argument("query", help="Search keyword or phrase")
    parser.add_argument("--teammate", "-t", help="Teammate name (default: from cwd)")
    parser.add_argument("--limit", "-l", type=int, default=50, help="Max results (default 50)")
    args = parser.parse_args()

    teammate = args.teammate
    if not teammate:
        teammate = teammate_from_cwd()
        if not teammate:
            print("Could not determine teammate from cwd. Use --teammate.", file=sys.stderr)
            sys.exit(1)

    project_dir = resolve_project_dir(teammate)
    if not os.path.isdir(project_dir):
        print(f"No project directory found for '{teammate}': {project_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(glob.glob(os.path.join(project_dir, "*.jsonl")))
    if not files:
        print(f"No transcript files found for '{teammate}'.")
        sys.exit(0)

    query_lower = args.query.lower()
    results = []

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
