# SAOL14 clean-room-generator: implementationskontrakt

## Syfte

Det här dokumentet är tänkt som startpunkt för en oberoende implementation som
läser `data/raw/saol14-faksimil.jsonl` och genererar böjningsformer **utan SALDO,
svenska.se eller någon annan lexikal jämförelsekälla i själva genereringen**.

Grundprincipen är att SAOL-artikeln är auktoritativ. En extern resurs får användas
för efterhandsaudit, men den får inte fylla i luckor, välja genus, lägga till plural
eller på annat sätt påverka vilka former generatorn producerar.

NOUN-kontraktet nedan är nu fruset mot den analyserade SAOL14-exporten: samtliga
icke-trunkerade NOUN-notationer som nått den slutliga parserauditen är mekaniskt
tolkbara, med `0` kvarvarande notationer och `0` unsupported i den senaste fulla
valideringen. Det betyder inte att externa resurser alltid håller med SAOL; sådana
skillnader är auditresultat, inte generatorregler.

Läs också:

- `docs/saol14-faksimil-format.md` för råformat, artikel/rubrik/referensmodell och
  `homonr=0`.
- `docs/saol14-paradigm-scope.md` för den självbärande artikelregeln.

## 1. Auktoritetsordning

För varje verklig SAOL-artikel/homonym:

1. identifiera artikelns rubrik eller rubriker,
2. identifiera den faktiska skrivna artikelbasen,
3. läs artikelns egen böjningsnotation,
4. tokenisera notationen till oberoende operationer och grenmarkörer,
5. mappa operationerna till grammatiska slots,
6. generera endast de slots som artikeln själv licensierar,
7. härled endast former som följer mekaniskt av en redan licensierad slot,
8. ärv aldrig böjning från efterled, närliggande lemma eller extern ordlista.

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

### 2.1 `normaliserat_ord` är inte alltid artikelbasen

`normaliserat_ord` är en viktig relations-/grupperingsnyckel, men får inte blint
användas som den skrivna bas som böjningsoperationerna appliceras på.

Ett observerat fall är:

```text
normaliserat_ord = kaprifol
ord              = kapri·foli·um
stycke           = kapri·foli·um
text             = kaprifolien kaprifolier
```

Den raden beskriver den skrivna artikeln `kaprifolium`, inte ytterligare former av
basen `kaprifol`. När städat `ord` och städat `stycke` entydigt anger samma skrivna
lemma får denna skrivna form därför vara artikelbas även om `normaliserat_ord`
skiljer sig.

Regeln ska vara konservativ. `normaliserat_ord` får inte ersättas av en mekanisk
sammanslagning av delar i `ord`: exempelvis `hall|ländska` normaliseras till
`halländska`, inte `hallländska`. Använd den skrivna artikelbasen endast när
`ord`/`stycke` själva ger entydigt stöd för den.

## 3. Gemensamma notationselement

Notationen ska tokeniseras innan ordklassspecifik slot-tolkning. **Varje formtoken
ska behandlas som en egen operation.** Implementationen ska inte bygga regler för
hela strängar som `+en; pl. +er el. +ar _ +n`.

### `+`

Oförändrad basform i den aktuella sloten.

### `+suffix`

Append operation: lägg `suffix` till den relevanta basen.

Exempel:

```text
bil +en +ar
```

ger nyckelformerna `bilen`, `bilar`.

`+en`, `+ar`, `+n`, `+t` osv. är inte olika parserfall. De är samma append-operation
med olika operand.

### `-tail`

Ersätt slutdelen av basen med `tail`. För sammansättningar med ett användbart `|`
appliceras ersättningen på den bärare som den tryckta strukturen anger och prefixet
bevaras.

Exempel som `flå|hacka +n -hackor` och `hall|ländska +n -ländskor` ska alltså inte
kräva lexikala specialfall för `hacka` eller `ländska`.

Operationen får inte tolkas genom godtycklig suffixgissning. Om strukturen inte ger
en säker mekanisk applicering ska posten lämnas unsupported hellre än att
generatorn hittar på en form.

### Fullständigt utskriven form

Ett vanligt token utan `+`/`-` är en explicit ordform när notationens struktur
placerar det i en böjningsslot. Den ska användas direkt och är principiellt samma
sorts instruktion oavsett ordklass.

Exempel:

