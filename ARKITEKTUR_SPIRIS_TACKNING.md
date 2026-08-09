# Arkitektur — full Spiris-täckning i sie-mcp

**Datum:** 2026-08-09
**Författare:** arkitekturunderlag, avsett att läsas före `PLAN_SPIRIS_TACKNING.md`
**Mätt mot:** `https://eaccountingapi.vismaonline.com/openapi/v2.json`
(*Bookkeeping & Invoicing/eAccounting API V2*), hämtad 2026-08-09.

---

## 1. Sammanfattning

Frågan var: **är allt som en MCP kan göra åt Spiris driftsatt i sie-mcp?**

Nej. Mätningen är entydig:

| Mått | Värde |
|---|---|
| Sökvägar i Spiris OpenAPI v2 | 274 |
| Varav med minst en definierad HTTP-metod | 233 sökvägar / **228 operationer** |
| Operationer som sie-mcp faktiskt anropar | **71** |
| **Täckningsgrad** | **31 %** |
| Otäckta operationer | 157 |

De 41 sökvägar som saknar metoder i specen (t.ex. `/company/info`,
`/webhooks`, `/purchasereceipts`, `/accountingtemplates`) är tomma objekt i
OpenAPI-dokumentet. De är **inte** anropbara utifrån specen och räknas därför
varken som täckta eller otäckta. De behandlas i avsnitt 7.

De 157 otäckta operationerna fördelar sig så här efter vad projektets egen
doktrin tillåter:

| Klass | Antal | Innebörd |
|---|---|---|
| **Läs** | 68 | Kan bli nya läsverktyg i MCP direkt |
| **Utkast** | 72 | Skrivande — får bara nå MCP som `forbered_*` mot utkastkön |
| **Ej aktuellt** | 17 | Partner-/plattformsfunktioner utan värde här (se 7.1) |

Utöver de funktionella luckorna finns **sex tvärgående kapacitetsluckor** i
transportlagret och i MCP-ytan (avsnitt 4). Flera av dem är billigare att
åtgärda än en enskild endpoint och ger mer nytta.

**Viktigaste enskilda fyndet:** utkastvägen är byggd men **halv**. sie-mcp kan
skapa ett verifikatutkast, ett kundfakturautkast och ett
leverantörsfakturautkast i Spiris — men saknar helt `…/convert`, `PUT` och
`DELETE` på samtliga fyra utkastslag. Ett utkast som lagts kan alltså varken
bokföras, rättas eller städas bort via sie-mcp. Se 5.1.

---

## 2. Metod

1. `openapi/v2.json` hämtades och alla operationer (`path` × `method`)
   extraherades.
2. Varje anrop till `SpirisKlient.hamta_alla / hamta_en / skicka / uppdatera /
   ta_bort` i `parser/spiris_adapter.py` lästes ut, inklusive de som byggs via
   tabellerna `_SALJDOKUMENT`, `_SALJDOKUMENTATGARDER`, `_MASTERDATA`,
   `_ATTESTOBJEKT` och `_BANKHANDELSE_STATUS`.
3. Mängderna jämfördes. **Noll** anropade sökvägar saknades i specen — inga
   döda eller uppfunna endpoints finns i adaptern. Det är i sig ett kvitto på
   att I6 (fältnamn ur boken) har hållits.
4. MCP-ytan (`mcp_server/server.py`, 85 `@mcp.tool`) jämfördes separat mot
   adapterns publika funktioner för att hitta byggd-men-oexponerad förmåga.

Baslinje för testsviten vid mätningen: **2096 passed, 1 skipped**
(`pytest tests -q`, 25 s).

---

## 3. Vad som redan är driftsatt

Det som finns är inte en slumpmässig delmängd — det är en **komplett
analysväg** plus en **påbörjad åtgärdsväg**.

**Läsning (fullt fungerande):** räkenskapsår, kontoplan, kontosaldon,
kontotransaktioner, verifikationer, verifikatutkast, företagsinfo,
resultat- och balansrapport, kassaflödesanalys, momsöversikt, momskoder,
momsrapporter, kund- och leverantörsreskontra, kundbetalbeteende,
likviditetsprognos, artiklar, kunder, leverantörer, projekt, kostnadsställen,
bankkonton, bankhändelser (matchade/omatchade), avstämningsläge, ordrar,
offerter, leverantörsfakturor, SIE4-export.

