#!/usr/bin/env bash
set -euo pipefail

start_page=${1:-}
count=${2:-10}

if [[ -z "$start_page" || ! "$start_page" =~ ^[0-9]+$ || ! "$count" =~ ^[0-9]+$ || "$count" -lt 1 ]]; then
    echo "Usage: bash scripts/scan_glyph_batch.sh START_PAGE [COUNT]" >&2
    echo "Example: bash scripts/scan_glyph_batch.sh 29       # pages 29-38" >&2
    echo "         bash scripts/scan_glyph_batch.sh 39 10    # pages 39-48" >&2
    exit 2
fi

end_page=$((start_page + count - 1))
jsonl=${SAOL_JSONL:-../saol14-faksimil.jsonl}
facit=${SAOL_FACIT:-glyphs/saol14-manual-glyph-facit-v2.json}
queue=${SAOL_QUEUE:-/tmp/saol-glyph-review-${start_page}-${end_page}.json}
log=$(mktemp /tmp/saol-glyph-scan-${start_page}-${end_page}.XXXXXX.log)
trap 'rm -f "$log"' EXIT

echo "Scanning pages ${start_page}-${end_page} ..." >&2

PYTHONPATH="${PYTHONPATH:-src}" python -m swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows_shared \
    "$jsonl" \
    --facit "$facit" \
    --start-page "$start_page" \
    --end-page "$end_page" \
    --output "$queue" \
    2>&1 | awk '
        /^scan: page [0-9]+: [0-9]+ rader analyserade,/ {
            rows = $4 + 0
            if (rows % 50 == 0) {
                print
                fflush()
            }
            next
        }
        /^scan: page [0-9]+: [0-9]+ rows need work \/ [0-9]+ rows / {
            print
            fflush()
            next
        }
        /^page [0-9]+ column [0-9]+ row [0-9]+:/ {
            print
            fflush()
            next
        }
        /^scan: [0-9]+ rows need work \/ [0-9]+ scanned rows on [0-9]+ pages$/ {
            summary = $0
            next
        }
        { next }
        END {
            if (summary != "") print summary
        }
    ' | tee "$log"
status=${PIPESTATUS[0]}
if [[ "$status" -ne 0 ]]; then
    exit "$status"
fi

if ! grep -qE '^page [0-9]+ column [0-9]+ row [0-9]+:' "$log"; then
    echo "No rows need work."
fi

echo "Review queue: $queue" >&2
