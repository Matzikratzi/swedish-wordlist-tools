from __future__ import annotations

from .adjective_slots import AdjectiveForm, AdjectiveSlots


def _expanded_superlative_forms(base: str) -> tuple[tuple[str, str], ...]:
    """Return regular definite superlative forms licensed by the surface ending.

    Regular ``-ast`` superlatives take ``-aste`` in definite/plural use. Other
    superlatives ending in ``-st`` take ``+a`` and optionally masculine ``+e``.
    The decision is based only on the already interpreted superlative form.
    """

    if base.endswith("ast"):
        return ((base + "e", "superlative_definite_or_plural"),)
    if base.endswith("st"):
        return (
            (base + "a", "superlative_definite_or_plural"),
            (base + "e", "superlative_masculine_definite"),
        )
    return ()


def expand_adjective_forms(slots: AdjectiveSlots) -> AdjectiveSlots:
    """Materialize regular inflection of already interpreted adjective slot forms.

    This layer deliberately runs *after* row interpretation: it does not
    reinterpret SAOL notation and it contains no lemma-specific exceptions.
    """

    forms = list(slots.forms)
    seen = {(form.written_form, form.slot) for form in forms}

    for form in slots.forms:
        if form.slot != "superlative":
            continue
        for written_form, slot in _expanded_superlative_forms(form.written_form):
            marker = (written_form, slot)
            if marker not in seen:
                forms.append(AdjectiveForm(written_form, slot, provenance="derived_inflection"))
                seen.add(marker)

    if tuple(forms) == slots.forms:
        return slots
    return AdjectiveSlots(
        lemma=slots.lemma,
        forms=tuple(forms),
        rule=slots.rule,
        restrictions=slots.restrictions,
    )