**Åtgärdsförslag (via utkastkön):** kund, kundfaktura, verifikat,
fakturautskick, e-fakturautskick, betalningspåminnelse,
betalningsregistrering, makulering, säljdokumentutskick, säljdokumentåtgärd,
leverantörsfakturautkast, attest, leverantörsbetalning, masterdataändring,
masterdataborttagning, SIE4-import.

Arkitekturen bakom är sund och ska inte röras:

```
mcp_server/server.py     verktygsdeklaration, koreografi
parser/spiris_rag.py     async-omslag, egressmaskering, envelope
parser/spiris_adapter.py rå JSON → domännycklar
parser/spiris_klient.py  HTTP, OAuth, paginering, fail-closed
parser/utkast.py         utkastkö + hashbindning   (rörs ej)
parser/sekretesslager.py maskering                 (rörs ej)
```

Utbyggnaden i planen sker **enbart** genom att lägga till i de fyra översta
lagren, i samma riktning som redan gäller.

---

## 4. Tvärgående kapacitetsluckor

Dessa är inte endpoints. De begränsar **allt** som byggs ovanpå, och tre av
dem är förutsättningar för att den funktionella utbyggnaden ska bli
användbar i ett bolag av verklig storlek.

### T1 — Klienten kan inte filtrera, välja fält eller sortera

`hamta_alla` skickar bara `$page`. Spiris stödjer utöver det `$filter`,
`$select`, `$orderby`/`$sort` och `$pagesize`.

Följden är konkret: `spiris_kontotransaktioner` hämtar **hela** räkenskapsårets
verifikationer och filtrerar i Python. I ett bolag med 20 000 verifikat är det
tiotals HTTP-rundor per fråga, och — allvarligare — **all** data passerar
egressgränsen innan den kastas. I2 säger att det som aldrig hämtas inte kan
läcka; utan `$select` hämtas allt.

Detta är den enskilt mest värdefulla åtgärden i hela underlaget.

### T2 — Ingen deltahämtning

`GET /customerinvoices` har parametern `modifiedSinceUtc`. Den används inte.
Utan den kan ingen inkrementell synk byggas, och varje fråga är en fullhämtning.

### T3 — Ingen hantering av 429 / rate limit

`spiris_klient._anrop_med_refresh` behandlar bara `401`. Spiris rate-limitar
och svarar `429` med `Retry-After`. I dag blir ett `429` ett vanligt
`SpirisKlientFel` — verktyget säger "Spiris avvisade förfrågan" och
användaren har ingen väg framåt utom att gissa. Fail-closed är rätt, men en
respekterad `Retry-After` med **en** omkörning är både rätt och artigt mot
leverantören.

### T4 — Klienten kan inte hämta binärt innehåll

Alla `…/pdf` och `…/print`-endpoints returnerar filer, inte JSON.
`_hamta_json` fail-closar på allt som inte är JSON. Det stänger ute
fakturakopior, orderutskrifter och nedladdning av bilagor — det underlag en
revisor faktiskt vill se.

### T5 — MCP-protokollets övriga ytor är helt oanvända

Servern exponerar 85 `@mcp.tool` och **noll** `@mcp.resource`, **noll**
`@mcp.prompt`. Frågan i uppdraget var vad *en MCP* kan hantera — resurser och
prompter är två tredjedelar av protokollet.

- **Resurser** passar det som är stabilt och adresserbart: kontoplanen,
  räkenskapsåren, företagsinfo. En resurs kan läsas utan att förbruka ett
  verktygsanrop och kan cachas av klienten.
- **Prompter** passar de återkommande arbetsgångarna: "stäm av banken",
  "granska momsperioden", "förbered bokslutsposter". I dag måste användaren
  kunna namnen på 85 verktyg.

### T6 — Inget verktyg kan sidbryta sitt eget svar

Ett verktyg returnerar hela resultatet i ett svar. `spiris_kontotransaktioner`
på ett stort konto kan spränga kontextfönstret hos klienten. Det finns ingen
`offset`/`limit` i verktygskontraktet och ingen indikation på trunkering.

---

## 5. Funktionella luckor per domän

Bilagan i avsnitt 9 listar samtliga 157. Här står de som **betyder något**.

### 5.1 Utkastvägen är halv — högst prioritet

sie-mcp skapar utkast i Spiris men kan inte göra något mer med dem:

