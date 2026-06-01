#!/usr/bin/env python3
"""
Honeybloom Reddit — Read-only MCP server.
JSON API with automatic fallback to old.reddit.com HTML/RSS scraping.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.2.0"]
# ///

import json
import html as html_mod
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

UA = "honeybloom:reddit-mcp:1.0.0 (by /u/valaquer)"
TIMEOUT = 15
ATOM_NS = "http://www.w3.org/2005/Atom"

_json_blocked = False

mcp = FastMCP("honeybloom-reddit", log_level="ERROR")


# --- Fetch helpers ---

def _fetch_json(url: str) -> dict:
    """Fetch JSON from Reddit. Raises on error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _fetch_text(url: str) -> str:
    """Fetch raw text (HTML or RSS) from old.reddit.com."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode()


def _is_blocked(e: Exception) -> bool:
    """Check if the error is a 403 block."""
    return isinstance(e, urllib.error.HTTPError) and e.code == 403


def _handle_error(e: Exception) -> str:
    """Convert exceptions to clear status strings."""
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 429:
            return "Rate limited by Reddit. Wait and retry."
        if e.code == 403:
            return "Blocked by Reddit (403). Check if subreddit is private or quarantined."
        return f"Reddit returned HTTP {e.code}."
    if isinstance(e, urllib.error.URLError):
        if "timed out" in str(e).lower():
            return "Request timed out (15s). Reddit may be slow — retry."
        return f"Connection error: {e.reason}"
    return f"Unexpected error: {e}"


def _ts(utc: float) -> str:
    """Unix timestamp to human-readable."""
    if not utc:
        return "unknown"
    return datetime.fromtimestamp(utc, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --- JSON extractors (existing) ---

def _extract_post(data: dict) -> dict:
    """Universal field extraction from a Reddit JSON post (t3)."""
    return {
        "title": data.get("title", ""),
        "author": data.get("author", "[deleted]"),
        "selftext": data.get("selftext", ""),
        "url": data.get("url", ""),
        "permalink": "https://www.reddit.com" + data.get("permalink", ""),
        "score": data.get("score", 0),
        "num_comments": data.get("num_comments", 0),
        "created": _ts(data.get("created_utc", 0)),
        "subreddit": data.get("subreddit", ""),
        "is_self": data.get("is_self", False),
        "is_video": data.get("is_video", False),
        "is_gallery": data.get("is_gallery", False),
        "over_18": data.get("over_18", False),
        "flair": data.get("link_flair_text", ""),
    }


def _flatten_comments(children: list, max_comments: int) -> tuple[list, int]:
    """Depth-first flatten of comment tree from JSON."""
    result = []
    more_count = 0

    def _walk(children: list, depth: int) -> None:
        nonlocal more_count
        for child in children:
            if len(result) >= max_comments:
                return
            kind = child.get("kind", "")
            if kind == "more":
                more_count += child.get("data", {}).get("count", 0)
                continue
            if kind != "t1":
                continue
            d = child.get("data", {})
            result.append({
                "author": d.get("author", "[deleted]"),
                "body": d.get("body", ""),
                "score": d.get("score", 0),
                "created": _ts(d.get("created_utc", 0)),
                "depth": depth,
            })
            replies = d.get("replies", "")
            if isinstance(replies, dict):
                _walk(replies.get("data", {}).get("children", []), depth + 1)

    _walk(children, 0)
    return result, more_count


# --- RSS parser for post listings ---

def _parse_rss_posts(xml_text: str) -> list[dict]:
    """Parse old.reddit.com Atom RSS feed into post dicts."""
    root = ET.fromstring(xml_text)
    posts = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        author_el = entry.find(f"{{{ATOM_NS}}}author")
        author_name = ""
        if author_el is not None:
            name_el = author_el.find(f"{{{ATOM_NS}}}name")
            if name_el is not None and name_el.text:
                author_name = name_el.text.lstrip("/u/")
        content_el = entry.find(f"{{{ATOM_NS}}}content")
        link_el = entry.find(f"{{{ATOM_NS}}}link")
        updated_el = entry.find(f"{{{ATOM_NS}}}updated")

        selftext = ""
        if content_el is not None and content_el.text:
            selftext = html_mod.unescape(content_el.text)
            selftext = selftext.replace("<table>", "").replace("</table>", "")
            selftext = selftext.replace("<tr>", "").replace("</tr>", "")
            selftext = selftext.replace("<td>", "").replace("</td>", "")

        permalink = ""
        if link_el is not None:
            permalink = link_el.get("href", "")

        posts.append({
            "title": title_el.text if title_el is not None and title_el.text else "",
            "author": author_name or "[deleted]",
            "selftext": selftext.strip(),
            "url": permalink,
            "permalink": permalink,
            "score": 0,
            "num_comments": 0,
            "created": updated_el.text if updated_el is not None and updated_el.text else "unknown",
            "subreddit": "",
            "is_self": False,
            "is_video": False,
            "is_gallery": False,
            "over_18": False,
            "flair": "",
            "source": "rss",
        })
    return posts


# --- HTML parser for thread pages (post + comments) ---

def _parse_thread_html(html_text: str, max_comments: int) -> dict:
    """Parse old.reddit.com thread HTML into post + comments."""
    import re

    # Extract post data from thing_t3 data attributes
    post_match = re.search(
        r'<div[^>]*class="[^"]*thing[^"]*"[^>]*id="thing_t3[^"]*"[^>]*'
        r'data-author="([^"]*)"[^>]*>',
        html_text
    )
    post_author = post_match.group(1) if post_match else "[deleted]"

    # Extract title
    title_match = re.search(
        r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>',
        html_text
    )
    post_title = html_mod.unescape(title_match.group(1)) if title_match else ""

    # Extract post selftext from the first usertext-body md div after the post thing
    post_selftext = ""
    selftext_match = re.search(
        r'thing_t3.*?<div class="(?:md|usertext-body)[^"]*"[^>]*>(.*?)</div>',
        html_text, re.DOTALL
    )
    if selftext_match:
        raw = selftext_match.group(1)
        raw = re.sub(r'<[^>]+>', ' ', raw)
        post_selftext = html_mod.unescape(raw).strip()
        post_selftext = re.sub(r'\s+', ' ', post_selftext)

    post = {
        "title": post_title,
        "author": post_author,
        "selftext": post_selftext,
        "permalink": "",
        "score": 0,
        "num_comments": 0,
        "source": "html",
    }

    # Extract comments using regex on thing_t1 divs
    comments = []
    # Find all comment things with their nesting context
    comment_pattern = re.compile(
        r'<div[^>]*class="([^"]*thing[^"]*)"[^>]*id="(thing_t1[^"]*)"[^>]*'
        r'data-author="([^"]*)"[^>]*>',
    )

    # Track depth by finding the sitetable nesting
    # Each level of comments is inside a div class="sitetable listing" > div class="child"
    child_opens = [m.start() for m in re.finditer(r'<div class="child"', html_text)]
    child_positions = sorted(child_opens)

    for m in comment_pattern.finditer(html_text):
        if len(comments) >= max_comments:
            break
        pos = m.start()
        author = m.group(3)

        # Depth = number of "child" divs that opened before this comment's position
        # minus the ones that opened before the comment area
        depth = sum(1 for cp in child_positions if cp < pos)
        # Subtract the base level (comments area itself has a child div)
        depth = max(0, depth - 1)

        # Extract comment body: find the next md div after this comment
        body_search = re.search(
            r'<div class="md"[^>]*>(.*?)</div>',
            html_text[pos:pos + 5000], re.DOTALL
        )
        body = ""
        if body_search:
            raw = body_search.group(1)
            raw = re.sub(r'<[^>]+>', ' ', raw)
            body = html_mod.unescape(raw).strip()
            body = re.sub(r'\s+', ' ', body)

        comments.append({
            "author": author or "[deleted]",
            "body": body,
            "score": 0,
            "created": "unknown",
            "depth": depth,
        })

    return {"post": post, "comments": comments}


# --- Tools ---

@mcp.tool()
def get_thread(url: str, max_comments: int = 50) -> str:
    """Fetch a Reddit thread (post + comments) by URL or permalink.

    Args:
        url: Reddit thread URL (e.g., https://www.reddit.com/r/CharacterAI/comments/...)
        max_comments: Maximum comments to return (default 50)
    """
    global _json_blocked

    # Try JSON first (unless already known blocked)
    if not _json_blocked:
        json_url = url.rstrip("/")
        if not json_url.endswith(".json"):
            json_url += ".json"
        try:
            data = _fetch_json(json_url)
            if isinstance(data, list) and len(data) >= 2:
                post_children = data[0].get("data", {}).get("children", [])
                if post_children:
                    post = _extract_post(post_children[0].get("data", {}))
                    comment_children = data[1].get("data", {}).get("children", [])
                    comments, more_count = _flatten_comments(comment_children, max_comments)
                    result = {"post": post, "comments": comments}
                    if more_count > 0 or len(comments) >= max_comments:
                        extra = more_count if more_count > 0 else "unknown"
                        result["note"] = f"Showing {len(comments)} comments ({extra} additional not loaded)"
                    return json.dumps(result, indent=2)
        except Exception as e:
            if _is_blocked(e):
                _json_blocked = True
            else:
                return _handle_error(e)

    # Fallback: old.reddit.com HTML scraping
    html_url = url.rstrip("/")
    # Rewrite to old.reddit.com
    html_url = html_url.replace("://www.reddit.com", "://old.reddit.com")
    html_url = html_url.replace("://reddit.com", "://old.reddit.com")
    if "://old.reddit.com" not in html_url:
        html_url = "https://old.reddit.com" + urllib.parse.urlparse(html_url).path
    # Remove .json suffix if present
    if html_url.endswith(".json"):
        html_url = html_url[:-5]

    try:
        html_text = _fetch_text(html_url)
    except Exception as e:
        return _handle_error(e)

    result = _parse_thread_html(html_text, max_comments)
    if result["comments"]:
        result["note"] = f"Scraped from old.reddit.com — scores and timestamps unavailable."
    else:
        result["note"] = "Scraped from old.reddit.com — no comments found on this page."
    return json.dumps(result, indent=2)


@mcp.tool()
def search_posts(subreddit: str, query: str, sort: str = "relevance", limit: int = 25) -> str:
    """Search posts in a subreddit.

    Args:
        subreddit: Subreddit name (e.g., "CharacterAI" or "r/CharacterAI")
        query: Search query
        sort: Sort order: relevance, hot, top, new, comments (default: relevance)
        limit: Number of results (default 25, max 100)
    """
    global _json_blocked
    limit = min(limit, 100)
    sub = subreddit.removeprefix("r/").strip("/")
    q = urllib.parse.quote(query)

    # Try JSON first
    if not _json_blocked:
        json_url = f"https://www.reddit.com/r/{sub}/search.json?q={q}&restrict_sr=on&sort={sort}&limit={limit}"
        try:
            data = _fetch_json(json_url)
            children = data.get("data", {}).get("children", [])
            posts = [_extract_post(c.get("data", {})) for c in children]
            return json.dumps(posts, indent=2)
        except Exception as e:
            if _is_blocked(e):
                _json_blocked = True
            else:
                return _handle_error(e)

    # Fallback: old.reddit.com RSS
    rss_url = f"https://old.reddit.com/r/{sub}/search.rss?q={q}&restrict_sr=on&sort={sort}&limit={limit}"
    try:
        xml_text = _fetch_text(rss_url)
    except Exception as e:
        return _handle_error(e)

    posts = _parse_rss_posts(xml_text)
    return json.dumps(posts[:limit], indent=2)


@mcp.tool()
def get_posts(subreddit: str, sort: str = "hot", limit: int = 25) -> str:
    """List posts from a subreddit.

    Args:
        subreddit: Subreddit name (e.g., "CharacterAI" or "r/CharacterAI")
        sort: Sort order: hot, new, top, rising (default: hot)
        limit: Number of posts (default 25, max 100)
    """
    global _json_blocked
    limit = min(limit, 100)
    sub = subreddit.removeprefix("r/").strip("/")

    # Try JSON first
    if not _json_blocked:
        json_url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}"
        try:
            data = _fetch_json(json_url)
            children = data.get("data", {}).get("children", [])
            posts = [_extract_post(c.get("data", {})) for c in children]
            return json.dumps(posts, indent=2)
        except Exception as e:
            if _is_blocked(e):
                _json_blocked = True
            else:
                return _handle_error(e)

    # Fallback: old.reddit.com RSS
    rss_url = f"https://old.reddit.com/r/{sub}/{sort}/.rss"
    try:
        xml_text = _fetch_text(rss_url)
    except Exception as e:
        return _handle_error(e)

    posts = _parse_rss_posts(xml_text)
    return json.dumps(posts[:limit], indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
