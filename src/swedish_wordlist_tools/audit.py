from __future__ import annotations

import argparse
import html
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .inflect import COMMON_PATTERNS, GeneratedEntry, generate_entry
from .jsonl import read_jsonl


DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_OUTPUT = Path("reports/saol14-inflection-audit.html")
DEFAULT_EXAMPLES = 50
DEFAULT_SEED = 14


@dataclass(frozen=True)
class AuditRow:
    record_id: str
    lemma: str
    pattern: str
    forms: tuple[str, ...]
    upos: str
    ordkl: str
    source: str
    flags: tuple[str, ...]


def audit_flags(record: dict[str, Any], entry: GeneratedEntry) -> tuple[str, ...]:
    flags: list[str] = []
    lemma = entry.lemma

    if str(record.get("upos", "")).strip() == "X":
        flags.append("upos-X")
    if any(char.isupper() for char in lemma):
        flags.append("versal")
    if "-" in lemma:
        flags.append("bindestreck")
    if " " in lemma:
        flags.append("flera-ord")
    if any(not form.startswith(lemma) for form in entry.forms[1:]):
        flags.append("stamändring")
    if any(len(form) > 45 for form in entry.forms):
        flags.append("mycket-lång")

    return tuple(flags)


def make_audit_row(record: dict[str, Any]) -> AuditRow | None:
    entry = generate_entry(record)
    if entry is None:
        return None
    return AuditRow(
        record_id=str(record.get("id") or record.get("subnr") or ""),
        lemma=entry.lemma,
        pattern=entry.pattern,
        forms=entry.forms,
        upos=str(record.get("upos", "")),
        ordkl=str(record.get("ordkl", "")),
        source=str(record.get("source", "")).strip(),
        flags=audit_flags(record, entry),
    )


def sample_rows(
    records: Iterable[dict[str, Any]], examples_per_pattern: int, seed: int
) -> tuple[dict[str, list[AuditRow]], dict[str, int], dict[str, int]]:
    if examples_per_pattern < 1:
        raise ValueError("examples_per_pattern must be at least 1")

    rng = random.Random(seed)
    samples: dict[str, list[AuditRow]] = defaultdict(list)
    counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()

    for record in records:
        row = make_audit_row(record)
        if row is None:
            continue

        counts[row.pattern] += 1
        for flag in row.flags:
            flag_counts[flag] += 1

        bucket = samples[row.pattern]
        seen = counts[row.pattern]
        if len(bucket) < examples_per_pattern:
            bucket.append(row)
        else:
            position = rng.randrange(seen)
            if position < examples_per_pattern:
                bucket[position] = row

    ordered = {
        pattern: sorted(samples.get(pattern, []), key=lambda row: row.lemma.casefold())
        for pattern in COMMON_PATTERNS
    }
    return ordered, dict(counts), dict(flag_counts)


def _row_key(row: AuditRow) -> str:
    return f"{row.record_id}:{row.pattern}:{row.lemma}"


def _source_link(source: str) -> str:
    if not source:
        return '<span class="muted">ingen ref</span>'
    escaped = html.escape(source, quote=True)
    return f'<a class="ref" href="{escaped}" target="_blank" rel="noopener noreferrer">Ref ↗</a>'


def render_html(
    samples: dict[str, list[AuditRow]],
    pattern_counts: dict[str, int],
    flag_counts: dict[str, int],
    examples_per_pattern: int,
    seed: int,
) -> str:
    total_supported = sum(pattern_counts.values())
    sections: list[str] = []

    for pattern in COMMON_PATTERNS:
        rows = samples.get(pattern, [])
        body_rows: list[str] = []
        for row in rows:
            key = html.escape(_row_key(row), quote=True)
            flags = " ".join(
                f'<span class="flag">{html.escape(flag)}</span>' for flag in row.flags
            ) or '<span class="muted">inga</span>'
            forms = ", ".join(html.escape(form) for form in row.forms)
            source_link = _source_link(row.source)
            body_rows.append(
                "<tr>"
                f"<td><strong>{html.escape(row.lemma)}</strong><br>"
                f'<span class="muted">{html.escape(row.upos)} · {html.escape(row.ordkl)} · {source_link}</span></td>'
                f"<td><code>{html.escape(row.pattern)}</code></td>"
                f"<td>{forms}</td>"
                f"<td>{flags}</td>"
                '<td class="choice">'
                f'<label><input type="radio" name="{key}" value="right"> rätt</label>'
                f'<label><input type="radio" name="{key}" value="wrong"> fel</label>'
                f'<label><input type="radio" name="{key}" value="unsure"> osäkert</label>'
                "</td>"
                "</tr>"
            )

        sections.append(
            f'<section id="pattern-{len(sections)}">'
            f"<h2><code>{html.escape(pattern)}</code></h2>"
            f'<p class="muted">{pattern_counts.get(pattern, 0)} poster totalt; '
            f"{len(rows)} granskningsexempel.</p>"
            "<table><thead><tr><th>Lemma</th><th>Notation</th><th>Genererade former</th>"
            "<th>Flaggor</th><th>Bedömning</th></tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table></section>"
        )

    flag_summary = "".join(
        f"<li><code>{html.escape(flag)}</code>: {count}</li>"
        for flag, count in sorted(flag_counts.items(), key=lambda item: (-item[1], item[0]))
    ) or "<li>Inga flaggor</li>"

    return f"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SAOL14 – granskning av genererade böjningar</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #f6f7f8; color: #202124; }}