| Saknas | Följd |
|---|---|
| `POST /voucherdrafts/{id}/convert` | Ett verifikatutkast kan aldrig bokföras |
| `POST /customerinvoicedrafts/{id}/convert` | Ett fakturautkast kan aldrig bli faktura |
| `POST /supplierinvoicedrafts/{id}/convert` | Samma för leverantörsfaktura |
| `PUT /voucherdrafts/{id}`, `PUT /customerinvoicedrafts/{id}`, `PUT /supplierinvoicedrafts/{id}` | Ett utkast med fel kan inte rättas — bara skapas om |
| `DELETE` på samtliga tre | Ett felaktigt utkast blir kvar i Spiris för alltid |
| `GET /voucherdrafts/{id}`, `GET /customerinvoicedrafts/{id}`, `GET /supplierinvoicedrafts/{id}` | Ett enskilt utkast kan inte läsas tillbaka för granskning |

Notera att detta **inte** bryter mot I4. Konverteringen är precis lika
skrivande som skapandet, och går samma väg: MCP lägger ett `forbered_*`-förslag
i den lokala kön, människan godkänner i Streamlit, `utfor_utkast` gör anropet.
Skillnaden mot i dag är bara att förslaget får finnas.

Sandboxprovet 2026-08-06 kunde inte pröva Steg 4 fullt ut just för att köerna
var tomma. Nu finns en verifierad `POST /voucherdrafts` att bygga vidare från.

### 5.2 Bilagor och underlag — saknas helt

`/attachments` (GET, POST, DELETE), `/attachmentlinks` (POST, DELETE) och
`/salesdocumentattachments` (13 operationer) är obefintliga i sie-mcp.

Det här är en principiell lucka, inte en bekvämlighetslucka. En
verifikation utan sitt underlag är inte granskningsbar. Ett verktyg som ska
"efterlikna revisionsanalys" och aldrig kan se kvittot bakom en post gör en
halv bedömning. `GET /attachments` med `includeMatched` visar dessutom
**omatchade** underlag — kvitton som ligger och väntar på att bokföras, vilket
är exakt den lista en redovisningskonsult börjar sin dag med.

Kräver T4 (binärhämtning) för själva filen, men listan och kopplingarna är
JSON och kan byggas först.

### 5.3 Periodiseringar — saknas helt

`/allocationperiods` (GET, POST, PUT) och
`DELETE /supplierinvoicedrafts/{id}/allocationperiods`.

Periodisering är kärnan i varje bokslut. Utan den kan sie-mcp läsa ett resultat
men aldrig se eller föreslå den justering som gör resultatet rätt. Läsvägen
(GET) är dessutom ren analysnytta och bryter ingenting.

### 5.4 Ingående balanser och räkenskapsårshantering

`GET/PUT /fiscalyears/openingbalances`, `POST /fiscalyears`,
`GET/PUT /fiscalyears/{id}`.

`GET openingbalances` är den enda vägen till ingående balans utan att gå
omvägen via SIE4-export. Det påverkar balansrapportens riktighet direkt.

### 5.5 Enskilda dokument går inte att slå upp

Mönstret återkommer i hela API:t: listorna är täckta, uppslagen är det inte.
`GET /customerinvoices/{id}`, `/supplierinvoices/{id}`, `/orders/{id}`,
`/quotes/{id}`, `/suppliers/{id}`, `/projects/{id}`, `/articles/{id}`,
`/vatreports/{id}`, `/vouchers/{fy}/{id}`, `/customerledgeritems/{id}`.

I dag måste sie-mcp hämta **hela listan** för att titta på ett dokument —
samma egressproblem som T1, i miniatyr, och det gäller varje gång en AI vill
följa upp en enskild post den just sett.

### 5.6 Kontoplansunderhåll

`GET /accounts`, `GET /accounts/standardaccounts`,
`GET/PUT /accounts/{fy}/{kontonr}`, `POST /accounts`.

`granska_kontotyper` finns redan som verktyg för SIE-filer. Motsvarigheten mot
Spiris kan inte föreslå att ett felaktigt konto rättas — bara konstatera felet.

### 5.7 Kundreskontraposter direkt

`GET/POST /customerledgeritems`, `POST
/customerledgeritems/customerledgeritemswithvoucher`.

I dag byggs kundreskontran av `bygg_kundreskontra_rader` ur fakturalistan.
Det är en härledning; `/customerledgeritems` är källan. Skillnaden märks på
manuella reskontraposter, som härledningen missar.

### 5.8 Över-/underbetalning och betalningsverifikat

`POST /paymentvoucher`, `POST /voucherwithoverunderpayment`,
`GET /voucherwithoverunderpayment/{id}`.

`forbered_betalningsregistrering` finns, men bara för en betalning som
stämmer exakt. Öresdifferenser och delbetalningar — det vanligaste verkliga
fallet — har ingen väg.

