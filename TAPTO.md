# TAPTO — SAOL14 OCR

Kvällsöverlämning och praktisk kommandoreferens för SAOL14-OCR-arbetet. Nästa arbetspass ska kunna börja här utan chattkontext.

## Aktuell status

- Stabil `master`: `6666de3eb8454a6d2827194a3ee8ea1ccf9ba5a5` — merge av PR #25, **Merge OCR split facit benchmark improvements**.
- Aktiv experimentbranch: `agent/ocr-whole-column-shadow`.
- Branch-head före denna TAPTO-commit: `d329e181758418e3f912c1feb1a952dabb3ec283` — **Allow writing a selected cluster glyph candidate**.
- Branchen är experimentell och ligger långt framför master. Merge först när Mats uttryckligen säger `Merga!` efter lokal test.
- Fruset checkpoint-läge: `checkpoint/ocr-baseline-pole-position` vid `1d7c9f3424a91efa04e34052e7894e43d7c07811`.
- Den frusna konservativa referensen använder **428 glyphmodeller**.
- Det finns fortfarande ingen PR för `agent/ocr-whole-column-shadow`.

## Senaste gröna verifierade regression och scope

Den senaste breda, explicit verifierade gröna stabilitetspunkten är fortfarande den frusna konservativa körningen sida 1–100:

```text
pages=100
rows=15858
exact=15851/15858
needs_work=7
facit_models=428
```

Efter att `facit-v2` gjordes till kanonisk källa kördes samma 15 858 rader igen och exakt jämförelse mot frusen radoutput gav:

```text
baseline-diff: differences=0
```

De sju kvarvarande konservativa felen är avsiktligt frusna och ska inte fyllas igen med extra facit bara för att få grönt.

Branch-head `d329e181...` har **ingen GitHub CI/status** registrerad. Dagens nya directional/profile/cluster-kod har omfattande unit-testfiler, men ska inte beskrivas som bred verifierad regression förrän Mats kört den fokuserade regressionssviten lokalt på aktuellt head.

Senaste incheckade branch-specifika regressionsscope omfattar särskilt:

```text
tests/test_ocr_column_left_profile.py
tests/test_ocr_page_start_geometry.py
tests/test_ocr_row_directional.py
tests/test_ocr_baseline_up.py
tests/test_ocr_live_profile_candidates.py
tests/test_ocr_candidate_survival.py
tests/test_ocr_build_cluster_glyph.py
```

## Arkitekturen vi går mot

Försegmenterade rader ska inte vara primär sanning. OCR:n ska gå sekventiellt genom hela kolumnens verkliga raster:

1. börja vid en känd/säker radstart,
2. hitta första glyphen uppifrån genom vänsterprofil/radstartsgeometri,
3. låt exakt glyph ge baseline,
4. hitta följande glyphar från baseline och kvarvarande bläck,
5. konsumera endast exakt förklarade pixlar,
6. härled nästa radstart från den faktiskt förklarade vertikala utsträckningen,
7. fortsätt rad för rad.

`row_map` får fortfarande användas i benchmark/shadow för kalibrering, antal referensrader och jämförelse, men inte som sanningen som styr den nya radtolkningen.

Den frusna konservativa outputen är referens för vad gamla tolken faktiskt tyckte. När ett konkret gammalt radresultat behövs ska det läsas ur:

```text
tests/reference/saol14-ocr/conservative-v1/rows.jsonl
```

inte gissas från bild eller shadow-logg.

## Genomfört idag — 2026-09-09

Sedan föregående TAPTO (`bb85ebed...`) har branchen flyttat **95 commits** framåt.

### 1. Directional top-down / baseline-up OCR

Det gamla whole-column profile-spåret har utvecklats till en sekventiell directional matcher:

- `ocr_row_directional.py` hittar första glyphen uppifrån i legal radstartszon.
- `ocr_baseline_up.py` använder etablerad baseline för att hitta nästa glyph i kvarvarande bläck.
- `ocr_directional_page_benchmark.py` kör rader sekventiellt, konsumerar accepterade glyphpixlar och härleder nästa radstart från den förklarade pixelutsträckningen.
- `ocr_page_start_geometry.py` infererar legitima radstartszoner för sidan.
- Benchmarken har explicit invariant: innan `next_row_top` lämnas vidare får det inte finnas oförklarade svarta pixlar ovanför den gränsen.

Detta är närmare slutarkitekturen än den tidigare globala kandidatlistan: vi tolkar nu vad som faktiskt händer i aktuell fysisk rad och låter resultatet styra var nästa rad börjar.

