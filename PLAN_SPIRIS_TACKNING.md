# Exekverbar plan — full Spiris-täckning

> **STATUS:** Etapp 0-3 är genomförda och testerna är godkända (2192 passed). Arbetet är pausat vid GRIND 3 i väntan på godkännande för Etapp 4.

**Läs `ARKITEKTUR_SPIRIS_TACKNING.md` först.** Den motiverar varje beslut
nedan. Det här dokumentet innehåller bara utförandet.

**Mottagare:** den AI som utför hantverket (Gemini 3.1 Pro).
**Avsändare:** arkitekten. Arkitekturbesluten är fattade. Din uppgift är att
genomföra dem exakt — inte att förbättra dem.

---

## 0. Innan du rör en fil

### 0.1 Läs konstitutionen

`hantverksbok/00_KONSTITUTION.md` (i arkivet:
`_arkiv/sie-mcp-2026-08-09/hantverksbok/00_KONSTITUTION.md`) gäller i sin
helhet för allt arbete i den här planen. Särskilt de sex invarianterna I1–I6
och listan över filer du aldrig ändrar.

Kortversionen, som **inte** ersätter läsningen:

| # | Invariant |
|---|---|
| I1 | `Decimal`, aldrig `float`. Enda tillåtna konverteringen är `_DecimalJSONEncoder`. |
| I2 | Fältallowlist. Du hämtar exakt de fält uppgiften listar — inte ett till. |
| I3 | Fail-closed. Väsentligt fält indexeras direkt; kompletterande via `.get()`. |
| I4 | MCP föreslår, utför aldrig. Inget i `server.py`/`spiris_rag.py` anropar `skicka`/`uppdatera`/`ta_bort`. |
| I5 | Maskering vid egressgränsen. En maskerare per hämtning, aldrig per post. |
| I6 | Fältnamn ur specen, aldrig ur gissning. Står det inte här — stanna och fråga. |

Filer du aldrig ändrar: `sekretesslager.py`, `utkast.py`, `reskontra_tvatt.py`,
`revisionslogg.py`, `namnreferens.py`, `saker_lagring.py`,
`masking_memory.py`, `compliance.py`, `spiris_session.py`, `spiris_auth_vy.py`,
`.env*`.

Du ändrar aldrig ett befintligt test för att få det grönt.

### 0.2 Baslinje

```
pytest tests -q
```

Ska ge **2096 passed, 1 skipped** innan du börjar. Gör den inte det: stanna
och rapportera. Bygg aldrig ovanpå en röd svit.

### 0.3 Testräkning

Varje uppgift anger ett **minsta** antal nya tester. Antalet passerade tester
ska efter uppgiften ha ökat med minst det talet, och **noll** får ha gått
från grönt till rött. Skriver du fler tester än minimum är det bra — skriv i
så fall ut det i rapporten. Färre är alltid ett stopp.

Detta skiljer sig medvetet från konstitutionens §2, som kräver ett exakt
antal. Skälet: fältmängderna i den här planen är spec-härledda och kan visa
sig innehålla fler fall än arkitekten kunnat räkna i förväg.

### 0.4 Arbetsordning och grindar

Etapperna körs **i ordning**. Mellan varje etapp finns en **grind**: ett
rökprov mot en riktig Spiris-sandbox som körs av arkitekten eller användaren,
aldrig av dig. Du rapporterar att etappen är klar och **stannar**. Börja inte
på nästa etapp innan du fått besked.

Skälet står i konstitutionen §8: fältnamnen här är hämtade ur
`https://eaccountingapi.vismaonline.com/openapi/v2.json` men är
**spec-härledda, inte sandbox-verifierade**. Specen har ljugit förr.

### 0.5 Etappernas ordning och varför

| Etapp | Innehåll | Beroende |
|---|---|---|
| 0 | Transportlagret: filtrering, 429, binärt | Inget. Allt annat vilar på det |
| 1 | Läsning — de billiga vinsterna | Etapp 0 (filtrering) |
| 2 | Utkastvägen görs hel | Etapp 1 (enkeluppslag på utkast) |
| 3 | Periodiseringar | Etapp 2 (utkast som periodiseringen fästs på) |
| 4 | Bilagor och underlag | Etapp 0 (binärt), ny datakategori |
| 5 | Betalningsavvikelser och kvittning | Etapp 1 |
| 6 | MCP-resurser och prompter | Etapp 1 |
| 7 | Sidbrytning i verktygssvar | Etapp 0 |
| 8+ | Återstoden — **spärrad**, se avsnitt 9 | Arkitektbeslut |

---

## Etapp 0 — Transportlagret

Enda etappen som rör `parser/spiris_klient.py`. Efter den rörs den inte igen.

### U0.1 — Filtrering, urval, sortering och sidstorlek

**Filer:** `parser/spiris_klient.py`, `tests/test_spiris_klient.py`

`hamta_alla` får fyra nya **valfria** nyckelordsargument. Utelämnade ska
metoden bete sig **exakt** som i dag — 71 befintliga anropsställen får inte
ändra beteende.

