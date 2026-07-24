#!/bin/bash
set -euo pipefail

ROOT="/Users/deepak-macmini/honeybloom/library"
ORG="$ROOT/ORG.md"
CSV="$ROOT/scripts/janus-config.csv"
LAUNCHER="$ROOT/scripts/kitty-open-teammate.sh"
FAIL46="$ROOT/scripts/failover-to-46.sh"
FAILV4="$ROOT/scripts/failover-to-v4.sh"

before_hash="$(shasum -a 256 "$CSV" | awk '{print $1}')"

# Sourcing must expose helpers without running production main.
source "$LAUNCHER"
ORG_CACHE="$ORG"
[ "$(get_group_info chica)" = "GROUP rio rio chica natalie" ]
[ "$(get_group_info burt)" = "GROUP burt burt" ]

# Count the actual execution-boundary calls for singleton, all-existing, partial,
# fresh, and --solo semantics without touching Kitty or Aether.
launch_calls=0
huddle_calls=0
launch_tab() { launch_calls=$((launch_calls + 1)); }
apply_tab_color() { :; }
start_group_huddle() { huddle_calls=$((huddle_calls + 1)); }

launch_group test burt "burt" ""
[ "$launch_calls:$huddle_calls" = "1:0" ]
launch_calls=0; huddle_calls=0
launch_group test rio "rio chica natalie" $'rio\nchica\nnatalie'
[ "$launch_calls:$huddle_calls" = "0:0" ]
launch_calls=0; huddle_calls=0
launch_group test rio "rio chica natalie" $'rio\nchica'
[ "$launch_calls:$huddle_calls" = "1:1" ]
launch_calls=0; huddle_calls=0
launch_group test rio "rio chica natalie" ""
[ "$launch_calls:$huddle_calls" = "3:1" ]
launch_calls=0; huddle_calls=0
launch_solo test chica ""
[ "$launch_calls:$huddle_calls" = "1:0" ]

hosts46="$(ORG_MD_OVERRIDE="$ORG" JANUS_CSV_OVERRIDE="$CSV" bash -c 'source "$1"; validate_org_and_print_hosts' _ "$FAIL46")"
hosts_v4="$(ORG_MD_OVERRIDE="$ORG" JANUS_CSV_OVERRIDE="$CSV" bash -c 'source "$1"; validate_org_and_print_hosts' _ "$FAILV4")"
[ "$hosts46" = "$hosts_v4" ]
[ "$(printf '%s\n' "$hosts46" | wc -l | tr -d ' ')" = 10 ]

for script in "$FAIL46" "$FAILV4"; do
    temp_csv="$(mktemp /tmp/janus-lifecycle.XXXXXX)"
    cp "$CSV" "$temp_csv"
    before_roles="$(awk -F, 'NR>1{print $1 ":" $2}' "$temp_csv")"
    before_machines="$(awk -F, 'NR>1{print $1 ":" $9}' "$temp_csv")"
    natalie_before="$(awk -F, '$1=="natalie"{print}' "$temp_csv")"

    ORG_MD_OVERRIDE="$ORG" JANUS_CSV_OVERRIDE="$temp_csv" HONEYBLOOM_TEST_MODE=1 bash -c \
        'source "$1"; validate_csv "$JANUS_CSV"; rewrite_csv "$JANUS_CSV"; validate_csv "$JANUS_CSV"' _ "$script"

    [ "$(awk -F, 'NR>1{print $1 ":" $2}' "$temp_csv")" = "$before_roles" ]
    [ "$(awk -F, 'NR>1{print $1 ":" $9}' "$temp_csv")" = "$before_machines" ]
    [ "$(awk -F, '$1=="natalie"{print}' "$temp_csv")" = "$natalie_before" ]
    [ "$(awk -F, 'NF!=9{bad++} END{print bad+0}' "$temp_csv")" = 0 ]
done

bad_csv="$(mktemp /tmp/janus-lifecycle-bad.XXXXXX)"
cp "$CSV" "$bad_csv"
sed '2s/,[^,]*$//' "$bad_csv" > "${bad_csv}.broken"
mv "${bad_csv}.broken" "$bad_csv"
if ORG_MD_OVERRIDE="$ORG" JANUS_CSV_OVERRIDE="$bad_csv" bash -c 'source "$1"; validate_csv' _ "$FAIL46" 2>/dev/null; then
    echo "malformed eight-column CSV passed preflight" >&2
    exit 1
fi

for defect in duplicate unknown missing; do
    invalid_csv="$(mktemp /tmp/janus-lifecycle-identity.XXXXXX)"
    case "$defect" in
        duplicate) awk -F, 'BEGIN{OFS=","} NR==3{$1="gunnar"} {print}' "$CSV" > "$invalid_csv" ;;
        unknown) awk -F, 'BEGIN{OFS=","} NR==2{$1="unknown"} {print}' "$CSV" > "$invalid_csv" ;;
        missing) awk 'NR!=2' "$CSV" > "$invalid_csv" ;;
    esac
    if ORG_MD_OVERRIDE="$ORG" JANUS_CSV_OVERRIDE="$invalid_csv" bash -c 'source "$1"; validate_csv' _ "$FAIL46" 2>/dev/null; then
        echo "$defect teammate identity defect passed preflight" >&2
        exit 1
    fi
done

if ORG_MD_OVERRIDE="$ORG" HONEYBLOOM_TEST_MODE=1 bash -c 'source "$1"; rewrite_csv "$CANONICAL_JANUS_CSV"' _ "$FAIL46" 2>/dev/null; then
    echo "test mode allowed canonical Janus mutation" >&2
    exit 1
fi

after_hash="$(shasum -a 256 "$CSV" | awk '{print $1}')"
[ "$before_hash" = "$after_hash" ]

echo "janus lifecycle fixtures passed"
