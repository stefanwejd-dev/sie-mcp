# Exekverbar plan — Etapp 8–17

**Datum:** 2026-08-10
**Mottagare:** den AI som utför hantverket (Gemini 3.1 Pro)
**Avsändare:** arkitekten
**Föregångare:** `PLAN_SPIRIS_TACKNING.md` (Etapp 0–7, genomförd)

Arkitekturbesluten är fattade och står i avsnitt 2. Din uppgift är att
genomföra dem exakt — inte att förbättra dem.

---

## 1. Förutsättningar

### 1.1 Läs först

- `hantverksbok/00_KONSTITUTION.md` — gäller i sin helhet, undantagslöst.
- `ARKITEKTUR_SPIRIS_TACKNING.md` — motiverar täckningsarbetet.
- `PLAN_SPIRIS_TACKNING.md` — Etapp 0–7, som du bygger vidare på.

Kortversionen av invarianterna, som **inte** ersätter läsningen:

| # | Invariant |
|---|---|
| I1 | `Decimal`, aldrig `float`. |
| I2 | Fältallowlist — exakt de fält uppgiften listar, inte ett till. |
| I3 | Fail-closed. Väsentligt fält indexeras direkt, kompletterande via `.get()`. |
| I4 | MCP föreslår, utför aldrig. `server.py`/`spiris_rag.py` rör aldrig `skicka`/`uppdatera`/`ta_bort`. |
| I5 | Maskering vid egressgränsen. En maskerare per hämtning. |
| I6 | Fältnamn ur specen, aldrig ur gissning. |

Filer du aldrig ändrar: `sekretesslager.py`, `utkast.py`, `reskontra_tvatt.py`,
`revisionslogg.py`, `namnreferens.py`, `saker_lagring.py`,
`masking_memory.py`, `compliance.py`, `spiris_session.py`, `spiris_auth_vy.py`,
`.env*`.

Du ändrar aldrig ett befintligt test för att få det grönt. **Undantag:** Etapp
9 är en avsiktlig kontraktsbrytning och pekar uttryckligen ut vilka tester som
ska skrivas om. Det undantaget gäller bara där.

### 1.2 Baslinje

```
python -m pytest tests -q
```

Ska ge **2236 passed, 1 skipped**. Gör den inte det: stanna och rapportera.

### 1.3 Testräkning

Varje uppgift anger ett **minsta** antal nya tester. Färre är alltid ett
stopp. Fler är bra — skriv ut det i rapporten.

### 1.4 Grindar

Etapperna körs i ordning. Efter varje etapp: rapportera och **stanna**.
Arkitekten eller användaren kör rökprovet mot sandbox. Börja inte på nästa
etapp utan besked.

---

## 2. Beslut fattade 2026-08-10

Dessa är arkitektbeslut. De ska inte omprövas av dig.

**D1 — Grunduppsättningen får ändras via utkastvägen.** Kontoplan
(`POST /accounts`, `PUT /accounts/{fy}/{nr}`), bokföringslås
(`PUT /companysettings/accountinglocksettings`) och ROT/RUT
(`PUT /companysettings/rotrut`) byggs, samtliga som `forbered_*`.

**D1a — Låsdatum får bara flyttas framåt.** Ett förslag som skulle flytta
`AccountingLockedAsOf` bakåt i tiden, eller nollställa det, avvisas med
`ValueError` innan det läggs i kön. Att låsa upp en stängd period är inte en
åtgärd sie-mcp föreslår. Detta är den enda spärr som skiljer ett bokslutslås
från en oavsiktlig upplåsning av hela bolagets bokföring.

**D2 — Fakturautkast får ändras brett, utom motpart och valuta.**
`CustomerId`/`SupplierId` och `InvoiceCurrencyCode`/`CurrencyCode` är låsta.
ROT/RUT-fälten på utkastet är också låsta — de styr ett skatteavdrag mot
Skatteverket och hör till D1:s kategori, inte till en radrättning.

**D3 — Belopp korsar MCP-gränsen som sträng.** Samtliga åtta berörda verktyg
migreras. Ett numeriskt värde avvisas med `ValueError` som säger att beloppet
ska skickas som sträng — aldrig en tyst konvertering. Se Etapp 9.

**D4 — Ordningen är: rättningar, beloppsmigrering, sandbox-prov, sedan nytt.**
Ingen ny funktion byggs ovanpå en trasig skrivväg.

**D5 — Byggs aldrig:** `/messagethreads`, `/appstore`, `/partnerresourcelinks`,
`/banks`, `/backgrounds`, `/warmup`, `POST /supplierinvoices/{id}/offset/undo`.
Skälen står i `ARKITEKTUR_SPIRIS_TACKNING.md` 7.1.

