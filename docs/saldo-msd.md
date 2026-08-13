# SALDO:s MSD-koder

Projektet behåller SALDO:s `msd`-värden exakt som de står i källan. Vi översätter alltså inte koderna till ett eget internt format. Det gör att genererade former kan jämföras direkt mot SALDO, kod för kod.

`msd` betyder **morphosyntactic descriptor** (morfosyntaktisk beskrivning).

## Vanliga kompletta MSD-värden

| MSD | Betydelse |
|---|---|
| `ci` | citation form, uppslags-/citeringsform |
| `sg indef nom` | singular, obestämd form, nominativ |
| `sg indef gen` | singular, obestämd form, genitiv |
| `sg def nom` | singular, bestämd form, nominativ |
| `sg def gen` | singular, bestämd form, genitiv |
| `pl indef nom` | plural, obestämd form, nominativ |
| `pl indef gen` | plural, obestämd form, genitiv |
| `pl def nom` | plural, bestämd form, nominativ |
| `pl def gen` | plural, bestämd form, genitiv |
| `pres ind aktiv` | presens, indikativ, aktiv form |
| `pres ind s-form` | presens, indikativ, s-form |
| `pret ind aktiv` | preteritum, indikativ, aktiv form |
| `pret ind s-form` | preteritum, indikativ, s-form |
| `imper` | imperativ |
| `inf aktiv` | infinitiv, aktiv form |
| `inf s-form` | infinitiv, s-form |
| `sup aktiv` | supinum, aktiv form |
| `sup s-form` | supinum, s-form |
| `pres_part nom` | presensparticip, nominativ |
| `pres_part gen` | presensparticip, genitiv |
| `pret_part indef sg u nom` | perfektparticip, obestämd singular utrum, nominativ |
| `pret_part indef sg n nom` | perfektparticip, obestämd singular neutrum, nominativ |
| `pret_part indef pl nom` | perfektparticip, obestämd plural, nominativ |
| `pret_part def sg no_masc nom` | perfektparticip, bestämd singular icke-maskulin, nominativ |
| `pret_part def sg masc nom` | perfektparticip, bestämd singular maskulin, nominativ |
| `pret_part def pl nom` | perfektparticip, bestämd plural, nominativ |
| `c` | sammansättningsform |
| `cm` | sammansättningsform |
| `sms` | sammansättningsform |

Genitivvarianter av particip följer samma mönster men avslutas med `gen` i stället för `nom`.

## Delkoder

### Numerus

| Kod | Betydelse |
|---|---|
| `sg` | singular |
| `pl` | plural |

### Bestämdhet

| Kod | Betydelse |
|---|---|
| `indef` | obestämd form |
| `def` | bestämd form |

### Kasus

| Kod | Betydelse |
|---|---|
| `nom` | nominativ/grundform |
| `gen` | genitiv |

### Genus

| Kod | Betydelse |
|---|---|
| `u` | utrum |
| `n` | neutrum |
| `masc` | maskulin form |
| `no_masc` | icke-maskulin form |

### Verb

| Kod | Betydelse |
|---|---|
| `pres` | presens |
| `pret` | preteritum |
| `inf` | infinitiv |
| `sup` | supinum |
| `imper` | imperativ |
| `ind` | indikativ |
| `aktiv` | aktiv diates |
| `s-form` | s-form, bland annat passiv eller deponens |
| `pres_part` | presensparticip |
| `pret_part` | perfektparticip |

### Komparation

| Kod | Betydelse |
|---|---|
| `pos` | positiv |
| `komp` | komparativ |
| `superl` | superlativ |

## Exempel

```xml
<WordForm>
  <feat att="writtenForm" val="hypotalamus"/>
  <feat att="msd" val="ci"/>
</WordForm>
```

Betyder att `hypotalamus` är en citerings-/uppslagsform.

```xml
<WordForm>
  <feat att="writtenForm" val="bankarna"/>
  <feat att="msd" val="pl def nom"/>
</WordForm>
```

Betyder plural, bestämd form, nominativ.

```xml
<WordForm>
  <feat att="writtenForm" val="bankarnas"/>
  <feat att="msd" val="pl def gen"/>
</WordForm>
```

Betyder plural, bestämd form, genitiv.

## Princip för generatorn

Generatorn ska i nästa steg lämna samma struktur som SALDO:

```text
writtenForm + msd
```

Jämförelsen ska ske på paret `(writtenForm, msd)`, inte bara på ordformen. En form som råkar stavas lika men har en annan morfologisk funktion ska därmed inte räknas som samma facitpost.

## Källor

Dokumentationen bygger på Språkbankens beskrivning av lemgram och MSD samt deras officiella MSD-taggmängd:

- Språkbanken: *Vad är ett lemgram?*
- Språkbanken: *MSD-taggmängd*
