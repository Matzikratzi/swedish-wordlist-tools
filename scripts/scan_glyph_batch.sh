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

# Do not put awk or another filter between the scanner and the terminal.
# Python already flushes every progress line; tee mirrors the same live stream
# to a temporary log so we can still decide whether any rows need review.
set +e
PYTHONPATH="${PYTHONPATH:-src}" python -u -m swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows_shared \
    "$jsonl" \
    --facit "$facit" \
    --start-page "$start_page" \
    --end-page "$end_page" \
    --output "$queue" \
    2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e
if [[ "$status" -ne 0 ]]; then
    exit "$status"
fi

if ! grep -qE '^page [0-9]+ column [0-9]+ row [0-9]+:' "$log"; then
    echo "No rows need work."
fi

echo "Review queue: $queue" >&2