**D6 — Landsbegränsade operationer byggs inte, och en redan byggd avvecklas.**
Fyra operationer är enligt specen otillgängliga för svenska bolag. En av dem
bär ett verktyg som redan levererats i Etapp 5. Se avsnitt 3 för listan, R8.7
för avvecklingen och GRIND 10 för verifieringen. Beslutet togs av samma skäl
som I6 finns: en förmåga som inte kan utföras är värre än en som saknas,
eftersom den ser ut att fungera ända fram till den skarpa körningen.

---

## Etapp 8 — Rättningar

Sex fel i Etapp 0–7 som måste bort innan något nytt byggs. Inget av dem är en
läcka; två av dem gör att ett dokumenterat verktyg inte fungerar.

### R8.1 — Periodiseringens skrivväg är död

**Filer:** `parser/spiris_adapter.py`, `mcp_server/server.py`, `tests/`

`forbered_periodisering` lägger ett utkast av typen `"periodisering"` i kön,
men `utfor_utkast` har ingen gren för den typen. Ett godkännande i Streamlit
träffar `raise SpirisKlientFel("Okänd utkasttyp: 'periodisering'.")`.
Spiris-kroppen byggs aldrig någonstans.

Tre saker ska göras:

**1.** Inför konstanten `UTKASTTYP_PERIODISERING = "periodisering"` i
`spiris_adapter.py`, bredvid de övriga `UTKASTTYP_*`.

**2.** Skriv `bygg_periodiseringspayload(nyttolast: dict) -> list[dict]` i
`spiris_adapter.py`. Ren funktion, ingen I/O. `POST /allocationperiods` tar en
**array** av objekt.

Fältallowlist (`AllocationPeriodCreateApi`, spec-härledd):

| Spirisfält | Källa i nyttolasten | Obligatoriskt |
|---|---|---|
| `BookkeepingStartDate` | `startdatum` | ja |
| `AmountToAllocate` | `belopp` (`Decimal`) | ja |
| `AllocationAccountNumber` | `konto` (heltal) | ja |
| `NumberOfAllocationPeriods` | `antal_perioder` (heltal) | ja |
| `VoucherId` + `VoucherRow` | kopplingspar | ett av tre |
| `SupplierInvoiceId` + `SupplierInvoiceRow` | kopplingspar | ett av tre |
| `SupplierInvoiceDraftId` + `SupplierInvoiceDraftRow` | kopplingspar | ett av tre |

`QuantityToAllocate` och `WeightToAllocate` tas inte med.

**Observera:** `CustomerInvoiceId`/`CustomerInvoiceRow` finns **inte** i
`POST`-kroppens schema, trots att `forbered_periodisering` i dag erbjuder
kundfaktura som kopplingspar. Ta bort det alternativet ur verktygets signatur
och ur valideringen. Ett kopplingspar som API:t inte kan ta emot är ett
förslag som garanterat misslyckas vid godkännandet.

**3.** Lägg grenen i `utfor_utkast`, i samma form som de övriga:

```python
if typ == UTKASTTYP_PERIODISERING:
    return klient.skicka("/allocationperiods", bygg_periodiseringspayload(nyttolast))
```

Fail-closed i `bygg_periodiseringspayload`: exakt ett kopplingspar (noll eller
två → `ValueError`), `antal_perioder >= 1`, `belopp` är `Decimal` och `> 0`.

**Tester (minst 10),** varav minst ett som låser att ett godkänt
periodiseringsutkast faktiskt når `/allocationperiods` med rätt kropp.

### R8.2 — `forbered_underlagskoppling` går förbi villkorsspärren

**Filer:** `mcp_server/server.py`, `parser/spiris_adapter.py`, `tests/`

Verktyget (`server.py`, ca rad 2057) anropar `utkast.skapa` direkt i stället
för via `_kor_utkastverktyg`. Följden är att **villkorsspärren inte gäller**,
att människan inte får se någon tidig sammanfattning innan förslaget läggs,
och att ingen Art. 30-post skrivs. Det är den enda platsen i kodbasen där
godkännandemodellen går att kringgå.

Skriv om verktyget så att det följer exakt samma form som
`forbered_masterdataandring`:

- Anropet går genom `_kor_utkastverktyg(_bygg, ctx, rubrik, sammanfattning)`.
- Payloadbygget flyttas till en funktion i `spiris_adapter.py`
  (`bygg_underlagskopplingspayload`). `server.py` ska inte känna till
  `DocumentId`, `AttachmentIds` eller `DocumentType`.
- `sammanfattning` är `list[list[str]]`, inte en sträng. `utkast.skapa`
  kräver den formen och godkännandevyn itererar över raderna.
- Inga `import` inuti funktionskroppen — flytta dem till modulnivå som i
  resten av filen.
- Returtypen är `dict`, inte `json.dumps(...)`.

`DocumentType` som sträng (`"SupplierInvoice"`, `"Voucher"`) är
sandbox-verifierat 2026-08-09 och behålls.

**Tester (minst 6),** varav **minst två** obligatoriska: att spärrat läge ger
noll poster i kön, och att sammanfattningen är en lista av rader.

