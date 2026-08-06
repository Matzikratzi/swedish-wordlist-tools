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
