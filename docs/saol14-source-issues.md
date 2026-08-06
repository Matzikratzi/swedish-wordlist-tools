# Kända fel i SAOL14-källmaterialet

Den här listan innehåller fel som har konstaterats i SAOL14-boken eller i den strukturerade SAOL14-exporten. Den ska inte innehålla äldre OCR- eller facitproblem från andra projektsteg.

## fansin / fanzine

- **Post:** `fansin` / `fanzine`
- **Sida:** 279
- **Text i exporten:** `+et; pl. + _ +t [-et]; pl. + H +<k>s</k>`
- **Problem:** Typografisk markup för kursivt `s` har följt med in i `text`-fältet.
- **Avsedd notation:** `+et; pl. + _ +t [-et]; pl. + H +s`
- **Lokal hantering:** HTML-taggar tas bort före tokenisering, så `+<k>s</k>` tolkas som `+s`.

## filigran

- **Post:** `filigran`
- **Text i exporten:** `+et el.+en; pl. + el. +er`
- **Problem:** Mellanslag saknas efter alternativmarkören `el.` även i SAOL14-boken.
- **Avsedd notation:** `+et el. +en; pl. + el. +er`
- **Lokal hantering:** En periodavslutad etikett som sitter direkt före `+` eller `-` får en implicit tokengräns före operationen.

## bygelbehå

- **Post:** `bygelbehå`
- **Sida:** 162
- **Stycke:** `bygel|be·hå`
- **Text i exporten:** `+n +ar _ -bh:n -bh:ar`
- **Problem:** Den vanliga stycke-styrda tolkningen av `-bh:n` och `-bh:ar` ger `bygelbh:n` och `bygelbh:ar`, medan den avsedda svenska stavningen rimligen är `bygel-bh:n` och `bygel-bh:ar`.
- **Bedömning:** Bindestrecket som behövs i de avsedda formerna uttrycks inte av den generella `-`-operationen. Parsern ska därför inte införa en särskild regel för `bh`.
- **Lokal hantering:** Dokumenteras som källfel tills formerna hanteras i ett separat, explicit källkorrigeringslager.

## sportbehå

- **Post:** `sportbehå`
- **Sida:** 162
- **Stycke:** `sport|be·hå`
- **Text i exporten:** `+n +ar _ -bh:n -bh:ar`
- **Problem:** Den vanliga stycke-styrda tolkningen av `-bh:n` och `-bh:ar` ger `sportbh:n` och `sportbh:ar`, medan den avsedda svenska stavningen rimligen är `sport-bh:n` och `sport-bh:ar`.
- **Bedömning:** Samma källfel som för `bygelbehå`; det ska inte lösas genom att parsern försöker identifiera förkortningar.
- **Lokal hantering:** Dokumenteras som källfel tills formerna hanteras i ett separat, explicit källkorrigeringslager.