```text
anka:      +n ankor
ganglion:  gangliet ganglier
bob:       bobben bobbar
```

`ankor`, `gangliet`, `ganglier`, `bobben` och `bobbar` är alltså inte specialfall.
De är explicita formoperationer. Samma princip ska senare kunna användas för t.ex.
verbens `springa -> sprang -> sprungit` och `kunna -> kan`.

Sentinelvärden som `(null)`/`null` är däremot frånvaro av notation och får aldrig
tolkas som explicita ordformer.

### `el.`

Nästa form är ett alternativ till föregående grammatiska slot, inte automatiskt
nästa slot.

### `ibl.`

`ibl.` betyder `ibland` och markerar en fullt giltig alternativ form. Den ändrar
inte operationens mekanik och ska inte göra alternativet unsupported.

### `pl.`

Byter kontext till plural.

### `best. pl.`

Byter kontext till bestämd plural.

### `_`

Separerar parallella notationsgrenar. Varje gren tolkas självständigt och ska inte
korsproduktkombineras med de andra.

Exempel:

```text
+en; pl. +er el. +ar _ +n
```

ska förstås som oberoende formoperationer inom två grenar, inte som ett namngivet
specialparadigm.

På samma sätt är blandningar av relativ och explicit notation normala:

```text
+en _ ankaret
+n +ar _ bh:n bh:ar
dreglet _ dräglet
tv:n tv:ar _ teven tevear
```

### Uttalsnotation

Hakparenteser med uttalsinformation, t.ex. `[haj>pen]`, är inte böjningsoperationer
och ska inte påverka formgenereringen.

### Parenteserad optionalitet

En enkel optionalitet i en formtoken expanderas ortografiskt.

Exempel:

