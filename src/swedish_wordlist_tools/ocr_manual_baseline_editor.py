from __future__ import annotations

"""Allow glyph review to bootstrap rows where OCR found no support baseline."""

from . import ocr_review_row_glyphs_html as legacy


_original_render_html = legacy.render_html
_original_apply_edit = legacy.apply_edit


def _suggested_baseline(state: dict) -> int | None:
    """Prefer the OCR baseline, otherwise derive the target row's geometric support line."""
    baseline = state.get("baseline")
    if baseline is not None:
        return int(baseline)

    neighbor_top = state.get("neighbor_page_top")
    crop_box = state.get("crop_box")
    if neighbor_top is None or not crop_box:
        return None

    wanted = f"STÖDLINJE row {int(state.get('row', -1))}"
    crop_top = int(crop_box[1])
    for entry in state.get("neighbor_row_boundaries") or []:
        if len(entry) < 2 or str(entry[1]) != wanted:
            continue
        # Support lines are deliberately rendered one pixel below the baseline.
        baseline = int(neighbor_top) + int(entry[0]) - crop_top - 1
        if 0 <= baseline < int(state.get("crop_height") or 0):
            return baseline
    return None


def _form_baseline(state: dict, form: dict[str, list[str]]) -> int:
    raw = (form.get("manual_baseline") or [""])[0].strip()
    if raw:
        try:
            baseline = int(raw)
        except ValueError as exc:
            raise ValueError("baseline måste vara ett heltal") from exc
    else:
        suggested = _suggested_baseline(state)
        if suggested is None:
            raise ValueError("ange baseline för glyphen")
        baseline = suggested

    height = int(state.get("crop_height") or 0)
    if not 0 <= baseline < height:
        raise ValueError(f"baseline {baseline} ligger utanför raden 0..{max(0, height - 1)}")
    return baseline


def render_html_with_manual_baseline(state: dict, message: str = "") -> str:
    document = _original_render_html(state, message)
    suggested = _suggested_baseline(state)
    value = "" if suggested is None else str(suggested)
    max_value = max(0, int(state.get("crop_height") or 1) - 1)

    needle = '<button name="action" value="add">Lägg till/slå ihop valda pixlar som glyph</button>'
    control = (
        '<label>Baseline<input name="manual_baseline" id="manualBaseline" type="number" '
        f'min="0" max="{max_value}" value="{value}" style="width:6em"></label>\n'
        + needle
    )
    if needle not in document:
        raise ValueError("could not find add-glyph button for manual baseline control")
    document = document.replace(needle, control, 1)

    if state.get("baseline") is None:
        hint_needle = '<p class="hint">'
        hint = (
            '<p class="hint"><b>Ingen OCR-baseline hittades.</b> Baseline-fältet är därför '
            'förifyllt från radens geometriska stödlinje när den finns. Ändra värdet för glyphar '
            'som ligger på en annan baseline.</p>\n'
        )
        if hint_needle in document:
            document = document.replace(hint_needle, hint + hint_needle, 1)

    script = r'''
<script>
(() => {
  const input=document.getElementById('manualBaseline');
  if(!input) return;
  function syncManualBaseline(){
    const raw=input.value.trim();
    S.baseline=raw===''?null:Number(raw);
    if(typeof draw==='function') draw();
  }
  input.addEventListener('input',syncManualBaseline);
  input.addEventListener('change',syncManualBaseline);
  syncManualBaseline();
})();
</script>
'''
    return document.replace('</body>', script + '</body>', 1)


def apply_edit_with_manual_baseline(state: dict, facit, form: dict[str, list[str]]) -> str:
    action = (form.get("action") or [""])[0]
    if action == "add":
        # Deliberately update this request-local state in place. The v2 review wrapper
        # runs immediately after legacy.apply_edit and must normalize the new model
        # against exactly the same manually chosen baseline.
        state["baseline"] = _form_baseline(state, form)
    return _original_apply_edit(state, facit, form)


def install_manual_baseline_editor() -> None:
    legacy.render_html = render_html_with_manual_baseline
    legacy.apply_edit = apply_edit_with_manual_baseline