### R8.3 — Spärrtestet är tystat, inte uppfyllt

**Filer:** `tests/test_mcp_villkorssparr.py`

`forbered_underlagskoppling` står i mängden `tackta` (ca rad 322) utan att ha
något faktiskt spärrtest. Metatestet kontrollerar bara att namnet finns i
uppsättningen. Skriv det riktiga spärrtestet, i samma form som de övriga
`forbered_*`-testerna i filen.

Detta är ett tillägg till ett befintligt test, inte en försvagning — det är
tillåtet och nödvändigt.

**Tester (minst 1).**

### R8.4 — Returtyperna på underlagsverktygen

**Filer:** `mcp_server/server.py`, `tests/`

`spiris_underlag`, `spiris_hamta_underlag` och `forbered_underlagskoppling` är
annoterade `-> str` men returnerar `dict` via `_kor_spiris_verktyg`.
MCP-schemat som genereras ur annoteringen lovar alltså en sträng.

Rätta annoteringarna till `-> dict`. Rör inte funktionskropparna utöver det
R8.2 kräver.

**Tester (minst 3).**

### R8.5 — Död kod i `utfor_utkast`

**Filer:** `parser/spiris_adapter.py`

Rad 630–649: hela SIE4-import-blocket är inklistrat en gång till, efter
`return`-satsen i `UTKASTTYP_UNDERLAGSKOPPLING`-grenen. Oåtkomligt och
vilseledande. Ta bort raderna 630–649. Rör inte den riktiga
`UTKASTTYP_SIE4IMPORT`-grenen på rad 606–626.

**Tester:** inga nya. Sviten ska vara oförändrat grön.

### R8.6 — `/accounts/standardaccounts` ska INTE byggas

**Filer:** inga. Detta är en instruktion om att avstå.

U1.4 i föregående plan begärde `GET /accounts/standardaccounts` och den
byggdes aldrig. Det visade sig vara tur. Specens operationsbeskrivning säger:
*"This endpoint is only available for Dutch companies."*

Bygg den inte. Kravet i U1.4 är härmed återkallat.

### R8.7 — `forbered_betalningsverifikat` är dödfött mot svenska bolag

**Filer:** `mcp_server/server.py`, `parser/spiris_adapter.py`, `tests/`

Etapp 5 byggde `forbered_betalningsverifikat` på
`POST /voucherwithoverunderpayment`. Specens beskrivning av den operationen
säger: *"This endpoint is not available for Swedish companies."*

Verktyget är alltså grönt testat och kan ändå aldrig fungera i ett svenskt
bolag. Enhetstesterna mockar klienten, så sviten kan omöjligt fånga det.

**Utför den här uppgiften först efter att GRIND 10 bekräftat spärren mot ett
riktigt bolag** (`python tools/prov_grind10.py --bolag "<namn>"`). Specen har
haft fel förr, och i den här riktningen vore ett förhastat borttagande lika
illa som ett kvarlämnat verktyg.

Bekräftas spärren:

- Ta bort `forbered_betalningsverifikat` från `mcp_server/server.py`, dess
  gren i `utfor_utkast`, `UTKASTTYP_BETALNINGSVERIFIKAT`,
  `_bygg_betalningsverifikat_payload` och `skapa_betalningsverifikat`.
- Ta bort typen ur `parser/utkast.py:GILTIGA_TYPER` — detta är det enda
  tillfälle i planen då den filen får röras, och bara den raden.
- Ta bort verktygets tester och dess post i `test_mcp_villkorssparr.py`.
- Skriv i `HISTORIK.md` varför det togs bort.

Över- och underbetalning hanteras i svensk bokföring som ett vanligt verifikat
med en differensrad, vilket `forbered_verifikat` redan klarar. Lägg en mening
om det i `forbered_verifikat`:s docstring så att vägen inte försvinner med
verktyget.

**Tester:** sviten ska minska med exakt det antal tester som hörde till det
borttagna verktyget, och inget annat får bli rött. Rapportera talet.

**GRIND 8.** Rapportera och stanna.

---

## Etapp 9 — Beloppsmigrering (kontraktsbrytande)

**Filer:** `mcp_server/server.py`, `tests/`

Åtta verktyg tar i dag belopp som `float` över MCP-gränsen, vilket I1
förbjuder. De migreras till `str`. Detta **bryter kontraktet** mot varje
MCP-klient som redan anropar dem, och det är avsiktligt (D3).

### U9.1 — Signaturer med explicit `float`

| Verktyg | Parameter |
|---|---|
| `forbered_betalningspaminnelse` | `drojsmalsavgift: float \| None` → `str \| None` |
| `forbered_betalningsregistrering` | `belopp: float` → `belopp: str` |
| `forbered_leverantorsfakturautkast` | `totalbelopp: float = 0.0` → `totalbelopp: str = ""` |
| `forbered_leverantorsbetalning` | `belopp: float` → `belopp: str` |
| `forbered_periodisering` | `belopp: float` → `belopp: str` |

