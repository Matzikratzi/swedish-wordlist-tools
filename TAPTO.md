# TAPTO — SAOL14 OCR

Kvällsöverlämning och praktisk kommandoreferens för SAOL14-OCR-arbetet. Nästa arbetspass ska kunna börja här utan chattkontext.

## Aktuell status

- Stabil `master`: `6666de3eb8454a6d2827194a3ee8ea1ccf9ba5a5` — merge av PR #25, **Merge OCR split facit benchmark improvements**.
- Aktiv experimentbranch: `agent/ocr-whole-column-shadow`.
- Branch-head vid denna TAPTO: `bb85ebed2b882217d9b4ef148336a9b751695904` — **Test tolerant small glyph profile holes**.
- Branchen ligger långt framför master och är experimentell. Merge först när Mats uttryckligen säger `Merga!` efter lokal test.
- Fruset checkpoint-läge finns på `checkpoint/ocr-baseline-pole-position`, commit `1d7c9f3424a91efa04e34052e7894e43d7c07811`.
- Facit är fruset på **428 glyphmodeller** för baseline-/shadow-arbetet.

## Senaste gröna verifierade regression

Den breda verifierade referensen är den frusna konservativa körningen över sida 1–100:

```text
pages=100
rows=15858
exact=15851/15858
needs_work=7
facit_models=428
```

De sju återstående raderna är avsiktligt kvar som konservativa fel; de ska inte "fixas" med extra facit bara för att få grönt.

Efter omläggning till `facit-v2` som kanonisk källa kördes samma 15 858 rader igen och exakt baseline-jämförelse gav:

```text
baseline-diff: differences=0
```

Det är den viktiga stabilitetspunkten: facit-loader-refaktorn ändrade **ingen** sparad rad-output.

Aktuellt branch-head `bb85ebed...` har ingen GitHub CI/status registrerad. De allra senaste whole-column/profile-ändringarna ska därför testas lokalt innan de räknas som verifierade.

## Arkitekturen vi går mot

Vi gör oss av med försegmenterade rader som primär sanning.

Målet är:

1. börja vid föregående säker radgräns,
2. leta nedåt efter första trovärdiga radstart,
3. låta en exakt känd glyph på legitim typografisk x-position etablera baseline,
4. tolka just den fysiska raden,
5. bestäm radens nedre gräns,
6. fortsätt därifrån till nästa rad.

Gamla `row_map` används under shadow-arbetet endast för yttre kolumngränser och jämförelse, inte för att hitta de nya raderna.

Page 39 / column 0 är huvudexperimentet. Den gamla felaktiga APNE-pseudoraden (`old=26`, y≈543..546) ska **inte** bli en ny rad; walkern ska direkt åter-synka till nästa verkliga rad.

## Frusen konservativ referens — använd den, gissa inte

Den gamla tolkens faktiska output finns sparad här:

```text
tests/reference/saol14-ocr/conservative-v1/manifest.json
tests/reference/saol14-ocr/conservative-v1/rows.jsonl
tests/reference/saol14-ocr/conservative-v1/problems.json
tests/reference/saol14-ocr/conservative-v1/summary.json
```

När vi undrar "vad tyckte gamla tolken att den här raden innehöll?" ska svaret tas ur `rows.jsonl`, inte rekonstrueras från shadow-logg eller synintryck.

Det gäller särskilt page 39 / column 0 / old row 32 (`y=631..648`): nästa arbetspass ska först läsa den sparade baseline-raden och fastställa exakt glyphsekvens, positioner/baseline och eventuella restpixlar. Vi tror att vänsterkanten är `~e`, men den frusna outputen är sanningskällan.

## Dagens genomförda arbete

### 1. Konservativ baseline fryst och bevisad

- APNE-reparationen kompakterar geometri och pixelägande atomärt.
- Sammanfogade två-baseline-rader kan delas konservativt när de två exakta baseline-täckningarna tillsammans täcker hela raden.
- Late-anchor-guard infördes för fall där en hög/sen glyph annars blev fel baseline-ankare.
- Resultatet frystes på sida 1–100 med 428 modeller.
- `facit-v2` gjordes till kanonisk källa; kompatibilitets-JSON kan regenereras från split-store.
- Exakt baseline-comparator bevisade `differences=0` efter loader-refaktorn.