### 5.9 Kvittning av kreditfakturor

`GET /supplierinvoices/{id}/offsetcandidates`,
`POST /supplierinvoices/{id}/offset`, `POST /…/offset/undo`.

`offsetcandidates` är läsning och ren analysnytta: den svarar på "vilka
skulder kan den här krediten kvittas mot".

### 5.10 Övrigt av verkligt värde

- `GET /vouchers` — verifikationer över **alla** räkenskapsår i en fråga.
- `GET /inventoryitems` — lagervärde, i dag helt osynligt.
- `GET /currencies/exchangerate` — valutakurs per datum; utan den kan ingen
  valutapost bedömas.
- `GET /discountagreements`, `/salespricelists` — förklarar avvikande
  fakturapriser.
- `GET /notes` — bokförarens egna anteckningar på kunder och dokument.
- `GET /users` — vem som gjort vad; relevant för granskning.
- `PUT /companysettings/accountinglocksettings` — bokföringslås. En
  utkastväg som föreslår "lås perioden fram till 30 juni" är en riktig
  bokslutsåtgärd.
- `GET /webshoporders`, `POST /webshoporders/{id}/convert`.
- `GET /banktransactions/{konto}/{id}` — enskild bankhändelse.

---

## 6. Arkitekturbeslut som styr utbyggnaden

Ingenting nedan är nytt. Det står här för att varje beslut i planen ska gå
att härleda till en redan fattad regel.

**B1 — Skrivning når aldrig MCP direkt.** Var och en av de 72
skrivoperationerna blir antingen ett `forbered_*`-verktyg (förslag i lokal kö)
eller byggs inte alls. `mcp_server/server.py` och `parser/spiris_rag.py` rör
aldrig `skicka`/`uppdatera`/`ta_bort`. (I4)

**B2 — Varje ny läsväg kräver ett explicit fältallowlist-beslut.** Nya
endpoints betyder nya fält. `/attachments`, `/notes` och `/users` bär alla
persondata. Inget fält tas med som inte står i stegspecifikationen. (I2)

**B3 — Varje nytt läsverktyg måste tilldelas en datakategori.** De fem som
finns (`KATEGORI_HUVUDBOK`, `_RESKONTRA`, `_STRUKTUR`, `_MOTPARTSREGISTER`,
`_UTKAST`) räcker inte för bilagor och anteckningar. En sjätte,
`KATEGORI_UNDERLAG`, införs i planens Etapp 4 — annars hamnar fritextinnehåll
i fel logg-kategori i Art. 30-loggen.

**B4 — Fritext maskeras alltid.** `/notes`, bilagors filnamn och
`VoucherText` är människoskriven fritext och behandlas som misstänkt. (I5)

**B5 — Decimal hela vägen.** Nya endpoints med belopp (`openingbalances`,
`allocationperiods`, `salespricelists`, `inventoryitems`) läses genom samma
`parse_float=Decimal`. Ingen ny float-konvertering. (I1)

**B6 — Fältnamn hämtas ur OpenAPI-specen, inte ur gissning, och betraktas
som obekräftade tills ett sandboxprov sagt annat.** Specen har ljugit förr
(`Type` för svenska bolag, saknat `#KTYP` i sie4export). Varje etapp avslutas
med ett rökprov som körs av arkitekten eller användaren. (I6, konstitutionen
§8)

**B7 — Binärhämtning bryter inte fail-closed.** T4 löses med en **ny** metod
`hamta_binart()` i klienten, inte genom att göra `_hamta_json` mildare. Den
befintliga JSON-vägen ska fortsatt fail-closa på allt som inte är JSON.

**B8 — Nya filtreringsparametrar är opt-in.** `hamta_alla` får valfria
`filter`/`select`/`sort`/`pagesize`. Utelämnade beter de sig exakt som i dag —
annars ändras beteendet i 71 befintliga anropsställen på en gång.

---

## 7. Avgränsningar

### 7.1 Ej aktuellt (17 operationer)

`/appstore/status`, `/partnerresourcelinks/*`, `/banks`, `/backgrounds`,
`/warmup_wnkq2yfuzq`, `/messagethreads/*`.

Skälen: partner-/plattformsadministration som hör till en Visma-partner, inte
till en bokföringsanalys (`appstore`, `partnerresourcelinks`); ren
infrastruktur (`warmup`); layoutresurser för utskrift (`backgrounds`);
och intern meddelandefunktion mellan bolag och byrå (`messagethreads`) — den
bär ostrukturerad fritext mellan människor, är den mest personuppgiftstäta
ytan i hela API:t och har inget analytiskt värde. **Bygg den inte.**