```python
def hamta_alla(
    self,
    path: str,
    params: dict | None = None,
    *,
    filter: str | None = None,
    select: list[str] | None = None,
    orderby: str | None = None,
    pagesize: int | None = None,
) -> list[dict]:
```

Parameternamnen mot Spiris är verifierade mot dokumentationen
(`developer.vismaonline.com`, hämtad 2026-08-09):

| Argument | Frågesträngsparameter | Form |
|---|---|---|
| `filter` | `$filter` | OData v4, t.ex. `Number gt 1337` |
| `select` | `$select` | kommaseparerad lista, t.ex. `Name,Number` |
| `orderby` | `$orderby` | ett egenskapsnamn |
| `pagesize` | `$pagesize` | heltal |

Regler:

- `pagesize` valideras: `1 <= pagesize <= 1000`. Utanför → `ValueError`.
  1000 är Spiris dokumenterade maximum; standard är 50.
- `select` fogas ihop med `,` utan mellanslag.
- `filter` skickas ordagrant vidare. Du bygger **ingen** OData-generator och
  ingen strängescape — det är anroparens ansvar och en tyst omskrivning av ett
  filter vore värre än inget filter. Ett `filter` som är tomt eller bara
  blanktecken → `ValueError`.
- Ingen av parametrarna får skriva över ett värde som redan finns i `params`.
  Krock → `ValueError`.

`hamta_en` får **inte** de nya argumenten. Den hämtar ett enskilt objekt;
paginering och sortering är meningslösa där.

**Tester (minst 9):** en per parameter att den hamnar rätt i frågesträngen;
att alla fyra kan kombineras; att utelämnade parametrar ger exakt samma
frågesträng som i dag; `pagesize=0` och `pagesize=1001` ger `ValueError`;
tomt `filter` ger `ValueError`; krock med `params` ger `ValueError`.

### U0.2 — 429 Too Many Requests

**Filer:** `parser/spiris_klient.py`, `tests/test_spiris_klient.py`

Spiris tillåter 600 anrop per minut och klient/endpoint och svarar annars
`429` med kroppen:

```json
{"ErrorCode": 4010, "DeveloperErrorMessage": "API calls quota exceeded! ...", "ErrorId": "..."}
```

I `_anrop_med_refresh`, **efter** den befintliga 401-hanteringen:

- Vid `429` med huvudet `Retry-After` (heltal sekunder): sov så länge, gör
  **exakt ett** omtag. Misslyckas det → `SpirisKlientFel`.
- Vid `429` **utan** `Retry-After`: inget omtag. `SpirisKlientFel` direkt.
- Väntetiden begränsas uppåt till 60 sekunder. Ett `Retry-After` som är
  längre → inget omtag, `SpirisKlientFel` direkt. En MCP-klient som blockeras
  i tio minuter är värre än ett tydligt fel.
- Felmeddelandet ska innehålla Spiris egen `DeveloperErrorMessage` när den
  finns. Nuvarande text ("Spiris avvisade förfrågan (HTTP 429)") lämnar
  användaren utan väg framåt.
- Sömnen sker via en modulnivåfunktion som testet kan ersätta. Ett test som
  faktiskt sover är ett trasigt test.

Retry-mekaniken för 401 rörs inte. En begäran kan alltså i värsta fall göras
tre gånger (original + 401-omtag + 429-omtag) och inte fler.

**Tester (minst 6):** 429 med `Retry-After: 2` ger ett omtag och lyckas; 429
utan huvud ger inget omtag; 429 med `Retry-After: 120` ger inget omtag;
`DeveloperErrorMessage` finns i feltexten; två 429 i rad ger `SpirisKlientFel`;
sömnfunktionen anropas med rätt antal sekunder.

### U0.3 — Binärhämtning

**Filer:** `parser/spiris_klient.py`, `tests/test_spiris_klient.py`

**Ny** metod. Rör inte `_hamta_json` — den ska fortsatt fail-closa på allt
som inte är JSON (B7 i arkitekturdokumentet).

```python
def hamta_binart(self, path: str) -> tuple[bytes, str]:
    """Returnerar (innehåll, content_type)."""
```

- Samma OAuth-refresh och samma fail-closed-mappning till `SpirisKlientFel`
  som de fyra befintliga verben.
- Ingen storleksgräns i klienten. Gränsen sätts i etapp 4, där det finns en
  domän att motivera den i.
- Metoden **loggar inte** och **sparar inte** innehållet någonstans.

**Tester (minst 4):** lyckad hämtning ger rätt bytes och content-type; 401
ger en refresh och ett omtag; HTTP-fel ger `SpirisKlientFel`; nätverksfel ger
`SpirisKlientFel`.

**GRIND 0.** Rapportera och stanna.

---

## Etapp 1 — Läsning: de billiga vinsterna

