#!/usr/bin/env bash
# Rescue script: restore OpenCode fork binary from GitHub Release
# Usage: chica/scripts/rescue-opencode.sh
set -euo pipefail

RELEASE="v1.14.30-honeybloom-8"
REPO="valaquer/opencode-fork"
BINARY="$HOME/.opencode/bin/opencode"

echo "Downloading OpenCode fork ${RELEASE}..."
mkdir -p "$(dirname "$BINARY")"

gh release download "${RELEASE}" --repo "${REPO}" -p "opencode" -O "$BINARY.tmp" || {
  echo "ERROR: gh CLI not found or not authenticated. Install: brew install gh && gh auth login"
  exit 1
}

chmod +x "$BINARY.tmp"
mv "$BINARY.tmp" "$BINARY"

echo "Verifying..."
"$BINARY" --version
echo "Done. OpenCode fork ${RELEASE} restored."