### U9.2 — Radbaserade verktyg

`forbered_kundfaktura`, `forbered_verifikat` och `forbered_betalningsverifikat`
tar `rader: list[dict]` där beloppen i dag tvingas genom `float(...)`.
Beloppsnycklarna (`pris`, `antal`, `debet`, `kredit`) ska tas emot som
sträng och konverteras med `Decimal(...)`.

### U9.3 — Gemensam konverterare

Skriv **en** hjälpfunktion i `mcp_server/server.py` och använd den överallt:

```python
def _belopp(varde: object, faltnamn: str) -> Decimal:
    """Konverterar ett beloppsargument från MCP-gränsen till Decimal.

    Ett int eller float avvisas med ValueError: flyttal avrundas redan innan
    värdet når hit, och en tyst konvertering skulle dölja felet i stället för
    att stoppa det."""
```

Regler:

- `bool`, `int` och `float` → `ValueError` med en text som säger att beloppet
  ska skickas som sträng, och som nämner fältnamnet.
- En sträng som inte är ett giltigt tal → `ValueError`.
- Decimalkomma godtas: `"1 234,50"` och `"1234.50"` ger båda
  `Decimal("1234.50")`. Blanksteg och ` ` tas bort. En sträng med både
  komma och punkt → `ValueError`; formen är tvetydig och en gissning ger fel
  belopp med faktor 1000.
- Returtypen är alltid `Decimal`. Inget `float` får finnas kvar i någon av de
  åtta funktionerna efter uppgiften.

Docstringarna på samtliga åtta verktyg ska säga att belopp anges som sträng
och visa ett exempel. Verktygsdocstringen är det enda en MCP-klient läser.

**Befintliga tester som ska skrivas om:** de som anropar de åtta verktygen med
numeriska belopp. Det är en avsiktlig kontraktsbrytning enligt D3 — men
**bara** dessa. Går ett annat test rött har du gjort något utöver uppgiften:
stanna.

**Tester (minst 16):** en per verktyg som låser att sträng fungerar, en per
verktyg som låser att `float` ger `ValueError`, plus komma/punkt-fallen och
det tvetydiga fallet.

**GRIND 9.** Rapportera och stanna.

---

## GRIND 10 — Sandbox-prov (utförs inte av dig)

Arkitekten eller användaren kör:

```
python tools/prov_grind10.py --bolag "<bolagsnamn>" --offset
```

Provet avgör två saker mot ett riktigt bolag i stället för mot specens ord:

1. **Landsspärrarna.** Finns `POST /voucherwithoverunderpayment`,
   `POST /paymentvoucher` och `GET /accounts/standardaccounts` för bolaget?
   Utfallet avgör om R8.7 ska genomföras.
2. **Kvittningsvägen.** Har bolaget en kreditfaktura med kvittningsbara
   debetfakturor, och godtar `POST /supplierinvoices/{id}/offset` den
   spec-fastställda kroppen?

Utfallet skrivs in här som ett nytt avsnitt innan R8.7 och Etapp 15b utförs.

---

## Etapp 11 — Periodiseringar färdigt

Förutsätter att R8.1 är grön.

### U11.1 — `forbered_periodiseringsandring`

**Filer:** adapter, server, tests

`PUT /allocationperiods`. Kroppen har **samma** form som `POST` — en array av
samma objekt. Återanvänd `bygg_periodiseringspayload` från R8.1.

Fail-closed: `PUT` ersätter hela periodiseringsplanen för den koppling som
anges. Sammanfattningen till människan ska därför visa **både** den nuvarande
planen (hämtad via `spiris_hamta_ett("periodiseringar", id)`) och den
föreslagna. Ett förslag som bara visar det nya döljer vad som försvinner.
Misslyckas hämtningen av det nuvarande läggs **inget** förslag.

**Tester (minst 7).**

### U11.2 — `forbered_periodiseringsborttagning`

**Filer:** adapter, server, tests

`DELETE /supplierinvoicedrafts/{id}/allocationperiods` — tar bort samtliga
periodiseringar på ett leverantörsfakturautkast.

Oåterkalleligt, och sammanfattningen ska säga det med ord. Den ska lista de
periodiseringar som försvinner, med belopp och antal perioder. Följ formen i
`forbered_masterdataborttagning`.

Detta är den **enda** DELETE-vägen för periodiseringar i API:t. Det finns
ingen `DELETE /allocationperiods/{id}` — en enskild periodisering på ett
verifikat kan alltså inte tas bort. Skriv det i docstringen, annars kommer en
AI-klient att föreslå det ändå.

**Tester (minst 6).**

**GRIND 11.** Rapportera och stanna.

---

## Etapp 12 — Kontoplansunderhåll

Beslut D1.

### U12.1 — `forbered_konto`

**Filer:** adapter, server, tests