Mönstret är identiskt för varje uppgift och finns redan i kodbasen. Läs
`hamta_leverantorsfakturor` (`spiris_adapter.py:808`) och dess väg upp genom
`spiris_rag.py` och `server.py` i sin helhet innan du börjar. **Kopiera den
formen.** Varje nytt läsverktyg ska ha:

1. en mappningsfunktion i `spiris_adapter.py`,
2. ett async-omslag med maskering i `spiris_rag.py`,
3. ett `spiris_*`-verktyg i `server.py` med rätt datakategori,
4. ett kort alias i aliasblocket längst ned i `server.py`.

### U1.1 — `spiris_kundfakturor`

**Filer:** `mcp_server/server.py`, `parser/spiris_rag.py`, `tests/`

Adapterfunktionen `hamta_kundfakturor` finns redan i `spiris_adapter.py:848`,
är testad, och saknar bara en väg upp. Skriv **ingen** ny mappning.

Datakategori: `KATEGORI_RESKONTRA`. Egressmaskering: samma väg som
`spiris_leverantorsfakturor`, alltså `maskera_for_egress`.

Skillnaden mot `spiris_kundreskontra` — att betalda fakturor ingår — ska stå i
verktygets docstring. Utan den kommer en AI-klient att välja fel verktyg.

**Tester (minst 3).**

### U1.2 — `spiris_verifikationer_alla`

**Filer:** `parser/spiris_adapter.py`, `parser/spiris_rag.py`,
`mcp_server/server.py`, `tests/`

`GET /vouchers` — verifikationer över **alla** räkenskapsår.

Fältallowlist (`VoucherApi`, spec-härledd):

| Spirisfält | Domännyckel | Väsentligt? |
|---|---|---|
| `VoucherDate` | `datum` | ja — indexeras direkt |
| `VoucherText` | `text` | ja — indexeras direkt |
| `Rows` | `rader` | ja — indexeras direkt |
| `Id` | `id` | nej |
| `NumberAndNumberSeries` | `nummer` | nej |
| `NumberSeries` | `serie` | nej |
| `VoucherType` | `verifikationstyp` | nej |
| `ModifiedUtc` | `andrad` | nej |

`CreatedUtc`, `SourceId`, `ImportedVoucherNumber` och `Attachments` tas
**inte** med.

Radernas mappning finns redan i `mappa_verifikation` — återanvänd den.
`VoucherText` är fritext och maskeras (I5, B4).

Verktyget tar valfria `fran_datum` och `till_datum` och översätter dem till
ett `$filter` via U0.1:
`VoucherDate ge <fran>T00:00:00.00Z and VoucherDate le <till>T23:59:59.00Z`.
Utan datum hämtas allt — det är avsiktligt och ska stå i docstringen.

Datakategori: `KATEGORI_HUVUDBOK`.

**Tester (minst 6),** varav minst ett som låser att fälten utanför
allowlisten *inte* finns i utdatat.

### U1.3 — `spiris_ingaende_balans`

**Filer:** adapter, rag, server, tests

`GET /fiscalyears/openingbalances`. Fältallowlist: `Name` → `kontonamn`,
`Number` → `kontonr`, `Balance` → `saldo`. Alla tre är väsentliga och
indexeras direkt.

`Balance` är `Decimal` (I1). `Name` är ett kontonamn och maskeras med
`skapa_kontonamnsmaskerare(las_namnreferens())` — **en** maskerare för hela
hämtningen (I5).

Datakategori: `KATEGORI_HUVUDBOK`.

**Tester (minst 4),** varav ett som låser att saldot är `Decimal` och ett som
låser att en och samma maskerare används för alla poster.

### U1.4 — `spiris_kontoplan_alla`

**Filer:** adapter, rag, server, tests

`GET /accounts` — kontoplanen över alla räkenskapsår.
`GET /accounts/standardaccounts` — BAS-standardkontoplanen.

Fältallowlist (`AccountApi`): `Number` → `kontonr` (REQ), `Name` →
`kontonamn` (REQ), `FiscalYearId` → `rakenskapsar_id` (REQ), `IsActive` →
`aktiv` (REQ), `Type` → `kontotyp` (via befintliga `spiris_typ_till_ktyp`),
`TypeDescription` → `kontotypstext`, `VatCodeId` → `momskod_id`,
`IsBlockedForManualBooking` → `sparrat_for_manuell_bokning`,
`IsProjectAllowed` → `projekt_tillatet`,
`IsCostCenterAllowed` → `kostnadsstalle_tillatet`.

`ReferenceCode`, `Description`, `AllowTransactionText`,
`IsFirstCostCenterMandatory`, `ModifiedUtc`, `CreatedUtc`,
`VatCodeDescription` tas **inte** med.

`Name` maskeras som kontonamn.

Datakategori: `KATEGORI_STRUKTUR`.

**Tester (minst 5).**

### U1.5 — Enkeluppslag

**Filer:** adapter, rag, server, tests

Ett generiskt verktyg, inte tolv. En hårdkodad tabell i `spiris_adapter.py`,
byggd på samma sätt som `_MASTERDATA` och `_SALJDOKUMENT` — fail-closed på en
typ som inte står i tabellen:

```python
_ENKELUPPSLAG: dict[str, str] = {
    "kundfaktura":            "/customerinvoices",
    "leverantorsfaktura":     "/supplierinvoices",
    "order":                  "/orders",
    "offert":                 "/quotes",
    "kund":                   "/customers",
    "leverantor":             "/suppliers",
    "artikel":                "/articles",
    "projekt":                "/projects",
    "momsrapport":            "/vatreports",
    "verifikatutkast":        "/voucherdrafts",
    "kundfakturautkast":      "/customerinvoicedrafts",
    "leverantorsfakturautkast": "/supplierinvoicedrafts",
}
```

Verktyget `spiris_hamta_ett(typ: str, objekt_id: str)`. Sökvägen blir
`f"{_ENKELUPPSLAG[typ]}/{objekt_id}"` via `hamta_en`.

Två regler utan undantag:

- **Återanvänd den befintliga mappningen** för varje typ. `kund` går genom
  samma mappning som `spiris_kunder`, `verifikatutkast` genom
  `mappa_verifikatutkast`, och så vidare. Skriv ingen ny fältmappning. Det är
  hela poängen: uppslaget får aldrig kunna returnera fler fält än listan
  redan gör.
- Ett tomt eller blankt `objekt_id` avvisas med `ValueError` innan något
  anrop görs. Utan den kontrollen blir sökvägen listendpointen och verktyget
  hämtar allt.

`GET /vouchers/{fiscalyearId}/{voucherId}` ingår **inte** — den har två
segment och passar inte tabellen. Den skjuts till etapp 8.

Datakategorin följer typen: `kund`/`leverantor` → `KATEGORI_MOTPARTSREGISTER`,
utkasten → `KATEGORI_UTKAST`, fakturorna → `KATEGORI_RESKONTRA`, övriga →
`KATEGORI_STRUKTUR`. Lägg tabellen bredvid `_ENKELUPPSLAG` så att den inte kan
glömmas när en typ läggs till.

**Tester (minst 8):** en per datakategori, okänd typ ger fel, tomt id ger
fel, och ett som låser att mappningen är densamma som listverktygets.

### U1.6 — Referens- och analysläsning

**Filer:** adapter, rag, server, tests

Fyra små verktyg, samma form som U1.3.

| Verktyg | Endpoint | Fältallowlist | Kategori |
|---|---|---|---|
| `spiris_valutakurs(datum, fran_valuta, till_valuta)` | `GET /currencies/exchangerate` | `Date`→`datum`, `SourceCurrency`→`fran_valuta`, `TargetCurrency`→`till_valuta`, `Rate`→`kurs` (Decimal) | `STRUKTUR` |
| `spiris_anlaggningstillgangar` | `GET /inventoryitems` | `Number`→`nummer`, `Name`→`benamning` (REQ, maskeras som etikett), `PurchasePrice`→`anskaffningsvarde`, `PurchaseDate`→`anskaffningsdatum`, `CurrentValue`→`bokfort_varde`, `ResidualValue`→`restvarde`, `LifeSpanInMonths`→`livslangd_manader`, `LatestDepreciationDate`→`senaste_avskrivning`, `InventoryItemStatus`→`status` | `HUVUDBOK` |
| `spiris_kundreskontraposter` | `GET /customerledgeritems` | `CustomerId`→`kund_id`, `InvoiceNumber`→`fakturanr`, `InvoiceDate`→`fakturadatum`, `DueDate`→`forfallodatum`, `TotalAmountInvoiceCurrency`→`belopp`, `RemainingAmountInvoiceCurrency`→`kvarvarande`, `IsCreditInvoice`→`ar_kredit`, `CurrencyCode`→`valuta`, `VoucherId`→`verifikat_id` — samtliga REQ i specen och indexeras direkt. `Id`→`id` och `PaymentReferenceNumber`→`betalreferens` via `.get()` | `RESKONTRA` |
| `spiris_anvandare` | `GET /users` | `Id`→`id`, `FirstName`+`LastName`→`namn`, `IsActive`→`aktiv`, `IsConsultant`→`ar_konsult`, `HasPurchaseInvoicesApprovalPermission`→`far_attestera_leverantorsfakturor`, `HasVATReportsApprovalPermission`→`far_attestera_momsrapporter` | `MOTPARTSREGISTER` |

`Email` på `/users` tas **inte** med. Ett namn på en anställd är personuppgift
och maskeras som motpart, inte som etikett — men det är alltid en fysisk
person, så det finns inget klartextfall. Är du osäker: stanna (konstitutionen
§6).

`Ocr`, `SupplierCorporateIdentityNumber` och liknande på andra endpoints
finns inte i den här uppgiften och ska inte dyka upp.

**Tester (minst 10).**

**GRIND 1.** Rapportera och stanna.

---

## Etapp 2 — Utkastvägen görs hel

