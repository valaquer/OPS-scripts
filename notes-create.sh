#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: notes-create.sh <title> <body>" >&2
    exit 1
fi

TITLE="$1"
BODY="$2"
FOLDER="${3:-Notes}"

ssh imac "osascript -e 'tell application \"Notes\" to make new note at folder \"${FOLDER}\" with properties {name:\"${TITLE}\", body:\"${BODY}\"}'"
