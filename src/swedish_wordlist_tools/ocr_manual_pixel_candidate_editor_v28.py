from __future__ import annotations

import re
import sys
from pathlib import Path

from . import ocr_manual_pixel_candidate_editor_v27 as v27


def main() -> int:
    """Generate v27 and collapse the old per-style duplicate rows.

    Since v26 each annotation carries its own roman/italic/bold style and all
    learned styles compete on every card.  The style-copy rows introduced in
    v13 are therefore obsolete: one raster row can contain annotations of all
    three styles.
    """
    argv = sys.argv[1:]
    out: Path | None = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            out = Path(argv[i + 1])

    rc = v27.main()
    if rc or out is None or not out.exists():
        return rc

    text = out.read_text(encoding="utf-8")

    # Remove the reveal button from primary rows.
    text = text.replace(
        '<button class="stylecopy-show" type="button">Kopiera rad för annan stil</button>',
        '',
    )

    # Remove every hidden duplicate card that v13 injected.  These have their
    # own ::stylecopy source id and no longer serve a purpose now that style is
    # stored per annotation.
    style_copy_re = re.compile(
        r'<article class="card style-copy" style="display:none"\n.*?</article>',
        re.S,
    )
    text, removed_cards = style_copy_re.subn('', text)

    # Remove the now-dead JS that wired primary/copy pairs.  Keeping it would be
    # harmless after deleting the cards, but removing it makes the generated
    # editor reflect the new one-row model cleanly.
    wiring_re = re.compile(
        r"for\(const primary of document\.querySelectorAll\('\.card:not\(\.style-copy\)'\)\)\{.*?\n\}\n(?=document\.querySelector\('#export'\)\.onclick=)",
        re.S,
    )
    text, _ = wiring_re.subn('', text, count=1)

    # The old export guard is unnecessary because no style-copy cards remain.
    text = text.replace(
        "\n  if(card.classList.contains('style-copy') && card.style.display==='none')continue;",
        '',
    )

    # Replace obsolete documentation from v13 with the current single-row rule.
    text = re.sub(
        r'<b>Blandad stil på samma tryckrad:</b>.*?<b>Stil per rad:</b>',
        '<b>En rad per raster:</b> roman, kursiv och fet kan märkas i samma rad. '
        'Kortets stil är bara förval för nästa annotation; använd <code>{{r}}</code>, '
        '<code>{{i}}</code> eller <code>{{b}}</code> när en enskild glyph har annan stil. '
        '<b>Stil per rad:</b>',
        text,
        count=1,
        flags=re.S,
    )

    text = text.replace('SAOL live-lärande pixelannotering v27', 'SAOL live-lärande pixelannotering v28', 1)
    text = text.replace('corrected-v27.json', 'corrected-v28.json')

    out.write_text(text, encoding='utf-8')
    print(f'v28: removed {removed_cards} obsolete per-style duplicate rows; one raster row now holds mixed-style annotations')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
