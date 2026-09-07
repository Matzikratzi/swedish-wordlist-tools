from swedish_wordlist_tools.ocr_jsonl_match import rank_articles
from swedish_wordlist_tools.ocr_tsv_articles import OcrArticle, OcrLine, OcrWord


def article(paragraph, *lines):
    out = []
    for line_num, text in enumerate(lines, 1):
        words = tuple(
            OcrWord(1, paragraph, line_num, i, i * 20, line_num * 20, 15, 12, 80.0, word)
            for i, word in enumerate(text.split(), 1)
        )
        out.append(OcrLine(1, paragraph, line_num, words))
    return OcrArticle(1, paragraph, tuple(out))


def test_abrovink_record_finds_ocr_corrupted_article():
    record = {
        "normaliserat_ord": "abrovink",
        "stycke": "abro·vink",
        "ord": "abro·vinsch",
    }
    articles = [
        article(15, "abrasionsvittne s. -t"),
        article(16, "abrowink [-vin'k] el. abror", "vinsch [-vin'J] s. -en er", "listig lösning"),
        article(17, "abrupt [-rupt] adj."),
    ]
    ranked = rank_articles(record, articles)
    assert ranked[0].paragraph == 16
    assert ranked[0].headword_score > 0.8


def test_bollek_uses_printed_headword_as_strongest_signal():
    record = {
        "normaliserat_ord": "bollek",
        "stycke": "bollek",
        "ord": "boll|lek",
    }
    articles = [
        article(1, "bollplank s."),
        article(2, "bollek uppdelas boll|lek s. -en -ar"),
        article(3, "bollmask s."),
    ]
    ranked = rank_articles(record, articles)
    assert ranked[0].paragraph == 2
    assert ranked[0].headword_score == 1.0
