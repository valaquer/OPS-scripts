#!/bin/bash
# Single-invocation Bitwarden retrieval.
# Bypasses sandbox session persistence bug by doing unlock + get in one shell.
# Usage: bw-get.sh <item-name> [field]
# Master password read from macOS Keychain (service: bitwarden-master).

BW="/opt/homebrew/bin/bw"
ITEM="$1"
FIELD="${2:-password}"

if [[ -z "$ITEM" ]]; then
    echo "Usage: bw-get.sh <item-name> [field]" >&2
    exit 1
fi

MASTER=$(security find-generic-password -s "bitwarden-master" -w 2>/dev/null)
if [[ -z "$MASTER" ]]; then
    echo "Error: No master password in Keychain (service: bitwarden-master)" >&2
    echo "Run: security add-generic-password -s \"bitwarden-master\" -a \"bw\" -w" >&2
    exit 1
fi

SESSION=$($BW unlock "$MASTER" --raw 2>/dev/null)
if [[ -z "$SESSION" ]]; then
    echo "Error: Vault unlock failed" >&2
    exit 1
fi

$BW get "$FIELD" "$ITEM" --session "$SESSION" 2>/dev/null
