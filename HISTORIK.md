# Historik före GitHub

`sie-mcp` utvecklades lokalt under sommaren 2026 innan kodförrådet gjordes
publikt. Den ursprungliga historiken kunde inte följa med: den innehöll
upphovsrättsskyddat referensmaterial — rättskällor, redovisningslitteratur,
SIE-gruppens filformatsspecifikation, akademiska artiklar om
gränssnittsdesign och en leverantörs avtalsvillkor — och en commit är
permanent. Materialet är läst och använt, men får inte spridas vidare.

Kodförrådet startades därför om från ren mark. Arbetet som ledde hit finns
kvar i sammandrag nedan: samtliga 135 commit-rubriker i
kronologisk ordning, från första raden till omstarten. De är projektets egna
meningar och kan därför återges.

Den fullständiga historiken, med diffar och referensmaterial, finns lokalt hos
utvecklaren.

| Datum | Commit |
|---|---|
| 2026-06-27 | chore: initial commit — spec, samples and .gitignore |
| 2026-06-27 | Extract domain model into domain_model.py (pure refactor, no behavior change) |
| 2026-06-27 | Add project scaffolding, tests, docs and reference material |
| 2026-07-01 | Add väsentlighetsberäkning (Modul 1) with TDD-verified benchmarks |
| 2026-07-01 | Add kontotyp-vakten (Modul 2) and correct väsentlighet sign convention |
| 2026-07-01 | Merge kontotyp-vakten addendum into ARCHITECTURE.md |
| 2026-07-02 | Add sekretesslager (Modul 3) with pseudonymisering across four detection layers |
| 2026-07-02 | Fix fail-open bug in uppdatera_efter_granskning |
| 2026-07-02 | Add kontomatchning (Modul 4) with account-plan-aware motivering guard |
| 2026-07-02 | Add first MCP server exposing Modul 1 and Modul 2 as tools |
| 2026-07-03 | Merge Modul 4 and MCP-brygga docs into ARCHITECTURE.md; add prosa_kontext |
| 2026-07-03 | Close Modul 5 gaps 1-3: saldo, belopp, föreslaget_kontonr |
| 2026-07-03 | Add haiku_klient.py: real Anthropic integration for kontomatchning |
| 2026-07-03 | Add ackumulering.py (Modul 5): ISA 450-ackumulering av felaktigheter |
| 2026-07-03 | Add local Streamlit app with multi-provider AI-config layer (DEL A+B) |
| 2026-07-03 | Verify Gap 1-3 closure and update Modul 5 docs to match reality |
| 2026-07-04 | Add ISA 450 analysis section (Sektion 8) to the Streamlit app |
| 2026-07-04 | Add central ai_adapter layer so vald_modell drives real Anthropic analysis |
| 2026-07-04 | Add pedagogical chat panel (Sektion 9) with safe, aggregated-only context |
| 2026-07-04 | Improve Sektion 9 UX: response modes, suggested questions, risk badge |
| 2026-07-05 | Add Spiris (Visma eAccounting) data-source adapter, client and orchestration |
| 2026-07-05 | Wire Spiris data source into Streamlit UI (Fas 5) |
| 2026-07-06 | Make AI clients thinking-model-robust; add account balances to chat context |
| 2026-07-06 | Add supplier-ledger GDPR washing machine (Fas C backend) |
| 2026-07-06 | Add Sektion 4 human-in-the-loop masking review; remove temp chat diagnostics |
| 2026-07-07 | Filter Spiris chart to active accounts before analysis |
| 2026-07-07 | Wire supplier-ledger reskontra into AI context (Fas C frontend) |
| 2026-07-07 | Wire customer-ledger reskontra into AI context (Fas D) |
| 2026-07-07 | Fix Sektion 4 crash on repeated sensitive text (unique widget keys) |
| 2026-07-07 | Add masked general-ledger RAG tools (Fas E, steg 2) |
| 2026-07-07 | Add Spiris RAG MCP tools with session handling (Fas E, steg 3) |
| 2026-08-10 | Fix bugs in periodisering and underlagskoppling (Etapp 8) |
| 2026-08-10 | Fix precision bug with Decimal in belopp validation (Etapp 9) |
| 2026-08-10 | Add support for periodisering via MCP tools (Etapp 11) |
| 2026-08-10 | Add support for kontoplan and kontosaldo lookup and editing (Etapp 12) |
| 2026-08-10 | Add support for bokföringslås and RUT/ROT details (Etapp 13) |
| 2026-08-10 | Add support for utkastandring with field whitelisting (Etapp 14) |
| 2026-08-10 | Add support for offertutkast, saljdokumentatgard (Etapp 15) |
| 2026-08-10 | Add support for supplier invoice offset / kvittning (Etapp 15b) |
| 2026-07-08 | Add structured BAS P&L report tool (Fas E, steg 4) |
| 2026-07-08 | Enrich P&L accounts with group + normalized signs (Fas E, steg 5) |
| 2026-07-08 | Add structured BAS balance-sheet tool (Fas E, steg 6) |
| 2026-07-08 | Add FP&A dashboard (P&L + balance sheet) to Streamlit app (Fas E, steg 7) |
| 2026-07-09 | Add KPI/nyckeltal engine + dashboard tab (Fas E, steg 8) |
| 2026-07-09 | Add indirect-method cash-flow engine + waterfall dashboard tab (Fas E, steg 9) |
| 2026-07-09 | Wire FP&A dashboard to live Spiris API path (Fas E, steg 10) |
| 2026-07-09 | Add masking memory and .env-backed AI config persistence |
| 2026-07-09 | Redesign Sektion 8 as dashboard with bidirectional threshold input |
| 2026-07-09 | Automate app.py UX: persistent settings, auto-fetch, AI in sidebar |
| 2026-07-09 | Add encrypted masking dictionary (Maskeringsliggare) to Sektion 1 |
| 2026-07-09 | Make KPI dashboard dynamic + BI-style layout |
| 2026-07-10 | Add graph-type toggle to Resultatrapport (bars/waterfall) |
| 2026-07-10 | Add Framtidens Balansräkning: what-if simulation + Sankey + narrative |
| 2026-07-22 | Härda säkerhet och GDPR enligt granskning.txt (utom fynd C) |
| 2026-07-22 | Åtgärda omgranskningens fynd 1-4 (maskeringstäckning) |
| 2026-07-22 | Täpp orgnr-lucka i fritext + fixa IBAN-kannibalisering (kontroll.md) |
| 2026-08-01 | security: close MCP PII leakage paths |
| 2026-08-01 | security: cover PII names at string start |
| 2026-08-01 | docs: document shared Lager 3b detector and scope limits |
| 2026-08-01 | security: disable demo screenshot egress fail-closed |
| 2026-08-01 | docs: document verified egress controls and residual risks |
| 2026-08-01 | docs: add security and GDPR risk register |
| 2026-08-01 | security: add fail-closed local secret storage foundation |
| 2026-08-01 | security: add tested local storage migration tool |
| 2026-08-01 | security: add explicit DPAPI session persistence |
| 2026-08-02 | B2.4-C: guardad .env-laddning + prefixmappning av Spiris-credentials vid MCP-serverstart, fail-closed. Verifierad end-to-end mot Spiris sandbox via spiris_kontosaldon (read-only). |
| 2026-08-02 | C1: lokal AI via Ollama — modellistning, samtal + agentläge med tool calling, fail-closed, 1259 gröna tester. |
| 2026-08-03 | feat: Område A fas 2 – Strukturerat svarskontrakt för AI-chatten |
| 2026-08-03 | fix: tål ChattMeddelande från session_state skapade före fas 11 |
| 2026-08-03 | docs: kunskapsöverlämning — status, juridisk färdplan och Område A fas 2 |
| 2026-08-03 | feat: Område B – kapitalstack med fria källor, leasing och staplad vy |
| 2026-08-03 | docs: uppdaterad kunskapsöverlämning efter Område B |
| 2026-08-03 | feat: sessionslogg över AI-utflöde — vad som faktiskt skickades |
| 2026-08-03 | docs: kunskapsöverlämning — sessionsloggen och korrigering av avsnitt 3 |
| 2026-08-03 | Säkra MCP och AI-egress för marknadslansering (Paket A–D): sökvägsvakt, ACL-härdad lagring, RAG-envelope, pseudonymiserad reskontra och kontotyper |
| 2026-08-03 | Uppdatera AI_PARTNER_KUNSKAPSOVERLAMNING.md med MCP-säkerhetsstatus (Paket A–D, 19c520e) |
| 2026-08-04 | Juridiskt lanseringspaket, läsande bredd och skrivgrind (Steg 1+2) |
| 2026-08-04 | docs: uppdatera arkitektur, riskregister och åtgärdslista efter Steg 1+2 |
| 2026-08-04 | docs: rätta motsägelsen i DATASKYDD §4.3 om var hemligheterna lagras |
| 2026-08-04 | R-01: rotationsverktyg för lokala nycklar och tokens |
| 2026-08-04 | S2-D: elicitation som tidig sammanfattning — aldrig som godkännande |
| 2026-08-04 | Steg 3 (S3-A + S3-B): sju läsande verktyg, MCP 22 -> 29 |
| 2026-08-04 | P0: flytta maskeringsgränsen från hämtningen till egressen |
| 2026-08-04 | P1+P2: snabbvyer med påminnelseförslag i två nivåer |
| 2026-08-04 | UI/UX (Område D & E): Omstrukturerad Kunder & Leverantörer-flik, leverantörssnabbvyer samt universell sifferformatering |
| 2026-08-04 | docs: Uppdatera Senaste commit-hash i AI_PARTNER_KUNSKAPSOVERLAMNING.md (22fc4e1) |
| 2026-08-04 | docs: dokumentera snabbvyerna och det nya UI-lagret (Område D & E) |
| 2026-08-05 | feat: Slutför Fas 1-7 (UI-omdesign med Sju-rums-modellen) |
| 2026-08-05 | fix: åtgärda fyra NameError/AttributeError-krascher efter Sju-rums-omdesignen |
| 2026-08-05 | feat: Quiet Numbers-branding i Streamlit-appen, MCP-servern och README |
| 2026-08-05 | docs: uppdatera arkitektur- och statusdokument efter c154cbb/79c1c76 |
| 2026-08-05 | fix: undanta Fas 6-aliaserna från spärrtestets täckningskrav |
| 2026-08-05 | feat: PUT och DELETE i Spiris-klienten + hantverksbok för Steg 1-8 |
| 2026-08-05 | Feat: Implementerat MCP-verktyg för läsbredd register och referensdata (Steg 2) |
| 2026-08-05 | Docs: Uppdaterat MCP-verktygsantalet i README och ARCHITECTURE |
| 2026-08-05 | feat(steg3): implementera bankavstämning |
| 2026-08-05 | docs: uppdatera dokumentation efter Steg 3 |
| 2026-08-06 | feat: utkast i Spiris som standardväg för godkända skrivningar (Steg 4) |
| 2026-08-06 | feat: kundfakturans livscykel med mottagargrind för utåtriktade åtgärder (Steg 5) |
| 2026-08-06 | feat: offert- och orderkedjan samt e-faktura (Steg 5b) |
| 2026-08-06 | fix: adressera onumrerade offerter/ordrar via id (sandbox-fynd 2026-08-06) |
| 2026-08-06 | docs: skrivprov mot sandbox — byggmomsvägen ger inte omvänd skattskyldighet |
| 2026-08-06 | feat(juridik): lägg till autonom styrning i docstrings för juridikverktygen |
| 2026-08-06 | docs: uppdatera arkitektur och status för juridik-verktyg |
| 2026-08-06 | fix(R-15): byggmoms ger nu faktiskt omvänd skattskyldighet |
| 2026-08-06 | feat(ui): lägg till juridik-rum med strikt agent |
| 2026-08-06 | docs: uppdatera arkitektur och status för juridik-rummet |
| 2026-08-06 | docs: R-15 stängd, R-16 öppnad, sandboxprotokollet uppdaterat |
| 2026-08-06 | feat: inköp och attest (Steg 6) |
| 2026-08-06 | feat: masterdata-ändring och borttagning med read-modify-write (Steg 7) |
| 2026-08-06 | feat: SIE4-export och -import (Steg 8) — sista steget |
| 2026-08-06 | docs: inventera UI-gapet efter Steg 1-8 |
| 2026-08-06 | docs: fullständig överlämning för UI-arbetet (fyra etapper) |
| 2026-08-06 | UI-etapp 1 - Böckerna: Vyerna, datahämtning, rumsdeklaration och tester klara |
| 2026-08-06 | Uppdatera arkitektur och status efter färdigställande av Etapp 1 |
| 2026-08-06 | feat: implement Etapp 2 (Bank & Register) |
| 2026-08-06 | Utför Etapp 3: Åtgärdsinitiering (Formulär) |
| 2026-08-06 | Slutför UI Etapp 4 och uppdaterar UI_OMDESIGN_GENOMFORANDE.md |
| 2026-08-06 | Uppdaterar arkitekturdokument med koncept från Etapp 4 |
| 2026-08-06 | Exponerar saknade MCP-verktyg i UI:t (väsentlighet och kontotypavvikelser) |
| 2026-08-06 | Uppdaterar statusdokument efter UI-driftsättning av saknade MCP-verktyg |
| 2026-08-06 | Rättar test_rum.py för dynamisk navigering av Data-rummet |
| 2026-08-06 | Lägger till klickbar drill-down i Kontosaldon |
| 2026-08-06 | Flyttar datakälla och omstrukturerar inställningar i vänstermenyn |
| 2026-08-06 | Åtgärdar fel där tomma register visades som saknade om klient saknas |
| 2026-08-06 | Åtgärdar styling-inkonsekvens: återställer Kontosaldon till HTML-tabell och implementerar drill-down via selectbox istället |
| 2026-08-06 | Designjustering: centrerar och gör Quiet Numbers-branding större i sidomenyn |
| 2026-08-06 | Åtgärdar krasch i juridik-rummet: rättstavning av leverantör i konfigurationskollen |
| 2026-08-06 | Ny AI-meny: Flyttar Juridik-chatten och återskapar den dedikerade Företagsdata-chatten |
| 2026-08-06 | Åtgärdar initiering av AssistentKontext i företagschatten |
| 2026-08-06 | Tar bort dubbel renderering av AI-inställningar från assistentpanelen |
| 2026-08-06 | Förbättrar JSON-parsning och uppdaterar instruktioner för svarslägen |
| 2026-08-06 | Släpper lös AI:ns fulla kraft i de olika svarslägena |
| 2026-08-06 | Uppdaterar arkitektur- och statusdokument kring menystruktur och AI-chattar |
| 2026-08-06 | Uppdaterar ARCHITECTURE.md med de senaste etapperna kring AI-chattar |
| 2026-08-06 | Fixar chatt-tystnad när rendering avbryts och åtgärdar deprecation-varningar för use_container_width i Streamlit |
| 2026-08-06 | Åtgärdar visning av noll rader istället för varning i register-rummet när data saknas |
| 2026-08-06 | Fixar typo spiris_token -> spiris_tokens för att hämta Spiris-register korrekt |
| 2026-08-06 | Synliggör fel vid hämtning av register från Spiris |
| 2026-08-06 | Fixar AttributeError när las_config kallades felaktigt som ladda() |
| 2026-08-06 | Uppdaterar arkitektur- och statusdokument med buggrättningar från 2026-08-06 |
| 2026-08-06 | feat(ui): flernivå-drilldown (motpart/fakturor) i Register och Balansräkningen, samt Spiris-buggrättningar |
| 2026-08-06 | docs: uppdatera statusruta med senast commit hash |
| 2026-08-09 | feat: Genomför Etapp 0-3 i Spiris-täckningsplanen (transport, läsning, utkast, periodisering) samt tester |
| 2026-08-09 | feat: Genomför Etapp 4-7 i Spiris-täckningsplanen (bilagor, kvittning, prompter, paginering) samt rökprov |