### 7.2 Metodlösa sökvägar i specen (41 st)

`/company/info`, `/companymetadata`, `/webhooks`, `/purchasereceipts`,
`/accountingtemplates`, `/reports/monthly`, `/financialoverviewstatistics`,
`/autoinvoice/*`, `/trial*`, `/integrations/amili/*`, `/zapier/*`,
`/statuses`, `/permissions`, `/identityLookup`, m.fl.

De är tomma objekt i OpenAPI-dokumentet. Två grupper är ändå värda att bevaka:

- **`/webhooks`** vore den enda vägen till *händelsestyrd* drift i stället för
  polling. Det är den största teoretiska förmågan som saknas — men den kan
  inte byggas mot en spec utan kontrakt. Skjuts till separat utredning.
- **`/purchasereceipts` / `/purchasereceiptdrafts`** (kvitton/utlägg) och
  `/reports/monthly` har verkligt bokföringsvärde. Kräver att formen fastställs
  mot sandbox innan något skrivs.

Ingen av dem ingår i planen. Att gissa payloadformen mot ett levande
affärssystem är exakt det I6 förbjuder.

### 7.3 Byggt men oexponerat

`hamta_kundfakturor` finns i `spiris_adapter.py:848` och har **inget**
MCP-verktyg. Den skiljer sig från reskontran genom att ta med även betalda
fakturor. Ett `spiris_kundfakturor` är därmed nästan gratis: mappningen är
redan skriven och testad. Planen tar det som första uppgift i Etapp 1 just
för att det är den billigaste verkliga vinsten i hela underlaget.

---

## 8. Målbild efter genomförd plan

| Mått | Nu | Efter |
|---|---|---|
| Täckta operationer | 71 | ca 190 |
| Täckningsgrad av allt anropbart | 31 % | ca 83 % |
| Täckningsgrad av det *relevanta* (228 − 17) | 34 % | ca 90 % |
| MCP-verktyg | 85 | ca 135 |
| MCP-resurser | 0 | 4 |
| MCP-prompter | 0 | 5 |

Utkastvägen blir hel: skapa → läsa → rätta → godkänna → bokföra → radera,
med människans godkännande i varje led som skriver.

Vad som **inte** ändras: MCP exponerar fortfarande noll skrivande verktyg,
allt utflöde går fortfarande genom maskeringen, och varje belopp är
fortfarande `Decimal`.

---

## 9. Bilaga — samtliga 157 otäckta operationer

Klass: **Läs** = kan bli läsverktyg. **Utkast** = skrivande, går bara via
utkastkön. **Ej aktuellt** = byggs inte, se 7.1.

Sammanfattningarna är hämtade ordagrant ur OpenAPI-specen och är därför på
engelska. De är obekräftade tills ett sandboxprov säger annat (B6).

### Accounts

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/accounts` | Get accounts | Läs |
| POST | `/accounts` | Create account | Utkast |
| GET | `/accounts/standardaccounts` | Get standard accounts | Läs |
| GET | `/accounts/{fiscalyearId}/{accountNumber}` | Get single account | Läs |
| PUT | `/accounts/{fiscalyearId}/{accountNumber}` | Replace account | Utkast |

### AllocationPeriods

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/allocationperiods` | Get allocation periods | Läs |
| POST | `/allocationperiods` | Add allocation periods for voucher or supplier invoice | Utkast |
| PUT | `/allocationperiods` | Update allocation periods for voucher or supplier invoice | Utkast |
| GET | `/allocationperiods/{allocationPeriodId}` | Get single allocation period | Läs |

### AppStoreActivationStatus

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/appstore/status` | Get app store activation statuses | Ej aktuellt |
| PUT | `/appstore/status` | Update app store activation status | Ej aktuellt |

### ArticleAccountCodings

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/articleaccountcodings/{articleAccountCodingId}` | Get a specific article account coding | Läs |

### ArticleLabels

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/articlelabels` | Gets all article labels | Läs |
| POST | `/articlelabels` | Create an article label | Utkast |
| DELETE | `/articlelabels/{articleLabelId}` | Delete an article label | Utkast |
| PUT | `/articlelabels/{articleLabelId}` | Replace an article label | Utkast |
| GET | `/articlelabels/{articlelabelid}` | Gets an article label by id | Läs |

### Articles

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/articles/{articleId}` | Gets an article by id | Läs |

