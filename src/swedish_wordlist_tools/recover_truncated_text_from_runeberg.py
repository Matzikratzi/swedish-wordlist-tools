from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .jsonl import read_jsonl

DEFAULT_INPUT = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_CACHE = Path("data/cache/runeberg-saol11-6")
DEFAULT_TEXT = Path("reports/saol14-truncated-runeberg-recovery.txt")
DEFAULT_JSON = Path("reports/saol14-truncated-runeberg-recovery.json")
RUNEberg_BASE = "https://runeberg.org/saol/11-6"
SOURCE_TEXT_LIMIT = 50
PAGE_START = 19
PAGE_END = 674

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_SPACE_RE = re.compile(r"\s+")
_WORD_CLEAN_RE = re.compile(r"[^0-9a-zåäöéüæø|\- ]+", re.IGNORECASE)


@dataclass(frozen=True)
class RunebergPage:
    page: int
    text: str
    folded: str


def _plain_html(source: str) -> str:
    source = _SCRIPT_STYLE_RE.sub(" ", source)
    source = source.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    source = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", source, flags=re.IGNORECASE)
    return html.unescape(_TAG_RE.sub(" ", source))


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u00ad", "").replace("·", "")
    value = value.replace("‐", "-").replace("‑", "-").replace("–", "-")
    value = _WORD_CLEAN_RE.sub(" ", value.casefold())
    return _SPACE_RE.sub(" ", value).strip()


def truncated_candidates(rows: Iterable[dict[str, Any]], *, upos: str | None = "NOUN") -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    wanted_upos = upos.upper() if upos else None
    for row in rows:
        text = str(row.get("text") or "")
        if len(text) != SOURCE_TEXT_LIMIT:
            continue
        if wanted_upos and str(row.get("upos") or "").upper() != wanted_upos:
            continue
        selected.append(row)
    return selected


def compound_parts(row: dict[str, Any]) -> tuple[str, str] | None:
    stycke = str(row.get("stycke") or "")
    if "|" not in stycke:
        return None
    clean = unicodedata.normalize("NFKC", stycke).replace("·", "")
    prefix, head = clean.rsplit("|", 1)
    prefix = prefix.replace("|", "").strip()
    head = head.strip()
    if not prefix or not head:
        return None
    return prefix, head


def _context(text: str, needle: str, *, radius: int = 180) -> str:
    folded = text.casefold()
    index = folded.find(needle.casefold())
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return _SPACE_RE.sub(" ", text[start:end]).strip()


def match_row(row: dict[str, Any], pages: Iterable[RunebergPage]) -> dict[str, Any]:
    lemma = str(row.get("normaliserat_ord") or "").strip()
    folded_lemma = _fold(lemma)
    parts = compound_parts(row)

    for page in pages:
        if folded_lemma and folded_lemma in page.folded:
            return {
                "status": "exact_lemma",
                "confidence": "high",
                "runeberg_page": page.page,
                "context": _context(page.text, lemma),
            }

    if parts is not None:
        prefix, head = parts
        folded_prefix = _fold(prefix)
        folded_head = _fold(head)
        suffix_needles = ("-" + folded_head, folded_head)
        for page in pages:
            prefix_index = page.folded.find(folded_prefix)
            if prefix_index < 0:
                continue
            window = page.folded[prefix_index : prefix_index + 1200]
            if any(needle and needle in window for needle in suffix_needles):
                context = _context(page.text, prefix)
                return {
                    "status": "compound_family",
                    "confidence": "medium",
                    "runeberg_page": page.page,
                    "context": context,
                    "compound_prefix": prefix,
                    "compound_head": head,
                }

    return {"status": "not_found", "confidence": "none", "runeberg_page": None, "context": ""}


def _ssl_context() -> ssl.SSLContext:
    """Return a verified HTTPS context, preferring certifi's CA bundle.

    Python.org macOS installations do not always inherit the Keychain CA roots.
    certifi gives urllib a portable verified trust store without disabling TLS
    certificate verification.
    """

    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "swedish-wordlist-tools/1.0 Runeberg recovery"})
    try:
        with urlopen(request, timeout=30, context=_ssl_context()) as response:
            return response.read().decode("utf-8", errors="replace")
    except URLError as error:
        reason = getattr(error, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise RuntimeError(
                "HTTPS-certifikatet kunde inte verifieras. Installera certifi i din venv "
                "med `python -m pip install certifi` och kör igen. TLS-verifiering stängs "
                "inte av av recoveryn."
            ) from error
        raise


def load_pages(cache_dir: Path, *, start: int = PAGE_START, end: int = PAGE_END, delay: float = 0.05) -> list[RunebergPage]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    pages: list[RunebergPage] = []
    for page in range(start, end + 1):
        cached = cache_dir / f"{page:04d}.txt"
        if cached.exists():
            plain = cached.read_text(encoding="utf-8")
        else:
            raw = _fetch(f"{RUNEberg_BASE}/{page:04d}.html")
            plain = _plain_html(raw)
            cached.write_text(plain, encoding="utf-8")
            if delay:
                time.sleep(delay)
        pages.append(RunebergPage(page, plain, _fold(plain)))
    return pages


def build_summary(rows: list[dict[str, Any]], pages: list[RunebergPage]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for row in rows:
        match = match_row(row, pages)
        status = str(match["status"])
        counts[status] = counts.get(status, 0) + 1
        results.append(
            {
                "lemma": str(row.get("normaliserat_ord") or ""),
                "homonym_number": str(row.get("homonr") or ""),
                "record_id": str(row.get("subnr") or row.get("urspr_lopnr") or ""),
                "source_text": str(row.get("text") or ""),
                "stycke": str(row.get("stycke") or ""),
                **match,
            }
        )
    return {"records": len(rows), "status_counts": counts, "rows": results}


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14: Runeberg-evidens för 50-teckenstrunkerade text-fält",
        "",
        "Runeberg SAOL 11 används endast som sekundär evidens. Rapporten ändrar inte SAOL14-data.",
        "exact_lemma = samma uppslagsord hittat i OCR; compound_family = sammansättningsfamilj hittad.",
        "",
        f"Poster: {summary['records']}",
    ]
    for status, count in sorted(summary["status_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"{status}: {count}")
    lines.append("")
    for row in summary["rows"]:
        lines.append(
            f"{row['lemma']} ({row['homonym_number']}) | {row['status']} | confidence={row['confidence']}"
            + (f" | Runeberg {row['runeberg_page']}" if row.get("runeberg_page") else "")
        )
        lines.append(f"  SAOL14: {row['source_text']}")
        if row.get("context"):
            lines.append(f"  OCR: {row['context']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--all-upos", action="store_true", help="Include every UPOS, not only NOUN")
    parser.add_argument("--page-start", type=int, default=PAGE_START)
    parser.add_argument("--page-end", type=int, default=PAGE_END)
    args = parser.parse_args()

    rows = truncated_candidates(list(read_jsonl(args.input)), upos=None if args.all_upos else "NOUN")
    print(f"50-teckenposter att kontrollera: {len(rows)}", flush=True)
    pages = load_pages(args.cache, start=args.page_start, end=args.page_end)
    summary = build_summary(rows, pages)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Resultat: " + ", ".join(f"{key}={value}" for key, value in summary["status_counts"].items()))
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()