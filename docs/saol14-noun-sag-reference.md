# SAG-referens för NOUN-generatorn

Den här filen dokumenterar de generella grammatiska regler som får användas för
mekanisk komplettering av ett paradigm som redan har licensierats av en SAOL14-artikel.

## Auktoritetsgräns

- **SAOL14-faksimilen** avgör vilka lexikala slots/paradigm som artikeln licensierar.
- **Svenska Akademiens grammatik (SAG)** får användas för generella grammatiska
  operationer mellan sådana redan licensierade slots.
- **svenska.se** används som stickprovsvalidering av vår tolkning, inte som input
  till exporten.
- **SALDO** är en diagnostisk jämförelsekälla och får inte fylla luckor.

Primär grammatisk referens:

> Svenska Akademiens grammatik, volym 2, *Ord*, kapitel 2 Substantiv.

Relevanta avsnitt:

- §43–64: substantivens numerusböjning.
- §44–52: deklinationerna och pluralbildning.
- §51: sjätte deklinationen, plural utan pluralsuffix, inklusive
  `lus : löss`, `mus : möss`, `gås : gäss`, `man : män`.
- §68: suffix för bestämd form, särskilt bestämd plural.

Officiell PDF: `https://svenska.se/SAG_Volym_2.pdf`.

## Regler som implementationen använder

### Produktiv plural på -r

SAG §68 anger `-na` som bestämdhetssuffix efter de vanliga pluraländelserna i
`-r`.

Exempel:

- `hundar -> hundarna`
- `idéer -> idéerna`
- `skor -> skorna`

### Femte deklinationen: plural på -n

SAG §68:2 anger `-a` efter pluralsuffixet `-n`.

Exempel:

- `knän -> knäna`
- `hjärtan -> hjärtana`
- `ställen -> ställena`

### Sjätte deklinationen: plural utan pluralsuffix

SAG §51 definierar sjätte deklinationen som plural utan synligt/hörbart
pluralsuffix. §68:3 beskriver bestämd plural.

För de stamväxlande orden anges bland annat:

- `gäss -> gässen`
- `löss -> lössen`
- `möss -> mössen`
- `män -> männen`

Det är därför fel att behandla den slutliga bokstaven `s` i `löss`/`möss`/`gäss`
som ett pluralsuffix `-s`.

### Latin/grekisk plural på -a/-i

SAG §68:5 anger att latinska och grekiska pluralformer på `-a` och `-i` inte tar
bestämdhetssuffix.

Exempel:

- `tentamina` används också där bestämd plural annars hade väntats.
- samma princip används mekaniskt för SAOL-licensierade pluraler som
  `doktorsexamina`.

### Plural på -s

SAG §68:4 ger `-en` efter `-s` när stammen är enstavig, t.ex. `chipsen`, `jeansen`,
`tricksen`, `oddsen`. För andra typer beskriver SAG variation eller att bestämd
plural undviks.

Därför gäller **inte** regeln "alla pluraler som råkar sluta på s får -en".
Om SAOL-artikeln endast licensierar en `-s`-plural men inte ger bestämd plural och
vi inte har tillräcklig information för en säker SAG-regel, lämnas `pl_def`
oregistrerad hellre än att generatorn gissar.

## Implementationsprincip

`noun_paradigm.py::_derive_definite_plural()` ska endast returnera en form när
SAOL-artikeln redan har licensierat `pl_indef` och SAG ger en entydig mekanisk
regel från tillgänglig artikelinformation. Annars returneras ingen härledd
bestämd plural.

Detta är förenligt med projektets övergripande regel: **unsupported/okänd är bättre
än en lexikal gissning**.
