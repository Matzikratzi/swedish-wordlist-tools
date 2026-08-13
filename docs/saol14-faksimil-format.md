# SAOL14-faksimil.jsonl — format och rekonstruerad semantik

Det här dokumentet beskriver hur `data/raw/saol14-faksimil.jsonl` beter sig i praktiken, baserat på systematisk analys av hela filen och jämförelser mot SAOL-artiklar. Syftet är att en oberoende implementation ska kunna tolka materialet utan att känna till den befintliga koden.

## Översikt

Filen är JSONL: en JSON-post per rad. Poster representerar inte alltid en fristående lexikal artikel. En råpost kan vara:

1. en primär artikelrubrik,
2. en alternativ rubrik som hör till samma artikel,
3. en hänvisningspost `(hv)`,
4. i vissa fall en böjnings-/relationshänvisning med extra notation.

Därför bör man inte använda `normaliserat_ord` + `homonr` som enda identitet utan att samtidigt tolka `ord`, `stycke`, `ordkl`, `urspr_lopnr` och `subnr`.

## Vanliga fält

### `normaliserat_ord`

Normaliserat lemma för den underliggande artikeln. Viktigt: för alternativa rubriker och hänvisningsposter kan detta vara **målartikeln** snarare än den synliga rubriken i `ord`.

Exempel:

```json
{"normaliserat_ord":"akne", "homonr":"0", "ord":"acne", ...}
```

Här är `acne` den aktuella rubriken, medan `akne` är den artikelpost som rubriken hör till.

### `homonr`

Homonymnummer för riktiga artikelhomonymer. Observerade värden inkluderar `1`, `2`, `3`, `4` och `0`.

- `1..n` = verklig homonymidentitet.
- `0` = **inte en verklig homonym 0**. I materialet används `0` för sekundära rå-rader som hör till en redan etablerad artikel, främst alternativa rubriker och vissa hänvisningsstrukturer.

`homonr=0` kan följa efter vilken verklig homonym som helst, inte bara homonym 1. Exempel: en alternativ rubrik kan tillhöra homonym 2.

### `ord`

Det viktigaste fältet för den aktuella rubriken. Det är inte bara en displayvariant av `normaliserat_ord` eller `stycke`.

`ord` kan innehålla:

- sammansättningsgräns `|`, t.ex. `bank|väsen`,
- stavelse-/uttalsmarkering `·`, t.ex. `abro·vink`,
- explicit homonymnummer som HTML, t.ex. `<sup>2</sup>abs·trakt`,
- alternativ rubrik, t.ex. `bank|väsende`,
- hänvisningsrubrik, t.ex. `färre`,
- versaliserad variant, t.ex. `Amar·ant`.

### `stycke`

Den tryckta artikelrubrik/ingång som raden är knuten till. För primära artikelrader brukar `ord` och `stycke` beskriva samma rubrik efter att markup ignorerats. För alternativa rubriker och hänvisningar kan de skilja sig.

Praktisk tolkning:

- `stycke` ≈ artikelkontext,
- `ord` ≈ den aktuella rubriken/radens lexikala uttryck.

### `ordkl`

Ordklass och ibland presentations-/hänvisningsinformation från SAOL.

Vanliga exempel:

- `s. <i>+en +er</i>`
- `adj. <i>+t +a</i>`
- `v. <i>...</i>`
- `(hv)`
- `(hv) <i>komp.</i>`

Viktigt: hänvisningsposter identifieras inte bara av exakt `ordkl == "(hv)"`; alla värden som börjar med `(hv)` ska behandlas som hänvisningar.

### `text`

Böjningsnotationen, t.ex.:

```text
+en +er
+t +n
+det; pl. +, best. pl. +dena _ +t +n
```

`_` används för att separera alternativa böjningsgrenar i samma artikel. Notationen är kompakt och måste tolkas tillsammans med artikelrubrikerna.

### `upos`

Grov ordklass, t.ex. `NOUN`, `ADJ`, `VERB`, `PRON`, `X`.

`X` betyder inte en enda grammatisk klass. I materialet används det bland annat för:

- hänvisningsposter `(hv)`,
- adverb och andra poster som inte mappats till en snäv UPOS-klass,
- diverse specialposter.

Alltså: `upos == "X"` ska inte tolkas som semantiskt homogen kategori.

