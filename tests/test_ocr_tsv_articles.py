from io import StringIO

from swedish_wordlist_tools.ocr_tsv_articles import group_articles, read_words


HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
)


def test_groups_abrovink_lines_into_one_article_and_abrupt_into_next() -> None:
    tsv = HEADER + """\
5\t1\t1\t16\t1\t1\t53\t561\t60\t12\t71.124969\tabrowink
5\t1\t1\t16\t1\t2\t118\t560\t48\t17\t90.484009\t[-vin'k]
5\t1\t1\t16\t1\t3\t171\t562\t12\t11\t46.418892\tel.
5\t1\t1\t16\t1\t4\t188\t562\t34\t11\t2.605392\tabror
5\t1\t1\t16\t2\t1\t60\t579\t39\t11\t93.157532\tvinsch
5\t1\t1\t16\t2\t2\t104\t578\t47\t16\t27.864120\t[-vin'J]
5\t1\t1\t16\t2\t3\t156\t584\t7\t6\t71.843643\ts.
5\t1\t1\t16\t2\t4\t168\t583\t21\t7\t75.594185\t-en
5\t1\t1\t16\t2\t5\t194\t583\t20\t7\t24.345184\ter
5\t1\t1\t16\t3\t1\t61\t598\t45\t13\t42.783489\t«(prov)
5\t1\t1\t16\t3\t2\t111\t595\t33\t17\t96.920555\tlistig
5\t1\t1\t16\t3\t3\t149\t595\t52\t17\t80.913872\tlösning
5\t1\t1\t17\t1\t1\t53\t615\t46\t14\t92.836502\tabrupt
5\t1\t1\t17\t1\t2\t104\t614\t47\t16\t13.350945\t[-rup”t]
"""

    articles = group_articles(read_words(StringIO(tsv)))

    assert len(articles) == 2
    assert articles[0].paragraph == 16
    assert [[word.text for word in line.words] for line in articles[0].lines] == [
        ["abrowink", "[-vin'k]", "el.", "abror"],
        ["vinsch", "[-vin'J]", "s.", "-en", "er"],
        ["«(prov)", "listig", "lösning"],
    ]
    assert articles[1].paragraph == 17
    assert [word.text for word in articles[1].lines[0].words][:1] == ["abrupt"]


def test_ignores_non_word_rows_and_empty_words() -> None:
    tsv = HEADER + """\
1\t1\t0\t0\t0\t0\t0\t0\t235\t1077\t-1\t
4\t1\t1\t16\t1\t0\t53\t560\t169\t18\t-1\t
5\t1\t1\t16\t1\t1\t53\t561\t60\t12\t71.1\tabrowink
5\t1\t1\t16\t1\t2\t118\t560\t48\t17\t90.4\t
"""

    words = read_words(StringIO(tsv))

    assert len(words) == 1
    assert words[0].text == "abrowink"
