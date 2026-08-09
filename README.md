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

Clean-room-specifikationen är idag tillräckligt frusen för relationsmaterialisering och NOUN. Adjektiv och verb har fungerande kod och tester, men deras fullständiga ordklassspecifika slotkontrakt är ännu inte dokumenterade lika komplett.

## Viktiga artefakter

Den kanoniska NOUN-generatorn skriver:

```text
reports/saol14-noun-forms.jsonl
```

Adjektivgeneratorn skriver:

```text
reports/saol14-adjective-forms.jsonl
```

Validerings- och auditrapporter under `reports/` är diagnostik. De är inte en del av den auktoritativa genereringsregeln.

## Nuvarande arbetssätt

1. Tolka SAOL-strukturen mekaniskt.
2. Generera det artikeln själv licensierar.
3. Bevara proveniens och unsupported-fall.
4. Jämför först därefter mot externa resurser för att hitta källskillnader, homonymproblem eller parserfel.

Målet är att en konkurrerande implementation ska kunna generera från SAOL 14 utan att optimera mot projektets egen output eller mot SALDO.