`POST /accounts`. Fältallowlist (`AccountApi`):

| Spirisfält | Domännyckel | Obligatoriskt |
|---|---|---|
| `Number` | `kontonr` | ja |
| `Name` | `kontonamn` | ja |
| `FiscalYearId` | `rakenskapsar_id` | ja |
| `IsActive` | `aktiv` | ja |
| `Type` | `kontotyp` | nej |
| `VatCodeId` | `momskod_id` | nej |
| `IsProjectAllowed` | `projekt_tillatet` | nej |
| `IsCostCenterAllowed` | `kostnadsstalle_tillatet` | nej |
| `IsBlockedForManualBooking` | `sparrat_for_manuell_bokning` | nej |

`ReferenceCode`, `Description`, `TypeDescription`, `AllowTransactionText`,
`IsFirstCostCenterMandatory`, `ModifiedUtc`, `CreatedUtc` och
`VatCodeDescription` tas **inte** med.

Frågesträngsparametern `useDefaultAccountType` sätts inte. Utelämnad låter
Spiris härleda typen ur kontonumret, vilket är BAS-kontoplanens egen logik.

Fail-closed: `kontonr` måste vara fyra siffror. Ett konto som redan finns i
`spiris_kontoplan_alla` för samma räkenskapsår → `ValueError` innan förslaget
läggs; `POST` på ett befintligt konto är inte en uppdatering.

**Tester (minst 8).**

### U12.2 — `forbered_kontoandring`

**Filer:** adapter, server, tests

`PUT /accounts/{fiscalyearId}/{accountNumber}`. `PUT` kräver hela objektet och
**nollar det som utelämnas** — följ därför exakt samma read-modify-write som
`bygg_masterdatauppdatering` (`spiris_adapter.py`): hämta nuvarande konto, lägg
ändringarna ovanpå, skicka hela objektet.

Ändringsallowlist: `kontonamn`, `aktiv`, `kontotyp`, `momskod_id`,
`projekt_tillatet`, `kostnadsstalle_tillatet`, `sparrat_for_manuell_bokning`.

`Number` och `FiscalYearId` är låsta — de identifierar objektet. Ett förslag
som ändrar dem byter konto, det rättar inte ett.

Sammanfattningen ska visa **före och efter** för varje ändrad nyckel. Det här
är verktyget som `granska_kontotyper` pekar mot, och en kontotypsändring på ett
använt konto flyttar posten mellan resultat- och balansräkning.

**Tester (minst 9),** varav minst ett som låser att ett fält utanför
allowlisten avvisas och ett som låser att utelämnade fält behåller sitt värde.

**GRIND 12.** Rapportera och stanna.

---

## Etapp 13 — Företagsinställningar

Beslut D1 och D1a. Den mest riskfyllda etappen i planen.

### U13.1 — `spiris_bokforingslas` (läsning först)

**Filer:** adapter, rag, server, tests

Läsvägen byggs **före** skrivvägen. Ett förslag om att flytta ett låsdatum
kräver att både människan och AI:n ser var låset står i dag.

`GET /companysettings` returnerar låsinställningarna. Fältallowlist:
`AccountingLockedAsOf` → `last_till_och_med`,
`AccountingLockInterval` → `lasintervall`,
`TaxDeclarationDate` → `skattedeklarationsdatum`.

`AccountingLockedAsOf` och `TaxDeclarationDate` är `object` i specen och är
alltså nullbara. Behandla dem som kompletterande (`.get()`), aldrig som
väsentliga (I3).

Datakategori: `KATEGORI_STRUKTUR`.

**Tester (minst 4).**

### U13.2 — `forbered_bokforingslas`

**Filer:** adapter, server, tests

`PUT /companysettings/accountinglocksettings`.

**D1a, fail-closed och utan undantag:**

- Hämta nuvarande `AccountingLockedAsOf` innan förslaget byggs. Misslyckas
  hämtningen läggs **inget** förslag.
- Ett nytt låsdatum som är **tidigare än eller lika med** det nuvarande →
  `ValueError`. Låset flyttas bara framåt.
- Ett tomt eller `None` som nytt låsdatum → `ValueError`. Upplåsning föreslås
  aldrig.
- Är inget lås satt i dag godtas vilket datum som helst som inte ligger i
  framtiden. Ett lås framåt i tiden spärrar bokföring som ännu inte finns.

Sammanfattningen ska innehålla ordet **oåterkalleligt** och ange både det
nuvarande och det föreslagna låsdatumet.

`AccountingLockInterval` och `TaxDeclarationDate` ingår **inte**. Ett verktyg
som gör en sak går att granska.

**Tester (minst 10),** varav minst fyra för D1a-spärrarna.

### U13.3 — `forbered_rotrut`

**Filer:** adapter, server, tests