### 2. Whole-column row walk

Ny shadow-walker arbetar på hela kolumnens pixlar och går uppifrån och ned en rad i taget.

Page 39 / column 0 visade den viktiga APNE-egenskapen:

```text
... old=25
... old=27
```

alltså: gamla `old=26` ignorerades och nästa riktiga rad hittades direkt.

Ordinarie vänsterkontur/fingerprint-sökning blev korrekt men dyr när alla x-trösklar 39..75 skannades. Reusable threshold contours och senare prefixhypoteser infördes för att behålla träffsäkerheten utan att reskanna alla svarta pixlar.

### 3. Mature-prefix-hypoteser

Fingerprint får nu börja mitt i en glyph. Kandidater följs tills deras egen vertikala kontur tar slut; då full-raster-verifieras hela glyphen, även pixlar ovanför fingerprintets start.

Detta ger en generell mekanism för exempel som `~e`, `-l`, `-B` och `: n` utan teckenspecifika specialfall.

På page 39 / column 0 / y≈631..648 hittade diagnostiken bland annat exakt `~` vid x=66, baseline=643 och en exakt `e` vid x=75 med samma baseline. Senare glyphar längre åt höger ska inte få etablera rad eftersom de ligger utanför legitima radstartszoner.

Första globala mature-prefix-sökningen var för dyr (~36,6 s), och prioriteringen gjorde dessutom att en senare vanlig träff kunde hoppa över en tidigare prefixrad. Koden ändrades därför så fysisk radordning styr och prefixsökning kan begränsas till aktuellt radfönster.

### 4. Whole-column profile-spåret

Det senaste spåret bygger **en tät vänsterprofil för hela kolumnen**: vänstra svarta x för varje fysisk y-rad, inklusive `None` för tomma rasterrader. Partiella facit-profiler indexeras, kandidater filtreras i 1D och hela glyphens 2D-raster verifieras därefter.

Senaste relevanta commits:

```text
d28e428  Test whole-column profile matching
c42fee5  Use twenty-row whole-column profile fragments
b706a89  Scan twenty-row profile fragments by default
a508557  Resolve profile baseline aliases by combined evidence
d0795b5  Allow small internal holes in column profile matching
bb85ebe  Test tolerant small glyph profile holes
```

Baseline-aliaser inom mindre än normal radpitch löses genom samlad evidens från verifierade glyphpixlar och separata x-ankare, i stället för att automatiskt välja första vertikala submatchen.

Små interna hål i glyphprofilen, t.ex. mellan prick och stam i `i`/`j` eller andra lösa diakritiska delar, kan nu vara wildcard i 1D-profilen. Den slutliga 2D-verifieringen är fortfarande exakt: alla verkliga facitpixlar måste finnas.

Det finns ännu ingen PR för `agent/ocr-whole-column-shadow`.

## Exakt nästa tekniska steg

1. **Läs först frusen baseline för page 39 / column 0 / old row 32** ur `conservative-v1/rows.jsonl`. Dokumentera vilka glyphar gamla konservativa tolken faktiskt identifierade, deras x/y/baseline och restpixlar. Gissa inte från bilden.
2. Kör fokuserade unit tests för whole-column/profile-mekanismen på aktuellt branch-head.
3. Kör `ocr_shadow_column_profile` på page 39 / column 0 och jämför fysisk radföljd mot den frusna referensen.
4. Kontrollera uttryckligen att:
   - APNE old26 fortfarande försvinner,
   - old32 (`~e`-området) etableras före old33,
   - old39 inte tappas,
   - efter en reparerad/missad rad åter-synkar nästa rad omedelbart,
   - söktiden ligger nära profile-spårets avsedda billiga 1D-sökning och inte tillbaka på tiotals sekunder.
5. Om old32 fortfarande missas: felsök **profilfragmentet och dess små interna hål/överlappande vänsterbläck**, inte gammal radsegmentering och inte ett `~`-specialfall.

## Viktiga lokala sökvägar — skriv inte över

Vanlig checkout:

```bash
cd ~/proj/saol14-fast-forward-test
```