Den viktigaste etappen. Läs `STEG_4_utkastvagen.md` i hantverksboken innan du
börjar, och `utfor_utkast` i `spiris_adapter.py` i sin helhet.

**Ingenting här bryter mot I4.** Varje ny förmåga blir ett `forbered_*`-verktyg
som lägger ett förslag i den lokala kön. Det är `utfor_utkast` — som körs från
Streamlit efter ett mänskligt godkännande — som gör anropet. `server.py` rör
aldrig `skicka`/`uppdatera`/`ta_bort`.

### U2.1 — `forbered_utkastandring`

**Filer:** `parser/spiris_adapter.py`, `mcp_server/server.py`, `tests/`

Ändrar ett **befintligt** utkast i Spiris.

```python
_UTKASTSLAG: dict[str, str] = {
    "verifikat":          "/voucherdrafts",
    "kundfaktura":        "/customerinvoicedrafts",
    "leverantorsfaktura": "/supplierinvoicedrafts",
}
```

`PUT` **nollar det som utelämnas**. Följ därför exakt samma mönster som
`bygg_masterdatauppdatering` (`spiris_adapter.py:2620`): hämta det nuvarande
objektet, lägg ändringarna ovanpå, skicka **hela** objektet. Skriv motiveringen
i docstringen — nästa läsare måste förstå varför hela objektet skickas.

Ändringsallowlist för `verifikat` (`VoucherDraftApi`, spec-härledd):
`VoucherDate` (REQ), `VoucherText`, `NumberSeries`, `Rows`.
`Id`, `CreatedUtc` och `ModifiedUtc` är serverägda och får aldrig sättas av
ett förslag.

Ändringsallowlisterna för `kundfaktura` och `leverantorsfaktura` är **inte**
fastställda. Bygg bara `verifikat` i den här uppgiften. De två andra ligger i
etapp 8 och kräver ett arkitektbeslut först — se avsnitt 9.

**Tester (minst 7).**

### U2.2 — `forbered_utkastborttagning`

**Filer:** adapter, server, tests

`DELETE` på samma tre slag. Detta är en **oåterkallelig** åtgärd och det ska
synas.

- Sammanfattningen som visas för människan före godkännande ska innehålla
  utkastets id, dess datum, dess text och dess totalbelopp. Ett förslag som
  bara säger "ta bort utkast 53060989-…" går inte att granska.
- Uppgifterna hämtas via `spiris_hamta_ett` från U1.5 — hämta dem, lägg dem i
  utkastet. Fungerar inte hämtningen läggs **inget** förslag (fail-closed).
- Följ formen i `forbered_masterdataborttagning` (`spiris_adapter.py:2723`).

**Tester (minst 6),** varav ett som låser att ett misslyckat uppslag ger noll
poster i kön.

### U2.3 — `forbered_utkastbokforing`

**Filer:** adapter, server, tests

Konverteringen. Den punkt där ett förslag blir en bokförd post.

| Slag | Anrop | Kropp |
|---|---|---|
| `verifikat` | `POST /voucherdrafts/{id}/convert` | ingen |
| `leverantorsfaktura` | `POST /supplierinvoicedrafts/{id}/convert` | ingen |
| `kundfaktura` | `POST /customerinvoicedrafts/{id}/convert` | **valfri** |

För `kundfaktura` finns två frågesträngsparametrar i specen,
`keepOriginalDraftDate` och `overrideCompanyKeepOriginalDraftDate`, och en
valfri kropp med `TotalAmountInvoiceCurrency`, `TotalVatAmountInvoiceCurrency`,
`TotalRoundingsInvoiceCurrency` och `Rows`.

**Skicka ingen kropp och ingen parameter.** Kroppens innebörd — om den
*validerar* utkastets summor eller *skriver över* dem — går inte att utläsa ur
specen, och skillnaden är ett felaktigt bokslut. Ett tomt anrop använder
utkastets egna siffror, vilket är det enda entydiga beteendet. Detta prövas i
grinden efter etappen; först då kan parametrarna övervägas.

Sammanfattningen till människan följer samma krav som U2.2: datum, text,
totalbelopp, radantal. Att bokföra ett verifikat man inte sett summan av är
inte ett godkännande.

**Tester (minst 8),** varav minst ett per slag som låser att anropet går till
rätt sökväg och **utan** kropp.

**GRIND 2.** Den viktigaste grinden i planen. Rapportera och stanna.

---

## Etapp 3 — Periodiseringar

### U3.1 — `spiris_periodiseringar` (läsning)

**Filer:** adapter, rag, server, tests

`GET /allocationperiods` och `GET /allocationperiods/{id}`.

