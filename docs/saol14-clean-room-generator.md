# SAOL14 clean-room-generator: implementationskontrakt

## Syfte

Det här dokumentet är tänkt som startpunkt för en oberoende implementation som
läser `data/raw/saol14-faksimil.jsonl` och genererar böjningsformer **utan SALDO,
svenska.se eller någon annan lexikal jämförelsekälla i själva genereringen**.

Grundprincipen är att SAOL-artikeln är auktoritativ. En extern resurs får användas
för efterhandsaudit, men den får inte fylla i luckor, välja genus, lägga till plural
eller på annat sätt påverka vilka former generatorn producerar.

Läs också:

- `docs/saol14-faksimil-format.md` för råformat, artikel/rubrik/referensmodell och
  `homonr=0`.
- `docs/saol14-paradigm-scope.md` för den självbärande artikelregeln.

## 1. Auktoritetsordning

För varje verklig SAOL-artikel/homonym:

1. identifiera artikelns rubrik eller rubriker,
2. läs artikelns egen böjningsnotation,
3. tolka notationen som operationer på grammatiska slots,
4. generera endast de slots som artikeln själv licensierar,
5. härled endast former som följer mekaniskt av en redan licensierad slot,
6. ärv aldrig böjning från efterled, närliggande lemma eller extern ordlista.

Exempel:

- `kyrkofrid +en` licensierar singular, inte plural.
- `fack|anslutning +en` får inte ärva `+ar` från `anslutning`.
- `hyperaktivitet +en` får inte ärva `+er` från `aktivitet`.
- `fostbrödraskap +et` får inte ärva plural från `brödraskap`.

`|` är ordstruktur, inte paradigmarv.

## 2. Materialisera artiklar innan böjning

Rå-raderna är inte 1:1 med lexikala artiklar. Bygg först minst tre relationer:

- `articles`: en rad per verklig artikelhomonym,
- `headings`: primär och alternativa rubriker per artikel,
- `references`: `(hv)`-poster separat.

`homonr=1..n` är verkliga homonymer. `homonr=0` är inte en extra homonym utan en
sekundär rå-rad som måste knytas till rätt artikel via käll-/artikelkontext.

En clean-room-implementation ska kunna redovisa alla rå-rader utan att tappa dem.
På den analyserade dataversionen har följande invariants uppnåtts:

```text
rå-rader:                 126900
artiklar/homonymer:       122541
rubrikrader:              125643
hänvisningar:               1257
rubrikrader utan artikel:      0
olösta strukturer:             0
rå-rader minus redovisade:     0
```

## 3. Gemensamma notationselement

Notationen ska tokeniseras innan ordklassspecifik slot-tolkning. Följande är
primitiva operationer:

### `+`

Oförändrad basform i den aktuella sloten.

### `+suffix`

Append operation: lägg `suffix` till den relevanta basen.

Exempel för substantiv:

```text
bil +en +ar
```

ger nyckelformerna `bilen`, `bilar`.

### `-tail`

Ersätt slutdelen av basen med `tail`. För sammansättningar med ett användbart `|`
appliceras ersättningen på komponenten efter sista `|` och prefixet bevaras.

Denna operation får inte tolkas genom godtycklig suffixgissning. Om strukturen
inte ger en säker mekanisk applicering ska posten lämnas unsupported hellre än att
generatorn hittar på en form.

### fullständigt utskriven form

Ett vanligt token utan `+`/`-` kan vara en explicit ordform och ska då användas som
sådan i den slot som notationens struktur tilldelar det.

### `el.`

Nästa form är ett alternativ till föregående grammatiska slot, inte automatiskt
nästa slot.

### `pl.`

Byter kontext till plural.

### `best. pl.`

Byter kontext till bestämd plural.

### `_`

Separerar alternativa notationsgrenar. Grenarna ska inte korsproduktkombineras.
Varje gren tolkas som en egen sammanhängande instruktion.

### parenteserad optionalitet

En enkel optionalitet i en formtoken expanderas ortografiskt.

Exempel:

```text
+(e)n  -> +n, +en
håll(e)s -> hålls, hålles
```

## 4. Rubrikvarianter

Två huvudfall måste skiljas.

### Gemensam notation

Exempel:

```text
brev|bär·ing el. brev|bär·ning substantiv +en
```

Båda rubrikerna får samma paradigmoperationer. Man genererar alltså singular för
både `brevbäring` och `brevbärning`.

### Parallella grenar

När notationen har separata grenar med `_` ska rätt gren kopplas till rätt
rubrikvariant. Gör inte en korsprodukt mellan alla rubriker och alla grenar.

Varje genererad form bör bära proveniens, t.ex. artikel-id, rubrik, heading type och
vilken notationsgren som genererade formen.

## 5. Substantiv: slots

För NOUN är kärnslotsen:

```text
lemma
sg_def
pl_indef
pl_def
```

Den vanliga olabellerade ordningen är:

1. första formoperationen -> `sg_def`,
2. nästa formoperation -> `pl_indef`.

Etiketter som `pl.` och `best. pl.` överstyr denna ordning.

Exempel:

```text
+en +er
```

betyder:

```text
sg_def = lemma + en
pl_indef = lemma + er
```

och inte ett specialfall för just strängen `+en +er`.

## 6. Substantiv: mekanisk komplettering

När en NOUN-slot finns får följande former härledas mekaniskt.

### Genitiv

För varje licensierad nominativform genereras genitiv med vanlig svensk
s-genitiv:

- slutar formen redan på `s`, `x` eller `z`: lämna stavningen oförändrad,
- annars: lägg till `s`.

