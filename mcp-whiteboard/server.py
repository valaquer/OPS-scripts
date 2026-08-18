#!/usr/bin/env python3
"""
Honeybloom Whiteboard — Canvas file management MCP server.
Manages multiple named canvases in library/whiteboard/.
Works alongside the Excalidraw drawing MCP (separate server).
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp[cli]>=1.2.0"]
# ///

import json
import os
import subprocess
import time
from pathlib import Path
from mcp.server.fastmcp import FastMCP

WHITEBOARD_DIR = Path("/Users/deepak-macmini/honeybloom/library/whiteboard")
ACTIVE_FILE = WHITEBOARD_DIR / ".active"
SWITCHING_FILE = WHITEBOARD_DIR / ".switching"
WRITE_LEDGER = Path("/var/tmp/whiteboard-write-ledger.json")
SERVER_URL = "http://127.0.0.1:51850"
CLI = "/opt/homebrew/bin/mcp-excalidraw-server"

mcp = FastMCP("honeybloom-whiteboard-mgmt")


def _log_write(teammate: str = "unknown"):
    try:
        entries = json.loads(WRITE_LEDGER.read_text()) if WRITE_LEDGER.exists() else []
    except Exception:
        entries = []
    entries.append({"teammate": teammate, "ts": time.time()})
    WRITE_LEDGER.write_text(json.dumps(entries))


def _active_canvas() -> str:
    if ACTIVE_FILE.exists():
        return ACTIVE_FILE.read_text().strip()
    return "canvas"


def _set_active(name: str):
    ACTIVE_FILE.write_text(name)


def _canvas_path(name: str) -> Path:
    return WHITEBOARD_DIR / f"{name}.excalidraw"


def _cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [CLI] + args + ["--url", SERVER_URL],
        capture_output=True, text=True, timeout=15
    )


def _save_current():
    name = _active_canvas()
    path = _canvas_path(name)
    _cli(["export", "--out", str(path)])


@mcp.tool()
def whiteboard_list() -> str:
    """List all whiteboard canvases with sizes, dates, and which one is active."""
    active = _active_canvas()
    canvases = []
    for f in sorted(WHITEBOARD_DIR.glob("*.excalidraw")):
        stat = f.stat()
        name = f.stem
        canvases.append({
            "name": name,
            "active": name == active,
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
        })
    if not canvases:
        return json.dumps({"canvases": [], "message": "No canvases found. Use whiteboard_new to create one."})
    return json.dumps({"canvases": canvases, "active": active}, indent=2)


@mcp.tool()
def whiteboard_open(name: str) -> str:
    """Save the current canvas and switch to a different named canvas."""
    path = _canvas_path(name)
    if not path.exists():
        return json.dumps({"error": f"Canvas '{name}' not found. Use whiteboard_list to see available canvases."})

    SWITCHING_FILE.touch()
    try:
        _save_current()
        _cli(["clear", "--yes"])
        result = _cli(["import", str(path), "--replace"])
        _set_active(name)
    finally:
        SWITCHING_FILE.unlink(missing_ok=True)

    return json.dumps({"opened": name, "message": f"Switched to canvas '{name}'."})


@mcp.tool()
def whiteboard_new(name: str) -> str:
    """Save the current canvas and create a new empty canvas."""
    path = _canvas_path(name)
    if path.exists():
        return json.dumps({"error": f"Canvas '{name}' already exists. Choose a different name or use whiteboard_open."})

    SWITCHING_FILE.touch()
    try:
        _save_current()
        _cli(["clear", "--yes"])
        _set_active(name)
        _cli(["export", "--out", str(path)])
    finally:
        SWITCHING_FILE.unlink(missing_ok=True)

    return json.dumps({"created": name, "message": f"New canvas '{name}' created and active."})


@mcp.tool()
def whiteboard_delete(name: str) -> str:
    """Delete a named canvas. Cannot delete the currently active canvas."""
    active = _active_canvas()
    if name == active:
        return json.dumps({"error": f"Cannot delete the active canvas '{name}'. Switch to a different canvas first."})

    path = _canvas_path(name)
    if not path.exists():
        return json.dumps({"error": f"Canvas '{name}' not found."})

    path.unlink()
    return json.dumps({"deleted": name, "message": f"Canvas '{name}' deleted."})


@mcp.tool()
def whiteboard_rename(old_name: str, new_name: str) -> str:
    """Rename a canvas file. Updates the active tracker if renaming the active canvas."""
    old_path = _canvas_path(old_name)
    new_path = _canvas_path(new_name)

    if not old_path.exists():
        return json.dumps({"error": f"Canvas '{old_name}' not found."})
    if new_path.exists():
        return json.dumps({"error": f"Canvas '{new_name}' already exists."})

    old_path.rename(new_path)
    if _active_canvas() == old_name:
        _set_active(new_name)

    return json.dumps({"renamed": {"from": old_name, "to": new_name}})


if __name__ == "__main__":
    mcp.run()