### 2. Live profile candidates / candidate survival

Nya `ocr_live_profile_candidates.py` och `ocr_candidate_survival.py` formaliserar kandidatlivscykeln längs hela kolumnens vänsterprofil:

- kandidater föds när deras topp kan äga aktuell vänsterkant,
- varje rasterrad kan behålla eller döda kandidaten,
- glyphens egna exakta pixlar måste finnas,
- annan bläck längre vänster får dölja kandidaten utan att göra den falsk,
- interna tomrader i t.ex. prick/stam-glyphar hanteras explicit,
- terminalhändelser krävs bara där den tidigare kända utsträckningen faktiskt ger information.

Senaste terminal-event-regressionen (`156fea96...`) verifierar bland annat att en kandidat som når känd `row_top` inte kräver en fiktiv uppåt-händelse och att nedåt-terminal bara får krävas inom tidigare känd botten.

En framtidsidé är sparad i `notes/ocr-profile-diff-followup-2026-09-09.md`: eventuellt ska långa `dx=0`-sträckor aggregeras och matchning främst ske på meningsfulla profiländringar/boundary-events. **Det är sparat för senare och ska inte implementeras före nuvarande directional/cluster-arbete.**

### 3. Syntetiska klusterglyphar

Dagens senaste spår hanterar fall där två tecken rastermässigt går ihop och därför kan behöva representeras som en enda exakt klusterglyph.

Relevanta commits:

```text
156fea9  Test terminal events only inside previously known extent
fa5aa48  Add synthetic cluster glyph builder
1e29f5f  Test synthetic cluster glyph geometry
d329e18  Allow writing a selected cluster glyph candidate
```

`ocr_build_cluster_glyph.py` kan kombinera två granskade komponentglyphar på samma baseline och söker endast placeringar som:

- inte överlappar svarta pixlar,
- har begärt antal ortogonala kontakter,
- skapar ett nytt inneslutet vitt hål,
- behåller gemensam stil när komponenterna har samma stil.

Nuvarande standardfall i verktyget är `f` + `r` -> `fr`.

`ocr_write_cluster_candidate.py` kan välja en explicit kandidat när geometrin inte ger exakt en unik placering.

### 4. Viktig persistensrisk upptäckt vid TAPTO-genomgången

**Använd inte `--write` på det riktiga facit ännu.**

Den senaste `ocr_write_cluster_candidate.py` skriver just nu direkt till den JSON-fil som ges som `facit`:

```python
args.facit.write_text(...)
```

men projektets fastställda arkitektur är att:

```text
glyphs/facit-v2
```

är kanonisk split-store och aggregate-filen

```text
glyphs/saol14-manual-glyph-facit-v2.json
```

är kompatibilitetsformat som ska regenereras från den kanoniska källan. Direkt skrivning till aggregate kan därför skapa divergens eller försvinna vid nästa regenerering.

## Exakt nästa tekniska steg

**Nästa kodändring ska vara att göra cluster-writern canonical-store-säker innan någon riktig `fr`-glyph skrivs.**

1. Ändra `ocr_write_cluster_candidate.py` så att den inte skriver aggregate-JSON direkt.
2. Återanvänd befintlig canonical facit-persistens (`ocr_glyph_facit_store.py` / `persist_facit_payload`) så att split-store skrivs först och aggregate regenereras från den.
3. Lägg regression som bevisar att en vald syntetisk klusterglyph får stabilt nytt `model_id`, hamnar i `glyphs/facit-v2` och återkommer identiskt i regenererad aggregate.
4. Kör fokuserad directional/profile/cluster-regression lokalt.
5. Först därefter: kör cluster-builder/writer i **dry-run**, välj rätt faktisk `fr`-kandidat och skriv den endast efter explicit kontroll.
6. Efter eventuell facitändring: rerun relevant directional page benchmark och kontrollera att den löser det konkreta klusterfallet utan att försämra tidigare rader.

Börja alltså **inte** nästa pass med att lägga `--write` på `glyphs/saol14-manual-glyph-facit-v2.json`.

## Viktiga lokala filer — skriv inte över

Vanlig checkout:

```bash
cd ~/proj/saol14-fast-forward-test
```

Skyddsvärda data/facit/referenser:

```text
/home/matsj/proj/saol14-faksimil.jsonl
glyphs/facit-v2
glyphs/saol14-manual-glyph-facit-v2.json
/home/matsj/proj/saol14-conservative-rebuild/tests/reference/saol14-ocr
tests/reference/saol14-ocr/conservative-v1
```

