#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-$HOME/saol14-ocr-test/left.png}"
OUT="${2:-/tmp/saol14-left}"

if [[ ! -f "$IMAGE" ]]; then
  echo "Image not found: $IMAGE" >&2
  exit 1
fi

tesseract "$IMAGE" "$OUT" -l swe --psm 6 hocr >/dev/null 2>&1

echo "hOCR: ${OUT}.hocr"
echo
echo "--- lines around abrovink ---"
grep -i -C 4 -E 'abro|vink|vinsch' "${OUT}.hocr" || true

echo
echo "--- style-related markup seen ---"
grep -oE '<(strong|em|b|i)([ >])' "${OUT}.hocr" | sort | uniq -c || true
