# swedish-wordlist-tools

Verktyg för att analysera SAOL 14 och bygga kvalitetssäkrade svenska ordlistor med böjningsformer.

Projektet börjar försiktigt: första versionen laddar ned SAOL 14:s JSONL-fil och kartlägger datans fält och böjningsnotationer. Själva böjningsgeneratorn byggs först när formatet är analyserat.

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

Analysera filen:

```bash
saol14-inspect
```

Det skriver en sammanfattning i terminalen och en full rapport till:

```text
reports/saol14-inspection.json
```

## Tester

```bash
python -m unittest discover -s tests
```

## Planerade steg

1. Kartlägg fält och notationer i hela SAOL 14.
2. Gruppera böjningsmönster per ordklass.
3. Importera den befintliga ordlistan som referens/facit.
4. Generera former med spårbarhet till uppslagsordet.
5. Exportera en filtrerad ordlista för olsbogo.

## Princip

SAOL 14 är huvudkälla. Äldre ordlistor används för kontroll och avvikelseanalys, inte för en blind sammanslagning.
