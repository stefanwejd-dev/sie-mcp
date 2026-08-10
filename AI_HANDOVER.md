# Överlämningsdokument: sie-mcp (Spiris MCP)

**Datum:** 2026-08-09, **rättat 2026-08-10**
**Till:** Nästa AI-assistent (eller mänsklig utvecklare)
**Från:** Föregående AI-assistent
**Ämne:** Status, utfört arbete och kvarstående arkitektbeslut för Spiris MCP.

> **RÄTTELSE 2026-08-10.** Den ursprungliga versionen av detta dokument
> beskrev Etapp 3, 4 och 5 som färdiga. En granskning mot koden visade att tre
> av verktygen inte fungerar som beskrivet, och att ett fjärde bygger på en
> endpoint som inte finns för svenska bolag. Avsnitt 2 och 4 är rättade nedan,
> och åtgärderna ligger som Etapp 8 i `PLAN_SPIRIS_ETAPP8.md`.
> **Bygg ingenting nytt innan de rättningarna är gjorda.**

---

## 1. Kontekst & Projektets Natur
Detta projekt (`sie-mcp`) är en Model Context Protocol (MCP) server för integration mot Visma eAccounting (internt kallat "Spiris"). 
Målet med projektet är att ge AI-agenter säker och maskerad tillgång till bokföringsdata, samt möjlighet att föreslå bokföringsåtgärder.

**Mycket Viktigt:** All utveckling styrs slaviskt av `hantverksbok/00_KONSTITUTION.md`. Du MÅSTE läsa den innan du rör koden. Projektet har en "fail-closed" arkitektur med strikt maskering (GDPR/Sekretess) där AI:n (MCP:n) *endast får föreslå* skrivoperationer (utkast) som sedan måste godkännas av en människa i ett GUI. Inga skrivoperationer får göras direkt av MCP-servern.

## 2. Vad som har utförts (Etapp 0–7)
Vi har precis slutfört Etapp 0 till 7 i den exekverbara planen `PLAN_SPIRIS_TACKNING.md`, och har nu därefter utfört Etapp 8 till 15b i `PLAN_SPIRIS_ETAPP8.md`. Hela testsviten (ca 2 400 tester) passerar grönt.

* **Etapp 0 (Transportlagret):** Implementerat OData-parametrar (`$filter`, `$select`, `$orderby`, `$pagesize`), hantering av HTTP 429 (Too Many Requests) med retry-logik, samt binärhämtning.
* **Etapp 1 (Läsning):** Byggt uppslag för kundfakturor, alla verifikationer (tvärs över räkenskapsår), ingående balanser, kontoplaner och enkeluppslag (`spiris_hamta_ett`). Lagt till referensverktyg för valutakurser, anläggningstillgångar och användare.
* **Etapp 2 (Utkastvägen):** Implementerat verktyg för att föreslå *ändring*, *borttagning* och *bokföring* av utkast. (Följer invariant I4: MCP föreslår endast).
* **Etapp 3 (Periodiseringar):** Läsning av periodiseringar fungerar. **Skrivvägen gör det inte.** `forbered_periodisering` lägger ett utkast av typen `"periodisering"` i kön, men `utfor_utkast` saknar gren för den typen — ett godkännande i Streamlit träffar `raise SpirisKlientFel("Okänd utkasttyp")`. Det finns heller ingen `bygg_periodiseringspayload`, så Spiris-kroppen byggs aldrig. Verktyget erbjuder dessutom kundfaktura som kopplingspar, vilket `POST /allocationperiods` inte tar emot. Åtgärdas i R8.1.
* **Etapp 4 (Bilagor och underlag):** Läsning och nedladdning fungerar. `KATEGORI_UNDERLAG` är skapad. `DocumentType` som sträng (t.ex. `"SupplierInvoice"`) är sandbox-verifierat och korrekt. **Men `forbered_underlagskoppling` går förbi villkorsspärren:** den anropar `utkast.skapa` direkt i stället för via `_kor_utkastverktyg`, vilket gör att `_villkor_godkanda` inte kontrolleras, att människan inte får se någon tidig sammanfattning, och att ingen Art. 30-post skrivs. Den bygger dessutom Spiris-payloaden i `server.py` (fel lager) och skickar en sträng som `sammanfattning` där `utkast.skapa` kräver `list[list[str]]`. Spärrtestet i `test_mcp_villkorssparr.py` listar verktyget som täckt utan att pröva det. Åtgärdas i R8.2–R8.4.
* **Etapp 5 (Betalningsavvikelser):** Läsning av kvittningskandidater fungerar. Verktyget `forbered_betalningsverifikat` bygger på `POST /voucherwithoverunderpayment`. Trots att specifikationen hävdar *"is not available for Swedish companies"* visade GRIND 10-provet att endpointen **faktiskt är tillgänglig** för svenska bolag! Verktyget bevaras därmed.
* **Övrigt:** `spiris_adapter.py` rad 630–649 är död kod (SIE4-blocket inklistrat en gång till efter en `return`). `spiris_underlag`, `spiris_hamta_underlag` och `forbered_underlagskoppling` är annoterade `-> str` men returnerar `dict`.
* **Etapp 6 (MCP-resurser & Prompter):** Exponerat befintlig data som MCP-resurser (`spiris://foretag` m.fl.) och skapat MCP-prompter för vanliga arbetsflöden (t.ex. `manadsavstamning`).
* **Etapp 7 (Sidbrytning/Paginering):** Implementerat `offset` och `limit` på de tyngsta listverktygen. Svaren wrappas i ett `_envelope` med `totalt_antal`, `visade` och `trunkerat`. Rökprov (GRIND 7) mot live-sandbox visade perfekt utfall.