### AttachmentLinks

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/attachmentlinks` | Create new links between an existing document and a set of attachments | Utkast |
| DELETE | `/attachmentlinks/{attachmentId}` | Delete the link between an existing document and its attachment | Utkast |

### Attachments

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/attachments` | Get attachments | Läs |
| POST | `/attachments` | Create an attachment | Utkast |
| DELETE | `/attachments/{attachmentId}` | Delete an attachment | Utkast |
| GET | `/attachments/{attachmentId}` | Get a specific attachment based on id | Läs |

### Bank

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/banks` | Get available banks | Ej aktuellt |

### BankAccounts

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/bankaccounts/{bankAccountId}` | Get a bank account | Läs |

### BankTransactions

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/banktransactions/{bankAccountId}/{bankTransactionId}` | Get a specific bank transaction | Läs |

### CompanySettings

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| PUT | `/companysettings` | Replace company settings | Utkast |
| PUT | `/companysettings/accountinglocksettings` | Update accounting lock settings | Utkast |
| PUT | `/companysettings/rotrut` | Update ROT/RUT settings | Utkast |

### CostCenterItems

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/costcenteritems` | Create a single cost center item | Utkast |
| PUT | `/costcenteritems/{costCenterItemId}` | Replace the data in a cost center item | Utkast |
| GET | `/costcenteritems/{itemId}` | Get a specific cost center item | Läs |

### CostCenters

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| PUT | `/costcenters/{id}` | Update a cost center | Utkast |

### Countries

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/countries/{countrycode}` | Get a specific country | Läs |

### Currencies

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/currencies/exchangerate` | Get currency exchange rate | Läs |

### CustomerInvoiceDrafts

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| DELETE | `/customerinvoicedrafts/{customerInvoiceDraftId}` | Delete a customer invoice draft | Utkast |
| PUT | `/customerinvoicedrafts/{customerInvoiceDraftId}` | Replace the data in a customer invoice draft | Utkast |
| POST | `/customerinvoicedrafts/{customerInvoiceDraftId}/convert` | Convert a CustomerInvoiceDraft to a CustomerInvoice | Utkast |
| GET | `/customerinvoicedrafts/{invoiceDraftId}` | Get a customer invoice draft by id | Läs |

### CustomerInvoices

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/customerinvoices/{invoiceId}` | Gets a customer invoice with a specific id | Läs |
| GET | `/customerinvoices/{invoiceId}/pdf` | Gets a customer invoice in Portable Document Format (PDF) | Läs |
| GET | `/customerinvoices/{invoiceId}/print` | Get a pdf file for an invoice | Läs |

### CustomerLabels

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/customerlabels` | Gets all customer labels | Läs |
| POST | `/customerlabels` | Create a customer label | Utkast |
| DELETE | `/customerlabels/{customerlabelid}` | Delete a customer label | Utkast |
| GET | `/customerlabels/{customerlabelid}` | Gets a customer label by id | Läs |
| PUT | `/customerlabels/{customerlabelid}` | Replace a customer label | Utkast |

### CustomerLedgerItems

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/customerledgeritems` | Get customer ledger items | Läs |
| POST | `/customerledgeritems` | Create a customer ledger item | Utkast |
| POST | `/customerledgeritems/customerledgeritemswithvoucher` | Create a customer ledger item with voucher | Utkast |
| GET | `/customerledgeritems/{customerLedgerItemId}` | Get a customer ledger item | Läs |

### DeliveryMethods

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/deliverymethods` | Create a delivery method | Utkast |
| GET | `/deliverymethods/{deliveryMethodId}` | Get a specific delivery method based on id | Läs |

### DeliveryTerms

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/deliveryterms` | Create a delivery term | Utkast |
| GET | `/deliveryterms/{deliveryTermId}` | Get a specific delivery term based on id | Läs |

### DiscountAgreements

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/discountagreements` | Gets all discount agreements | Läs |
| GET | `/discountagreements/{discountAgreementId}` | Gets a discount agreement by id | Läs |

### Documents

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/backgrounds` | Get all available document backgrounds | Ej aktuellt |
| GET | `/documents/{id}` | Get a document by id | Läs |

### FiscalYears

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/fiscalyears` | Create a fiscal year | Utkast |
| GET | `/fiscalyears/openingbalances` | Get opening balances | Läs |
| PUT | `/fiscalyears/openingbalances` | Update opening balances | Utkast |
| GET | `/fiscalyears/{id}` | Get a fiscal year | Läs |
| PUT | `/fiscalyears/{id}` | Update a fiscal year | Utkast |