`PUT /companysettings/rotrut`. Fältallowlist, samtliga `Decimal`:
`RutMaxAmountForPersBelow65Year`, `RutMaxAmountForPersOver65Year`,
`RutReducedInvoicingPercent`, `RotReducedInvoicingMaxAmount`,
`RotReducedInvoicingPercent`.

Read-modify-write som U12.2 — `PUT` nollar det som utelämnas.

Fail-closed: procentsatserna måste ligga i `0 <= x <= 100`, beloppen `> 0`.
Sammanfattningen visar före och efter per fält.

Docstringen ska säga att värdena styr skattereduktion mot Skatteverket och att
felaktiga värden ger felaktiga avdrag på utställda fakturor.

**Tester (minst 8).**

**GRIND 13.** Rapportera och stanna.

---

## Etapp 14 — Fakturautkastens ändringsallowlist

Beslut D2. Låser upp `forbered_utkastandring` för de två slag som U2.1 lämnade
ofärdiga. `_UTKASTSLAG` och read-modify-write-mekaniken finns redan — du
lägger bara till allowlisterna.

### U14.1 — Kundfakturautkast

**Filer:** `parser/spiris_adapter.py`, `tests/`

Ändringsallowlist (`CustomerInvoiceDraftApi`, spec-härledd):

`Rows`, `InvoiceDate`, `DueDate`, `DeliveryDate`, `YourReference`,
`OurReference`, `BuyersOrderReference`, `ElectronicReference`,
`InvoiceCustomerName`, `InvoiceAddress1`, `InvoiceAddress2`,
`InvoicePostalCode`, `InvoiceCity`, `InvoiceCountryCode`,
`DeliveryCustomerName`, `DeliveryAddress1`, `DeliveryAddress2`,
`DeliveryPostalCode`, `DeliveryCity`, `DeliveryCountryCode`,
`DeliveryMethodName`, `DeliveryTermName`, `DeliveryMethodCode`,
`DeliveryTermCode`, `TermsOfPaymentId`, `IncludesVat`, `EuThirdParty`,
`IsCreditInvoice`.

**Låsta, och inget av dem är ett förbiseende:**

| Fält | Skäl |
|---|---|
| `CustomerId`, `CustomerNumber`, `CustomerName` | Byter mottagare (D2) |
| `InvoiceCurrencyCode` | Byter valuta (D2) |
| Alla `Rot*`, `HouseWorkOtherCosts`, `MaxAllowedTaxReductionAmount`, `UsesGreenTechnology` | Skattereduktion mot Skatteverket (D2) |
| `Id`, `CreatedUtc` | Serverägda |
| `TotalAmount`, `TotalVatAmount`, `TotalRoundings`, `TotalAmountBaseCurrency`, `TotalVatAmountBaseCurrency` | Härleds ur raderna. Ett förslag som sätter dem kan göra summan oförenlig med raderna |
| `SalesDocumentAttachments`, `MessageThreads`, `Notes` | Egna resurser med egna endpoints |
| `ReverseChargeOnConstructionServices` | Härledd ur kunden — se R-15 i riskregistret |
| `Persons`, `ContributionMargin`, `BackgroundId`, `IsDirectDebit`, `SubscriptionNumber`, `ContractNumber`, `ReplaceUnitPriceWhenZero`, `CustomerIsPrivatePerson` | Utanför beslutad omfattning |

`RotReducedInvoicingType` och `EuThirdParty` är obligatoriska i specen och
måste alltså följa med i read-modify-write-kroppen även när de inte ändras.
Det är precis vad read-modify-write ger — men skriv ett test som låser det.

### U14.2 — Leverantörsfakturautkast

**Filer:** `parser/spiris_adapter.py`, `tests/`

Ändringsallowlist (`SupplierInvoiceDraftApi`):

`Rows`, `InvoiceDate`, `DueDate`, `PaymentDate`, `InvoiceNumber`,
`OcrNumber`, `Message`, `BankAccountId`, `IsCreditInvoice`,
`SkipSendToBank`, `AccountingTemplateId`.

**Låsta:** `SupplierId`, `SupplierName`, `SupplierNumber` (motpart, D2);
`CurrencyCode`, `CurrencyRate` (valuta, D2); `TotalAmount`, `Vat`, `VatHigh`,
`VatMedium`, `VatLow` (härleds ur raderna); `Id`, `CreatedUtc`, `ModifiedUtc`
(serverägda); `ApprovalStatus`, `Approvers`, `ApprovalOrderType`,
`ApprovalRequestedBy`, `CanBeApprovedByCurrentUser`,
`CanBeBookeptByCurrentUser` (attestkedjan — den ändras via
`forbered_attest`, inte här); `AllocationPeriods` (Etapp 11);
`Attachments`, `MessageThreads`, `Notes` (egna endpoints);
`SupplierInvoiceOrigin`, `IsAutoInvoiceInterimSupplier`, `IsQuickInvoice`,
`IsDomestic`, `SelfEmployedWithoutFixedAddress` (utanför omfattning).