main {{ max-width: 1400px; margin: auto; padding: 24px; }}
header {{ position: sticky; top: 0; z-index: 3; background: #fff; padding: 18px 24px; border-bottom: 1px solid #ddd; }}
h1 {{ margin: 0 0 8px; }} section {{ margin: 28px 0 44px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; }}
th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; vertical-align: top; }}
th {{ background: #eef0f2; }} code {{ white-space: nowrap; }}
.choice label {{ display: block; margin-bottom: 5px; white-space: nowrap; }}
.flag {{ display: inline-block; padding: 2px 6px; margin: 1px; border-radius: 999px; background: #ffe7a8; }}
.muted {{ color: #666; font-size: .9em; }}
.ref {{ white-space: nowrap; font-weight: 600; }}
button {{ padding: 8px 12px; margin-right: 8px; }}
.summary {{ display: flex; gap: 24px; flex-wrap: wrap; }}
@media (max-width: 800px) {{ main {{ padding: 12px; }} table {{ font-size: .88rem; }} th, td {{ padding: 6px; }} }}
</style>
</head>
<body>
<header>
<h1>SAOL14 – böjningsgranskning</h1>
<div class="summary">
<span><strong>{total_supported}</strong> stödda poster</span>
<span><strong>{examples_per_pattern}</strong> exempel per mönster</span>
<span>slumpfrö <strong>{seed}</strong></span>
<span id="progress">0 bedömda</span>
</div>
<p><button id="export">Exportera bedömningar som JSON</button><button id="clear">Rensa bedömningar</button></p>
</header>
<main>
<section><h2>Automatiska flaggor</h2><ul>{flag_summary}</ul></section>
{''.join(sections)}
</main>
<script>
const storageKey = 'saol14-inflection-audit-v1';
const radios = [...document.querySelectorAll('input[type=radio]')];
let reviews = JSON.parse(localStorage.getItem(storageKey) || '{{}}');
function refresh() {{
  radios.forEach(radio => {{ radio.checked = reviews[radio.name] === radio.value; }});
  document.getElementById('progress').textContent = Object.keys(reviews).length + ' bedömda';
}}
radios.forEach(radio => radio.addEventListener('change', () => {{
  reviews[radio.name] = radio.value;
  localStorage.setItem(storageKey, JSON.stringify(reviews));
  refresh();
}}));
document.getElementById('clear').addEventListener('click', () => {{
  if (confirm('Rensa alla sparade bedömningar?')) {{ reviews = {{}}; localStorage.removeItem(storageKey); refresh(); }}
}});
document.getElementById('export').addEventListener('click', () => {{
  const blob = new Blob([JSON.stringify(reviews, null, 2) + '\n'], {{type: 'application/json'}});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'saol14-inflection-reviews.json';
  link.click();
  URL.revokeObjectURL(link.href);
}});
refresh();
</script>
</body>
</html>
"""


def build_audit(
    input_path: Path,
    output_path: Path,
    examples_per_pattern: int = DEFAULT_EXAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    samples, pattern_counts, flag_counts = sample_rows(
        read_jsonl(input_path), examples_per_pattern, seed
    )
    document = render_html(
        samples, pattern_counts, flag_counts, examples_per_pattern, seed
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return {
        "output": str(output_path),
        "supported_records": sum(pattern_counts.values()),
        "sampled_records": sum(len(rows) for rows in samples.values()),
        "patterns": len([count for count in pattern_counts.values() if count]),
        "pattern_counts": pattern_counts,
        "flag_counts": flag_counts,
        "examples_per_pattern": examples_per_pattern,
        "seed": seed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an HTML audit report for generated SAOL14 inflections"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--examples", type=int, default=DEFAULT_EXAMPLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_audit(args.input, args.output, args.examples, args.seed)
    print(f"Stödda poster: {report['supported_records']}")
    print(f"Granskningsexempel: {report['sampled_records']}")
    print(f"Mönster i rapporten: {report['patterns']}")
    print(f"HTML-rapport: {args.output}")


if __name__ == "__main__":
    main()