### ForeignPaymentCodes

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/foreignpaymentcodes` | Get foreign payment codes | Läs |
| GET | `/foreignpaymentcodes/{foreignpaymentcodeId}` | Get a foreign payment code | Läs |

### InventoryItems

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/inventoryitems` | Get inventory items | Läs |
| GET | `/inventoryitems/{id}` | Get an inventory item | Läs |

### MessageThreads

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/messagethreads` | Get all message threads | Ej aktuellt |
| POST | `/messagethreads` | Create message thread | Ej aktuellt |
| GET | `/messagethreads/messages` | Get all messages | Ej aktuellt |
| GET | `/messagethreads/{messageThreadId}` | Get message thread | Ej aktuellt |
| POST | `/messagethreads/{messageThreadId}` | Reply to message thread | Ej aktuellt |
| PUT | `/messagethreads/{messageThreadId}` | Mark message thread | Ej aktuellt |
| GET | `/messagethreads/{messageThreadId}/messages` | Get message thread messages | Ej aktuellt |

### Notes

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/notes` | Get all notes | Läs |
| POST | `/notes` | Create a new note | Utkast |
| GET | `/notes/{noteId}` | Get a specific note | Läs |
| PUT | `/notes/{noteId}` | Update a note | Utkast |

### Orders

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/orders` | Create an order | Utkast |
| DELETE | `/orders/{id}` | Delete an order | Utkast |
| GET | `/orders/{id}` | Get a specific order based on Id | Läs |
| POST | `/orders/{id}/backorder` | Create a backorder | Utkast |
| POST | `/orders/{id}/converteddrafttoorder` | Convert order draft to order | Utkast |
| GET | `/orders/{id}/deliverynote/print` | Print a delivery note for an order as pdf | Läs |
| GET | `/orders/{id}/print` | Print an order as pdf | Läs |

### PartnerResourceLinks

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/partnerresourcelinks` | Get partner resource links | Ej aktuellt |
| POST | `/partnerresourcelinks` | Create a partner resource link | Ej aktuellt |
| DELETE | `/partnerresourcelinks/{partnerResourceLinkId}` | Delete a partner resource link | Ej aktuellt |
| GET | `/partnerresourcelinks/{partnerResourceLinkId}` | Get a partner resource link | Ej aktuellt |
| PUT | `/partnerresourcelinks/{partnerResourceLinkId}` | Update a partner resource link | Ej aktuellt |

### PaymentVoucher

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/paymentvoucher` | Create a payment voucher | Utkast |

### Projects

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/projects/{id}` | Get a project | Läs |

### QuoteDrafts

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/quotedrafts` | Get all quote drafts | Läs |
| POST | `/quotedrafts` | Create a quote draft | Utkast |
| DELETE | `/quotedrafts/{id}` | Delete a quote draft | Utkast |
| GET | `/quotedrafts/{id}` | Get a specific quote draft based on id | Läs |
| PUT | `/quotedrafts/{id}` | Update a quote draft | Utkast |
| PUT | `/quotedrafts/{id}/convert` | Convert a quote draft to a quote | Utkast |

### Quotes

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/quotes` | Create a quote | Utkast |
| DELETE | `/quotes/{id}` | Delete a quote | Utkast |
| GET | `/quotes/{id}` | Get a specific quote based on id | Läs |
| PUT | `/quotes/{id}` | Update a quote | Utkast |
| POST | `/quotes/{id}/previeworder` | Preview the result of converting a quote to an order | Utkast |
| GET | `/quotes/{id}/print` | Print a quote as pdf | Läs |