`SupplierId`, `IsCreditInvoice` och `Rows` är obligatoriska i specen.

**Tester (minst 14 sammanlagt för U14.1 och U14.2),** varav minst ett per
låst kategori som låser att fältet avvisas.

**GRIND 14.** Rapportera och stanna.

---

## Etapp 15 — Order- och offertutkast

### U15.1 — `spiris_offertutkast` (läsning)

**Filer:** adapter, rag, server, tests

`GET /quotedrafts` och `GET /quotedrafts/{id}`. Lägg också in
`"offertutkast": "/quotedrafts"` i `_ENKELUPPSLAG`.

Fältallowlist (`QuoteDraftApi`): `Id`, `Number`, `CustomerId`, `CustomerName`
(maskeras som **motpart**), `CustomerNumber`, `QuoteDate`, `DueDate`,
`DeliveryDate`, `CurrencyCode`, `TotalAmount` (`Decimal`), `VatAmount`
(`Decimal`), `RoundingsAmount` (`Decimal`), `Status`, `Rows`, `IncludesVat`,
`IsDomestic`, `YourReference`/`CustomerReference`, `OurReference`/
`CompanyReference`.

Adressfälten, `Persons`, alla `Rot*`, `ContributionMargin`,
`SalesDocumentAttachments`, `MessageThreads`, `Notes`, `BackgroundId` och
`TermsOfPayment` tas **inte** med.

Datakategori: `KATEGORI_RESKONTRA`.

**Tester (minst 6).**

### U15.2 — `forbered_offertutkast`

**Filer:** adapter, server, tests

`POST /quotedrafts`. Obligatoriskt i specen: `CustomerId`, `QuoteDate`,
`DueDate`.

Skickade fält: de tre obligatoriska plus `Rows`, `CurrencyCode`,
`IncludesVat`, `DeliveryDate`, `CustomerReference`, `CompanyReference`.
Inget annat.

`Rows` byggs med **samma** radbyggare som `forbered_kundfaktura` redan
använder. Skriv ingen ny. Belopp är `Decimal` (D3, Etapp 9).

Fail-closad kundupplösning: `CustomerId` slås upp vid **utförandet**, inte när
förslaget läggs — samma resonemang som `_hitta_kund` i `utfor_utkast`. En kund
kan ha ändrats mellan förslag och godkännande.

**Tester (minst 8).**

### U15.3 — `forbered_saljdokumentutkastatgard`

**Filer:** adapter, server, tests

Två konverteringar, in i den befintliga `_SALJDOKUMENTATGARDER`-tabellen:

| Nyckel | Verb | Suffix | Kropp |
|---|---|---|---|
| `("offertutkast", "till_offert")` | `PUT` | `convert` | `{}` |
| `("order", "till_backorder")` | `POST` | `backorder` | `{}` |

Tabellen är hårdkodad och fail-closed. En kombination som inte står där utförs
aldrig — det är hela poängen med den, och den regeln gäller även dina tillägg.

`DELETE /quotedrafts/{id}` läggs till i `forbered_utkastborttagning` via
`_UTKASTSLAG` med nyckeln `"offertutkast"`.

**Tester (minst 7).**

### U15.4 — `POST /quotes` och `POST /orders`

**Bygg inte.** En offert eller order skapas som **utkast** (U15.2) och
konverteras (U15.3). Den direkta vägen förbi utkaststadiet finns inte i den
här planen, av samma skäl som `MAL_UTKAST` är standard i `utfor_utkast`.

**GRIND 15.** Rapportera och stanna.

---

## Etapp 15b — Kvittning av leverantörskredit

### U15b.1 — `forbered_kvittning`

**Filer:** adapter, server, tests

`POST /supplierinvoices/{creditInvoiceId}/offset`. Kroppen ÄR specificerad
(`SupplierInvoiceOffsetCreateApi`) — den tidigare bedömningen att den saknades
var fel:

| Fält | Typ | Obligatoriskt |
|---|---|---|
| `DebitInvoiceIds` | array av uuid | ja |
| `VoucherDate` | `YYYY-MM-DD` | ja |

`additionalProperties: false` — **ingenting annat får skickas**. Ett extra
fält ger 400, och det är den enda gången i planen där ett överflödigt fält
faller på API:t i stället för på vår allowlist.

Fail-closed:

- `DebitInvoiceIds` får inte vara tom.
- Varje id måste finnas bland kandidaterna från
  `spiris_kvittningskandidater` (Etapp 5). Hämtningen görs vid utförandet,
  inte när förslaget läggs — kandidatlistan är levande data. Misslyckas den,
  eller saknas ett angivet id i den, utförs ingenting.
- Sammanfattningen till människan listar kreditfakturan och varje debetfaktura
  som kvittas, med belopp, samt det totala kvittningsbeloppet.

Docstringen ska säga att kvittningen skapar ett verifikat och att ångringen
(`POST /supplierinvoices/{id}/offset/undo`) medvetet inte finns i sie-mcp
(D5) — den får göras för hand i Spiris.