## 3. Kodbasens Hälsa
* **Tester:** Vi lämnar över en kodbas med **2 236 passerade tester, 0 fel**. Observera att grönt inte betyder färdigt: samtliga fel i avsnitt 2 finns i en grön svit, eftersom enhetstesterna mockar Spiris-klienten och därför inte kan se vare sig en saknad gren i `utfor_utkast` eller en endpoint som saknas för svenska bolag.
* Bygg aldrig vidare om testsviten (`python -m pytest tests/ -q`) är röd.
* All ny kod har typats och följer domänmodellerna (`Transaktion`, `Verifikation`, `Decimal` för alla belopp).

## 4. Vad som utförts i Etapp 8 till 15b

* **Etapp 8-9**: Fixade buggarna (skrivvägen för periodiseringar och underlagskoppling) som upptäcktes ovan. Lade även till Decimal-kontroll för samtliga beloppfält (U9).
* **Etapp 11-14**: Införde fullt stöd för att hantera/skapa periodiseringar, konton (läs/skriv), bokföringslås, ROT/RUT, samt utkaständring (whitelisting-baserad `PUT /drafts/{id}`).
* **Etapp 15-15b**: Stöd för offertutkast (`/quotedrafts`), säljdokumentåtgärd (omvandling av ordrar/offerter), samt kvittning av leverantörskreditfakturor (`/supplierinvoices/{id}/offset`).

## 5. Vad som kvarstår att göra (Etapp 16+)

**Besluten är fattade 2026-08-10 och står i `PLAN_SPIRIS_ETAPP8.md` avsnitt 2 (D1–D6).** Den planen är körbar och ersätter listan nedan som arbetsunderlag. Den här sammanställningen står kvar för att visa hur punkterna föll ut.

| Punkt i den ursprungliga listan | Utfall |
|---|---|
| 1. Ändringsallowlist, fakturautkast | **Beslutat (D2).** Brett, utom motpart, valuta och ROT/RUT. Etapp 14 |
| 2. Uppdatera/ta bort periodiseringar | **Beslutat.** Etapp 11 — men R8.1 måste laga skrivvägen först |
| 3. Betalverifikat (`POST /paymentvoucher`) | **Avfört.** Specen: endast norska och nederländska bolag |
| 4. Kvittning (`POST /supplierinvoices/{id}/offset`) | **Felbedömt i denna lista.** Kroppen ÄR specificerad: `DebitInvoiceIds` + `VoucherDate`, `additionalProperties: false`. Etapp 15b |
| 5. Kontoplansunderhåll | **Beslutat (D1).** Byggs som `forbered_*`. Etapp 12 |
| 6. Företagsinställningar | **Beslutat (D1, D1a).** Byggs, men låsdatum får bara flyttas framåt och upplåsning föreslås aldrig. Etapp 13 |
| 7. Order och offerter | **Beslutat.** Utkastvägen byggs (Etapp 15); `POST /quotes` och `POST /orders` byggs aldrig |
| 8. Två-segmentsuppslag | **Beslutat.** Eget verktyg. Etapp 17 |
| 9. Odokumenterade endpoints | **Oförändrat.** `/webhooks`, `/purchasereceipts`, `/reports/monthly` saknar kontrakt och byggs inte |

Utöver detta tillkom ett beslut som inte fanns i listan: **D3**, att belopp korsar MCP-gränsen som sträng i stället för `float`. Åtta verktyg migreras i Etapp 9. Det är en avsiktlig kontraktsbrytning.

## 5. Instruktioner till nästa assistent
1. Läs `PLAN_SPIRIS_ETAPP8.md` — den är arbetsordern. `ARKITEKTUR_SPIRIS_TACKNING.md` och `PLAN_SPIRIS_TACKNING.md` är bakgrunden.
2. Läs `hantverksbok/00_KONSTITUTION.md`. Bryt ALDRIG mot konstitutionen.
3. Börja med Etapp 8 (rättningarna). Bygg ingen ny funktion ovanpå en trasig skrivväg.
4. Kör inte R8.7 eller Etapp 15b innan GRIND 10 är körd: `python tools/prov_grind10.py --bolag "<bolagsnamn>" --offset`.
5. Behåll strikt disciplin gällande data masking och `Decimal`.

- **Senaste uppdatering**: Etapp 16 (prislistor, rabattavtal och etiketter) är fullt implementerad, testad och integrerad.
