#!/bin/bash
# Persistent whiteboard server with auto-save.
# Runs as a launchd service. Starts the server, imports the last saved canvas,
# and exports every 30s to survive restarts.
# Reads .active file for current canvas name. Skips save during .switching.

export HOST=0.0.0.0
export PORT=51850
export PATH=/opt/homebrew/bin:$PATH
export EXPRESS_SERVER_URL="http://127.0.0.1:${PORT}"

CANVAS_DIR="/Users/deepak-macmini/honeybloom/library/whiteboard"
ACTIVE_FILE="${CANVAS_DIR}/.active"
SWITCHING_FILE="${CANVAS_DIR}/.switching"
SERVER_JS="/opt/homebrew/lib/node_modules/mcp-excalidraw-server/dist/server.js"
SERVER_BIN="/opt/homebrew/bin/mcp-excalidraw-server"

get_canvas_file() {
    if [ -f "$ACTIVE_FILE" ]; then
        local name
        name=$(cat "$ACTIVE_FILE")
        echo "${CANVAS_DIR}/${name}.excalidraw"
    else
        echo "${CANVAS_DIR}/canvas.excalidraw"
    fi
}

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting whiteboard server on ${HOST}:${PORT}"

node "$SERVER_JS" &
SERVER_PID=$!

sleep 3

CANVAS_FILE=$(get_canvas_file)
if [ -f "$CANVAS_FILE" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Importing saved canvas from ${CANVAS_FILE}"
    ${SERVER_BIN} import "$CANVAS_FILE" --replace --url "${EXPRESS_SERVER_URL}" 2>&1 || true
fi

cleanup() {
    CANVAS_FILE=$(get_canvas_file)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Saving canvas before shutdown"
    ${SERVER_BIN} export --out "$CANVAS_FILE" --url "${EXPRESS_SERVER_URL}" 2>/dev/null || true
    kill "$SERVER_PID" 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

while true; do
    sleep 30
    [ -f "$SWITCHING_FILE" ] && continue
    # Clear stale lock (>60s)
    if [ -f "$SWITCHING_FILE" ]; then
        age=$(( $(date +%s) - $(stat -f %m "$SWITCHING_FILE") ))
        [ "$age" -gt 60 ] && rm -f "$SWITCHING_FILE"
        continue
    fi
    CANVAS_FILE=$(get_canvas_file)
    ${SERVER_BIN} export --out "$CANVAS_FILE" --url "${EXPRESS_SERVER_URL}" 2>/dev/null || true
done