### SalesDocumentAttachments

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/salesdocumentattachments` | Get all sales document attachments | Läs |
| POST | `/salesdocumentattachments` | Create sales document attachment | Utkast |
| POST | `/salesdocumentattachments/customerinvoice` | Create sales document attachment for customer invoice | Utkast |
| DELETE | `/salesdocumentattachments/customerinvoice/{customerInvoiceId}/{attachmentId}` | Delete customer invoice attachment | Utkast |
| POST | `/salesdocumentattachments/customerinvoicedraft` | Create sales document attachment for customer invoice draft | Utkast |
| DELETE | `/salesdocumentattachments/customerinvoicedraft/{customerInvoiceDraftId}/{attachmentId}` | Delete customer invoice draft attachment | Utkast |
| POST | `/salesdocumentattachments/order` | Create sales document attachment for order | Utkast |
| DELETE | `/salesdocumentattachments/order/{orderId}/{attachmentId}` | Delete order attachment | Utkast |
| POST | `/salesdocumentattachments/quote` | Create sales document attachment for quote | Utkast |
| DELETE | `/salesdocumentattachments/quote/{quoteId}/{attachmentId}` | Delete quote attachment | Utkast |
| GET | `/salesdocumentattachments/{attachmentId}` | Get sales document attachment information by Id | Läs |
| GET | `/salesdocumentattachments/{attachmentId}.pdf` | Download sales document attachment | Läs |
| DELETE | `/salesdocumentattachments/{customerInvoiceDraftId}/{attachmentId}` | Delete customer invoice draft attachment | Utkast |

### SalesPriceLists

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/salespricelists` | Get sales price lists | Läs |
| POST | `/salespricelists` | Create a sales price list | Utkast |
| GET | `/salespricelists/prices` | Get sales prices | Läs |
| GET | `/salespricelists/prices/{salesPriceListId}` | Get sales prices in a price list | Läs |
| GET | `/salespricelists/prices/{salesPriceListId}/{articleId}` | Get a specific sales price for an article in a price list | Läs |
| DELETE | `/salespricelists/{salesPriceListId}` | Delete a sales price list | Utkast |
| GET | `/salespricelists/{salesPriceListId}` | Get a specific sales price list based on id | Läs |
| PUT | `/salespricelists/{salesPriceListId}` | Update a sales price list | Utkast |
| PUT | `/salespricelists/{salesPriceListId}/prices` | Update article prices in a sales price list | Utkast |

### SupplierInvoiceDrafts

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| DELETE | `/supplierinvoicedrafts/{id}` | Delete a supplier invoice draft | Utkast |
| GET | `/supplierinvoicedrafts/{id}` | Get a supplier invoice draft | Läs |
| PUT | `/supplierinvoicedrafts/{id}` | Update a supplier invoice draft | Utkast |
| DELETE | `/supplierinvoicedrafts/{id}/allocationperiods` | Delete allocation periods for a supplier invoice draft | Utkast |
| POST | `/supplierinvoicedrafts/{id}/convert` | Convert a supplier invoice draft to a supplier invoice | Utkast |

### SupplierInvoices

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/supplierinvoices` | Create a supplier invoice | Utkast |
| POST | `/supplierinvoices/transactionalcosts` | Validate transactional costs for a supplier invoice | Utkast |
| POST | `/supplierinvoices/{creditInvoiceId}/offset` | Create an offset between a credit invoice and one or more debit invoices | Utkast |
| GET | `/supplierinvoices/{creditInvoiceId}/offsetcandidates` | Get available debit invoices that can be offset by a credit invoice | Läs |
| GET | `/supplierinvoices/{id}` | Get a supplier invoice | Läs |
| POST | `/supplierinvoices/{invoiceId}/offset/undo` | Undo an existing offset | Utkast |

### Suppliers

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/suppliers/{id}` | Get a supplier | Läs |

### TermsOfPayment

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/termsofpayments/{id}` | Get a terms of payment based on id | Läs |

### Units

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/units/{id}` | Get unit | Läs |

### Users

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/users` | Get users | Läs |

### VatCode

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/vatcodes/{id}` | Get a vat code by Id | Läs |

### VatReport

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/vatreports/{id}` | Get a vat report by Id | Läs |

### VoucherDrafts

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| DELETE | `/voucherdrafts/{voucherDraftId}` | Delete voucher draft | Utkast |
| GET | `/voucherdrafts/{voucherDraftId}` | Get voucher draft by id | Läs |
| PUT | `/voucherdrafts/{voucherDraftId}` | Update voucher draft | Utkast |
| POST | `/voucherdrafts/{voucherDraftId}/convert` | Convert voucher draft to voucher | Utkast |

### VoucherWithOverunderPayment

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| POST | `/voucherwithoverunderpayment` | Create over/under payment voucher | Utkast |
| GET | `/voucherwithoverunderpayment/{voucherId}` | Get voucher relations | Läs |

### Vouchers

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/vouchers` | Get vouchers | Läs |
| GET | `/vouchers/{fiscalyearId}/{voucherId}` | Get a voucher | Läs |

### Warmup

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/warmup_wnkq2yfuzq` |  | Ej aktuellt |

### WebshopOrders

| Metod | Sökväg | Vad den gör | Klass |
|---|---|---|---|
| GET | `/webshoporders` | Get webshop orders | Läs |
| GET | `/webshoporders/{webshopOrderId}` | Get a specific webshop order | Läs |
| POST | `/webshoporders/{webshopOrderId}/convert` | Convert webshop order to invoice | Utkast |