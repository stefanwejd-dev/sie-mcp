# Dataskydd — DPIA, biträdes- och överföringsdokumentation

> [!CAUTION]
> **DETTA DOKUMENT ÄR EN TEKNISK BESKRIVNING — INTE EN UTFÄSTELSE OM EFTERLEVNAD.**
> `sie-mcp` gör inget anspråk på att uppfylla GDPR, dataskyddslagen, krav på personuppgiftsbiträdesavtal eller någon annan lagstiftning, och lämnar inga garantier om att de beskrivningar som följer är korrekta, fullständiga eller aktuella. Ingenting här är juridisk rådgivning och ingenting här kan åberopas som bevis för att ett lagkrav är uppfyllt.
>
> Dokumentet beskriver hur programvaran är **avsedd** att fungera, som råmaterial för slutanvändarens eget arbete. **Du som slutanvändare ansvarar ensam** för att granska, verifiera, korrigera och komplettera innehållet, för att bedöma om din användning är laglig, och för alla konsekvenser av användningen. Se avsnitt 2.4 för kända begränsningar i maskeringsfunktionen — den får inte förlitas på som ett dataskydd.
>
> `sie-mcp` är fri, lokalt körande programvara (BYOK/BYOA). Upphovsmännen bakom den behandlar inga personuppgifter för din räkning, är varken Personuppgiftsansvarig eller Personuppgiftsbiträde, och har ingen åtkomst till din data eller dina API-nycklar. De bär inget ansvar för din användning. Gällande villkor: [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md) och [LICENSE](file:///LICENSE), som vid motstridighet gäller före detta dokument.

Detta dokument svarar mot granskningens åtgärd 9 ("Skriv DPIA +
biträdes-/överföringsdokumentation för slutanvändare") och sammanfattar hur
sie-mcp förhåller sig till dataskyddsförordningen (EU 2016/679, GDPR) och svensk
särreglering. Det är avsett att kunna lämnas vidare till en slutanvändare
(revisor/redovisningskonsult/organisation) som underlag för dennes eget Art. 30-register och
DPIA.

> **Terminologi (Art. 4(5) + skäl 26):** sie-mcp *pseudonymiserar* — den ersätter
> namn, organisationsnummer, personnummer m.m. med typade tokens (`PERSON_1`,
> `BOLAG_1`, `PERSONNUMMER_1`) och behåller en kodnyckel i minnet. Eftersom
> kodnyckeln existerar är allt som skickas till en AI-leverantör fortfarande
> **personuppgifter** i GDPR:s mening. Kalla det därför **aldrig**
> "anonymisering" i dokumentation eller marknadsföring — det är ett vanligt och
> dyrt misstag.

---

## 1. Roller

| Roll | Vem | Rättslig status |
|---|---|---|
| **Programvaruleverantör / Mjukvaruupphovsman** | **Utvecklarna bakom `sie-mcp`** | Behandlar NOLL personuppgifter. Agerar varken Personuppgiftsansvarig eller Personuppgiftsbiträde enligt GDPR kapitel IV. |
| **Personuppgiftsansvarig** | **Slutanvändarens klient** (bolaget vars bokföring granskas), alternativt slutanvändaren själv för sina egna kunduppgifter | Beslutar om ändamål och medel för behandlingen av bokföringsuppgifterna. |
| **Personuppgiftsbiträde** | **Slutanvändaren** (revisor/konsult/organisation) som driver `sie-mcp` lokalt | Ansvarar fullt ut för att behandlingen sker i enlighet med gällande lag och avtal gentemot klienten. |
| **Underbiträden** | **AI-leverantören** (Anthropic; ev. OpenAI/Google) och **Spiris/Visma** | Kontrakteras direkt av slutanvändaren via BYOK/BYOA-modellen. |

Kedjan personuppgiftsansvarig → biträde → underbiträde (via BYOK) måste dokumenteras av slutanvändaren och täckas av personuppgiftsbiträdesavtal (DPA, Art. 28). Se avsnitt 4 och [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md).

---

## 2. DPIA (konsekvensbedömning, Art. 35)

Systematisk behandling av ekonomiska uppgifter med ny teknik (LLM) för tredje
parts räkning ligger nära tröskeln för obligatorisk DPIA. Att avgöra om en DPIA
krävs, och att i så fall genomföra den, är slutanvändarens eget ansvar. Avsnitten
nedan är underlag att granska och verifiera — inte en genomförd DPIA.

### 2.1 Behandlingens art och ändamål
Granskning/analys av svensk bokföring (SIE4 eller live via Spiris): väsentlighet
(ISA 320/450), kontotypskontroll, semantisk kontomatchning, FP&A-rapporter och
en pedagogisk chatt/agent. AI används för kontomatchning och den pedagogiska
ytan.

### 2.2 Personuppgifter som kan förekomma
Namn, organisationsnummer, personnummer, adresser, telefonnummer, e-post,
bankgiro/IBAN, fastighetsbeteckningar (ROT), samt indirekt identifierande
transaktionstext. Särskilda kategorier (Art. 9) kan avslöjas indirekt
(fackavgift på lön, vårdkostnader, samfundsavgifter) — se 2.5.

### 2.3 Skyddsåtgärder (tekniska)
- **Sekretesslagret (Modul 3)** maskerar före varje AI-anrop:
  - Lager 1: `#FNAMN`/`#ORGNR`/`#ADRESS`/personaldimensioners objektnamn samt
    `#GEN`-signatur och objektnamn utanför personaldimensioner.
  - Lager 2: personnummer **med och utan** separator (regex + datumkontroll +
    Luhn), organisationsnummer i fritext (Luhn + orgnr-form), samt e-post,
    telefon, gatuadress och bankgiro/IBAN.
  - Lager 3a: referenslista över vanliga svenska namn — auto-maskeras (körs
    före 3b).
  - Lager 3b: en delad, deterministisk detektor fångar okända namn i titel-/
    namnform (två till tre ord, med bindestreck och apostrof) **oavsett position
    i strängen** — början, mitten eller slut. En liten, versionsstyrd ekonomisk
    stopplista (BAS-/bokföringsrubriker) begränsar falska positiva. I fritext
    och chatt **blockeras** en osäker träff fail-closed för lokal mänsklig
    granskning innan något skickas externt.
- **Kontonamn (och andra identifierande fält) maskeras** via samma 3b-detektor —
  tokeniserade lokalt — innan de når någon AI-/MCP-väg (analys, chatt, RAG-
  rapporter, MCP-svar). Det råa misstänkta namnet lämnar aldrig appen.
- **Chattmeddelanden pseudonymiseras** (personnummer, maskeringsliggare och
  Lager 3a) innan de skickas; en osäker Lager 3b-träff blockeras fail-closed.
- **ROT-personnummer** samlas in i ett lokalt formulär och når aldrig AI:n.
- **Fail-closed** i varje AI/HTTP-lager; **HITL-godkännande** före varje POST.
- **Kodnyckeln lever bara i minnet**; demaskering sker enbart lokalt.
- **Behandlingslogg** (Art. 30, se 5) över AI-utflöde.
- **PKCE + obligatorisk state-kontroll** i OAuth-inloggningen mot Spiris.

### 2.3.1 Verifierade egress-vägar och kontrollstatus

En egress-inventering har kartlagt varje väg där data kan lämna sie-mcp eller
serialiseras för en extern mottagare (AI-leverantör, MCP-klient, Spiris/Visma,
loggning/filer, dev-verktyg). Sammanfattad kontrollstatus:

| Kategori | Vägar | Kontrollstatus |
|---|---|---|
| AI-leverantör (analys, chatt, agent, modell-listning) | E-01–E-06 | Pseudonymiserat/aggregerat före sändning; fail-closed |
| MCP-verktyg (läsande) | E-07–E-13, E-24–E-32 | Maskerat/aggregerat; blockerade poster uteslutna; statiska fel |
| Spiris/Visma (läsning, OAuth, skrivning) | E-14–E-17 | HITL före varje skrivande anrop; fail-closed |
| Loggning/filer | E-18–E-21 | Lokal behandlingslogg med metadata, utan nyttolast eller personuppgifter; en lokal stderr-restrisk (E-21) |
| Dev-/demoverktyg | E-22, E-23 | E-22 stängd; E-23 lokal restrisk (se nedan) |

Inventeringen är en egen bedömning vid en viss tidpunkt, inte en granskning av
tredje part, och den ska läsas tillsammans med de verifierade luckorna i avsnitt
2.4 — de innebär att data som lämnar datorn kan innehålla personuppgifter i
klartext trots vad tabellen ovan anger. Ingen aktiv egress-väg bedömdes som
kritisk vid inventeringstillfället. Den
separat dokumenterade högrisken med molnsynkade hemligheter, OAuth-token och
krypteringsnycklar kvarstår och blockerar extern kunddrift. Data som lämnar
datorn till en AI- eller MCP-mottagare är **pseudonymiserad** (typade tokens;
kodnyckeln stannar lokalt) — aldrig anonymiserad.

**E-22 (regissörens skärmbilder → AI-leverantör) — Stängd/inaktiverad.** Den
AI-regisserade demoinspelningen skärmdumpade den körande appen och skickade
bilderna till AI-leverantören — en väg där riktig eller lokalt demaskerad
kunddata kunde lämna datorn utan att passera sekretesslagret. Vägen är hårt
avstängd: avbrottet sker fail-closed **före browserstart, före varje skärmbild
och före att någon AI-klient kan instansieras eller anropas**, och gäller även
direktanrop. Ingen override, miljövariabel eller dold väg finns. Kontrollbevis:
`tests/test_regissor_guard.py` (sex tester); commit `67b0591`.

**E-23 (lokal videoinspelning) — lokal restrisk.** Inspelade demovideor sparas
enbart lokalt (ingen extern sändning), men bilden kan innehålla lokalt
demaskerade uppgifter. Sådana inspelningar får **inte delas eller exporteras**
utan en manuell integritetsgranskning.

**Hemligheter, OAuth-token och krypteringsnycklar (R-01 status) — Migrering slutförd, rotation kvarstår.**
Migreringen bort från Google Drive-synkad katalog är slutförd: all state, session och logg lagras numera i `%LOCALAPPDATA%\sie-mcp`. Innan extern kunddrift tillåts kvarstår kravet att **rotera** de nycklar, API-referenser och OAuth-tokens som historiskt låg i den synkade mappen.

**E-24–E-32 (nio nya läsande MCP-vägar, Steg 1).** MCP-serverns läsande yta
utökades från 7 till 16 verktyg (plus `visa_anvandarvillkor`). Ingen ny
egress-KATEGORI tillkom — samtliga går genom `spiris_rag`, omfattas av
villkorsspärren, Art. 30-loggen och sessionsloggen, och bär injektionsnoten.
Två nya datatyper i utflödet:

| Väg | Datatyp | Skydd |
|---|---|---|
| E-24 `spiris_rakenskapsar` | Räkenskapsårs-id och datum | Ingen PII |
| E-25 `spiris_kontoplan` | Kontonummer och kontonamn | Kontonamn pseudonymiserade (delad tokengenerator) |
| E-37 `spiris_artiklar` | Artikelnamn, pris, kontokoppling | Artikelnamn pseudonymiserade (delad tokengenerator) |
| E-26 `spiris_foretagsinfo` | Firmanamn, org.nr | Firmanamn pseudonymiserat (enskild firma kan bära personnamn) |
| E-27 `spiris_kassaflodesanalys` | Aggregat | Inga transaktionsrader |
| E-28 `spiris_dashboard` | Aggregat | Inga transaktionsrader |
| E-29 `spiris_leverantorsreskontra` | **Motpartsuppgifter** | GDPR-tvättad (juridisk person i klartext, fysisk person som pseudonym), fail-closed vid otolkbart org.nr, `maskerad`-flagga följer med |
| E-30 `spiris_kundreskontra` | **Motpartsuppgifter** | Samma som E-29 |
| E-31 `spiris_kundbetalbeteende` | Opaka motpart-id och dagar | Inga namn passerar vägen |
| E-32 `spiris_likviditetsprognos` | Aggregat + motpartsuppgifter | Ärver E-29/E-30:s tvätt; kassasaldo hämtas ur balansrapporten |

Art. 30-loggen skiljer sedan Steg 1 på tre datakategorier
(`huvudboksdata (maskerad)`, `reskontrauppgifter (GDPR-tvättade)`,
`strukturdata`) i stället för att logga allt som huvudboksdata — registret ska
vara riktigt, inte ungefärligt.

**E-33–E-36 (utkastvägen, Steg 2) — förslag som inte utförs.** MCP-servern kan
numera lägga ett *förslag* till skrivning (ny kund, kundfaktura, verifikat) i en
lokal kö via `forbered_kund`, `forbered_kundfaktura`, `forbered_verifikat` samt
läsa den med `kontrollera_utkast`. Ingen av vägarna kontaktar Spiris.

**Detta är ingen egress-väg utåt — men det är en ny personuppgiftsbehandling
på disk, och den viktigaste avvikelsen från övriga lagringsformer i systemet:**

| | Utkastfilerna |
|---|---|
| Plats | `%LOCALAPPDATA%\sie-mcp\state\utkast\` (ACL-härdad, samma som hemligheter) |
| Innehåll | **OMASKERADE verkliga värden** — namn, adresser, belopp, kontonummer |
| Varför omaskerat | Det är exakt den nyttolast som ska POSTas, och människan måste kunna granska den. En maskerad payload vore obrukbar för båda ändamålen. |
| Lagringstid | **24 timmar**, gallras vid appstart oavsett status |
| Integritetsskydd | SHA-256 över kanoniserad nyttolast, verifieras före sändning |

Två konsekvenser som inte får tas bort:

1. **Gallringen omfattar även skickade och avvisade utkast.** Statusen minskar
   inte innehållets känslighet.
2. **`utkast_id` valideras mot ett strikt format** innan det blir ett filnamn.
   Id:t kommer från en MCP-klient, alltså från en AI; utan kontrollen vore
   `kontrollera_utkast` en filläsningsprimitiv.

**Art. 22.** Grinden är projektets rättsliga vägval, inte en bekvämlighet:
förslaget utförs först efter att en människa sett de verkliga uppgifterna och
uttryckligen godkänt dem. MCP-serverns källkod får inte ens referera
skrivfunktionerna (statiskt testat). MCP-protokollets `elicitation` används
medvetet INTE som godkännande — specen tillåter en agentklient att besvara den
automatiskt, och en grind som kan passeras av samma modell som lade förslaget är
ingen grind.

**Revideringsplikt.** Egress-inventeringen ska revideras vid varje ny extern
integration, ny AI-leverantör, ny MCP-väg eller ändrad datatyp som kan lämna
datorn.

### 2.3.2 Lokal lagringsplats för hemligheter och state (Paket B1–C3)

Applikationskoden löser numera alla sökvägar för hemligheter, OAuth-session,
krypterade liggare och loggar centralt via `parser/saker_lagring.py` till en
**per-användare, icke-synkad** katalog — på Windows `%LOCALAPPDATA%\sie-mcp`
(`secrets\`, `state\`, `logs\`), eller en explicit och validerad
`SIE_MCP_DATA_ROOT`. En fail-closed-guard höjer fel **före** läsning/skrivning
för en relativ sökväg, för projekt-/repomappen och alla dess barn, samt för
kända molnsynk-markörer i sökvägen. OAuth-sessionen lagras DPAPI-skyddad (per
Windows-användare); på icke-Windows persisteras ingen session (ingen osäker
fallback), vilket kräver återautentisering.

**Krypteringsomfattning och restrisk (Paket C3):** Fernet-nyckeln (`SIE_MCP_FERNET_KEY` i `secrets/.env`) och de krypterade liggarna (`mask_dict.enc`, `allowlist.enc`, `konteringsminne.enc` i `state/`) ligger under samma per-användare-katalog. Krypteringen av liggarna skyddar effektivt mot oavsiktlig spridning via säkerhetskopior, molnsynk eller loggutdrag. Den skyddar däremot **inte** mot en lokal angripare eller skadlig kod som körs under samma Windows-användarkonto, eftersom nyckeln och datan är samlokaliserade på användarens profil. Detta är ett medvetet arkitekturbeslut för att undvika komplex nyckelhantering, och restrisken är godkänd i denna DPIA.

MCP-serverns Spiris-credentials (`SPIRIS_CLIENT_ID`/`SPIRIS_CLIENT_SECRET`) läses
ur **processmiljön** eller lokal `.env` i `secrets/`, och ska sättas i den terminal/tjänst som
startar servern (se `.env.example`) — aldrig i en Drive-synkad fil.

**R-01 status:** Migreringen till non-synkad profilmapp (`%LOCALAPPDATA%\sie-mcp`) är utförd. Risk **R-01 kvarstår som blockerande (Rotation kvarstår)** för extern kunddrift tills nyckel- och tokenrotation är genomförd.

### 2.4 Kända begränsningar och kvarstående risker

> [!CAUTION]
> **Maskeringsfunktionen är ofullständig och får inte förlitas på som ett dataskydd.**
> Personuppgifter kan nå en extern AI-leverantör **i klartext**, i flera fall utan
> att något blockeras, flaggas eller räknas i `antal_exkluderade` — alltså utan att
> användaren varnas. Uppräkningen nedan är inte uttömmande; okända brister kan finnas.
> Slutanvändaren ansvarar ensam för att bedöma vilken data som sänds och för följderna.

**Åtgärdade sedan säkerhetsgenomgången 2026-08-03** (paket A+B, verifierade
end-to-end genom MCP-verktygen i `tests/test_sekretess_lackprobe.py`):
- **Icke-latinsk skrift:** namn i kyrillisk, grekisk och latinsk skrift med
  diakriter maskeras nu helt (unicode-medvetna teckenklasser). Skriftsystem utan
  versalbegrepp — kinesiska, japanska, koreanska, arabiska, hebreiska,
  thailändska — fångas av lager 3c och får tokentypen `MOTPART`.
- **Latinska diakriter utanför teckenklassen:** gav tidigare PARTIELL maskering
  (`PERSON_1śniewski`). Stängt.
- **Samordningsnummer utan separator** (dag 61–91) identifieras nu.
- **Reskontrans namnkontroll** (`innehaller_kant_personnamn`) är inkopplad i
  `spiris_adapter.py`.
- Dessutom tillkom kortnummer (PAN, Luhn-grindat), utländska telefonnummer och
  stabila pseudonymer per person (genitiv fångas; två personer kan inte längre
  dela token).

Att dessa är stängda är en observation om koden vid en viss tidpunkt, inte en
garanti. Regressionsskyddet ligger i `tests/test_sekretesslager.py` och
`tests/test_sekretess_lackprobe.py`.

**Kända begränsningar som kvarstår:**
- **Art. 9- och Art. 10-attribut maskeras inte.** "Fackavgift", "sjukvård",
  "polisanmäld" passerar tillsammans med en stabil pseudonym. Medveten
  avgränsning — hanteras genom fältminimering och i klientens DPIA, inte genom
  ordlistor.
- **Okänt personnamn med bolagsformssuffix och giltigt org.nr** ("Xerxes Qoolio
  AB") behandlas som juridisk person i reskontran. Lokal `namnreferens.txt` är
  utvägen för den som behöver täcka det.
- **Kortnummer i vissa grupperingar** (Amex 4-6-5) fångas inte; den obrutna
  15-siffriga formen gör det.
- Lager 3b:s deterministiska detektor täcker okända namn i titel-/namnform (två
  till tre ord) oavsett position i strängen, men fångar **inte**: helt VERSALA
  namn ("XERXES QOOLIO"), helt gemena namn ("xerxes qoolio"), initial + efternamn
  ("A. Svensson") eller mononymer/enordsnamn. Detta är dokumenterade, snäva
  restrisker — inget påstått stöd. Dokumentera i klientens DPIA.
- Kombinationen `PERSON_1` + transaktionstext ("medlemsavgift Svenska kyrkan")
  kan indirekt röja särskild kategori (Art. 9). Namnmaskeringen är huvudskyddet.
- `_innehallsfingeravtryck` (`masking_memory`) täcker numera både fritext och strukturfält, vilket säkerställer att ändrad verifikationstext alltid utlöser en ny granskning (tidigare R-08 är stängd).
- Filbaserade MCP-verktyg skyddas av en sökvägsvakt (`_tillaten_siefil`) och kräver explicit tillåtna kataloger via `SIE_MCP_SIE_KATALOGER` (fail-closed).

### 2.5 Art. 9 — särskilda kategorier
Bokföringstext kan avslöja fackligt medlemskap, hälsa eller religion.
Namnmaskeringen är huvudskyddet; restrisken (token + avslöjande transaktionstext)
bör noteras i klientens DPIA.

---

## 3. Dataminimering (Art. 5(1)(c))

Läsvägen är minimerad, men **olika mycket i olika AI-vägar**. Skillnaden är
verifierad mot koden och ska inte skrivas ihop till ett enda påstående — en
tidigare version av detta avsnitt gjorde det och överdrev därmed minimeringen.

| AI-väg | Vad som faktiskt skickas | Verifierat |
|---|---|---|
| **Chatt/agent** (`samtalsflode.bygg_saker_kontext`) | **Enbart aggregerade fakta**: filöversikt, antal, maskerade kontosaldon, väsentlighetstal, ackumuleringsresultat, tvättad reskontra. Verifikationernas fritext utesluts medvetet, trots att den är maskerad. | Ja |
| **Modul 4, kontomatchning** (`kontomatchning.bygg_bunt` → AI-leverantör) | **Maskerad fritext per transaktion**: `transtext`, `vertext`, `text_analyserad`, maskerat kontonamn, kontonummer, belopp och plats (serie/vernr/radindex). Detta är inte aggregat — uppgiften kräver texten för att kunna matcha konto semantiskt. | Ja |
| **MCP-verktygen** | Maskerade/aggregerade svar; blockerade poster utesluts och räknas i `antal_exkluderade`. | Ja |

Gemensamt för alla vägar, verifierat:

- **Rå, omaskerad fritext lämnar aldrig datorn.** Det som Modul 4 skickar har
  passerat sekretesslagret.
- **Blockerade verifikationer utesluts helt.** Ett verifikat med ett olöst
  maskeringsbehov ingår inte i den sändningsbara mängden och når därmed varken
  Modul 4, chatten eller MCP. (Probe: en fil med två verifikat, varav ett med
  okänt namn, gav 1 sändningsbart och 3 registrerade maskeringsbehov.)
- **Reskontran GDPR-tvättas VID EGRESSEN** — juridisk person i klartext, fysisk
  person som stabil pseudonym — med fail-closed klassning: saknat eller
  otolkbart organisationsnummer ger maskering, inte klartext.

  **Gränsen flyttades 2026-08-04 (P0).** Tidigare byttes namnet redan vid
  hämtningen, vilket innebar att även Streamlit-appens lokala vyer visade
  "Fiktiv Kund 3" — uppgifter användaren själv är ansvarig för och ser i sitt
  affärssystem. Maskeringen finns för att skydda **utflödet till en
  AI-leverantör**, inte för att skydda användaren från sin egen bokföring.

  Klassningen (`ska_maskeras`) sätts numera vid hämtningen och följer alltid
  med; själva namnbytet sker i `reskontra_tvatt.maskera_for_egress`, som är det
  ENDA stället i kodbasen där ett motpartsnamn ersätts. Varje utflödesväg
  anropar den själv och litar aldrig på anroparen:

  | Väg | Maskerar |
  |---|---|
  | `spiris_rag.hamta_leverantorsreskontra` / `hamta_kundreskontra_rag` (MCP) | Ja |
  | `spiris_rag.hamta_likviditetsprognos` (motparter i prognosen) | Ja |
  | `samtalsflode.bygg_saker_kontext` (AI-chattens kontext) | Ja |
  | Lokala vyer i `app.py` (snabbvyerna) | Nej — avsiktligt klartext |

  Funktionen är idempotent, och två statiska tester bevakar gränsen åt båda
  håll: att ingen egressväg saknar anropet, och att hämtningen inte återinför
  maskering (`tests/test_egressgransen.py`).

  **De lokala vyerna finns sedan 2026-08-04** (snabbvyerna i Rapporter-fliken:
  utestående, förfallna, åldersanalys, påminnelse-/betalningsförslag). De visar
  riktiga motparts- och kontonamn, räknar uteslutande lokalt och anropar aldrig
  en AI-leverantör — statiskt testat. Ingen ny egress-väg tillkom därmed.
  Slutanvändaren bör ändå notera behandlingen i sitt eget Art. 30-register: en
  skärm som visar kunduppgifter är en behandling, även om ingen data lämnar
  datorn.

  **Typkontrollen i `maskera_for_egress`** använder `type(post).__name__` i
  stället för `isinstance`. Streamlit kan ladda om en modul mellan omkörningar,
  varvid klassidentiteten byts och `isinstance` fallerar för objekt skapade av
  den gamla klassen. Felläget var fail-closed (ett fångat AttributeError, inte
  en läcka), men strängjämförelsen överlever omladdningen.
- **Raderingsfunktioner finns** för de lokala liggarna (`app_config.rensa_config`,
  `tom_maskeringsliggare`, `tom_undantagslista`, `tomt_konteringsminne`,
  `spiris_session.radera_session`, `sessionslogg.rensa_gamla`).

Ingenting av detta är en utfästelse om efterlevnad — se dokumentets inledning.

---

## 4. Personuppgiftsbiträden och tredjelandsöverföring (Art. 28 + Kap. V)

### 4.1 Biträdesavtal (Art. 28)
AI-leverantören blir slutanvändarens **underbiträde**. Slutanvändaren måste teckna
personuppgiftsbiträdesavtal (DPA) direkt med leverantören under sitt eget konto (BYOK — utvecklarna bakom `sie-mcp` är inte avtalspart):
- **Anthropic** erbjuder ett DPA. Kommersiella API-villkor tränar inte modeller
  på inskickad data — bekräfta detta i avtalet.
- Om OpenAI/Google aktiveras framöver krävs motsvarande DPA per leverantör.

### 4.2 Tredjelandsöverföring (Art. 44–49)
API-anropen går till USA. En giltig överföringsmekanism krävs:
- **EU–US Data Privacy Framework**-certifiering hos leverantören, **eller**
- **Standardavtalsklausuler (SCC)** + transfer impact assessment.

Detta bör framgå av slutanvändarens dokumentation och gärna visas i UI:t vid
leverantörsval.

### 4.3 Spiris/Visma

Bokföringssystemet är ett separat underbiträde med eget biträdesavtal, som
slutanvändaren tecknar direkt. Anslutningen sker med slutanvändarens **eget**
utvecklarkonto och egna OAuth-uppgifter (BYOA) — upphovsmännen bakom `sie-mcp`
är inte part. Vismas användningsvillkor (p. 2.3.2) kräver dessutom att den som
använder Spiris API som utvecklare eller ISV aktivt godkänner särskilda
utvecklarvillkor och tillgängliga partneravtal.

**Lagring av OAuth-tokens.** Tokens lagras lokalt i den per-användare,
icke-synkade katalogen `%LOCALAPPDATA%\sie-mcp\secrets\` — samma
fail-closed-guard som övriga hemligheter (se 2.3.2). På Windows skyddas
sessionen med DPAPI, bunden till användarkontot. På andra plattformar
persisteras ingen session alls; det finns ingen osäker fallback, vilket i
stället kräver återautentisering.

> [!IMPORTANT]
> **Rättelse (2026-08-04).** Detta avsnitt påstod tidigare att hemligheterna
> "ligger kvar i den molnsynkade projektmappen enligt uttryckligt beslut". Det
> är inte längre sant och motsade dokumentets eget avsnitt 2.3.2. Migreringen
> bort från den Google Drive-synkade projektmappen är **genomförd**, och
> lagringsvakten avvisar numera fail-closed både projektmappen, dess barn och
> kända molnsynk-markörer (Google Drive, OneDrive, Dropbox).
>
> **Vad som kvarstår:** de nycklar, API-referenser och OAuth-tokens som
> historiskt låg i den synkade mappen är **ännu inte roterade**. R-01 är därför
> fortfarande **blockerande före extern kunddrift** — se `RISKREGISTER.md`.
> Migrering och rotation är två skilda åtgärder, och bara den första är gjord.

---

## 5. Ansvarsskyldighet och register (Art. 30 + 5(2))
sie-mcp för en lokal **behandlingslogg** (`ai_utflodeslogg.jsonl`, gitignorerad)
via `revisionslogg.py`. Varje AI-utflöde loggas med **metadata** — tidpunkt,
mottagare (leverantör + modell), förmåga, datakategorier och maskeringsstatistik
— **aldrig** nyttolasten, fritexten, kodnyckeln eller ett enda personnummer.
Loggen utgör underlag för slutanvändarens Art. 30-register och för
incidentutredning.

---

## 6. Svensk särreglering
Personnummer har förstärkt skydd (dataskyddslagen 3 kap. 10 §). Behandling ska
vara klart motiverad; maskeringen (Lager 2, med och utan separator) är utformad
för att personnummer aldrig ska nå en AI-leverantör.

---

## 7. Checklista för slutanvändaren
- [ ] Läs och acceptera användarvillkoren i [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md).
- [ ] Teckna DPA med Anthropic (och ev. andra AI-leverantörer) under ditt eget konto (BYOK).
- [ ] Säkerställ giltig tredjelandsöverföringsmekanism (DPF/SCC) vid val av molnbaserad AI.
- [ ] Teckna biträdesavtal med Spiris/Visma för bokföringssystemet.
- [ ] För in behandlingen i ditt Art. 30-register (använd utflödesloggen i `%LOCALAPPDATA%\sie-mcp\`).
- [ ] Skriv/uppdatera din DPIA utifrån avsnitt 2 och denna mall.
- [ ] Informera dina klienter (personuppgiftsansvariga) om biträdeskedjan.
- [ ] Beskriv behandlingen som *pseudonymisering*, aldrig *anonymisering*.
- [ ] Överväg att i första hand använda **Ollama (lokal LLM)** där 100 % lokal bearbetning utan tredjelandsöverföring önskas.

---

## 8. Två medvetna arkitekturgränser (omgranskning, kontroll.md)

### 8.1 HITL-granskning görs ALDRIG över MCP
Ett förslag var att exponera MCP-verktyg för att lista och avgöra oavgjorda
maskeringsbehov direkt i en MCP-klient (Claude Desktop/Code), så att en blockerad
verifikation kan godkännas utan att öppna Streamlit-appen.

**Detta implementeras medvetet INTE.** Ett `Maskeringsbehov` bär `misstänkt_text`
— den **råa flaggade strängen** (t.ex. ett okänt namn). Att skicka den till en
MCP-klient innebär att skicka den till en AI-leverantör (MCP-klienten *är*
mottagaren), vilket bryter mot lagrets grundinvariant: *`misstänkt_text` lämnar
aldrig appen* (ARCHITECTURE.md, Modul 3 §5). Ett HITL-steg kräver att en människa
**ser** den misstänkta texten för att bedöma den — och den enda plats där det kan
ske utan att texten når en tredje part är **lokalt** (Streamlit-fliken Åtgärder).

Konsekvens: blockerade verifikationer förblir uteslutna ur MCP-svaren (klienten
ser bara räknaren `antal_exkluderade`), och upplösningen sker i den lokala appen.
Detta är fail-closed **med flit** — inte en lucka. En MCP-klient kan aldrig förmås
att avslöja en oavgjord flaggad sträng.

### 8.2 Skrivvägen bär aldrig maskerad eller AI-genererad text
Demaskering (token → verkligt värde) sker **enbart lokalt vid visning för
användaren**, aldrig i eller inför ett AI-anrop.

Skrivfunktionerna mot Spiris (`skapa_kund`, `skapa_kundfaktura`) bygger sina
payloads uteslutande ur **lokalt inmatade, verkliga värden** — kundnamnet som
användaren själv skrev, konteringen från den lokala granskningen, ROT-uppgifterna
från det lokala formuläret. Ingen maskerad token (`PERSON_1`) och ingen
AI-genererad text flödar in i en POST. En token kan därför aldrig läcka in i
affärssystemet, och ingen demaskering behövs på skrivvägen.

**Invariant för framtida skrivvägar:** om en kommande funktion skulle POSTa text
som härstammar från ett AI-svar måste demaskeringen ske i `spiris_adapter.py`
omedelbart före anropet — aldrig tidigare, aldrig i ett AI-anrop.
