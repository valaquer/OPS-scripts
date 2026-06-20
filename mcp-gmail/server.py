#!/usr/bin/env python3
"""
Honeybloom Gmail — MCP server for Felix.
Search/read/attachments via API. Compose/reply via API drafts (Boss clicks Send in Safari).
Two accounts: deepakpatnaik1@gmail.com and deepakpatnaik1@oovar.ai.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp[cli]>=1.2.0",
#   "google-api-python-client",
#   "google-auth-httplib2",
#   "google-auth-oauthlib",
# ]
# ///

import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from mcp.server.fastmcp import FastMCP

CREDENTIALS_FILE = "/Users/deepak-macmini/honeybloom/library/gmail/credentials.json"
TOKEN_DIR = "/Users/deepak-macmini/honeybloom/library/gmail/tokens"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

ACCOUNTS = {
    "gmail": {"email": "deepakpatnaik1@gmail.com", "token": "gmail.json"},
    "oovar": {"email": "deepakpatnaik1@oovar.ai", "token": "oovar.json"},
}

SAFE_DIRS = [
    os.path.expanduser("~/honeybloom/felix/"),
    "/tmp/",
]

mcp = FastMCP("honeybloom-gmail", log_level="ERROR")


# --- Auth ---

def _get_token_path(account: str) -> str:
    return os.path.join(TOKEN_DIR, ACCOUNTS[account]["token"])


def _get_service(account: str):
    """Return authenticated Gmail API service for the given account."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if account not in ACCOUNTS:
        valid = ", ".join(ACCOUNTS.keys())
        raise ValueError(f"Unknown account '{account}'. Valid accounts: {valid}")

    token_path = _get_token_path(account)

    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"No token for '{account}'. Boss needs to run:\n"
            f"  uv run /Users/deepak-macmini/honeybloom/chica/mcp-gmail/server.py --setup {account}\n"
            f"This opens a browser for OAuth authorization."
        )

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            os.chmod(token_path, 0o600)
        except Exception:
            raise PermissionError(
                f"Token for '{account}' expired and refresh failed. Boss needs to re-authorize:\n"
                f"  uv run /Users/deepak-macmini/honeybloom/chica/mcp-gmail/server.py --setup {account}"
            )

    if not creds.valid:
        raise PermissionError(
            f"Token for '{account}' is invalid. Boss needs to re-authorize:\n"
            f"  uv run /Users/deepak-macmini/honeybloom/chica/mcp-gmail/server.py --setup {account}"
        )

    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def _setup_account(account: str) -> None:
    """Interactive OAuth setup for one account. Opens browser."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if account not in ACCOUNTS:
        valid = ", ".join(ACCOUNTS.keys())
        print(f"Unknown account '{account}'. Valid: {valid}")
        sys.exit(1)

    if not os.path.exists(CREDENTIALS_FILE):
        print(
            f"Missing credentials file: {CREDENTIALS_FILE}\n\n"
            "Setup steps:\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create a project (or select existing)\n"
            "3. Enable Gmail API (APIs & Services > Library > Gmail API)\n"
            "4. Configure OAuth consent screen (External, Testing mode)\n"
            "   - Add both email addresses as test users\n"
            "5. Create credentials: OAuth client ID > Desktop app\n"
            "6. Download JSON and save to:\n"
            f"   {CREDENTIALS_FILE}"
        )
        sys.exit(1)

    os.makedirs(TOKEN_DIR, exist_ok=True)

    email = ACCOUNTS[account]["email"]
    print(f"Opening browser for {email}...")
    print(f"Sign in with: {email}")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    token_path = _get_token_path(account)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    os.chmod(token_path, 0o600)

    print(f"Token saved to {token_path}")
    print(f"Account '{account}' ({email}) is ready.")


# --- MIME helpers ---

def _decode_body(data: str) -> str:
    """Decode base64url-encoded body data from Gmail API."""
    if not data:
        return ""
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> tuple[str, str]:
    """Walk MIME tree. Return (text, html). Uses .get() throughout — no type branching."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime == "text/plain":
        return (_decode_body(body_data), "")
    if mime == "text/html":
        return ("", _decode_body(body_data))

    text, html = "", ""
    for part in payload.get("parts", []):
        t, h = _extract_body(part)
        text = text or t
        html = html or h
    return (text, html)


