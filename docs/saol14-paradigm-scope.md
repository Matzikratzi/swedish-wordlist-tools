# SAOL14 paradigmomfång

## Stark empirisk regel: varje artikel är självbärande

Varje SAOL-artikel behandlas som en självbärande böjningsenhet. Generatorn ska
utgå från den enskilda artikelns egen notation och får inte ärva böjningsinformation
från en morfologisk familj, från ett separat uppslagsord eller från högersvansen i
en sammansättning.

Det gäller inte bara pluralomfång utan hela paradigmet: genus/bestämd singular,
plural, bestämd plural, stamväxlingar och alternativa former måste komma från den
aktuella artikeln eller från generella operationer som är direkt licensierade av
den aktuella artikelns notation.

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
- `höns|arv` har notation `+en`, medan det självständiga uppslagsordet `arv` har
  `+et; pl. +`. Sammansättningen är alltså ett konkret exempel på att inte ens
  genus/bestämd singular ärvs från högersvansen.

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

Dessutom finns fall som `höns|arv`, där sammansättningen och högersvansen inte ens
har samma genus/bestämda singular. Det stöder den starkare slutsatsen att `|` är
strukturinformation, inte paradigmarv.

## Generatorimplikation

En notation som endast ger bestämd singular, till exempel `+en`, `+et`, `+n` eller
`+t`, ska inte kompletteras med plural enbart utifrån ordets suffix, böjningsklass,
SALDO-paradigm eller efterledens paradigm.

På samma sätt får genus eller andra böjningsval inte hämtas från högersvansen.
`fack|anslutning +en` betyder att just artikeln `fackanslutning` ska tolkas med
`+en`; generatorn ska inte fråga hur `anslutning` böjs för att fylla några luckor.

Plural får genereras när SAOL-artikeln själv innehåller en pluralinstruktion,
exempelvis `+er`, `+ar`, `pl. +`, `pl. +s` eller annan explicit pluraloperation.

Detta kontrakt låses i `tests/test_noun_article_scope.py`: sammansättningar med
singular-only-notation får inte ärva efterledens plural, `höns|arv` får inte ärva
`arv`-artikelns genus, och förekomsten av `|` får inte i sig ändra vilka former
som genereras.