Fältallowlist (`AllocationPeriodApi`): `Id`→`id`, `Rows`→`rader` (REQ),
`BookkeepingDate`→`bokforingsdatum`, `Amount`→`belopp` (Decimal),
`IsCredit`→`ar_kredit`, `DebitAccountNumber`→`debetkonto`,
`CreditAccountNumber`→`kreditkonto`, `Description`→`beskrivning` (fritext →
maskeras), `Status`→`status`, `SourceDate`→`kalldatum`,
`NumberAndNumberSeries`→`verifikationsnummer`,
`AllocationPeriodSourceType`→`kalltyp`, `ProjectId`→`projekt_id`,
`VoucherId`→`verifikat_id`, `SupplierInvoiceId`→`leverantorsfaktura_id`,
`CustomerInvoiceId`→`kundfaktura_id`.

Radnummerfälten (`*Row`), `CostCenterItemId1-3`, `VoucherFiscalYearId`,
utkast-id:na och `CreatedUtc`/`ModifiedUtc` tas **inte** med.

Datakategori: `KATEGORI_HUVUDBOK`.

**Tester (minst 5).**

### U3.2 — `forbered_periodisering`

**Filer:** adapter, server, tests

`POST /allocationperiods`. Kroppen är en **array** av objekt (spec-härledd):

| Fält | Obligatoriskt |
|---|---|
| `BookkeepingStartDate` | ja |
| `AmountToAllocate` | ja (Decimal) |
| `AllocationAccountNumber` | ja (heltal) |
| `NumberOfAllocationPeriods` | ja (heltal) |
| `VoucherId` + `VoucherRow` | ett av kopplingsparen |
| `SupplierInvoiceId` + `SupplierInvoiceRow` | ett av kopplingsparen |
| `SupplierInvoiceDraftId` + `SupplierInvoiceDraftRow` | ett av kopplingsparen |

Fail-closed-regler:

- Exakt **ett** kopplingspar får anges. Noll eller två → `ValueError`.
  En periodisering som pekar på både ett verifikat och en faktura är
  meningslös, och en som inte pekar någonstans är obokförbar.
- `NumberOfAllocationPeriods` måste vara `>= 1`. Annars `ValueError`.
- `AmountToAllocate` är `Decimal`, aldrig `float` (I1).
- `QuantityToAllocate` och `WeightToAllocate` tas inte med.

Sammanfattningen till människan: konto, belopp, antal perioder, startdatum och
vad periodiseringen fästs på.

`PUT /allocationperiods` och `DELETE /supplierinvoicedrafts/{id}/allocationperiods`
ingår **inte** i den här uppgiften — de ligger i etapp 8.

**Tester (minst 9),** varav minst tre för kopplingsparsreglerna.

**GRIND 3.** Rapportera och stanna.

---

## Etapp 4 — Bilagor och underlag

Etappen som kräver ett nytt begrepp i sekretessarkitekturen. Läs
`ARKITEKTUR_SPIRIS_TACKNING.md` avsnitt 5.2 och B3 innan du börjar.

### U4.1 — Ny datakategori

**Filer:** `mcp_server/server.py`, `tests/`

```python
KATEGORI_UNDERLAG = "underlag och bilagor (filnamn och metadata)"
```

Läggs bredvid de fem befintliga (`server.py:319-323`). Kategorin används av
allt i etapp 4 och av ingenting annat.

Skälet står i B3: bilagors filnamn och kommentarer är fritext skriven av en
människa och hör varken hemma i `HUVUDBOK` eller i `STRUKTUR` i Art. 30-loggen.

**Tester (minst 2).**

### U4.2 — `spiris_underlag` (lista)

**Filer:** adapter, rag, server, tests

`GET /attachments` med parametern `includeMatched` (bool). `includeMatched=false`
ger de **omatchade** underlagen — kvitton som väntar på att bokföras.

Fältallowlist (`AttachmentResultApi`): `Id`→`id`, `FileName`→`filnamn`
(**fritext, maskeras**), `ContentType`→`filtyp`,
`AttachmentStatus`→`status`, `Type`→`typ`,
`AttachedDocumentType`→`kopplad_dokumenttyp`, `DocumentId`→`dokument_id`,
`ImageDate`→`bilddatum`, `TransactionDate`→`transaktionsdatum`,
`DueDate`→`forfallodatum`, `InvoiceNumber`→`fakturanummer`,
`AmountInvoiceCurrency`→`belopp` (Decimal), `Vat`→`moms` (Decimal),
`CurrencyCode`→`valuta`, `SupplierName`→`leverantorsnamn` (maskeras som
**motpart**, inte som etikett).

Följande tas **inte** med, och det är inte ett förbiseende:

- `TemporaryUrl` — en signerad länk till innehållet. Skickas den till en
  AI-modell har underlaget lämnat kodbasen utan att passera maskeringen.
  Använd `includeTemporaryUrl=false`.
- `SupplierCorporateIdentityNumber` — organisationsnummer, som för en
  enskild firma är ett personnummer.
- `Ocr`, `Comment`, `UploadedBy`, `MessageThreads`, `Notes`, `PhotoSource`,
  `PaymentDate`.

Datakategori: `KATEGORI_UNDERLAG`.

**Tester (minst 8),** varav **minst två** som uttryckligen låser att
`TemporaryUrl` och `SupplierCorporateIdentityNumber` inte finns i utdatat.
Det är den enda sortens fel konstitutionen säger att testsviten annars missar
(I2).