def _strip_html(html: str) -> str:
    """Basic HTML tag stripping. No external deps."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    return text.strip()


def _get_header(headers: list, name: str) -> str:
    """Extract a header value by name. Case-insensitive."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def _get_attachments_metadata(payload: dict) -> list:
    """Walk MIME tree for attachment parts."""
    attachments = []

    def _walk(part: dict) -> None:
        filename = part.get("filename", "")
        body = part.get("body", {})
        if filename and body.get("attachmentId"):
            attachments.append({
                "id": body["attachmentId"],
                "filename": filename,
                "mime_type": part.get("mimeType", "unknown"),
                "size": body.get("size", 0),
            })
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    return attachments


# --- Draft helpers ---

def _validate_attachments(paths: list[str]) -> list[tuple[str, str, str]]:
    """Validate attachment paths. Returns list of (real_path, filename, mime_type)."""
    validated = []
    total_size = 0

    for path in paths:
        real_path = os.path.realpath(os.path.expanduser(path))

        safe = any(real_path.startswith(d) for d in SAFE_DIRS)
        if not safe:
            allowed = ", ".join(SAFE_DIRS)
            raise ValueError(f"Attachment path must be under one of: {allowed}\nGot: {real_path}")

        if not os.path.isfile(real_path):
            raise FileNotFoundError(f"Attachment not found: {real_path}")

        file_size = os.path.getsize(real_path)
        total_size += file_size

        if total_size > 25 * 1024 * 1024:
            size_mb = total_size / (1024 * 1024)
            raise ValueError(
                f"Total attachment size ({size_mb:.1f} MB) exceeds Gmail's 25 MB limit."
            )

        mime_type, _ = mimetypes.guess_type(real_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        validated.append((real_path, os.path.basename(real_path), mime_type))

    return validated


def _build_mime_message(
    from_email: str,
    to: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, str, str]] | None = None,
    reply_headers: dict | None = None,
) -> str:
    """Build MIME message and return base64url-encoded raw string for Gmail API."""
    if attachments:
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText(body, "plain", "utf-8"))

        for real_path, filename, mime_type in attachments:
            maintype, subtype = mime_type.split("/", 1)
            with open(real_path, "rb") as f:
                part = MIMEBase(maintype, subtype)
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject

    if reply_headers:
        if reply_headers.get("message_id"):
            msg["In-Reply-To"] = reply_headers["message_id"]
            msg["References"] = reply_headers["message_id"]

    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


# --- MCP Tools ---