Regler:

- `glyphs/facit-v2` är den kanoniska v2-källan. Skriv inte över den via checkout/reset/kopiering.
- Aggregate-JSON får inte bli en konkurrerande källa; regenerera i rätt riktning från split-store.
- Skriv inte över `conservative-v1`; skapa nya baseline-körningar i `/tmp` om inte en ny frusen baseline uttryckligen beslutas.
- Rör inte lokala review-köer och användarens ej incheckade filer i `glyphs/` eller `/tmp` annat än avsiktligt.
- Nuvarande `ocr_write_cluster_candidate --write` ska betraktas som **osäker för canonical facit** tills nästa persistensfix är gjord.

## Praktiska återanvändbara kommandon

### Pull + aktuell fokuserad regression

```bash
cd ~/proj/saol14-fast-forward-test
git pull

PYTHONPATH=src python -m unittest \
  tests/test_ocr_column_left_profile.py \
  tests/test_ocr_page_start_geometry.py \
  tests/test_ocr_row_directional.py \
  tests/test_ocr_baseline_up.py \
  tests/test_ocr_live_profile_candidates.py \
  tests/test_ocr_candidate_survival.py \
  tests/test_ocr_build_cluster_glyph.py
```

### Directional page benchmark — primär nuvarande benchmark

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_directional_page_benchmark \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --page 30 \
    --column 0
```

För en återkommande riktad felsökning av en rad kan `--trace-row N` läggas till; behåll grundkommandot ovan som benchmarkreferens.

### Candidate-survival shadow

```bash
/usr/bin/time -f 'TOTALT: %e s' \
  env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_shadow_candidate_survival \
    /home/matsj/proj/saol14-faksimil.jsonl \
    --facit glyphs/saol14-manual-glyph-facit-v2.json \
    --page 39 \
    --column 0
```

Använd `--show-steps` bara vid kandidatlivscykel-felsökning; det är inte normal benchmarkoutput.

### Bygg syntetiska klusterglyph-kandidater — dry-run

```bash
env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_build_cluster_glyph \
    glyphs/saol14-manual-glyph-facit-v2.json \
    --left-label f \
    --right-label r \
    --label fr
```

Detta är säkert så länge `--write` **inte** anges.

### Explicit vald klusterkandidat — endast dry-run tills canonical-store-fixen är klar

```bash
env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_write_cluster_candidate \
    glyphs/saol14-manual-glyph-facit-v2.json \
    --candidate N \
    --left-label f \
    --right-label r \
    --label fr
```

**Lägg inte till `--write` ännu.**

### Fånga konservativ baseline i temporär katalog

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

### Jämför mot frusen konservativ referens

```bash
env PYTHONPATH=src \
  python -m swedish_wordlist_tools.ocr_compare_baseline \
    tests/reference/saol14-ocr/conservative-v1/rows.jsonl \
    /tmp/saol14-conservative-baseline/rows.jsonl
