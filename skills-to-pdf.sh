#!/bin/bash
# Batch convert SKILL.md files to PDF using md-to-pdf
# Usage: bash skills-to-pdf.sh

set -euo pipefail

OUTPUT_BASE="/Users/d.patnaik/honeybloom/print-skills"
TMPDIR_BASE=$(mktemp -d)
trap "rm -rf $TMPDIR_BASE" EXIT

CSS='body { font-family: "JetBrainsMono Nerd Font Mono"; font-size: 14px; line-height: 1.5; }
code, pre { font-size: 11px; background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }
pre { padding: 8px 12px; }
h1 { font-size: 22px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
h2 { font-size: 18px; }
h3 { font-size: 16px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 12px; }
th { background: #f5f5f5; font-weight: bold; }
hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
ul, ol { padding-left: 20px; }
li { margin: 2px 0; }
blockquote { border-left: 3px solid #ccc; padding-left: 12px; color: #555; }'

PDF_OPTS='{"format":"A4","margin":{"top":"20mm","right":"20mm","bottom":"20mm","left":"20mm"}}'

TEAMMATES=("gunnar" "samara" "hana" "guru")
TOTAL=0
SKIPPED=0
SEEN_FILE="$TMPDIR_BASE/.seen"
touch "$SEEN_FILE"

convert_file() {
    local src="$1"
    local dest_dir="$2"
    local dest_name="$3"

    # Resolve symlinks
    local real_src
    real_src=$(readlink -f "$src" 2>/dev/null || echo "$src")

    if [ ! -f "$real_src" ]; then
        echo "  WARN: File not found: $src" >&2
        return 1
    fi

    if [ ! -s "$real_src" ]; then
        echo "  WARN: Empty file: $src" >&2
        return 1
    fi

    # Copy to temp dir for conversion (md-to-pdf outputs next to source)
    local tmpfile="$TMPDIR_BASE/${dest_name}.md"
    cp "$real_src" "$tmpfile"

    # Strip YAML frontmatter
    if head -1 "$tmpfile" | grep -q '^---$'; then
        # Find the closing --- and remove everything up to and including it
        local end_line
        end_line=$(tail -n +2 "$tmpfile" | grep -n '^---$' | head -1 | cut -d: -f1)
        if [ -n "$end_line" ]; then
            tail -n +$((end_line + 2)) "$tmpfile" > "${tmpfile}.tmp"
            mv "${tmpfile}.tmp" "$tmpfile"
        fi
    fi

    # Convert
    md-to-pdf --css "$CSS" --pdf-options "$PDF_OPTS" "$tmpfile" 2>/dev/null
    local pdf_out="$TMPDIR_BASE/${dest_name}.pdf"

    if [ -f "$pdf_out" ]; then
        mkdir -p "$dest_dir"
        mv "$pdf_out" "$dest_dir/${dest_name}.pdf"
        echo "  ${dest_name}.pdf"
        return 0
    else
        echo "  WARN: Conversion failed for $dest_name" >&2
        return 1
    fi
}

# Flat output — all PDFs go to OUTPUT_BASE directly, deduplicated
mkdir -p "$OUTPUT_BASE"

for name in "${TEAMMATES[@]}"; do
    skills_dir="/Users/d.patnaik/honeybloom/${name}/.claude/skills"

    echo ""
    echo "$(echo "$name" | tr '[:lower:]' '[:upper:]'):"

    if [ ! -d "$skills_dir" ]; then
        echo "  WARN: Skills dir not found: $skills_dir" >&2
        continue
    fi

    for skill_path in "$skills_dir"/*/; do
        [ -d "$skill_path" ] || continue
        skill_name=$(basename "$skill_path")

        # Dedup — skip if already converted
        if grep -qx "$skill_name" "$SEEN_FILE"; then
            echo "  (skip) ${skill_name} — already converted"
            SKIPPED=$((SKIPPED + 1))
            continue
        fi

        md_file="${skill_path}SKILL.md"
        real_path=$(readlink -f "$skill_path" 2>/dev/null || echo "$skill_path")
        if [ -d "$real_path" ]; then
            md_file="${real_path}/SKILL.md"
        fi

        if convert_file "$md_file" "$OUTPUT_BASE" "$skill_name"; then
            echo "$skill_name" >> "$SEEN_FILE"
            TOTAL=$((TOTAL + 1))
        fi
    done
done

# Extra files
echo ""
echo "EXTRA:"
extra_src="/Users/d.patnaik/honeybloom/lea/ai-pm-tools-landscape-2026.md"
if convert_file "$extra_src" "$OUTPUT_BASE" "ai-pm-tools-landscape-2026"; then
    TOTAL=$((TOTAL + 1))
fi

echo ""
echo "Done. ${TOTAL} unique PDFs (${SKIPPED} duplicates skipped) in ${OUTPUT_BASE}/"
