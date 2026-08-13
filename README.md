# swedish-wordlist-tools

Verktyg för att analysera SAOL 14 och bygga spårbara svenska ordlistor med böjningsformer.

Projektets huvudprincip är att **SAOL 14 är auktoritativ källa för artikelstruktur och böjningsomfång**. Andra resurser, t.ex. SALDO, används för efterhandsaudit och avvikelseanalys men ska inte styra vilka former SAOL-generatorn producerar.

## Datakälla

SAOL 14 (2015) – faksimil, distribuerad av Språkbanken Text under CC BY 4.0:

- https://spraakbanken.gu.se/resurser/saol14-faksimil
- DOI: 10.23695/fqh2-af42

Rådata checkas inte in i Git.

## Kom igång

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Hämta SAOL 14:

```bash
saol14-download
```

Kör tester:

```bash
python -m unittest discover -s tests
```

## Arkitektur

Råfilen `saol14-faksimil.jsonl` materialiseras först som artiklar/homonymer,
rubriker/varianter och hänvisningar. Böjningsnotation tolkas därefter som generella
formoperationer som mappas till ordklassspecifika slots.

Viktiga principer:

- varje SAOL-artikel är en självbärande böjningsenhet,
- sammansättningar ärver inte paradigm från efterleden,
- `homonr=0` är sekundär artikelstruktur, inte en verklig extra homonym,
- alternativa rubriker och alternativa notationsgrenar måste hållas strukturellt isär,
- genererade former ska bära proveniens,
- unsupported är bättre än att gissa,
- SALDO/svenska.se får användas för audit, inte för att fylla luckor i generatorn.

## Dokumentation

För en oberoende implementation, börja här:

1. `docs/saol14-clean-room-generator.md` – implementationskontrakt för en generator som inte använder externa lexikala facit.
2. `docs/saol14-faksimil-format.md` – råformat, artikel/rubrik/referensmodell och kända strukturella slutsatser.
3. `docs/saol14-paradigm-scope.md` – den självbärande artikelregeln och varför plural/paradigm inte får ärvas från högersvansen.
4. `docs/saol14-noun-sag-reference.md` – SAG-regler som används för mekanisk komplettering av redan SAOL-licensierade NOUN-slots.

Clean-room-specifikationen är idag tillräckligt frusen för relationsmaterialisering och NOUN. Adjektiv och verb har fungerande kod och tester, men deras fullständiga ordklassspecifika slotkontrakt är ännu inte dokumenterade lika komplett.

## Viktiga artefakter

### Kanonisk spelordlista

Den officiella spelordlistan byggs reproducerbart med:

```bash
python -m swedish_wordlist_tools.build_final_wordlist_pipeline
```

Efter `python -m pip install -e .` finns samma kommando även som
`saol14-build-final-wordlist`.

Kommandot kör tre avgränsade steg:

1. bygger den gemensamma, proveniensförsedda SAOL14-ordlistan,
2. normaliserar till NFC och gemener, kräver minst två bokstäver och deduplicerar,
3. jämför den färdiga listan globalt med `saldom.xml` som en separat audit.

Kompakt SAOL-notation tolkas som paradigm. Exempelvis kompletteras det
regelbundna första verbparadigmet `+de +t` mekaniskt med presens, passiv,
imperativ och particip. Regelbundna positiva adjektiv får också den maskulina
bestämda formen på `-e`. Kompletteringarna bygger endast på SAOL-notation och
allmän morfologi; de hämtar inga former från SALDO.

Den kanoniska outputen är:

```text
data/processed/saol14-gamewords.txt
```

SALDO läses först efter att filen har skrivits och kan därför varken lägga till,
ta bort eller godkänna former. Skillnaderna hamnar i:

```text
reports/saol14-gamewords-vs-saldo.txt
reports/saol14-gamewords-only-saol14.txt
reports/saol14-gamewords-only-saldo.txt
reports/saol14-gamewords-saldo-review-candidates.jsonl
```

Den fullständiga bygg- och dedupliceringsredovisningen finns i
`reports/saol14-gamewords-summary.json`. Alla bortfiltrerade SAOL-rader, med
orsak och proveniens, finns i `reports/saol14-gamewords-rejected.jsonl`. Den
normaliserade ordlistan med bibehållen proveniens finns i
`reports/saol14-gamewords.jsonl`.

De äldre kommandona `saol14-game-wordlist-legacy` och
`saol14-build-game-wordlist-legacy` skapar historiska SALDO-filtrerade
diagnostikartefakter under `legacy-*`. De är inte en alternativ väg till den
officiella filen.

Den kanoniska NOUN-generatorn skriver:

```text
reports/saol14-noun-forms.jsonl
```

Adjektivgeneratorn skriver:

```text
reports/saol14-adjective-forms.jsonl
```

Validerings- och auditrapporter under `reports/` är diagnostik. De är inte en del av den auktoritativa genereringsregeln.

### Bygg alltid om NOUN-artefakten före validering

`revalidate_direct_forms` läser den redan materialiserade filen
`reports/saol14-noun-forms.jsonl`; kommandot regenererar inte NOUN-formerna.
Efter en ändring i NOUN-generatorn ska därför artefakten byggas om först.

Det säkra standardkommandot är:

```bash
python -m swedish_wordlist_tools.refresh_noun_validation
```

Det kör i ordning:

1. `generate_noun_forms`
2. `revalidate_direct_forms`
3. `rebaseline_noun_validation`
4. `analyze_remaining_noun_notations`

På så sätt kan en gammal NOUN-artefakt inte av misstag användas som bevis för att en ny generatorregel saknar effekt.

## Nuvarande arbetssätt

1. Tolka SAOL-strukturen mekaniskt.
2. Generera det artikeln själv licensierar.
3. Bevara proveniens och unsupported-fall.
4. Bygg om den kanoniska ordklassartefakten efter generatorändringar.
5. Jämför först därefter mot externa resurser för att hitta källskillnader, homonymproblem eller parserfel.

Målet är att en konkurrerande implementation ska kunna generera från SAOL 14 utan att optimera mot projektets egen output eller mot SALDO.