Data/facit/referens:

```text
/home/matsj/proj/saol14-faksimil.jsonl
glyphs/saol14-manual-glyph-facit-v2.json
glyphs/facit-v2
/home/matsj/proj/saol14-conservative-rebuild/tests/reference/saol14-ocr
```

**Viktigt:** det lokalt granskade facit får inte skrivas över av `checkout`, `reset`, kopiering eller regenerering i fel riktning. `glyphs/facit-v2` är den kanoniska split-store-källan för v2; aggregate-JSON är kompatibilitetsformat.

Rör inte heller lokala review-köer/loggar i `glyphs/` eller `/tmp` annat än när det är avsiktligt.

## Praktiska återanvändbara kommandon

### Pull + fokuserad regression för nuvarande whole-column-spår

```bash
cd ~/proj/saol14-fast-forward-test
git pull

PYTHONPATH=src python -m unittest \
  tests/test_ocr_left_edge_prefix_hypotheses.py \
  tests/test_ocr_left_edge_local_index.py \
  tests/test_ocr_row_start_band_search.py \
  tests/test_ocr_row_start_prefix_fallback.py \
  tests/test_ocr_whole_column_row_walk.py \
  tests/test_ocr_whole_column_profile.py
```

### Whole-column/profile shadow — huvudexperiment

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_shadow_column_profile \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --page 39 \
    --column 0 \
    --homonym-x 46 \
    --headword-x 57 \
    --continuation-x 68 \
  2>&1 | tee /tmp/saol14-profile-shadow-page39-c0.log
```

### Äldre whole-column fingerprint/prefix shadow — jämförelseväg

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_shadow_whole_column \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --page 39 \
    --column 0 \
    --homonym-x 46 \
    --headword-x 57 \
    --continuation-x 68 \
  2>&1 | tee /tmp/saol14-shadow-page39-c0.log
```

### Fånga konservativ baseline

Kör bara när en ny uttrycklig baseline ska skapas; skriv inte över `conservative-v1` slentrianmässigt.

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_capture_conservative_baseline \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --start-page 1 \
    --end-page 100 \
    --output-dir /tmp/saol14-conservative-baseline
```

### Jämför ny baseline mot frusen referens

```bash
env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_compare_baseline \
    tests/reference/saol14-ocr/conservative-v1/rows.jsonl \
    /tmp/saol14-conservative-baseline/rows.jsonl
```

För loader-/resultatneutralitet är målet:

```text
baseline-diff: differences=0
```

### Preferred glyph-editor

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_html \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 31 \
  --column 1 \
  --row 3 \
  --port 8766
```

Använd inte `ocr_review_row_glyphs_html` som standard.

### Review-kö med samma pixel-array-editor

```bash
PYTHONPATH=src python -m swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_queue_html \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --queue /tmp/saol14-conservative-problem-pages.json \
  --port 8766
```

## Kända frusna konservativa fel

Dessa sju är medvetet kvar i baseline:

- p39 c2 r2 — 6 restpixlar
- p48 c1 r13 — sannolikt ännu saknad kursiv glyph/stil
- p50 c2 r12 — 27 restpixlar
- p61 c2 r24 — baseline faller senare i raden
- p61 c2 r25 — följdfel
- p64 c0 r43 — 26 restpixlar
- p75 c0 r24 — 13 restpixlar

De ska inte blandas ihop med whole-column-radstartsproblemen.

## Git-flöde

1. Arbeta på `agent/...`-branch.
2. Assistenten implementerar och committar.
3. Mats kör `git pull` och testar lokalt.
4. Iterera tills relevant regression är grön.
5. Merge först när Mats uttryckligen säger `Merga!`.

Kontroll före lokal test:

```bash
git status --short
git rev-parse --short HEAD
```

## TAPTO-rutin

Vid dagens slut uppdateras denna fil med stabil master-commit, aktiv branch/head, senaste gröna regression och omfattning, praktiska nya kommandon, relevanta commits/PR, dagens färdiga arbete, exakt nästa steg och filer som inte får skrivas över. Håll kommandodelen återanvändbar; lägg inte in engångsdiagnostik om den inte blivit en återkommande del av arbetsflödet.
