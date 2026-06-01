#!/usr/bin/env python3
"""
Honeybloom Reddit — Read-only MCP server.
JSON API with automatic fallback to old.reddit.com HTML scraping.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.2.0"]
# ///

import json
import html as html_mod
import re
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

UA = "honeybloom:reddit-mcp:1.0.0 (by /u/valaquer)"
TIMEOUT = 15

_json_blocked = False

mcp = FastMCP("honeybloom-reddit", log_level="ERROR")


# --- Fetch helpers ---

def _fetch_json(url: str) -> dict:
    """Fetch JSON from Reddit. Raises on error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _fetch_html(url: str) -> str:
    """Fetch HTML from old.reddit.com."""
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


# --- JSON extractors (original path) ---

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


# --- HTML scraping: post listings from old.reddit.com ---

_THING_T3_RE = re.compile(
    r'<div[^>]*class="([^"]*thing[^"]*)"[^>]*id="thing_t3[^"]*"([^>]*)>'
)
_DATA_ATTR_RE = re.compile(r'(data-[\w-]+)="([^"]*)"')
_TITLE_A_RE = re.compile(r'<a[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
_FLAIR_RE = re.compile(r'<span class="linkflairlabel[^"]*"[^>]*title="([^"]*)"')


def _parse_listing_html(html_text: str, limit: int) -> list[dict]:
    """Parse old.reddit.com listing page into post dicts."""
    posts = []
    for m in _THING_T3_RE.finditer(html_text):
        if len(posts) >= limit:
            break
        attrs = dict(_DATA_ATTR_RE.findall(m.group(0)))

        # Extract title from the next <a class="title"> after this div
        title_search = _TITLE_A_RE.search(html_text[m.start():m.start() + 4000])
        title = html_mod.unescape(re.sub(r'<[^>]+>', '', title_search.group(1))).strip() if title_search else ""

        # Extract flair
        flair_search = _FLAIR_RE.search(html_text[m.start():m.start() + 4000])
        flair = html_mod.unescape(flair_search.group(1)) if flair_search else ""

        # Extract selftext from expando
        selftext = ""
        expando_search = re.search(
            r'<div class="[^"]*expando[^"]*"[^>]*>.*?<div class="md"[^>]*>(.*?)</div>',
            html_text[m.start():m.start() + 10000], re.DOTALL
        )
        if expando_search:
            raw = re.sub(r'<[^>]+>', ' ', expando_search.group(1))
            selftext = html_mod.unescape(raw).strip()
            selftext = re.sub(r'\s+', ' ', selftext)

        timestamp = int(attrs.get("data-timestamp", "0")) // 1000
        is_self = attrs.get("data-domain", "").startswith("self.")

        posts.append({
            "title": title,
            "author": attrs.get("data-author", "[deleted]"),
            "selftext": selftext,
            "url": attrs.get("data-url", ""),
            "permalink": "https://www.reddit.com" + attrs.get("data-permalink", ""),
            "score": int(attrs.get("data-score", "0")),
            "num_comments": int(attrs.get("data-comments-count", "0")),
            "created": _ts(timestamp) if timestamp else "unknown",
            "subreddit": attrs.get("data-subreddit", ""),
            "is_self": is_self,
            "is_video": False,
            "is_gallery": attrs.get("data-is-gallery", "false") == "true",
            "over_18": attrs.get("data-nsfw", "false") == "true",
            "flair": flair,
            "source": "html",
        })
    return posts


# --- HTML scraping: search results from old.reddit.com ---

_SEARCH_RESULT_RE = re.compile(
    r'<div[^>]*class="[^"]*search-result search-result-link[^"]*"[^>]*>'
)
_SEARCH_TITLE_RE = re.compile(
    r'<a[^>]*href="([^"]*)"[^>]*class="[^"]*search-title[^"]*"[^>]*>(.*?)</a>', re.DOTALL
)
_SEARCH_AUTHOR_RE = re.compile(r'<a[^>]*class="author[^"]*"[^>]*>([^<]+)</a>')
_SEARCH_SCORE_RE = re.compile(r'(\d+) points?')
_SEARCH_COMMENTS_RE = re.compile(r'(\d+) comments?')
_SEARCH_TIME_RE = re.compile(r'datetime="([^"]*)"')
_SEARCH_SUB_RE = re.compile(r'<a[^>]*class="search-subreddit-link[^"]*"[^>]*>r/([^<]+)</a>')


def _parse_search_html(html_text: str, limit: int) -> list[dict]:
    """Parse old.reddit.com search results page into post dicts."""
    posts = []
    for m in _SEARCH_RESULT_RE.finditer(html_text):
        if len(posts) >= limit:
            break
        chunk = html_text[m.start():m.start() + 3000]

        title_match = _SEARCH_TITLE_RE.search(chunk)
        title = html_mod.unescape(re.sub(r'<[^>]+>', '', title_match.group(2))).strip() if title_match else ""
        permalink = title_match.group(1) if title_match else ""
        if permalink and not permalink.startswith("http"):
            permalink = "https://old.reddit.com" + permalink

        author_match = _SEARCH_AUTHOR_RE.search(chunk)
        score_match = _SEARCH_SCORE_RE.search(chunk)
        comments_match = _SEARCH_COMMENTS_RE.search(chunk)
        time_match = _SEARCH_TIME_RE.search(chunk)
        sub_match = _SEARCH_SUB_RE.search(chunk)

        posts.append({
            "title": title,
            "author": author_match.group(1) if author_match else "[deleted]",
            "selftext": "",
            "url": permalink,
            "permalink": permalink,
            "score": int(score_match.group(1)) if score_match else 0,
            "num_comments": int(comments_match.group(1)) if comments_match else 0,
            "created": time_match.group(1) if time_match else "unknown",
            "subreddit": sub_match.group(1) if sub_match else "",
            "is_self": False,
            "is_video": False,
            "is_gallery": False,
            "over_18": False,
            "flair": "",
            "source": "html",
        })
    return posts


# --- HTML scraping: thread page (post + comments) from old.reddit.com ---

_THING_T1_RE = re.compile(
    r'<div[^>]*id="(thing_t1[^"]*)"[^>]*data-author="([^"]*)"[^>]*>'
)
_SCORE_SPAN_RE = re.compile(
    r'<span class="score[^"]*"[^>]*title="(\d+)"'
)
_DATETIME_RE = re.compile(
    r'datetime="([^"]*)"'
)


def _parse_thread_html(html_text: str, max_comments: int) -> dict:
    """Parse old.reddit.com thread page into post + comments."""

    # --- Post extraction ---
    post_thing = re.search(
        r'<div[^>]*id="thing_t3[^"]*"([^>]*)>',
        html_text
    )
    post_attrs = dict(_DATA_ATTR_RE.findall(post_thing.group(0))) if post_thing else {}

    title_match = re.search(
        r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>',
        html_text
    )
    post_title = html_mod.unescape(re.sub(r'<[^>]+>', '', title_match.group(1))).strip() if title_match else ""

    # Post selftext
    post_selftext = ""
    if post_thing:
        selftext_search = re.search(
            r'<div class="[^"]*expando[^"]*"[^>]*>.*?<div class="md"[^>]*>(.*?)</div>',
            html_text[post_thing.start():post_thing.start() + 20000], re.DOTALL
        )
        if selftext_search:
            raw = re.sub(r'<[^>]+>', ' ', selftext_search.group(1))
            post_selftext = html_mod.unescape(raw).strip()
            post_selftext = re.sub(r'\s+', ' ', post_selftext)

    post_timestamp = int(post_attrs.get("data-timestamp", "0")) // 1000

    post = {
        "title": post_title,
        "author": post_attrs.get("data-author", "[deleted]"),
        "selftext": post_selftext,
        "url": post_attrs.get("data-url", ""),
        "permalink": "https://www.reddit.com" + post_attrs.get("data-permalink", ""),
        "score": int(post_attrs.get("data-score", "0")),
        "num_comments": int(post_attrs.get("data-comments-count", "0")),
        "created": _ts(post_timestamp) if post_timestamp else "unknown",
        "subreddit": post_attrs.get("data-subreddit", ""),
        "source": "html",
    }

    # --- Comment extraction ---
    comments = []
    comment_area_match = re.search(r'<div class=["\']commentarea["\']', html_text)
    if not comment_area_match:
        return {"post": post, "comments": comments}

    comment_html = html_text[comment_area_match.start():]
    child_opens = [m.start() for m in re.finditer(r'<div class="child"', comment_html)]

    for m in _THING_T1_RE.finditer(comment_html):
        if len(comments) >= max_comments:
            break
        pos = m.start()
        author = m.group(2)

        depth = sum(1 for cp in child_opens if cp < pos)
        depth = max(0, depth - 1)

        comment_slice = comment_html[pos:pos + 5000]

        # Score
        score = 0
        score_match = _SCORE_SPAN_RE.search(comment_slice)
        if score_match:
            score = int(score_match.group(1))

        # Timestamp
        created = "unknown"
        time_match = _DATETIME_RE.search(comment_slice)
        if time_match:
            created = time_match.group(1)

        # Body
        body = ""
        body_match = re.search(
            r'<div class="md"[^>]*>(.*?)</div>',
            comment_slice, re.DOTALL
        )
        if body_match:
            raw = re.sub(r'<[^>]+>', ' ', body_match.group(1))
            body = html_mod.unescape(raw).strip()
            body = re.sub(r'\s+', ' ', body)

        comments.append({
            "author": author or "[deleted]",
            "body": body,
            "score": score,
            "created": created,
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

    html_url = url.rstrip("/")
    html_url = html_url.replace("://www.reddit.com", "://old.reddit.com")
    html_url = html_url.replace("://reddit.com", "://old.reddit.com")
    if "://old.reddit.com" not in html_url:
        html_url = "https://old.reddit.com" + urllib.parse.urlparse(html_url).path
    if html_url.endswith(".json"):
        html_url = html_url[:-5]

    try:
        html_text = _fetch_html(html_url)
    except Exception as e:
        return _handle_error(e)

    result = _parse_thread_html(html_text, max_comments)
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

    html_url = f"https://old.reddit.com/r/{sub}/search?q={q}&restrict_sr=on&sort={sort}&limit={limit}"
    try:
        html_text = _fetch_html(html_url)
    except Exception as e:
        return _handle_error(e)

    posts = _parse_search_html(html_text, limit)
    return json.dumps(posts, indent=2)


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

    html_url = f"https://old.reddit.com/r/{sub}/{sort}/"
    try:
        html_text = _fetch_html(html_url)
    except Exception as e:
        return _handle_error(e)

    posts = _parse_listing_html(html_text, limit)
    return json.dumps(posts, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