```

Resultatneutralitet betyder:

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

## Kända frusna konservativa fel

Dessa sju hör till den konservativa baselinen, inte det nya directional-spåret:

- p39 c2 r2 — 6 restpixlar
- p48 c1 r13 — sannolikt ännu saknad kursiv glyph/stil
- p50 c2 r12 — 27 restpixlar
- p61 c2 r24 — baseline faller senare i raden
- p61 c2 r25 — följdfel
- p64 c0 r43 — 26 restpixlar
- p75 c0 r24 — 13 restpixlar

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

Vid dagens slut uppdateras denna fil med stabil master-commit, aktiv branch/head, senaste gröna regression och omfattning, praktiska återanvändbara kommandon, relevanta commits/PR, dagens färdiga arbete, exakt nästa steg och lokala filer som inte får skrivas över. Undvik engångsdiagnostik i kommandoreferensen.


---

## Pixel-OCR arbetsläge — 2026-09-10 kväll

### Git och aktuell checkpoint

Aktiv branch är `agent/ocr-whole-column-shadow`.

Kod-head före denna TAPTO-uppdatering:

```text
06d9fc1b3334c1986ce36b7671cb457b88c02557
Anchor residual candidates to one leftmost pixel
```

Närliggande föregående commit:

```text
e866305f0bf89508e87df9183d9271a16e973460
Anchor residual candidates only at leftmost pixel
```

Verifiera lokal checkout före test:

```bash
cd ~/proj/saol14-fast-forward-test
git fetch origin
git status --short
git log -2 --oneline --decorate
git rev-parse HEAD
git rev-parse origin/agent/ocr-whole-column-shadow
```

Återställ denna avsedda testcheckout exakt till publicerad experimentbranch:

```bash
git fetch origin
git reset --hard origin/agent/ocr-whole-column-shadow
```

### Nuvarande algoritmiska checkpoint

Residualsteget fungerar nu enligt modellen:

1. föregående glyphs baseline begränsar bara y-området där nästa startpixel söks,
2. en enda gemensam vänstraste residualpixel väljs,
3. alla kandidater föds endast från den pixeln,
4. inga kandidater föds på nytt längre ned i profilen,
5. kandidatens egen rastergeometri bestämmer dess placering och baseline,
6. kandidater följs nedåt och uppåt från startpixeln,
7. annan glyph får ligga framför kandidaten i vänsterprofilen,
8. överlevare måste därefter klara full 2D: varje svart glyphpixel måste finnas i residualbilden, men extra sidbläck är tillåtet.

Kritiska p36/c0/r2-fallet fungerar semantiskt:

```text
start=(66,122)
initial=3953
profile_survivors=18
exact=1
accepted='i'
```

`(66,122)` är vänsterseriffen på `i`.

Nästa större mål är prestanda: 3953 initiala kandidater är för många. Optimera kandidatgenereringen utan att ändra semantiken ovan.

Separat kvarstående optimering: 2D-prova flerpixliga kandidater före färrepixliga och avbryt omedelbart vid första saknade pixel.

### Standardkommando för aktuell felsökning

```bash
cd ~/proj/saol14-fast-forward-test

OCR_FIRST_GLYPH_TRACE=1 env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_directional_page_peak_benchmark \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 36 \
  --column 0 \
  --rows 3 \
  --trace-row=2
```

Spara trace reproducerbart:

```bash
OCR_FIRST_GLYPH_TRACE=1 env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_directional_page_peak_benchmark \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 36 --column 0 --rows 3 --trace-row=2 \
  > /tmp/saol14-p36-c0-r2-trace.log 2>&1
```

Bra nyckelrader i trace:

```text
directional-trace-raster:
directional-trace first-glyph-pick:
directional-residual-profile:
directional-residual-profile-death:
directional-residual-2d-fail:
directional-residual-2d-pass:
directional-residual-pick:
directional-row:
directional-timing:
directional-page-done:
```

Filtrera kritiska i-spåret:

```bash
grep -E 'first-glyph-pick|residual-profile:|residual-profile-death:.*label=.i.|residual-2d-(pass|fail):.*label=.i.|residual-pick:|directional-row: row=2|directional-page-done:' \
  /tmp/saol14-p36-c0-r2-trace.log
```

### ASCII-pixelraster i trace

`--trace-row=N` skriver ett 25 pixelrader högt band över hela spaltbredden:

- `kind=start`: residualen innan glyphen tas,
- `kind=glyph:<tecken>`: bara accepterad glyph,
- `kind=residual`: kvarvarande raster efter att glyphens pixlar nollats.

```text
. = vit pixel
# = svart pixel
```

Detta är snabbaste sättet att kontrollera exakt vilka pixlar en glyph tog med sig.

### Mm-papper / pixel-grid-debugbild

Verktyget `ocr_page_pixel_grid` använder samma threshold-konvention som OCR:n och ritar varje källpixel som en kvadrat med koordinatnät.

```bash
cd ~/proj/saol14-fast-forward-test

env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_page_pixel_grid \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --page 36 \
  --threshold 210 \
  --scale 3 \
  --major-grid-step 10 \
  --label-step 50 \
  --output /tmp/saol14-page36-pixel-grid.png
```

`--scale 4` eller större kan användas för större rutor utan att ändra OCR-pixlarna.

### Timing utan trace

```bash
/usr/bin/time -f 'TOTALT: %e s' \
env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_directional_page_peak_benchmark \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 36 --column 0 --rows 3
```

### Kör hela kolumnen och jämför mot sparad referens

`--rows 0` betyder alla referensrader i vald kolumn.

```bash
env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_directional_page_peak_benchmark \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 36 --column 0 --rows 0 \
  > /tmp/directional-p36-c0.log 2>&1

env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_compare_directional_reference \
  /tmp/directional-p36-c0.log \
  tests/reference/saol14-ocr/conservative-v1/rows.jsonl \
  --page 36 --column 0
