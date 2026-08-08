# SAOL14 paradigmomfång

## Stark empirisk regel: varje artikel är självbärande

Varje SAOL-artikel behandlas som en självbärande böjningsenhet. Generatorn ska
utgå från den enskilda artikelns egen notation och får inte ärva böjningsinformation
från en morfologisk familj, från ett separat uppslagsord eller från högersvansen i
en sammansättning.

Detta är i första hand empiriskt belagt för paradigmomfång/plural. Som
arkitekturregel gäller samma princip hela böjningsanalysen: genus/bestämd singular,
plural, bestämd plural, stamväxlingar och alternativa former ska komma från den
aktuella artikeln eller från generella operationer som är direkt licensierade av
den aktuella artikelns notation. Generatorn ska alltså inte slå upp högersvansen
för att fylla luckor.

Sammansättningsstrecket `|` i exempel som `fack|anslutning` beskriver ordstruktur.
Det kan användas för att förstå var en uttrycklig stam- eller suffixoperation ska
appliceras, men det är **inte** en länk som säger att generatorn ska slå upp
`anslutning` och komplettera `fackanslutning` med dess paradigm.

## Exempel

- `kyrkofrid` har notation `+en` och genereras därför endast i singularformer.
- `fostbrödraskap` har notation `+et`, trots att `brödraskap` som eget uppslagsord
  har explicit plural.
- `hyperaktivitet` har notation `+en`, trots att `aktivitet` som eget uppslagsord
  har `+en +er`.
- `ackordsarbete` har notation `+t`, trots att `arbete` som eget uppslagsord har
  `+t +n`.
- `fackanslutning` har notation `+en`, trots att `anslutning` som eget uppslagsord
  har `+en +ar`.

2026 års svenska.se har manuellt kontrollerats för `kyrkofrid`,
`fostbrödraskap` och `hyperaktivitet` och visar endast singularformer för dessa
artiklar. Det stratifierade 42-ordsstickprovet används för fortsatt manuell
kontroll av fler efterledsfamiljer.

## Empiriskt stöd i SAOL14-faksimilen

Auditen `analyze_singular_only_compound_heads` hittar 6 252 singular-only-
sammansättningar där efterleden som eget uppslagsord har explicit plural, fördelat
på 1 017 unika efterleder. Mönstret förekommer bland annat med efterlederna
`aktivitet`, `anslutning`, `arbete`, `ansvar`, `bekämpning`, `frihet`,
`skyldighet`, `säkerhet`, `produktion`, `forskning` och `brödraskap`.

Detta är starkt stöd för att pluralomfång inte ska ärvas mekaniskt från efterleden.
Det tidigare exemplet `höns|arv` används inte som evidens, eftersom `arv` har
homonymer och sammansättningen hör ihop med växtbetydelsen, inte med neutrumordet
`arv`. Homonymer måste alltså hållas isär när högersvansar används i audit och
förklaringar.

## Generatorimplikation

En notation som endast ger bestämd singular, till exempel `+en`, `+et`, `+n` eller
`+t`, ska inte kompletteras med plural enbart utifrån ordets suffix, böjningsklass,
SALDO-paradigm eller efterledens paradigm.

På samma sätt ska andra böjningsval tas från den aktuella artikelns notation, inte
från ett separat uppslagsord som råkar motsvara högersvansen. `fack|anslutning +en`
betyder att just artikeln `fackanslutning` ska tolkas med `+en`; generatorn ska
inte fråga hur `anslutning` böjs för att fylla några luckor.

Plural får genereras när SAOL-artikeln själv innehåller en pluralinstruktion,
exempelvis `+er`, `+ar`, `pl. +`, `pl. +s` eller annan explicit pluraloperation.

Detta kontrakt låses i `tests/test_noun_article_scope.py`: sammansättningar med
singular-only-notation får inte ärva efterledens plural, förekomsten av `|` får
inte i sig ändra vilka former som genereras, och artikelns egen notation styr
böjningsoperationerna oberoende av högersvansen.