Det gäller lemma, bestämd singular, obestämd plural och bestämd plural när dessa
slots finns.

### Bestämd plural från explicit obestämd plural

Om `pl_indef` finns men `pl_def` inte står explicit får bestämd plural härledas
endast när artikeln också ger tillräcklig singularstruktur.

Nuvarande mekaniska regler är:

- nollplural + neutrum bestämd singular på `-et`: `hus -> husen`; lemma på `-e`
  tar `-n` i stället för `-en`,
- plural på `-n` tillsammans med neutrum singular på `-t`: lägg `a`,
- plural på `-en`: lägg `a`,
- annars: lägg `na`.

Ett bart `pl. +` utan singularstruktur licensierar inte att generatorn hittar på en
bestämd plural.

## 7. Substantiv: artikelomfång

Det här är ett hårt kontrakt:

```text
+en
+et
+n
+t
```

är singular-only om ingen pluralinstruktion också finns i artikelns egen notation.
Suffix, efterled, SALDO-paradigm eller statistisk böjningsklass får inte användas
för att lägga till plural.

Plural får genereras först när artikeln själv innehåller explicit pluralinformation,
t.ex. `+er`, `+ar`, `+n`, `pl. +`, `pl. +s`, explicit pluralform eller motsvarande
mekanisk pluraloperation.

## 8. Multiword och sammansättningar

Append/ersättningsoperationer ska appliceras på den bärare som artikelns tryckta
struktur anger.

- `|` kan identifiera vilken sammansättningskomponent som operationen gäller.
- För flerordslemma kan artikelns `stycke` ange en carrier-del medan resten av
  uttrycket lämnas orört.
- Man får inte böja ett annat ord i flerordsuttrycket bara för att det ser
  morfologiskt rimligt ut.

Om den nödvändiga bäraren inte kan identifieras mekaniskt ska resultatet vara
unsupported, inte en gissning.

## 9. Referenser är inte böjningsinstruktioner

Poster vars `ordkl` börjar med `(hv)` ska materialiseras som referenser. De ska inte
behandlas som vanliga böjningsartiklar.

Om målhomonym inte är uttrycklig i råmaterialet ska den förbli unresolved. En
clean-room-generator ska inte välja målhomonym genom likhet mot en extern källa.

## 10. Källfel och korrigeringar

Målet är mekanisk tolkning av källan, men råmaterialet kan innehålla fel. Ett
källfel får därför bara korrigeras genom en **explicit, versionsstyrd correction
manifest**, aldrig genom en dold parserregel.

För närvarande finns en dokumenterad misstänkt källkorrigering i implementationen:

```text
anhörig, homonym 1: text "pl. -a" -> "pl. +a"
```

En konkurrerande implementation kan välja att:

1. tolka rådata bokstavligt och rapportera avvikelsen, eller
2. applicera samma explicit dokumenterade correction manifest.

Den får inte generalisera detta till att `-a` alltid betyder `+a`.

## 11. Unsupported är ett giltigt resultat

En clean-room-implementation ska föredra:

```text
unsupported / cannot interpret mechanically
```

framför en lexikal gissning.

Detta är centralt för konkurrerande implementationer: målet är att mäta hur långt
SAOL-notationen själv räcker, inte att maximera täckning med specialfall.

## 12. Externa källor får endast användas efteråt

SALDO, svenska.se eller annan ordlista får användas för:

- audit,
- jämförelse,
- felsökning,
- upptäckt av misstänkta källfel.

De får inte användas för att:

- lägga till en plural som SAOL inte anger,
- välja genus,
- välja homonym,
- ärva efterledens paradigm,
- fylla en unsupported slot.

En generator ska därför kunna köras från SAOL14-faksimilen ensam och producera
samma output oavsett om SALDO finns installerat eller inte.

## 13. Vad som är fruset och vad som ännu inte är det

### Fruset nog för clean-room-jämförelse

- råformatets artikel/rubrik/referensmodell,
- `homonr=0`-semantiken,
- alternativa rubriker,
- ordklassneutrala formoperationer,
- den självbärande artikelregeln,
- NOUN-slotmodellen och NOUN:s mekaniska komplettering ovan,
- principen att unsupported är bättre än gissning.

### Inte ännu fullständigt fruset i dokumentation

Adjektiv och verb har fungerande implementationskod och omfattande tester, men
alla deras ordklassspecifika slotregler och historiska source-corrections är ännu
inte dokumenterade här som ett komplett clean-room-kontrakt.

**Konsekvens:** det här dokumentet räcker idag för att någon ska skriva en
oberoende relationsmaterialisering och en konkurrerande NOUN-generator. Det räcker
inte ännu för att lova en fullständigt specifikationsdriven clean-room-generator
för samtliga ordklasser utan att läsa befintlig kod.

## 14. Rekommenderad clean-room-arbetsgång

1. Hämta exakt samma `saol14-faksimil.jsonl`.
2. Implementera relationsmaterialisering utan att läsa befintlig generatorcode.
3. Kontrollera de strukturella invariants i avsnitt 2.
4. Implementera notationstokenisering och de fyra primitiva operationerna.
5. Implementera NOUN-slotmappning och komplettering enligt avsnitt 5–7.
6. Generera former med proveniens.
7. Jämför först därefter output mot projektets genererade artefakt.
8. Rapportera skillnader som antingen struktur-, tolkning-, source-error- eller
   unsupported-skillnad.

Den konkurrerande implementationen ska inte optimera mot vår output. Skillnader är
själva poängen med clean-room-kontrollen.