```

Nyckelresultat är `reference-ok`, `reference-diff`, `reference-summary` och `reference-not-run`.

### Kör sida 1–100, kolumn 0–2

Directional page-benchmarken tar en sida och kolumn per process, så helkörningen görs som shell-loop:

```bash
cd ~/proj/saol14-fast-forward-test
mkdir -p /tmp/saol14-directional

for page in $(seq 1 100); do
  for column in 0 1 2; do
    echo "=== page=$page column=$column ==="
    outfile=$(printf '/tmp/saol14-directional/p%03d-c%d.log' "$page" "$column")
    env PYTHONPATH=src \
    python -m swedish_wordlist_tools.ocr_directional_page_peak_benchmark \
      /home/matsj/proj/saol14-faksimil.jsonl \
      --facit glyphs/saol14-manual-glyph-facit-v2.json \
      --page "$page" --column "$column" --rows 0 \
      > "$outfile" 2>&1 \
      || echo "BENCH FAIL page=$page column=$column"
  done
done
```

Behåll felloggar; vissa sidor kan ha avvikande kolumnlayout och sådant ska inte döljas.

### Jämför hela batchen mot frusen konservativ referens

```bash
cd ~/proj/saol14-fast-forward-test
mkdir -p /tmp/saol14-directional-compare

for page in $(seq 1 100); do
  for column in 0 1 2; do
    log=$(printf '/tmp/saol14-directional/p%03d-c%d.log' "$page" "$column")
    out=$(printf '/tmp/saol14-directional-compare/p%03d-c%d.txt' "$page" "$column")
    [ -f "$log" ] || continue

    env PYTHONPATH=src \
    python -m swedish_wordlist_tools.ocr_compare_directional_reference \
      "$log" \
      tests/reference/saol14-ocr/conservative-v1/rows.jsonl \
      --page "$page" --column "$column" \
      > "$out" 2>&1 || true
  done
done

grep -h '^reference-summary:' /tmp/saol14-directional-compare/*.txt
grep -l '^reference-diff:' /tmp/saol14-directional-compare/*.txt
```

Den sista raden listar direkt vilka page/column-körningar som skiljer sig.

### Frusen konservativ sida-1–100-regression

För det äldre konservativa spåret:

```bash
/usr/bin/time -f 'TOTALT: %e s' \
env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_capture_conservative_baseline \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --start-page 1 --end-page 100 \
  --output-dir /tmp/saol14-conservative-baseline

env PYTHONPATH=src \
python -m swedish_wordlist_tools.ocr_compare_baseline \
  tests/reference/saol14-ocr/conservative-v1/rows.jsonl \
  /tmp/saol14-conservative-baseline/rows.jsonl
```

Resultatneutralitet:

```text
baseline-diff: differences=0
```

### CPU-profilering

Kör utan full trace när timing är syftet:

```bash
env PYTHONPATH=src \
python -m cProfile -s tottime \
  -m swedish_wordlist_tools.ocr_directional_page_peak_benchmark \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 36 --column 0 --rows 3 \
  > /tmp/saol14-directional-cprofile.log 2>&1

head -80 /tmp/saol14-directional-cprofile.log
```

### Skyddsvärda data och referenser

Skriv inte över dessa bara för att få ett test grönt:

```text
/home/matsj/proj/saol14-faksimil.jsonl
glyphs/facit-v2
glyphs/saol14-manual-glyph-facit-v2.json
tests/reference/saol14-ocr/conservative-v1/rows.jsonl
/home/matsj/proj/saol14-conservative-rebuild/tests/reference/saol14-ocr
```

Använd `/tmp` för nya benchmarkloggar, profiler, jämförelser och debugbilder.

### Bra rutin före/efter större optimering

1. Notera `git rev-parse HEAD`.
2. Spara p36/c0/r2-trace.
3. Spara timing utan trace.
4. Kör fokuserade unit tests.
5. Kontrollera efter ändring att `-i` fortfarande ger `start=(66,122)` och `accepted='i'`.
6. Jämför hel sida mot konservativ referens.
7. Vid större algoritmändring: kör sida 1–100 och lista alla `reference-diff`.
8. Optimera vidare först när beteendet är begripligt.

### Git-arbetsregel

Assistenten implementerar och committar på `agent/ocr-whole-column-shadow`. Mats testar lokalt på hinken. Vi itererar på loggarna. Merge till master först när Mats uttryckligen säger `Merga!`.
