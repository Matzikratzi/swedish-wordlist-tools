from swedish_wordlist_tools.ocr_recover_tail import locate_known_text, recover_tail
from swedish_wordlist_tools.ocr_tsv_articles import OcrArticle, OcrLine, OcrWord


def article(*lines: str) -> OcrArticle:
    out = []
    for line_num, text in enumerate(lines, 1):
        words = tuple(
            OcrWord(1, 16, line_num, i, i * 20, line_num * 20, 15, 12, 80.0, token)
            for i, token in enumerate(text.split(), 1)
        )
        out.append(OcrLine(1, 16, line_num, words))
    return OcrArticle(1, 16, tuple(out))


def test_locates_known_inflection_despite_marker_ocr_difference():
    entry = {"text": "+en +er"}
    a = article("abrovink s. -en er", "«(prov) listig lösning")
    located = locate_known_text(entry, a)
    assert located is not None
    assert located[2] > 0.9


def test_stops_before_meaning_bullet():
    entry = {"text": "+en"}
    a = article("ord s. -en -ar", "«betydelse här")
    result = recover_tail(entry, a, 0.95)
    assert result.recovered_tail == "-ar"
    assert result.stop_reason == "bullet"


def test_stops_before_sense_number():
    entry = {"text": "+en"}
    a = article("ord s. -en -ar 1 betydelse")
    result = recover_tail(entry, a)
    assert result.recovered_tail == "-ar"
    assert result.stop_reason == "sense-number"
