# Överlämningsdokument: sie-mcp (Spiris MCP)

**Datum:** 2026-08-09
**Till:** Nästa AI-assistent (eller mänsklig utvecklare)
**Från:** Föregående AI-assistent
**Ämne:** Status, utfört arbete och kvarstående arkitektbeslut för Spiris MCP.

---

## 1. Kontekst & Projektets Natur
Detta projekt (`sie-mcp`) är en Model Context Protocol (MCP) server för integration mot Visma eAccounting (internt kallat "Spiris"). 
Målet med projektet är att ge AI-agenter säker och maskerad tillgång till bokföringsdata, samt möjlighet att föreslå bokföringsåtgärder.

**Mycket Viktigt:** All utveckling styrs slaviskt av `hantverksbok/00_KONSTITUTION.md`. Du MÅSTE läsa den innan du rör koden. Projektet har en "fail-closed" arkitektur med strikt maskering (GDPR/Sekretess) där AI:n (MCP:n) *endast får föreslå* skrivoperationer (utkast) som sedan måste godkännas av en människa i ett GUI. Inga skrivoperationer får göras direkt av MCP-servern.

## 2. Vad som har utförts (Etapp 0–7)
Vi har precis slutfört Etapp 0 till 7 i den exekverbara planen `PLAN_SPIRIS_TACKNING.md`. Hela testsviten (2 236 tester) passerar grönt.

* **Etapp 0 (Transportlagret):** Implementerat OData-parametrar (`$filter`, `$select`, `$orderby`, `$pagesize`), hantering av HTTP 429 (Too Many Requests) med retry-logik, samt binärhämtning.
* **Etapp 1 (Läsning):** Byggt uppslag för kundfakturor, alla verifikationer (tvärs över räkenskapsår), ingående balanser, kontoplaner och enkeluppslag (`spiris_hamta_ett`). Lagt till referensverktyg för valutakurser, anläggningstillgångar och användare.
* **Etapp 2 (Utkastvägen):** Implementerat verktyg för att föreslå *ändring*, *borttagning* och *bokföring* av utkast. (Följer invariant I4: MCP föreslår endast).
* **Etapp 3 (Periodiseringar):** Läsning av periodiseringar och verktyg för att föreslå nya periodiseringar med exakta valideringsregler för kopplingspar.
* **Etapp 4 (Bilagor och underlag):** Skapat `KATEGORI_UNDERLAG` för fritextfiler. Byggt läsning och nedladdning av underlag. **Särskilt beslut:** Vi provkörde `POST /attachmentlinks` mot sandboxen och fastställde att `DocumentType` ska anges som sträng (t.ex. `"SupplierInvoice"`), vilket nu är kodat och fungerar.
* **Etapp 5 (Betalningsavvikelser):** Läsning av kvittningskandidater och möjlighet att föreslå balanserade betalningsverifikat (för över-/underbetalningar).
* **Etapp 6 (MCP-resurser & Prompter):** Exponerat befintlig data som MCP-resurser (`spiris://foretag` m.fl.) och skapat MCP-prompter för vanliga arbetsflöden (t.ex. `manadsavstamning`).
* **Etapp 7 (Sidbrytning/Paginering):** Implementerat `offset` och `limit` på de tyngsta listverktygen. Svaren wrappas i ett `_envelope` med `totalt_antal`, `visade` och `trunkerat`. Rökprov (GRIND 7) mot live-sandbox visade perfekt utfall.

## 3. Kodbasens Hälsa
* **Tester:** Vi lämnar över en kodbas med **2 236 passerade tester, 0 fel**.
* Bygg aldrig vidare om testsviten (`python -m pytest tests/ -q`) är röd.
* All ny kod har typats och följer domänmodellerna (`Transaktion`, `Verifikation`, `Decimal` för alla belopp).

## 4. Vad som kvarstår att göra (Etapp 8+)
Arbetet är medvetet pausat här. De kvarstående delarna i API:et har bedömts sakna antingen fältallowlist, fastställd payloadform, eller ett **arkitektbeslut** kring om de ens hör hemma i sie-mcp. 

Du (nästa AI) ska **inte** implementera dessa utan att först få en tydlig instruktion och specifikation från arkitekten (användaren).

**Kvarstående punkter (Blockerade):**
1. **Ändringsallowlist för kund- och leverantörsfakturautkast:** (Tänkta för U2.1). De innehåller 40+ fält. Arkitekten måste besluta vilka fält en AI ska få ändra.
2. **Uppdatera/Ta bort periodiseringar:** (`PUT /allocationperiods`, `DELETE /supplierinvoicedrafts/{id}/allocationperiods`). Semantiken för vad som sker med en pågående periodisering är oklar.
3. **Betalverifikat:** (`POST /paymentvoucher`). Parametrarnas inbördes påverkan (momsberäkning vs default-koder) går inte att utläsa ur specen.
4. **Kvittning:** (`POST /supplierinvoices/{id}/offset`). Kroppens form är inte definierad i OpenAPI-specen.
5. **Kontoplansunderhåll:** (`POST /accounts`, `PUT /accounts/{fy}/{nr}`). Policyfråga: Ska en AI överhuvudtaget få föreslå kontoplansändringar?
6. **Företagsinställningar:** (`PUT /companysettings/*`). Påverkar fundamentala lås och ROT/RUT. Mycket hög risk.
7. **Order & Offerter:** Prioritering saknas mot det övriga reskontraarbetet.
8. **Två-segmentsuppslag:** (`GET /vouchers/{fiscalyearId}/{voucherId}`). Passar inte den existerande mappen för `spiris_hamta_ett`.
9. **Odokumenterade endpoints:** `/webhooks`, `/purchasereceipts`, `/reports/monthly` saknar API-kontrakt.

## 5. Instruktioner till nästa assistent
1. Läs `ARKITEKTUR_SPIRIS_TACKNING.md` och `PLAN_SPIRIS_TACKNING.md`. De är dina kartor.
2. Läs `hantverksbok/00_KONSTITUTION.md`. Bryt ALDRIG mot konstitutionen.
3. Be användaren (arkitekten) att specificera vilken av punkterna i Etapp 8+ ni ska låsa upp och arbeta med, och be om nödvändiga arkitekturbeslut innan kod skrivs.
4. Behåll strikt disciplin gällande data masking och `Decimal`.
