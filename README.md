<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/branding/logo-reversed.svg">
  <img src="assets/branding/logo-color.svg" alt="Quiet Numbers" height="40">
</picture>

# sie-mcp — verktyg för SIE4-filer och Spiris/Visma

**Utgiven av Quiet Numbers.**

**sie-mcp** är ett svenskt hobbyprojekt i Python för att läsa och sammanställa bokföring, med två gränssnitt mot en delad kärna: en **Streamlit-app (`app.py`)** och en **MCP-server (`mcp_server/server.py`)**.

Verktyget läser SIE4-bokföringsfiler och/eller ansluter mot affärssystem (t.ex. Spiris/Visma eAccounting) med användarens egna uppgifter, kan ersätta vissa identifierande uppgifter med tokens innan text skickas till en AI-modell (lokal Ollama eller molnbaserad), och producerar sammanställningar som är avsedda att efterlikna revisionsanalys (ISA 320/450), FP&A-rapportering och AI-assisterad konteringshjälp.

---

> [!CAUTION]
> ## ⚖️ Läs detta innan du använder programvaran
>
> **`sie-mcp` lämnar inga garantier och gör inga utfästelser** — varken om att den fungerar, om att det den visar är riktigt, om att den skyddar någon uppgift, eller om att den eller din användning av den uppfyller GDPR eller annan lagstiftning. **Hela det juridiska ansvaret för användningen och för allt den leder till bärs av dig som använder den.**
>
> - **Resultaten kan inte antas motsvara verkligheten.** Siffror, tabeller, nyckeltal, väsentlighetstal, klassificeringar och AI-svar kan vara felaktiga, ofullständiga eller helt påhittade. Du ansvarar ensam för att verifiera varje uppgift mot originalkällan innan du använder den.
> - **Det är inte professionell rådgivning.** Programvaran utgör inte revisions-, redovisnings-, skatte- eller juridisk rådgivning och ersätter inte din egen bedömning enligt ISA, god revisionssed, BFN:s allmänna råd eller bokföringslagen.
> - **Ingen utfästelse om lagefterlevnad.** Programvaran gör inget anspråk på att uppfylla GDPR, dataskyddslagen, krav på personuppgiftsbiträdesavtal eller annan lagstiftning. Att bedöma och säkerställa att din användning är laglig är helt ditt ansvar.
> - **Maskeringsfunktionen är inte ett skydd du kan förlita dig på.** Den är ofullständig och har kända begränsningar — personuppgifter kan nå en extern AI-leverantör i klartext utan att du varnas. Se [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md) avsnitt 6.
> - **Programvaran beskrivs inte som säker.** Den är inte säkerhetsgranskad av tredje part och skriver lokala, okrypterade loggfiler som kan innehålla personuppgifter.
> - **BYOK/BYOA.** Alla anslutningar sker med dina egna API-nycklar och konton, under dina egna avtal. Du ansvarar ensam för personuppgiftsbiträdesavtal, tredjelandsöverföring, laglig grund och för att följa varje leverantörs villkor — inklusive Vismas/Spiris utvecklarvillkor, som kräver ett eget utvecklarkonto.
>
> Programvaran är **spärrad** tills villkoren godkänts punkt för punkt av en människa på datorn där den körs.
>
> **Fullständiga villkor:** 📄 [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md) · 📄 [LICENSE](file:///LICENSE)
> **Tekniskt underlag (ingen compliance-utfästelse):** [DATASKYDD.md](file:///DATASKYDD.md) · [ARCHITECTURE.md](file:///ARCHITECTURE.md) · [RISKREGISTER.md](file:///RISKREGISTER.md)

---

## Snabbstart

### 1. Installation

> **Spiris-anslutningen kräver Windows.** OAuth-sessionen skyddas med Windows
> DPAPI (per användare) och har medvetet ingen fallback på andra plattformar —
> en osäker lagring vore värre än ingen. SIE4-vägen är inte beroende av detta.

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Godkänn villkoren

Programvaran vägrar köra tills användarvillkoren godkänts. Det görs antingen i Streamlit-appen (kryssa i samtliga punkter) eller i en terminal:

```bash
python parser/compliance.py --godkann   # läser upp villkoren och kräver en bekräftelsefras
python parser/compliance.py --status    # visar om villkoren är godkända
python parser/compliance.py --aterkalla # tar bort godkännandet och spärrar igen
```

Godkännandet gäller den dator och det användarkonto där det gjorts. Det kan inte lämnas via MCP — en AI-assistent får inte godkänna villkor åt dig.

### 3. Kör Streamlit-appen

```bash
streamlit run app.py
```

Under **Rapporter** finns ett fält med snabbvyer — utestående och förfallna
kund- respektive leverantörsfakturor, åldersanalys och påminnelseförslag.
Vyerna beräknas **lokalt och utan AI-anrop**, och fungerar därför även utan
API-nyckel. De visar riktiga motpartsnamn; pseudonymiseringen sker först när
data lämnar datorn.

### 4. Kör som MCP-server

MCP-servern (`mcp_server/server.py`) exponerar 88 primära verktyg över `stdio` — 56 läsande, 31 som föreslår åtgärder utan att utföra dem, och `visa_anvandarvillkor` (samt 37 domänspecifika alias, totalt 125). Dessutom tillhandahålls 3 resurser, 1 resursmall och 5 prompter. Alla är spärrade tills villkoren godkänts enligt steg 2; `visa_anvandarvillkor` går alltid att anropa och visar villkoren.

När den godkänts loggas varje anrop, med alla argument, automatiskt i `.system_generated/logs/` (eller den sökväg `SIE_MCP_LOGGKATALOG` pekar på). Du kan även följa trafiken i realtid i appens loggflik.

Klienten (Claude Desktop e.dyl.) listar automatiskt alla verktyg när servern ansluts. Verktygen är indelade i följande logiska grupper:

* **SIE4-filer:** Beräkningar och analyser.
* **Struktur & Register:** Kontoplan, räkenskapsår, artiklar, företagsinfo, bankkonton m.m.
* **Huvudbok & Rapporter:** Saldon, transaktioner, verifikat och finansiella rapporter.
* **Reskontra & Affärsdokument:** Kund-/leverantörsreskontra, fakturor, order och offerter.
* **Moms:** Momsöversikt och rapporter.
* **Masterdata:** Prislistor, rabattavtal och etiketter.
* **Förslag (Utkastvägen):** `forbered_*`-verktyg för att skapa fakturor, bokföra, kvitta betalningar, ändra kontoplan, periodisera och hantera bokföringslås. Dessa utför ingenting, utan lägger utkast för mänsklig granskning.
* **Villkor:** `visa_anvandarvillkor` för att läsa avtalet.


**Inga skrivande verktyg exponeras över MCP.** `forbered_*`-verktygen skriver ingenting — de lägger ett *förslag* i en lokal kö. Förslaget utförs först när du själv har granskat de verkliga uppgifterna i appens flik **Åtgärder** och tryckt "Godkänn och skicka". MCP-servern kan alltså föreslå men aldrig utföra, och dess källkod refererar inte ens skrivfunktionerna.

Förslaget binds till en SHA-256-hash: ändras nyttolasten mellan förslag och godkännande vägras sändningen. Utkast gallras efter 24 timmar, eftersom underlaget i affärssystemet kan ha hunnit ändras.

**Ett godkänt verifikat eller en godkänd kundfaktura hamnar som standard i affärssystemets egen utkastkö** — inte direkt i räkenskaperna. Där kan du ändra eller ta bort posten, och du bokför den själv i affärssystemet när du är nöjd. Skälet är att ett bokfört verifikat inte kan tas bort, bara rättas med ett nytt, och att en bokförd faktura kan mejlas till mottagaren. Vill du bokföra direkt går det, men det kräver ett uttryckligt val vid godkännandet.

MCP-protokollets `elicitation` används medvetet **inte** som godkännande — specen tillåter en agentklient att besvara den automatiskt, och en grind som kan passeras av samma modell som lade förslaget är ingen grind.

Börja med `spiris_rakenskapsar` — räkenskapsårets id krävs som indata till flera av de andra verktygen.

```json
{
  "mcpServers": {
    "sie-mcp": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "SIE_MCP_SIE_KATALOGER": "C:\\dina\\sie\\kataloger"
      }
    }
  }
}
```

---

## Så är programvaran uppbyggd

Beskrivningarna nedan säger vad koden är **avsedd** att göra. De är inte utfästelser om att den gör det korrekt eller fullständigt.

1. **Maskeringsfunktionen (Modul 3):** söker efter namn, organisationsnummer, personnummer och vissa adressuppgifter och ersätter dem med tokens (`[PERSON_1]`, `[BOLAG_1]`) innan text kan sändas externt. Okända namn i fritext är tänkta att stoppas för lokal granskning. Funktionen är ofullständig och har kända begränsningar — se [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md) avsnitt 6. Resultatet är pseudonymiserat, aldrig anonymiserat: uppgifterna förblir personuppgifter.
2. **Lokal lagring (`saker_lagring.py`):** nycklar, OAuth-tokens, krypterade liggare och loggar placeras i en katalog per användare under `%LOCALAPPDATA%\sie-mcp` i stället för i projektmappen. Åtkomstskyddet är operativsystemets; du ansvarar själv för filernas säkerhet.
3. **Utflödesloggning (`sessionslogg.py` och `revisionslogg.py`):** en läsbar, **okrypterad** markdownfil per session med den nyttolast som sänts, plus en metadatalogg. Filerna kan innehålla personuppgifter och är ditt ansvar att skydda och gallra.
4. **Fail-closed som designprincip:** koden är skriven för att neka hellre än att gissa, och för att inte returnera råa felmeddelanden. Det är en ambition i konstruktionen, inte en garanti om utfallet.

---

## Varumärken

`sie-mcp` är inte utvecklat, godkänt, granskat eller understött av Visma/Spiris, Anthropic, OpenAI, Google, SIE-gruppen, BAS-intressenternas Förening eller Bokföringsnämnden. Namn och varumärken som förekommer används enbart för att beskriva vad programvaran kan anslutas till, och tillhör respektive innehavare.
