#!/usr/bin/env bash
# OPS-44: One-time cleanup of all teammate MEMORY.md files and individual memory files.
# Globs actual directories — no hardcoded teammate list.

set -euo pipefail

MEMORY_BASE="$HOME/.claude/projects"
PATTERN="-Users-d-patnaik-honeybloom-*"

cleaned_files=0
cleaned_dirs=0

for memory_dir in "$MEMORY_BASE"/$PATTERN/memory; do
    [ -d "$memory_dir" ] || continue

    # Skip directories that don't have a MEMORY.md (Rio's edge case note)
    [ -f "$memory_dir/MEMORY.md" ] || continue

    teammate_project="$(basename "$(dirname "$memory_dir")")"
    echo "=== $teammate_project ==="

    # Delete individual memory files first (Pattern 4: clear indexed files before index)
    for md_file in "$memory_dir"/*.md; do
        [ -f "$md_file" ] || continue
        filename="$(basename "$md_file")"
        if [ "$filename" = "MEMORY.md" ]; then
            continue
        fi
        echo "  DELETE $filename"
        rm "$md_file"
        ((cleaned_files++))
    done

    # Truncate MEMORY.md (preserve file, wipe contents)
    echo "  WIPE   MEMORY.md"
    : > "$memory_dir/MEMORY.md"
    ((cleaned_dirs++))

    echo ""
done

echo "Done. Wiped $cleaned_dirs MEMORY.md files, deleted $cleaned_files individual memory files."
