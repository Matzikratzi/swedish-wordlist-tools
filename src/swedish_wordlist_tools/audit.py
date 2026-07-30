from __future__ import annotations

import argparse
import html
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .inflect import COMMON_PATTERNS, EXPLICIT_PATTERN_GROUP, GeneratedEntry, generate_entry
from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_OUTPUT = Path("reports/saol14-inflection-audit.html")
DEFAULT_EXAMPLES = 50
DEFAULT_BATCH_SIZE = 5
DEFAULT_SEED = 14


@dataclass(frozen=True)
class AuditRow:
    record_id: str
    lemma: str
    pattern: str
    notation: str
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
    if entry.pattern_group == EXPLICIT_PATTERN_GROUP:
        flags.append("explicit-form")
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
        pattern=entry.pattern_group or entry.pattern,
        notation=entry.pattern,
        forms=entry.forms,
        upos=str(record.get("upos", "")),
        ordkl=str(record.get("ordkl", "")),
        source=str(record.get("source", "")).strip(),
        flags=audit_flags(record, entry),
    )


def pattern_order(patterns: Iterable[str]) -> list[str]:
    preferred = list(COMMON_PATTERNS) + [EXPLICIT_PATTERN_GROUP]
    present = set(patterns)
    return [pattern for pattern in preferred if pattern in present] + sorted(present - set(preferred))


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
        flag_counts.update(row.flags)
        bucket = samples[row.pattern]
        seen = counts[row.pattern]
        if len(bucket) < examples_per_pattern:
            bucket.append(row)
        else:
            position = rng.randrange(seen)
            if position < examples_per_pattern:
                bucket[position] = row
    ordered = {
        pattern: sorted(samples[pattern], key=lambda row: row.lemma.casefold())
        for pattern in pattern_order(samples)
    }
    return ordered, dict(counts), dict(flag_counts)