### U4.3 — `spiris_hamta_underlag` (innehåll)

**Filer:** adapter, rag, server, tests

`GET /attachments/{id}` via `hamta_binart` från U0.3.

Regler:

- Filen **returneras aldrig** i verktygssvaret. Ett verktyg som lämnar
  tillbaka en base64-kodad faktura har skickat hela underlaget till en extern
  modell utan maskering.
- Filen sparas lokalt i användarens nedladdningsmapp, på samma sätt som
  `ladda_ner_sie` redan gör (`spiris_adapter.py`). Läs den funktionen och
  kopiera formen, inklusive dess sökvägshantering.
- Verktyget returnerar sökvägen, filnamnet, storleken och filtypen.
- Storleksgräns: 25 MB. Över det → `SpirisKlientFel` med tydlig text. Gränsen
  hör hemma här och inte i klienten (U0.3).

Datakategori: `KATEGORI_UNDERLAG`.

**Tester (minst 6),** varav ett som låser att innehållet inte finns i svaret.

### U4.4 — `forbered_underlagskoppling`

**Filer:** adapter, server, tests

`POST /attachmentlinks` — kopplar ett befintligt underlag till ett befintligt
dokument. Kroppens form fastställs i grinden före implementation; specen anger
den inte entydigt.

**Bygg den här uppgiften först efter besked från arkitekten.** Står du här
utan besked: stanna och fråga (konstitutionen §6).

**GRIND 4.** Rapportera och stanna.

---

## Etapp 5 — Betalningsavvikelser och kvittning

### U5.1 — `spiris_kvittningskandidater`

**Filer:** adapter, rag, server, tests

`GET /supplierinvoices/{creditInvoiceId}/offsetcandidates`. Ren läsning.

Fältallowlist: `InvoiceId`→`faktura_id`, `InvoiceNumber`→`fakturanr`,
`InvoiceDate`→`fakturadatum`, `SupplierName`→`leverantor` (maskeras som
motpart), `RemainingAmount`→`kvarvarande` (Decimal),
`CurrencyCode`→`valuta`.

Datakategori: `KATEGORI_RESKONTRA`.

**Tester (minst 4).**

### U5.2 — `forbered_kvittning`

**Filer:** adapter, server, tests

`POST /supplierinvoices/{creditInvoiceId}/offset`. Kroppens form är **inte**
fastställd i specen. Samma villkor som U4.4: bygg först efter besked.

`POST /supplierinvoices/{id}/offset/undo` ingår inte — en ångring av en
kvittning är en åtgärd som ska göras i Spiris av en människa som ser hela
bilden.

### U5.3 — `forbered_betalningsverifikat`

**Filer:** adapter, server, tests

`POST /voucherwithoverunderpayment` — verifikat för över- eller
underbetalning. Det vanligaste verkliga betalningsfallet, och det som
`forbered_betalningsregistrering` inte klarar.

Kropp (spec-härledd): `VoucherDate` (REQ), `VoucherText`, `Rows` (REQ).
`Attachments` tas inte med.

`Rows` byggs med **samma** radbyggare som `forbered_verifikat` redan använder.
Skriv ingen ny.

Fail-closed: raderna måste balansera. Debet ≠ kredit → `ValueError` innan
förslaget läggs. Ett obalanserat verifikat i kön är ett fel som upptäcks
först vid godkännandet, och då har människan redan lagt tid på att granska
det.

`POST /paymentvoucher` ingår **inte**. Den har fyra frågesträngsparametrar
som styr momsberäkning och verifikationsserie (`useAutomaticVatCalculation`,
`useDefaultVatCodes`, `useDefaultVoucherSeries`, `checkExistingBankTransaction`),
och deras samspel går inte att utläsa ur specen. Etapp 8.

**Tester (minst 7),** varav minst två för balanskontrollen.

**GRIND 5.** Rapportera och stanna.

---

## Etapp 6 — MCP-resurser och prompter

**Filer:** `mcp_server/server.py`, `tests/`

Ingen ny Spiris-åtkomst. Etappen exponerar det som redan finns genom två
protokollytor som i dag är helt oanvända (T5).

### U6.1 — Resurser

Fyra `@mcp.resource`, var och en ett tunt omslag om ett **befintligt**
verktyg. Ingen ny hämtning, ingen ny mappning, ingen ny maskering.

| URI | Innehåll | Bakomliggande verktyg |
|---|---|---|
| `spiris://foretag` | Företagsuppgifter | `spiris_foretagsinfo` |
| `spiris://rakenskapsar` | Räkenskapsåren | `spiris_rakenskapsar` |
| `spiris://kontoplan/{rakenskapsar_id}` | Kontoplanen | `spiris_kontoplan` |
| `spiris://villkor` | Användarvillkorens status | `visa_anvandarvillkor` |

