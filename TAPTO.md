# TAPTO — SAOL14 OCR

Kvällsöverlämning och kommandoreferens för SAOL14-OCR-arbetet. Målet är att nästa arbetspass ska kunna börja här utan att vara beroende av chattkontext.

## Aktuell status

- Stabil bas: `master`
- Senaste merge till master: PR #25, merge-commit `6666de3eb8454a6d2827194a3ee8ea1ccf9ba5a5`
- Regression före merge: sida 1–30, `4765/4765` exakta rader, `needs_work=0`
- Aktiv experimentbranch: `agent/ocr-left-edge-index`
- Nästa arbete: undersök vänsterkontur-/glyphindex som kandidatfilter och som möjlig väg till mindre baseline-beroende OCR.
- Vänsterkontur-mätning på nuvarande facit: 428 modeller, full kontur ger i snitt ca 2.08 kandidater; 257/428 modeller har unik full kontur.

## Viktiga lokala sökvägar

Vanlig checkout:

```bash
cd ~/proj/saol14-fast-forward-test
```

Data och facit:

```text
/home/matsj/proj/saol14-faksimil.jsonl
glyphs/saol14-manual-glyph-facit-v2.json
glyphs/facit-v2
/home/matsj/proj/saol14-conservative-rebuild/tests/reference/saol14-ocr
```

Facit redigeras lokalt och ska inte skrivas över av slentrianmässiga checkout/reset-kommandon.

## 1. Scanna efter rader som behöver granskas

En sida:

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 31 \
  --output glyphs/saol14-review-rows-page31.json
```

Ett sidintervall:

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --start-page 32 \
  --end-page 100 \
  --slow-row-seconds 0.20 \
  --output /tmp/saol14-review-p32-100.json \
  > /tmp/saol14-scan-p32-100.log 2>&1
```

Regression, exempel sida 1–30:

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --start-page 1 \
    --end-page 30 \
    --slow-row-seconds 0.20 \
    --output /tmp/saol14-regression-p1-30.json \
  2>&1 | tee /tmp/saol14-regression-p1-30.log
```

Bra slutresultat är `needs_work=0` och att output-kön innehåller 0 rader.

## 2. Editera glyphar — preferred editor

Använd pixel-array-editorn med tre rader. Det är den editor som ska användas i första hand: rektangelmarkering, tre-radersvy och snabbnavigation.

En viss rad:

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_html \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 31 \
  --column 1 \
  --row 3 \
  --port 8766
```

Kö av rader över flera sidor:

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_review_page_pixel_array_queue_html \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --queue /tmp/saol14-review-p32-100.json \
  --mode queue \
  --port 8766
```

Fortsätt från en viss köposition:

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_review_page_pixel_array_queue_html \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --queue /tmp/saol14-review-p32-100.json \
  --mode queue \
  --queue-index N \
  --port 8766
```

Använd inte den äldre enkla `ocr_review_row_glyphs_html` som standard.

## 3. Benchmark mot referens

Vanlig benchmark:

```bash
env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_headword_first_glyph_sequence_benchmark \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --split-facit glyphs/facit-v2 \
    --reference-dir /home/matsj/proj/saol14-conservative-rebuild/tests/reference/saol14-ocr \
    --start-page 1 \
    --end-page 5
```

Benchmark med cProfile:

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m cProfile \
    -s tottime \
    -m swedish_wordlist_tools.ocr_headword_first_glyph_sequence_benchmark \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --split-facit glyphs/facit-v2 \
    --reference-dir /home/matsj/proj/saol14-conservative-rebuild/tests/reference/saol14-ocr \
    --start-page 1 \
    --end-page 5 \
  > /tmp/saol14-headword-cprofile.log 2>&1
```

Läs dyraste funktionerna längst upp i loggen eftersom `-s tottime` används.

## 4. Diagnostik av radsegmentering

När två fysiska rader verkar ha slagits ihop eller radgränsen ser fel ut:

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_debug_row_segmentation \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --page 36 \
  --column 2 \
  --row 48
```

## 5. Vänsterkontur-analys

Mät hur diskriminerande glypharnas vänsterkonturer är:

```bash
PYTHONPATH=src python -m unittest \
  tests/test_ocr_left_edge_signature_analysis.py

PYTHONPATH=src python -m swedish_wordlist_tools.ocr_left_edge_signature_analysis \
  glyphs/saol14-manual-glyph-facit-v2.json \
  --max-depth 24
```

Idén är att använda vänsterkonturen som snabbt kandidatindex, inte nödvändigtvis som ensam klassificerare. Full pixelmatchning verifierar kandidaterna.

## 6. Relevanta riktade tester

Köeditorns koordinat-/save-säkerhet:

```bash
PYTHONPATH=src python -m unittest \
  tests/test_ocr_queue_editor_save_safety.py
```

Vänsterkontursignatur:

```bash
PYTHONPATH=src python -m unittest \
  tests/test_ocr_left_edge_signature_analysis.py
```

När en OCR-ändring görs ska nya regressionstester läggas nära den berörda mekanismen och de gamla köras innan merge.

## 7. Git-flöde

Arbetsprincip:

1. Arbeta på `agent/...`-branch.
2. Assistenten implementerar och committar.
3. Mats kör `git pull` och testar lokalt.
4. Iterera tills regressionen är grön.
5. Merge först när Mats uttryckligen säger `Merga!`.

Kontroll före test:

```bash
git status --short
git rev-parse --short HEAD
```

Undvik att röra lokala otrackade review-/benchmark-köer om de inte uttryckligen ska sparas.

## 8. Kända buggar / nästa kandidater

Följande typer har observerats efter den stabila 1–30-basen:

- Missad fysisk radsegmentering: två tryckta rader blir en geometrisk rad.
- Baseline/start-anchor för långt åt höger: små `-`, `,`, `.` kan bli falska ankare trots tidigare bläck längre åt vänster.
- Orimlig baseline från små skiljetecken/punktuation.
- Baseline kan flytta sig mitt i samma tryckta rad; nuvarande matchning tappar då senare glyphar och radseparatorn kan klippa descenders.

Vänsterkontur-indexet är nästa experiment eftersom det kan hjälpa både radstart och åter-synkning efter lokal baselineförskjutning.

## 9. Kvällens TAPTO-rutin

Vid dagens slut ska denna fil uppdateras med:

- aktuell stabil branch/master-commit,
- aktiv branch,
- senaste gröna regression och dess omfattning,
- nya viktiga kommandon,
- senaste relevanta commit/PR,
- vad som precis blev klart,
- exakt nästa tekniska steg,
- eventuella lokala filer som inte får skrivas över.

Håll kommandodelen stabil och praktisk. Lägg inte in varje engångskommando; ta med sådant som faktiskt återanvänds.