### 2026-08-10 (Etapp 8 - Periodisering och Underlagskoppling)
*   **Status**: IMPLEMENTERAT & RÖKTESTAT.
*   **Ändringar**:
    *   **R8.1**: Lagt till `UTKASTTYP_PERIODISERING` och skapat `bygg_periodiseringspayload` i `spiris_adapter.py`. Uppdaterat `forbered_periodisering` i `mcp_server/server.py` för att bygga korrekt `payload` med exakt koppling mot `Voucher`, `SupplierInvoice` eller `SupplierInvoiceDraft`.
    *   **R8.2**: Skrivit om `forbered_underlagskoppling` att nyttja `_kor_utkastverktyg` samt skapat `bygg_underlagskopplingspayload` i adaptern, och därmed lagat maskeringsläckaget där parametrar passerade direkt in till utkastvyn (som därmed missade fail-closed grinden).
    *   **R8.3**: Lagt till test för `forbered_underlagskoppling` i `test_mcp_villkorssparr.py` så att villkorsspärren täcker även denna typ.
    *   **R8.4**: Rättat annoteringar så att funktioner som `spiris_underlag` returnerar `dict` istället för `str`, vilket krävs för async to thread-bron i `spiris_rag`.
    *   **R8.5**: Raderat de döda if-satserna (rad 630-649) inuti utkastutföraren för underlagskoppling i `spiris_adapter.py`.
    *   **R8.6**: Bekräftat att dökodstester är raderade och inte längre körs mot de borttagna raderna i adaptern.
    *   **R8.7 (GRIND 10)**: Utfört GRIND 10 i sandboxen. Provet visade att specifikationen återigen **har fel**! Endpointen `POST /voucherwithoverunderpayment` FINNS faktiskt för svenska bolag (ger 400 Bad Request på tom kropp, inte 404/501). Funktionen `forbered_betalningsverifikat` är därmed INTE dödfödd och ska **inte** raderas.
*   **Resultat**: 2238/2238 tester gröna. Maskeringsgränsen (Lagergräns 5) intakt.

### 2026-08-10 (Etapp 16 - Prislistor, rabattavtal och etiketter)
*   **Status**: IMPLEMENTERAT & TESTAT.
*   **Ändringar**:
    *   **R16.1**: Implementerat `spiris_prislistor` med stöd för hämtning av alla prislistor (GET `/salespricelists`) eller priser för specifik lista (GET `/salespricelists/prices/{id}`).
    *   **R16.2**: Implementerat `spiris_rabattavtal` för läsning av rabattavtal (GET `/discountagreements`).
    *   **R16.3**: Implementerat `spiris_etiketter` som stöder typ-argumentet ("kund" eller "artikel") och anropar antingen `/customerlabels` eller `/articlelabels`.
    *   **R16.4**: Lagt till verktygen i MCP-servern (`mcp_server/server.py`) bakom `_kor_spiris_verktyg` så att de skyddas av användargodkännande.
    *   **R16.5**: Uppdaterat testsviterna (`test_mcp_lasande_bredd.py` och `test_mcp_villkorssparr.py`) och skapat separata tester i `test_etapp16_strukturer.py`.
*   **Resultat**: 206/206 tester gröna.
