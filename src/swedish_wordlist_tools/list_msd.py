from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .saldo import read_saldo_analyses

DEFAULT_SALDO = Path("data/raw/saldom.xml")


def inventory_msd(path: Path) -> dict[str, Any]:
    """Count every raw SALDO MSD value, globally and by UPOS."""
    analyses_by_lemma = read_saldo_analyses(path)
    seen_entries: set[str] = set()
    total = Counter()
    by_upos: dict[str, Counter[str]] = defaultdict(Counter)
    word_forms = 0

    for analyses in analyses_by_lemma.values():
        for analysis in analyses:
            identity = analysis.entry_id or repr(analysis)
            if identity in seen_entries:
                continue
            seen_entries.add(identity)
            upos = analysis.upos or "UNKNOWN"
            for word_form in analysis.word_forms:
                msd = word_form.msd or "(saknas)"
                total[msd] += 1
                by_upos[upos][msd] += 1
                word_forms += 1

    return {
        "lexical_entries": len(seen_entries),
        "word_forms": word_forms,
        "unique_msd": len(total),
        "msd": [
            {"msd": msd, "count": count}
            for msd, count in sorted(total.items(), key=lambda item: (-item[1], item[0]))
        ],
        "by_upos": {
            upos: [
                {"msd": msd, "count": count}
                for msd, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            ]
            for upos, counts in sorted(by_upos.items())
        },
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"LexicalEntry: {report['lexical_entries']}",
        f"WordForm: {report['word_forms']}",
        f"Unika msd-koder: {report['unique_msd']}",
        "",
        "Alla msd-koder:",
    ]
    for row in report["msd"]:
        lines.append(f"{row['count']:>9}  {row['msd']}")

    for upos, rows in report["by_upos"].items():
        lines.extend(("", f"{upos}:"))
        for row in rows:
            lines.append(f"{row['count']:>9}  {row['msd']}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventera alla faktiska msd-koder i en SALDO-XML-fil"
    )
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--json", dest="json_path", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = inventory_msd(args.saldo)
    print(format_text(report), end="")
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
