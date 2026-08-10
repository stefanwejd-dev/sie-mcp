# Överlämningsdokument - MCP Etapp 12

Detta dokument sammanfattar arbetet som utförts för Etapp 12 (Kontoplansunderhåll) samt nästa steg.

## Vad som har utförts

### U12.1 — `forbered_konto` (Skapa konto)
* **Implementering**: Skapade ett nytt verktyg för att förbereda skapandet av konton via `POST /accounts`.
* **API & Data**: Endast angivna och tillåtna fält enligt kravspecifikationen (som `kontonr`, `kontonamn`, `rakenskapsar_id`, `aktiv`) packas ihop till en Spiris-payload. Resten ignoreras för att säkerställa att inga otillåtna uppdateringar skickas (t.ex. datumfält).
* **Fail-closed Validating**: Kontrollerar specifikt att `kontonr` exakt är fyra siffror, och validerar lokalt via `spiris_kontoplan_alla` ifall kontot redan existerar för det angivna räkenskapsåret, och i så fall kastar `ValueError` tidigt innan utkastet ritas upp.

### U12.2 — `forbered_kontoandring` (Ändra konto)
* **Implementering**: Skapade verktyget för att modifiera befintliga konton via `PUT /accounts/{fiscalyearId}/{accountNumber}`.
* **Read-modify-write**: `PUT` kräver hela objektet, så logiken hämtar först det befintliga API-objektet (den råa versionen), applicerar ändringarna på de fält som tillåts i ändringslistan, och bibehåller alla tidigare värden på de övriga fälten (samt konverterar tillbaka null-värden korrekt). 
* **Tydlig preview**: Verktyget genererar en "före/efter"-sammanfattning, vilket låter användaren exakt se hur det befintliga fältet ändrats (exempel: "Ändring kontotyp: S ➡️ K") vilket är livsviktigt för transparensen, särskilt när ett konto byter från resultat- till balansräkning.

### Kvalitetssäkring och Tester
* Skapat `tests/test_etapp12_konto.py`.
* Totalt **17 nya tester** lades till (8 för skapande, 9 för ändringar).
* Inkluderar tester som explicit säkerställer att vi inte kan ändra ospecificerade fält samt tester som intygar att utelämnade fält behåller sina gamla värden.
* `test_mcp_villkorssparr.py` och `test_atgardsformular.py` uppdaterades med de nya metaverktygen. Hela testsviten (17/17 + 78/78 meta) är knallgrön.

## Återstående arbete & Beslut

Etapp 12 är nu färdig. Nästa steg enligt `PLAN_SPIRIS_ETAPP8.md` är **Etapp 13 — Företagsinställningar**.

Observera att etapp 13 beskrivs som den "mest riskfyllda etappen", där bland annat bokföringslås justeras. 

**GRIND 12** är nådd. Jag stannar här och inväntar inspektion/okey. Säg till när du är redo för Etapp 13!
