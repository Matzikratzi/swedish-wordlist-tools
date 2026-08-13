from __future__ import annotations

from typing import Any, Iterable


def _source(
    *,
    article_id: str,
    heading: str,
    heading_type: str,
    variant_lemma: str = "",
    variant_mode: str = "",
) -> dict[str, str]:
    """Return one canonical source record for a generated SAOL form."""

    result = {
        "article_id": article_id,
        "heading": heading,
        "heading_type": heading_type,
    }
    if variant_lemma:
        result["variant_lemma"] = variant_lemma
    if variant_mode:
        result["variant_mode"] = variant_mode
    return result


def generated_from(form: dict[str, Any]) -> list[dict[str, str]]:
    """Return canonical provenance for one generated form.

    ``generated_from`` is the canonical representation.  The older
    ``variant_sources``/``variant_source`` fields are accepted as a
    compatibility input so existing noun artifacts can be upgraded without
    regenerating or changing any word forms.
    """

    existing = form.get("generated_from")
    if isinstance(existing, list) and existing:
        return [dict(item) for item in existing if isinstance(item, dict)]

    article_id = str(form.get("article_id") or "")
    variant_mode = str(form.get("variant_mode") or "")
    sources = form.get("variant_sources")
    if isinstance(sources, list) and sources:
        result: list[dict[str, str]] = []
        for item in sources:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("heading") or "")
            heading_type = str(item.get("variant_source") or "unknown")
            source = _source(
                article_id=article_id,
                heading=heading,
                heading_type=heading_type,
                variant_lemma=str(item.get("variant_lemma") or heading),
                variant_mode=variant_mode,
            )
            if source not in result:
                result.append(source)
        if result:
            return result

    headings = form.get("headings")
    if isinstance(headings, list) and headings:
        # This fallback is only for old merged artifacts that lack
        # variant_sources.  We cannot recover primary/alternative reliably,
        # so preserve the ambiguity explicitly.
        return [
            _source(
                article_id=article_id,
                heading=str(heading),
                heading_type="unknown",
                variant_mode=variant_mode,
            )
            for heading in headings
            if str(heading)
        ]

    heading = str(form.get("heading") or "")
    if heading:
        return [
            _source(
                article_id=article_id,
                heading=heading,
                heading_type=str(form.get("variant_source") or "primary"),
                variant_lemma=str(form.get("variant_lemma") or heading),
                variant_mode=variant_mode,
            )
        ]
    return []


def enrich_form(form: dict[str, Any]) -> dict[str, Any]:
    result = dict(form)
    result["generated_from"] = generated_from(form)
    return result


def enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["forms"] = [
        enrich_form(form) if isinstance(form, dict) else form
        for form in row.get("forms", [])
    ]
    paradigms = []
    for paradigm in row.get("variant_paradigms", []):
        if not isinstance(paradigm, dict):
            paradigms.append(paradigm)
            continue
        enriched = dict(paradigm)
        enriched["forms"] = [
            enrich_form(form) if isinstance(form, dict) else form
            for form in paradigm.get("forms", [])
        ]
        paradigms.append(enriched)
    if paradigms:
        result["variant_paradigms"] = paradigms
    return result


def enrich_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_row(row) for row in rows]


def written_form_signature(rows: Iterable[dict[str, Any]]) -> list[tuple[str, str, tuple[str, ...]]]:
    """Return a stable signature proving provenance enrichment changed no forms."""

    signature: list[tuple[str, str, tuple[str, ...]]] = []
    for row in rows:
        forms = tuple(sorted(
            str(form.get("written_form") or "")
            for form in row.get("forms", [])
            if isinstance(form, dict) and form.get("written_form")
        ))
        signature.append((
            str(row.get("record_id") or ""),
            str(row.get("lemma") or ""),
            forms,
        ))
    return signature