### `urspr_lopnr` och `subnr`

Källidentiteter/sekvensnummer. För de analyserade posterna är de ofta lika. Sekvensen är i huvudsak källordning, inte lexikal sorteringsnyckel. Hänvisningsrader kan göra att ordningen ser alfabetiskt "fel" ut, eftersom `normaliserat_ord` då kan peka på målartikeln medan `ord` är den synliga rubriken på den aktuella sidan.

### `sidnr1`, `sidnr2`, `source`

Källproveniens till SAOL-faksimilen. `source` pekar på motsvarande skannad sida.

## Homonymer

Explicit homonymmarkup i `ord` använder `<sup>n</sup>`.

Exempel:

```json
{"homonr":"4", "ord":"<sup>4</sup>abs·trakt", ...}
```

I en fullständig audit av filen stämde explicit `<sup>n</sup>` konsekvent med `homonr`; inga avvikelser observerades i de analyserade posterna.

Rekommendation: när `<sup>n</sup>` finns, behandla det som en stark explicit homonymankare.

## Alternativa rubriker och `homonr=0`

Ett vanligt mönster är två rå-rader med samma `urspr_lopnr`/`subnr` och samma artikelmetadata:

```json
{"normaliserat_ord":"abrovink","homonr":"1", ...,"ord":"abro·vink"}
{"normaliserat_ord":"abrovink","homonr":"0", ...,"ord":"abro·vinsch"}
```

Det betyder inte två homonymer. Det betyder en artikel med två rubriker/varianter.

Samma sak för:

```json
{"normaliserat_ord":"bankväsen","homonr":"1", ...,"ord":"bank|väsen"}
{"normaliserat_ord":"bankväsen","homonr":"0", ...,"ord":"bank|väsende"}
```

Den tryckta SAOL-artikeln motsvarar:

```text
bank|väsen ... el. bank|väsende ...
```

### Viktig regel

`homonr=0` måste knytas till den verkliga artikelhomonymen genom artikelkontext/källidentitet, inte genom antagandet att den alltid hör till homonym 1.

## Hänvisningsposter `(hv)`

`(hv)` står för hänvisningspost i råformatet. `normaliserat_ord` pekar normalt på målartikeln och `ord` är den synliga hänvisningsrubriken.

Exempel:

```json
{"normaliserat_ord":"akne","homonr":"1","ordkl":"(hv)","ord":"acne", ...}
```

På den tryckta sidan motsvarar detta ungefär "acne variantform till akne".

Ett annat exempel:

```json
{"normaliserat_ord":"få","homonr":"0","ordkl":"(hv) <i>komp.</i>","ord":"färre", ...}
```

Detta är en böjningshänvisning från `färre` till artikeln `få`.

### Begränsning

Råformatet innehåller inte alltid tillräckligt med information för att identifiera **vilken homonym** av mållemman som avses. Exempelvis kan två identiska hänvisningsrubriker `de` peka på olika homonymer av `den`, men någon explicit målhomonym finns inte i posten.

En konkurrerande implementation bör därför representera sådana mål som "lemma resolved, homonym unresolved" i stället för att gissa.

## Lodstreck `|`

`|` markerar sammansättningsgräns i SAOL-rubriken. Det ska inte bara tas bort och glömmas bort; det kan vara relevant när alternativa rubriker eller sammansättningsstammar ska förstås.

Exempel:

```text
bank|väsen
bank|väsende
brev|bär·ing
brev|bär·ning
```

För normaliserad ordform kan `|` tas bort, men den strukturella informationen bör bevaras separat om möjligt.

## Alternativa varianter och böjningsnotation

Två huvudmönster har observerats.

### Shared notation

Flera rubriker delar samma notation. Exempel:

```text
brev|bär·ing el. brev|bär·ning substantiv ~en
```

Båda rubrikerna böjs enligt samma mönster:

```text
brevbäring, brevbärings, brevbäringen, brevbäringens
brevbärning, brevbärnings, brevbärningen, brevbärningens
```

Det är missvisande att se detta som två oberoende artiklar; det är en artikel med två rubrikstammar och gemensamt paradigm.

### Parallel branches

I andra artiklar anger notationen två explicita grenar separerade med `_`. Då bör varje gren kopplas till rätt rubrikvariant i stället för att korsprodukt-generera alla kombinationer.

## Rekommenderad relationsmodell