Villkorsspärren (`_villkor_godkanda`) gäller resurser precis som verktyg. En
resurs som läcker förbi spärren vore en väg runt hela godkännandemodellen.
Låt detta vara det första testet du skriver.

**Tester (minst 6),** varav ett per resurs plus ett som låser spärren.

### U6.2 — Prompter

Fem `@mcp.prompt`, en per återkommande arbetsgång. Varje prompt är text som
namnger vilka verktyg som ska köras i vilken ordning — den anropar ingenting
själv.

| Prompt | Arbetsgång |
|---|---|
| `stam_av_banken` | bankkonton → omatchade bankhändelser → avstämningsläge |
| `granska_momsperioden` | momsöversikt → momskoder → momsrapporter |
| `manadsavstamning` | resultatrapport → balansrapport → kontosaldon → väsentlighet |
| `granska_kundfordringar` | kundreskontra → kundbetalbeteende → likviditetsprognos |
| `forbered_bokslutsposter` | ingående balans → periodiseringar → anläggningstillgångar |

Varje prompt ska avslutas med en mening som säger att inget skrivs förrän en
människa godkänt i Streamlit-appen. En prompt är det första en AI-klient
läser, och den ska bära modellen.

**Tester (minst 6).**

**GRIND 6.** Rapportera och stanna.

---

## Etapp 7 — Sidbrytning i verktygssvar

**Filer:** `mcp_server/server.py`, `parser/spiris_rag.py`, `tests/`

De verktyg som kan returnera stora mängder — `spiris_kontotransaktioner`,
`spiris_verifikationer_alla`, `spiris_kundfakturor`, `spiris_kundreskontra`,
`spiris_leverantorsreskontra`, `spiris_underlag` — får två valfria argument:

```python
offset: int = 0, limit: int = 0   # limit=0 betyder "allt", som i dag
```

Envelopet får tre nya nycklar: `totalt_antal`, `visade`, `trunkerat` (bool).

Två regler:

- Standardvärdena ger **exakt** dagens beteende. Inget befintligt test får
  ändras.
- `trunkerat: True` ska åtfölja en text som säger hur resten hämtas. En AI
  som inte vet att den fått en delmängd drar slutsatser av ofullständig data —
  och det är precis den sortens fel som är svårast att upptäcka i efterhand.

**Tester (minst 8).**

**GRIND 7.** Rapportera och stanna.

---

## 9. Etapp 8+ — spärrat

Följande är **inte** klart för utförande. Var och en saknar antingen en
fältallowlist, en fastställd payloadform eller ett arkitektbeslut om huruvida
den överhuvudtaget hör hemma i sie-mcp.

**Rör dem inte. Fråga inte om att få rita dem själv.**

| Område | Vad som saknas |
|---|---|
| Ändringsallowlist för kundfaktura- och leverantörsfakturautkast (U2.1) | Fältvalet — de har 40+ fält vardera |
| `PUT /allocationperiods`, `DELETE /supplierinvoicedrafts/{id}/allocationperiods` | Semantiken vid ändring av en pågående periodisering |
| `POST /paymentvoucher` | De fyra frågesträngsparametrarnas samspel |
| `POST /attachmentlinks`, `POST /salesdocumentattachments/*` | Kroppens form |
| `POST /supplierinvoices/{id}/offset` | Kroppens form |
| Kontoplansunderhåll (`POST /accounts`, `PUT /accounts/{fy}/{nr}`) | Om en AI ska få föreslå ändringar i kontoplanen alls |
| `PUT /companysettings/*` (bokföringslås, ROT/RUT) | Samma fråga, högre insats |
| Offert- och orderutkast (`/quotedrafts`, `POST /quotes`, `POST /orders`) | Prioritet mot resten |
| Prislistor, rabattavtal, etiketter | Prioritet |
| `GET /vouchers/{fiscalyearId}/{voucherId}` | Passar inte enkeluppslagstabellen |
| `/webhooks`, `/purchasereceipts`, `/reports/monthly` | Saknar kontrakt i OpenAPI-specen helt |

Byggs **aldrig**: `/messagethreads`, `/appstore`, `/partnerresourcelinks`,
`/banks`, `/backgrounds`, `/warmup`. Skälen står i arkitekturdokumentet 7.1.

---

## 10. Rapportmall

Efter varje uppgift, ordagrant enligt konstitutionen §7:

```
UPPGIFT: <U-nummer>
STATUS:  klar | stoppad

TESTER:  före N passed → efter M passed  (+K nya, 0 nya röda)
KOMMANDO: pytest tests -q

FILER SOM ÄNDRATS:
  <sökväg>  (+rader/-rader, kort beskrivning)

AVVIKELSER FRÅN SPECIFIKATIONEN:
  <ingen | beskrivning>

FRÅGOR TILL ARKITEKTEN:
  <ingen | frågorna>
```

Rapportera aldrig "klar" om sviten inte är grön. Rapportera aldrig ett
antagande som ett faktum.

Vid varje grind: rapportera **etappen** i samma form, summera uppgifterna, och
**stanna**.
