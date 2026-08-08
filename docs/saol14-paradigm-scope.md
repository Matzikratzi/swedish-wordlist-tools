# SAOL14 paradigmomfång

## Provisoriskt verifierad regel

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

2026 års svenska.se har manuellt kontrollerats för dessa exempel och visar endast
singularformer för respektive sammansättning/artikel.

## Empiriskt stöd i SAOL14-faksimilen

Auditen `analyze_singular_only_compound_heads` hittar 6 252 singular-only-
sammansättningar där efterleden som eget uppslagsord har explicit plural, fördelat
på 1 017 unika efterleder. Detta är starkt stöd för att pluralomfång inte ska
ärvas mekaniskt från efterleden.

## Generatorimplikation

En notation som endast ger bestämd singular, till exempel `+en`, `+et`, `+n` eller
`+t`, ska inte kompletteras med plural enbart utifrån ordets suffix, böjningsklass,
SALDO-paradigm eller efterledens paradigm.

Plural får genereras när SAOL-artikeln själv innehåller en pluralinstruktion,
exempelvis `+er`, `+ar`, `pl. +`, `pl. +s` eller annan explicit pluraloperation.

Regeln är dokumenterad som provisoriskt verifierad tills ett stratifierat stickprov
över flera efterledsfamiljer har kontrollerats mot 2026 års svenska.se.