En robust implementation bör materialisera råformatet till minst tre logiska relationer.

### `articles`

En rad per verklig artikelhomonym.

Minimala fält:

```text
article_id
lemma
homonym_number
upos
notation
record_id / source ids
source page
```

### `headings`

En rad per rubrik som hör till artikeln.

```text
article_id
heading
heading_type = primary | alternative
raw_homonym_number
source_order
```

### `references`

En rad per `(hv)`-post.

```text
source_heading
target_lemma
target_homonym = nullable/unresolved
reference_type
source ids
```

Observerade referenstyper som är användbara att skilja på:

- `plain_reference`
- `inflection_reference`
- `morphology_annotated_reference`

## Förlustfri materialisering

En verifierad materialisering av hela filen gav:

```text
Rå-rader: 126900
Artiklar/homonymer: 122541
Rubrikrader: 125643
Hänvisningar: 1257
Rubrikrader utan artikel: 0
Olösta strukturer: 0
Rå-rader minus redovisade: 0
```

Det visar att `articles + headings + references` räcker för att redovisa samtliga rå-rader i den analyserade versionen av filen.

## Formproveniens

När böjningsformer genereras bör varje form bära information om vilken rubrik den genererades från.

Rekommenderad modell:

```json
{
  "written_form": "brevbärningen",
  "generated_from": [
    {
      "article_id": "9875",
      "heading": "brevbärning",
      "heading_type": "alternative"
    }
  ]
}
```

Om två rubriker producerar samma form ska båda anges i `generated_from`.

Detta är viktigt för att skilja:

- böjningsskillnader,
- varianttäckningsskillnader,
- alternativa stavningar som saknas i en jämförelsekälla.

## Två oberoende jämförelseaxlar

Vid jämförelse mot en annan lexikal resurs, t.ex. SALDO, bör man inte pressa allt till en enda `form_set_mismatch`.

Använd två oberoende axlar:

### Variant coverage

```text
full
partial
missing
not_applicable
```

Fråga: finns alla SAOL-rubriker representerade i jämförelsekällan?

### Paradigm status

För de varianter som faktiskt finns i båda källorna:

```text
exact_form_set
exact_form_set_case_difference
saol_forms_are_subset
form_set_mismatch
not_comparable
```

Exempel `brevbäring / brevbärning` mot SALDO:

```text
coverage = partial
paradigm = saol_forms_are_subset
```

SALDO saknar den alternativa rubriken `brevbärning`, samtidigt som den representerade huvudvarianten har fler pluralformer än SAOL.

## Kända osäkerheter och sådant man inte bör anta

1. `homonr=0` är inte en lexikal homonym.
2. En `(hv)`-post behöver inte ha exakt `ordkl == "(hv)"`; kontrollera prefix.
3. `normaliserat_ord` är inte alltid den synliga rubriken.
4. `upos=X` är heterogent.
5. Hänvisningsmålets homonym är ibland omöjlig att avgöra ur JSONL-posten ensam.
6. `urspr_lopnr`/`subnr` är inte alfabetiska nycklar.
7. Alternativa rubriker ska inte generera en okontrollerad korsprodukt av alla böjningsgrenar.
8. Lodstreck och annan rubrikmarkup bör normaliseras för ordform men bevaras som struktur/proveniens.

## Rekommenderad implementeringsordning

1. Läs JSONL utan att generera former.
2. Klassificera varje rå-rad som artikelrubrik, alternativ rubrik eller hänvisning.
3. Bygg verkliga artikelhomonymer och länka `homonr=0`-rader till rätt artikel.
4. Materialisera rubriker separat från artiklar.
5. Tolka böjningsnotation per artikel och variantgren.
6. Generera former med `generated_from`-proveniens.
7. Validera relationell täckning: inga rå-rader får tappas.
8. Vid källjämförelse: mät variant coverage och paradigm status separat.

## Oberoende verifiering

En konkurrerande implementation bör minst kontrollera följande invariants på samma dataversion:

```text
raw rows accounted for == total raw rows
headings without article == 0
unresolved structural rows == 0
explicit <sup>n</sup> agrees with homonr
```

Dessutom bör kända exempel som `akne/acne`, `bankväsen/bankväsende`, `brevbäring/brevbärning`, `abrovink/abrovinsch` och `få/färre` användas som regressionstester.
