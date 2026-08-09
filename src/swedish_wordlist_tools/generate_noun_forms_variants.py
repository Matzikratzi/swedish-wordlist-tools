from __future__ import annotations

import json

from .generate_noun_forms import (
    _write_jsonl,
    build_parser,
    generate_noun_artifact,
    render_comparison,
)
from .jsonl import read_jsonl
from .saol_noun_variants import prepare_noun_variant_records


def main() -> None:
    """Generate canonical noun forms after conservative sibling-variant binding."""

    args = build_parser().parse_args()
    records = prepare_noun_variant_records(read_jsonl(args.saol))
    rows, comparisons, summary = generate_noun_artifact(records)
    _write_jsonl(args.jsonl, rows)
    _write_jsonl(args.comparison, comparisons)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.comparison_text.write_text(
        render_comparison(summary, comparisons),
        encoding="utf-8",
    )
    print(f"Substantivposter: {summary['noun_records']}")
    print(f"Kanoniskt genererade poster: {summary['generated_noun_records']}")
    print(f"Kanoniska formrader: {summary['canonical_form_rows']}")
    print(f"JSONL: {args.jsonl}")
    print(f"Jämförelse: {args.comparison_text}")


if __name__ == "__main__":
    main()