```text
+(e)n    -> +n, +en
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

`homonr=0` kan bära variantinformation för samma artikel. Det ska inte skapas en
extra lexikal homonym av detta, och identiska genererade ordformer behöver inte
dupliceras i den slutliga ordlistan. Proveniensen ska däremot kunna visa alla
rubriker/artikelgrenar som licensierar formen.

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

Det gäller oavsett om operationen är `+suffix`, `-tail` eller en fullt utskriven
form. Etiketter som `pl.` och `best. pl.` överstyr ordningen.

Exempel:

```text
+en +er
```

betyder:

```text
sg_def = append("en")
pl_indef = append("er")
```

och inte ett specialfall för just strängen `+en +er`.

Likaledes betyder:

```text
gangliet ganglier
```

```text
sg_def = explicit("gangliet")
pl_indef = explicit("ganglier")
```

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
- Normaliserad stavning får inte rekonstrueras genom naiv konkatenering av
  komponenter; använd källans normaliserade form eller en entydigt skriven
  artikelbas enligt avsnitt 2.1.

Om den nödvändiga bäraren inte kan identifieras mekaniskt ska resultatet vara
unsupported, inte en gissning.

## 9. Referenser är inte böjningsinstruktioner

Poster vars `ordkl` börjar med `(hv)` ska materialiseras som referenser. De ska inte
behandlas som vanliga böjningsartiklar.

En hänvisningsrad kan samtidigt ge viktig strukturell evidens om en alternativ
stavning, men den får inte användas som en dold extern paradigmregel.

Om målhomonym inte är uttrycklig i råmaterialet ska den förbli unresolved. En
clean-room-generator ska inte välja målhomonym genom likhet mot en extern källa.

## 10. Trunkerad källtext och källfel

### 50-teckenstrunkering

Den analyserade exporten innehåller rader där `text` är avklippt vid 50 tecken.
Dessa ska klassificeras separat som `source_text_truncated`. Ett avklippt slut får
inte fyllas i genom SALDO, svenska.se, efterledsparadigm eller sannolikhetsregler.

I den senaste fulla NOUN-valideringen låg **106 poster** i denna kategori. De är
källdataproblem/osäkerheter, inte kända parserfel.

### Explicita korrigeringar

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

Att den nuvarande NOUN-auditen har nått `0` unsupported är ett resultat av generisk
tolkning av notationselementen ovan, inte ett skäl att ersätta principen med
fallback-gissningar.

## 12. Externa källor får endast användas efteråt

SALDO, svenska.se eller annan ordlista får användas för:

- audit,
- jämförelse,
- felsökning,
- upptäckt av misstänkta källfel,
- oberoende stickprov av former som redan genererats från SAOL.

De får inte användas för att:

- lägga till en plural som SAOL inte anger,
- välja genus,
- välja homonym,
- ärva efterledens paradigm,
- fylla en unsupported eller trunkerad slot.

En generator ska därför kunna köras från SAOL14-faksimilen ensam och producera
samma output oavsett om SALDO finns installerat eller inte.

Vid jämförelse ska minst följande hållas isär:

- `exact_form_set` / case-skillnad,
- `saol_forms_are_subset`,
- verklig formmismatch,
- `variant_coverage_difference`,
- `source_text_truncated`,
- parser-`unsupported`.

En `variant_coverage_difference` är inte i sig evidens för ett parserfel. Den kan
betyda att SALDO saknar eller modellerar en SAOL-rubrikvariant annorlunda.

## 13. Nuvarande NOUN-baslinje

Senaste fulla körningen efter att explicit-formtolkningen generaliserats gav:

```text
Substantivposter:                  95089
Kanoniskt genererade poster:       95070
Kanoniska formrader:              685886
remaining noun notations:              0
unsupported nouns:                    0
source_text_truncated:               106
variant_coverage_difference:          108
```

De två nollorna är clean-room-kontraktets viktigaste regressionsmått: bland de
fullständiga rader som når parserauditen finns inga kända notationer som kräver ett
lexikalt specialfall och inga kända unsupported NOUN-paradigm.

`source_text_truncated` ska inte pressas till noll genom parserregler. Den gruppen
måste lösas genom bättre källdata eller lämnas explicit osäker.

SALDO-mismatchar och proveniensrapporter är diagnostik och får inte användas som
målvärde för generatorn.

## 14. Vad som är fruset och vad som ännu inte är det

### Fruset nog för clean-room-jämförelse

- råformatets artikel/rubrik/referensmodell,
- `homonr=0`-semantiken,
- skillnaden mellan `normaliserat_ord` och faktisk skriven artikelbas,
- alternativa rubriker,
- ordklassneutrala `+`, `-` och explicit-formoperationer,
- oberoende token-/slot-tolkning i stället för helparadigmspecialfall,
- `_` som parallella grenar utan korsprodukt,
- `el.` och `ibl.` som alternativmarkörer,
- den självbärande artikelregeln,
- NOUN-slotmodellen och NOUN:s mekaniska komplettering ovan,
- principen att uttalsnotation inte är böjningsnotation,
- principen att trunkerad text är källosäkerhet,
- principen att unsupported är bättre än gissning.

### Inte ännu fullständigt fruset i dokumentation

Adjektiv och verb har fungerande implementationskod och omfattande tester, men
alla deras ordklassspecifika slotregler och historiska source-corrections är ännu
inte dokumenterade här som ett komplett clean-room-kontrakt.

**Konsekvens:** det här dokumentet räcker idag för att någon ska skriva en
oberoende relationsmaterialisering och en konkurrerande NOUN-generator. Det räcker
inte ännu för att lova en fullständigt specifikationsdriven clean-room-generator
för samtliga ordklasser utan att läsa befintlig kod.

## 15. Rekommenderad clean-room-arbetsgång

1. Hämta exakt samma `saol14-faksimil.jsonl`.
2. Implementera relationsmaterialisering utan att läsa befintlig generatorkod.
3. Kontrollera de strukturella invariants i avsnitt 2.
4. Identifiera faktisk artikelbas utan att anta att den alltid är
   `normaliserat_ord`.
5. Implementera notationstokenisering där varje `+`, `-` och explicit form är en
   oberoende operation.
6. Implementera branch-/alternativmarkörer (`_`, `el.`, `ibl.`) separat från
   formoperationerna.
7. Implementera NOUN-slotmappning och komplettering enligt avsnitt 5–7.
8. Generera former med proveniens och deduplicera identiska skrivformer utan att
   kasta proveniensen.
9. Klassificera trunkerade källrader separat.
10. Jämför först därefter output mot projektets genererade artefakt eller externa
    lexikala resurser.
11. Rapportera skillnader som struktur-, tolkning-, source-error-, truncation-,
    variant-coverage- eller unsupported-skillnad.

Den konkurrerande implementationen ska inte optimera mot vår output. Skillnader är
själva poängen med clean-room-kontrollen.