**Tester (minst 9),** varav minst två för kandidatkontrollen och ett som låser
att kroppen innehåller exakt två nycklar.

### U15b.2 — `POST /paymentvoucher`

**Bygg aldrig.** Specen: *"only available for Norwegian and Dutch companies."*
Punkten är därmed avförd, inte uppskjuten.

---

## Etapp 16 — Prislistor, rabattavtal och etiketter

Ren läsning. Låg risk, och den etapp som förklarar varför en fakturarad har
ett annat pris än artikelregistret säger.

### U16.1 — `spiris_prislistor`

`GET /salespricelists` — `Id`, `Name` (maskeras som etikett), `Number`,
`CurrencyCode`, `IsStandard`, `IsActive`. `Note` och `ChangedUtc` tas inte med.

`GET /salespricelists/prices/{salesPriceListId}` — priserna i en lista.
Fältallowlisten fastställs ur `SalesPriceApi` i specen; står den inte där när
du kommer hit: stanna och fråga.

### U16.2 — `spiris_rabattavtal`

`GET /discountagreements` — `Id`, `Name` (etikett), `Number`, `IsActive`.
`Notes` och `ChangedUtc` tas inte med.

### U16.3 — `spiris_etiketter`

`GET /customerlabels` och `GET /articlelabels` i **ett** verktyg med argumentet
`typ: str` (`"kund"` eller `"artikel"`), byggt på en hårdkodad tabell som
`_ENKELUPPSLAG`. Fältallowlist: `Id`, `Name` (REQ, etikett), `Description`.

`POST`, `PUT` och `DELETE` på etiketter byggs inte. En etikett är en
organisatorisk bekvämlighet, inte en bokföringshändelse.

Datakategori för hela etappen: `KATEGORI_STRUKTUR`.

**Tester (minst 10 sammanlagt).**

**GRIND 16.** Rapportera och stanna.

---

## Etapp 17 — Småplock

### U17.1 — `spiris_verifikation`

`GET /vouchers/{fiscalyearId}/{voucherId}`. Passar inte `_ENKELUPPSLAG`
eftersom sökvägen har två segment — bygg den som ett eget verktyg med två
argument. Återanvänd `mappa_verifikation`. Datakategori: `KATEGORI_HUVUDBOK`.

Fail-closed: båda argumenten måste vara ifyllda.

**Tester (minst 4).**

### U17.2 — `spiris_bankhandelse`

`GET /banktransactions/{bankAccountId}/{bankTransactionId}`. Samma mönster,
samma mappning som `spiris_bankhandelser`. Datakategori: `KATEGORI_HUVUDBOK`.

**Tester (minst 3).**

**GRIND 17.** Rapportera och stanna.

---

## 3. Byggs aldrig

`/messagethreads`, `/appstore`, `/partnerresourcelinks`, `/banks`,
`/backgrounds`, `/warmup`, `POST /supplierinvoices/{id}/offset/undo`,
`POST /quotes`, `POST /orders`, samt skrivande operationer på etiketter.

**Landsbegränsade — finns inte för ett svenskt bolag** (specens egna
operationsbeskrivningar, lästa 2026-08-10):

| Operation | Specens text |
|---|---|
| `POST /paymentvoucher` | *only available for Norwegian and Dutch companies* |
| `POST /voucherwithoverunderpayment` | *not available for Swedish companies* |
| `GET /voucherwithoverunderpayment/{id}` | *not available for Swedish companies* |
| `GET /accounts/standardaccounts` | *only available for Dutch companies* |

Den andra raden är skälet till R8.7: ett verktyg byggdes redan på den.
`GET /documents/{id}` bär en liknande notering men gäller *Swedish and Dutch
companies* och är alltså tillgänglig.

`/webhooks`, `/purchasereceipts`, `/purchasereceiptdrafts` och
`/reports/monthly` saknar kontrakt i OpenAPI-specen helt. De kan inte byggas
mot en gissad form (I6). Om de blir aktuella kräver de en egen utredning och
ett eget sandbox-prov — inte en rad i den här planen.

---

## 4. Rapportmall

Efter varje uppgift, ordagrant enligt konstitutionen §7:

```
UPPGIFT: <U- eller R-nummer>
STATUS:  klar | stoppad

TESTER:  före N passed → efter M passed  (+K nya, 0 nya röda)
KOMMANDO: python -m pytest tests -q

FILER SOM ÄNDRATS:
  <sökväg>  (+rader/-rader, kort beskrivning)

AVVIKELSER FRÅN SPECIFIKATIONEN:
  <ingen | beskrivning>

FRÅGOR TILL ARKITEKTEN:
  <ingen | frågorna>
```

Rapportera aldrig "klar" om sviten inte är grön. Rapportera aldrig ett
antagande som ett faktum.

Vid varje grind: summera etappen i samma form och **stanna**.
