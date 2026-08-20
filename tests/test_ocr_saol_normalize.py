from swedish_wordlist_tools.ocr_saol_normalize import (
    article_text_for_match,
    normalize_headword_structure,
    normalize_text_for_match,
)
from swedish_wordlist_tools.ocr_tsv_articles import OcrArticle, OcrLine, OcrWord


def _word(text: str, line: int, word: int) -> OcrWord:
    return OcrWord(
        block=1,
        paragraph=16,
        line=line,
        word=word,
        left=0,
        top=0,
        width=1,
        height=1,
        confidence=90.0,
        text=text,
    )


def test_normalize_removes_pronunciation_and_word_boundary_marks():
    assert normalize_text_for_match("abro|vink [-vin'k]") == "abrovink"
    assert normalize_text_for_match("abro¦vinsch [-vin'ʃ]") == "abrovinsch"
    assert normalize_text_for_match("abro·vinsch [-vin'ʃ]") == "abrovinsch"


def test_headword_structure_preserves_jsonl_boundary_mark():
    assert normalize_headword_structure("abro·vink") == "abro·vink"
    assert normalize_headword_structure("abro·vinsch") == "abro·vinsch"
    assert normalize_headword_structure("abro|vink [-vin'k]") == "abro·vink"
    assert normalize_headword_structure("abro¦vinsch [-vin'ʃ]") == "abro·vinsch"


def test_normalize_unifies_typographic_dashes():
    assert normalize_text_for_match("-en –er —arna") == "-en -er -arna"


def test_article_match_text_joins_line_broken_word():
    article = OcrArticle(
        block=1,
        paragraph=16,
        lines=(
            OcrLine(
                block=1,
                paragraph=16,
                line=1,
                words=(
                    _word("abro-", 1, 1),
                ),
            ),
            OcrLine(
                block=1,
                paragraph=16,
                line=2,
                words=(
                    _word("vinsch", 2, 1),
                    _word("[-vin'J]", 2, 2),
                    _word("s.", 2, 3),
                    _word("-en", 2, 4),
                    _word("-er", 2, 5),
                ),
            ),
        ),
    )

    assert article_text_for_match(article) == "abrovinsch s. -en -er"