@mcp.tool()
def search_gmail(query: str, account: str = "gmail", max_results: int = 10) -> str:
    """Search Gmail using Gmail's native search syntax.

    Args:
        query: Gmail search query (e.g., "from:otelo subject:Rechnung after:2026/01/01")
        account: Which account to search — "gmail" (deepakpatnaik1@gmail.com) or "oovar" (deepakpatnaik1@oovar.ai)
        max_results: Max results to return (default 10, max 50)
    """
    max_results = min(max_results, 50)

    try:
        service = _get_service(account)
    except Exception as e:
        return str(e)

    try:
        response = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
    except Exception as e:
        return f"Gmail API error: {e}"

    messages = response.get("messages", [])
    if not messages:
        return "No messages found."

    results = []
    for msg in messages:
        try:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"]
            ).execute()
            headers = detail.get("payload", {}).get("headers", [])
            results.append({
                "id": detail["id"],
                "thread_id": detail.get("threadId", ""),
                "subject": _get_header(headers, "Subject"),
                "from": _get_header(headers, "From"),
                "to": _get_header(headers, "To"),
                "date": _get_header(headers, "Date"),
                "snippet": detail.get("snippet", ""),
            })
        except Exception:
            results.append({"id": msg["id"], "error": "Failed to fetch metadata"})

    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def read_gmail(message_id: str, account: str = "gmail") -> str:
    """Read a full email by message ID.

    Args:
        message_id: Gmail message ID (from search_gmail results)
        account: Which account — "gmail" or "oovar"
    """
    try:
        service = _get_service(account)
    except Exception as e:
        return str(e)

    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    except Exception as e:
        return f"Gmail API error: {e}"

    headers = msg.get("payload", {}).get("headers", [])
    payload = msg.get("payload", {})

    text_body, html_body = _extract_body(payload)
    body = text_body if text_body else _strip_html(html_body) if html_body else "(empty body)"

    attachments = _get_attachments_metadata(payload)

    result = {
        "id": msg["id"],
        "thread_id": msg.get("threadId", ""),
        "subject": _get_header(headers, "Subject"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "cc": _get_header(headers, "Cc"),
        "date": _get_header(headers, "Date"),
        "body": body,
        "labels": msg.get("labelIds", []),
    }

    if attachments:
        result["attachments"] = attachments

    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def download_attachment(message_id: str, attachment_id: str, save_to: str, account: str = "gmail") -> str:
    """Download an email attachment to a local file.

    Args:
        message_id: Gmail message ID
        attachment_id: Attachment ID (from read_gmail results)
        save_to: Local file path to save the attachment
        account: Which account — "gmail" or "oovar"
    """
    # Path normalization — prevent traversal (Rio nit #1)
    real_path = os.path.realpath(os.path.expanduser(save_to))
    safe = any(real_path.startswith(d) for d in SAFE_DIRS)
    if not safe:
        allowed = ", ".join(SAFE_DIRS)
        return f"save_to path must be under one of: {allowed}\nGot: {real_path}"

    try:
        service = _get_service(account)
    except Exception as e:
        return str(e)

    try:
        att = service.users().messages().attachments().get(
            userId="me", id=attachment_id, messageId=message_id
        ).execute()
    except Exception as e:
        return f"Gmail API error: {e}"

    data = att.get("data", "")
    if not data:
        return "Attachment data is empty."

    padded = data + "=" * (4 - len(data) % 4)
    file_bytes = base64.urlsafe_b64decode(padded)

    os.makedirs(os.path.dirname(real_path), exist_ok=True)
    with open(real_path, "wb") as f:
        f.write(file_bytes)

    size_kb = len(file_bytes) / 1024
    return f"Saved to {real_path} ({size_kb:.1f} KB)"


@mcp.tool()
def compose_gmail(
    to: str, subject: str, body: str,
    account: str = "gmail", attachments: list[str] | None = None,
) -> str:
    """Create a Gmail draft and open it in Safari. Boss reviews and clicks Send.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
        account: Which account to send from — "gmail" or "oovar"
        attachments: Optional list of local file paths to attach
    """
    if account not in ACCOUNTS:
        valid = ", ".join(ACCOUNTS.keys())
        return f"Unknown account '{account}'. Valid: {valid}"

    email = ACCOUNTS[account]["email"]

    try:
        validated_attachments = _validate_attachments(attachments) if attachments else None
    except (ValueError, FileNotFoundError) as e:
        return str(e)

    raw = _build_mime_message(
        from_email=email, to=to, subject=subject, body=body,
        attachments=validated_attachments,
    )

    try:
        service = _get_service(account)
    except Exception as e:
        return str(e)

    try:
        draft = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "insufficient" in error_str.lower():
            return (
                f"Insufficient permissions. Gmail compose scope required.\n"
                f"Boss needs to re-authorize:\n"
                f"  uv run /Users/deepak-macmini/honeybloom/chica/mcp-gmail/server.py --setup {account}"
            )
        return f"Gmail API error: {e}"

    drafts_url = f"https://mail.google.com/mail/?authuser={email}#drafts"

    try:
        subprocess.run(["open", drafts_url], check=True, timeout=5)
    except Exception:
        pass  # URL open failure is non-fatal

    att_note = f" with {len(attachments)} attachment(s)" if attachments else ""
    return (
        f"Draft created{att_note} — it's at the top of the Drafts folder ({email}).\n"
        f"Subject: {subject}\n"
        f"Boss reviews and clicks Send."
    )


@mcp.tool()
def reply_gmail(
    message_id: str, body: str,
    account: str = "gmail", attachments: list[str] | None = None,
) -> str:
    """Create a Gmail reply draft and open it in Safari. Boss reviews and clicks Send.

    Args:
        message_id: Gmail message ID to reply to
        body: Reply body text
        account: Which account — "gmail" or "oovar"
        attachments: Optional list of local file paths to attach
    """
    if account not in ACCOUNTS:
        valid = ", ".join(ACCOUNTS.keys())
        return f"Unknown account '{account}'. Valid: {valid}"

    email = ACCOUNTS[account]["email"]

    try:
        validated_attachments = _validate_attachments(attachments) if attachments else None
    except (ValueError, FileNotFoundError) as e:
        return str(e)

    # Fetch original for thread ID + headers
    try:
        service = _get_service(account)
        original = service.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["Subject", "Message-ID", "From", "To", "Reply-To"]
        ).execute()
    except Exception as e:
        return f"Failed to fetch original message: {e}"

    thread_id = original.get("threadId", message_id)
    headers = original.get("payload", {}).get("headers", [])
    subject = _get_header(headers, "Subject")
    original_msg_id = _get_header(headers, "Message-ID")
    original_from = _get_header(headers, "From")
    original_to = _get_header(headers, "To")
    reply_to = _get_header(headers, "Reply-To")

    # Determine reply recipient — priority chain:
    # 1. Reply-To header (sender explicitly set a reply address)
    # 2. If From matches Boss's account email (sent mail) → use original To
    # 3. Default: use From (normal reply to received mail)
    if reply_to:
        recipient = reply_to
    elif original_from and email in original_from:
        # Boss sent this message — reply to the original recipient
        if not original_to:
            return "Cannot determine reply recipient — sent message has no To header."
        recipient = original_to
    elif original_from:
        recipient = original_from
    else:
        return "Cannot determine reply recipient — original message has no From header."

    re_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    reply_headers = {}
    if original_msg_id:
        reply_headers["message_id"] = original_msg_id

    raw = _build_mime_message(
        from_email=email, to=recipient, subject=re_subject, body=body,
        attachments=validated_attachments, reply_headers=reply_headers,
    )

    try:
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw, "threadId": thread_id}},
        ).execute()
    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "insufficient" in error_str.lower():
            return (
                f"Insufficient permissions. Gmail compose scope required.\n"
                f"Boss needs to re-authorize:\n"
                f"  uv run /Users/deepak-macmini/honeybloom/chica/mcp-gmail/server.py --setup {account}"
            )
        return f"Gmail API error: {e}"

    drafts_url = f"https://mail.google.com/mail/?authuser={email}#drafts"

    try:
        subprocess.run(["open", drafts_url], check=True, timeout=5)
    except Exception:
        pass  # URL open failure is non-fatal

    att_note = f" with {len(attachments)} attachment(s)" if attachments else ""
    return (
        f"Reply draft created{att_note} — it's at the top of the Drafts folder ({email}).\n"
        f"Subject: {re_subject}\n"
        f"Boss reviews and clicks Send."
    )


# --- CLI entry point ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Honeybloom Gmail MCP Server")
    parser.add_argument("--setup", metavar="ACCOUNT",
                        help="Run OAuth setup for an account (gmail or oovar)")
    args = parser.parse_args()

    if args.setup:
        _setup_account(args.setup)
    else:
        mcp.run(transport="stdio")
