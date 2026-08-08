# SAOL14 paradigmomfång

## Stark empirisk regel

Böjningsomfånget behandlas som en egenskap hos den enskilda SAOL-artikeln.
Generatorn får inte ärva pluralparadigm från en morfologisk familj eller från
efterleden i en sammansättning om sammansättningens egen notation saknar
pluralinstruktion.

Exempel:

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

## Generatorimplikation

En notation som endast ger bestämd singular, till exempel `+en`, `+et`, `+n` eller
`+t`, ska inte kompletteras med plural enbart utifrån ordets suffix, böjningsklass,
SALDO-paradigm eller efterledens paradigm.

Plural får genereras när SAOL-artikeln själv innehåller en pluralinstruktion,
exempelvis `+er`, `+ar`, `pl. +`, `pl. +s` eller annan explicit pluraloperation.

Detta kontrakt låses i `tests/test_noun_article_scope.py`: sammansättningar med
singular-only-notation får inte ärva efterledens plural, medan motsvarande enkla
uppslagsord fortfarande genererar plural när deras egen notation uttryckligen
anger den.
