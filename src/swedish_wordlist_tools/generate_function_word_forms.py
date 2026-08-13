from __future__ import annotations

import re
from typing import Any

from .saol_surface import clean_saol_word

_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_WORD_RE = re.compile(r"[A-Za-zÅÄÖåäöÉéÜü-]+")


def function_class(record: dict[str, Any]) -> str:
    head = str(record.get("ordkl") or "").split("<", 1)[0].strip().casefold()
    if re.search(r"(?:^|\s)(?:best\.|obest\.)\s+artikel(?=\s|$)", head):
        return "DET"
    if re.search(r"(?:^|\s)infinitivmärke(?=\s|$)", head):
        return "PART"
    return ""


def _article_forms(text: str) -> list[dict[str, str]]:
    cleaned = _BRACKET_RE.sub("", text or "")
    forms: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(written: str, slot: str) -> None:
        word = clean_saol_word(written)
        if not word or word.casefold() in seen:
            return
        seen.add(word.casefold())
        forms.append({
            "written_form": word,
            "slot": slot,
            "provenance": "explicit_article_notation",
            "source_token": written,
        })

    neuter = re.search(r"(?:^|[;,])\s*n\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", cleaned, re.IGNORECASE)
    if neuter:
        add(neuter.group(1), "neuter")

    plural = re.search(r"(?:^|[;,])\s*pl\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", cleaned, re.IGNORECASE)
    if plural:
        add(plural.group(1), "plural")

    colloquial = re.search(r"(?:^|[,;])\s*vard\.\s*([A-Za-zÅÄÖåäöÉéÜü-]+)", cleaned, re.IGNORECASE)
    if colloquial:
        add(colloquial.group(1), "colloquial")

    return forms


def generated_row(record: dict[str, Any]) -> dict[str, Any] | None:
    upos = function_class(record)
    if not upos:
        return None
    lemma = clean_saol_word(record.get("ord")) or clean_saol_word(record.get("normaliserat_ord"))
    if not lemma:
        return None

    forms = [{
        "written_form": lemma,
        "slot": "lemma",
        "provenance": "lemma_only_function_word",
        "source_token": "",
    }]
    if upos == "DET":
        forms.extend(_article_forms(str(record.get("text") or "")))

    return {"target_upos": upos, "forms": forms}