def _row_key(row: AuditRow) -> str:
    return f"{row.record_id}:{row.notation}:{row.lemma}"


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
    batch_size: int,
    seed: int,
) -> str:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    sections: list[str] = []
    for section_index, pattern in enumerate(pattern_order(samples)):
        rows = samples[pattern]
        body_rows: list[str] = []
        for row_index, row in enumerate(rows):
            key = html.escape(_row_key(row), quote=True)
            flags = " ".join(
                f'<span class="flag">{html.escape(flag)}</span>' for flag in row.flags
            ) or '<span class="muted">inga</span>'
            forms = ", ".join(html.escape(form) for form in row.forms)
            hidden = " audit-hidden" if row_index >= batch_size else ""
            body_rows.append(
                f'<tr class="audit-row{hidden}">'
                f'<td><strong>{html.escape(row.lemma)}</strong><br><span class="muted">{html.escape(row.upos)} · {html.escape(row.ordkl)} · {_source_link(row.source)}</span></td>'
                f'<td><code>{html.escape(row.notation)}</code></td><td>{forms}</td><td>{flags}</td>'
                f'<td class="choice"><label><input type="radio" name="{key}" value="right"> rätt</label>'
                f'<label><input type="radio" name="{key}" value="wrong"> fel</label>'
                f'<label><input type="radio" name="{key}" value="unsure"> osäkert</label></td></tr>'
            )
        visible = min(batch_size, len(rows))
        more_button = (
            f'<button type="button" class="more" data-target="pattern-{section_index}" data-batch="{batch_size}">Nästa {batch_size} exempel</button>'
            if len(rows) > batch_size
            else ""
        )
        all_right_row = (
            f'<tr class="category-actions"><td></td><td></td><td>'
            f'<button type="button" class="all-right" data-target="pattern-{section_index}">Alla rätt</button>'
            f'<span class="muted">markerar synliga obesvarade</span></td><td></td><td></td></tr>'
        )
        sections.append(
            f'<section id="pattern-{section_index}"><h2><code>{html.escape(pattern)}</code></h2>'
            f'<p class="muted">{pattern_counts.get(pattern, 0)} poster totalt; <span class="shown-count">{visible}</span> av {len(rows)} urvalda exempel visas.</p>'
            '<table><thead><tr><th>Lemma</th><th>Notation</th><th>Genererade former</th><th>Flaggor</th><th>Bedömning</th></tr></thead><tbody>'
            + "".join(body_rows)
            + all_right_row
            + f'</tbody></table><p>{more_button}</p></section>'
        )
    flag_summary = "".join(
        f'<li><code>{html.escape(flag)}</code>: {count}</li>'
        for flag, count in sorted(flag_counts.items(), key=lambda item: (-item[1], item[0]))
    ) or "<li>Inga flaggor</li>"
    return f'''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SAOL14 – böjningsgranskning</title>
<style>
body {{ font-family: system-ui,sans-serif; margin:0; background:#f6f7f8; color:#202124 }} main {{ max-width:1400px; margin:auto; padding:24px }}
header {{ position:sticky; top:0; z-index:3; background:#fff; padding:18px 24px; border-bottom:1px solid #ddd }}
table {{ width:100%; border-collapse:collapse; background:#fff }} th,td {{ padding:10px; border:1px solid #ddd; text-align:left; vertical-align:top }} th {{ background:#eef0f2 }}
.choice label {{ display:block; margin-bottom:5px; white-space:nowrap }} .flag {{ display:inline-block; padding:2px 6px; margin:1px; border-radius:999px; background:#ffe7a8 }}
.muted {{ color:#666; font-size:.9em }} .ref {{ white-space:nowrap; font-weight:600 }} .audit-hidden {{ display:none }} button {{ padding:8px 12px; margin-right:8px }}
.summary {{ display:flex; gap:24px; flex-wrap:wrap }} section {{ margin:28px 0 44px }} code {{ white-space:nowrap }}
.category-actions td {{ background:#fafafa; border-top:2px solid #bbb }} .category-actions .muted {{ margin-left:6px }}
</style></head><body><header><h1>SAOL14 – böjningsgranskning</h1><div class="summary">
<span><strong>{sum(pattern_counts.values())}</strong> stödda poster</span><span><strong>{batch_size}</strong> visas först per mönster</span><span>upp till <strong>{examples_per_pattern}</strong> finns per mönster</span><span>slumpfrö <strong>{seed}</strong></span><span id="progress">0 bedömda</span></div>
<p><button type="button" id="export">Exportera bedömningar som JSON</button><button type="button" id="clear">Rensa bedömningar</button></p></header>
<main><section><h2>Automatiska flaggor</h2><ul>{flag_summary}</ul></section>{''.join(sections)}</main>
<script>
const storageKey = 'saol14-inflection-audit-v2';
let reviews = {{}};
try {{ reviews = JSON.parse(localStorage.getItem(storageKey) || '{{}}'); }} catch (_) {{ reviews = {{}}; }}
const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
function refresh() {{ radios.forEach(r => r.checked = reviews[r.name] === r.value); document.getElementById('progress').textContent = Object.keys(reviews).length + ' bedömda'; }}
function saveReviews() {{ localStorage.setItem(storageKey, JSON.stringify(reviews)); refresh(); }}
radios.forEach(r => r.addEventListener('change', () => {{ reviews[r.name] = r.value; saveReviews(); }}));
document.querySelectorAll('.more').forEach(button => button.addEventListener('click', () => {{
  const section = document.getElementById(button.dataset.target); const hidden = Array.from(section.querySelectorAll('.audit-row.audit-hidden')); const batch = Number(button.dataset.batch);
  hidden.slice(0, batch).forEach(row => row.classList.remove('audit-hidden')); section.querySelector('.shown-count').textContent = section.querySelectorAll('.audit-row:not(.audit-hidden)').length;
  if (!section.querySelector('.audit-row.audit-hidden')) button.remove();
}}));
document.querySelectorAll('.all-right').forEach(button => button.addEventListener('click', () => {{
  const section = document.getElementById(button.dataset.target);
  section.querySelectorAll('.audit-row:not(.audit-hidden)').forEach(row => {{
    const right = row.querySelector('input[value="right"]');
    if (right && !reviews[right.name]) reviews[right.name] = 'right';
  }});
  saveReviews();
}}));
document.getElementById('clear').addEventListener('click', () => {{ if (confirm('Rensa alla sparade bedömningar?')) {{ reviews = {{}}; localStorage.removeItem(storageKey); refresh(); }} }});
document.getElementById('export').addEventListener('click', () => {{
  const blob = new Blob([JSON.stringify(reviews, null, 2) + '\\n'], {{type:'application/json'}}); const url = URL.createObjectURL(blob); const link = document.createElement('a');
  link.href = url; link.download = 'saol14-inflection-reviews.json'; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 0);
}});
refresh();
</script></body></html>'''


def build_audit(
    input_path: Path,
    output_path: Path,
    examples_per_pattern: int = DEFAULT_EXAMPLES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    samples, pattern_counts, flag_counts = sample_rows(read_jsonl(input_path), examples_per_pattern, seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_html(samples, pattern_counts, flag_counts, examples_per_pattern, batch_size, seed),
        encoding="utf-8",
    )
    return {
        "output": str(output_path),
        "supported_records": sum(pattern_counts.values()),
        "sampled_records": sum(map(len, samples.values())),
        "patterns": len(pattern_counts),
        "pattern_counts": pattern_counts,
        "flag_counts": flag_counts,
        "examples_per_pattern": examples_per_pattern,
        "batch_size": batch_size,
        "seed": seed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an HTML audit report for generated SAOL14 inflections")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--examples", type=int, default=DEFAULT_EXAMPLES)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_audit(args.input, args.output, args.examples, args.batch, args.seed)
    print(f"Stödda poster: {report['supported_records']}")
    print(f"Granskningsexempel i rapporten: {report['sampled_records']}")
    print(f"Visas först per mönster: {report['batch_size']}")
    print(f"Mönster i rapporten: {report['patterns']}")
    print(f"HTML-rapport: {args.output}")


if __name__ == "__main__":
    main()
