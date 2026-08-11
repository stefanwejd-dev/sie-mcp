# Arkitektur — UI-täckning för sie-mcp:s verktygsyta

**Datum:** 2026-08-11
**Skriven av:** arkitekten (Claude Opus 5)
**Mottagare:** Gemini 3.1 Pro, som utför hantverket — samt den människa som beställer det
**Status:** arkitekturbesluten B1–B14 nedan är fattade och ska inte omprövas av utföraren
**Följs av:** `PLAN_UI_TACKNING.md` (den exekverbara arbetsordern)

---

## 0. Till dig som ska utföra arbetet

Du har troligen aldrig sett det här projektet. Det här avsnittet är den
minsta mängd bakgrund du behöver för att inte göra fel, och du ska läsa det
innan du öppnar en enda kodfil.

### 0.1 Läsordning

1. **Det här dokumentet, i sin helhet.** Särskilt §4 (maskeringsregeln), §5
   (utkastgrinden) och §9 (besluten).
2. `PLAN_UI_TACKNING.md` — arbetsordern. En uppgift i taget.
3. `hantverksbok/00_KONSTITUTION.md` och `hantverksbok/UI_ARKITEKTUR.md` i
   arkivet `_arkiv/sie-mcp-2026-08-09/`. De är projektets grundlag respektive
   UI-lagrets ritning. De gäller fortfarande, ord för ord.
4. `README.md` och `ARCHITECTURE.md` i kodförrådet, som referens.

### 0.2 Vad projektet är

`sie-mcp` läser svensk bokföring — antingen ur en lokal SIE4-fil eller live ur
affärssystemet Visma eAccounting (internt kallat **Spiris**) — och ger både en
människa och en AI-assistent tillgång till den. Det finns **två gränssnitt mot
en delad kärna**:

| Gränssnitt | Fil | Mottagare | Vad det får göra |
|---|---|---|---|
| **Streamlit-appen** | `app.py` → `parser/rum_render.py` | människan vid datorn | läsa **omaskerat**, och **utföra** godkända skrivningar |
| **MCP-servern** | `mcp_server/server.py` | en extern AI (Claude Desktop m.fl.) | läsa **maskerat**, och **föreslå** skrivningar — aldrig utföra dem |

Den bärande principen i hela systemet är att **AI:n föreslår, människan
beslutar**. MCP-servern har noll skrivförmåga: dess källkod refererar inte ens
skrivfunktionerna. Ett förslag hamnar i en lokal kö och utförs först när en
människa har granskat de verkliga uppgifterna i appen och tryckt på en knapp.

### 0.3 Vad uppdraget går ut på

MCP-ytan har vuxit i tre vågor och är i dag **125 verktyg**. Användargränssnittet
har inte följt med. Uppdraget är att stänga gapet: **allt MCP:n kan, ska
människan kunna göra själv i appen — utan att be en AI om det.**

Det är inte kosmetik. Se §7, lucka L7, för varför asymmetrin är ett verkligt
problem och inte en bekvämlighetsfråga.

---

## 1. Svaret på frågan som ställdes

> *Är de funktioner som ingår i MCP:n driftsatta och tillgängliga för
> användaren i användargränssnittet?*

**MCP-servern själv: ja.** Den startar, registrerar alla 125 verktyg, 3
resurser, 1 resursmall och 5 prompter, och är registrerad som MCP-server hos
klienten. Testsviten är grön: **2 394 passerade, 1 hoppad** (`python -m pytest
tests -q`, mätt 2026-08-11).

**I användarens UI: nej, inte i närheten.** Verifierat mot koden:

| Fråga | Utfall |
|---|---|
| Hur många av **56 läsande** verktyg har en yta i appen? | **26 helt eller delvis. 30 saknar yta helt.** |
| Hur många av **29 utkasttyper** kan människan **initiera själv**? | **8 fungerar från början till slut.** 6 har ett formulär som skapar ett utkast som sedan **inte går att verkställa**. 5 har ett formulär som **aldrig ritas ut någonstans**. 10 saknar formulär helt. |
| Fungerar **godkännandevägen**? | **Ja, och den är komplett.** Alla utkasttyper renderas och kan godkännas i rummet Beslut. Grinden håller. |
| Finns det **trasiga** funktioner som ser fungerande ut? | **Ja, åtta stycken.** Se §7 lucka L2 och L3. En av dem, `forbered_offertutkast`, är ett MCP-verktyg som är dödfött sedan Etapp 15 och som ett grönt test döljer. |

**Det som saknas är inte skyddet. Det är ytan.** Samma slutsats som drogs
2026-08-06 (`UI_OMDESIGN_GENOMFORANDE.md` §12.1) gäller fortfarande — och det
är i sig den viktigaste iakttagelsen i det här dokumentet. Se §8.

---

## 2. Historik — hur läget uppstod

Du behöver den här historien för att förstå varför koden ser ut som den gör,
och varför vissa saker som verkar vara förbiseenden i själva verket är
kvarlämnade halvfärdiga etapper.

### Våg 1 (juni–juli 2026) — appen först

Streamlit-appen byggdes först och var **SIE4-filcentrerad**: användaren laddade
upp en fil, den maskerades, och rapporterna räknades fram lokalt ur filen. MCP-
servern var liten (18 anropade endpoints). Spår av detta finns kvar överallt —
flera rum kräver fortfarande en inläst `sie` i sessionen, och `parser/`
innehåller ett tjugotal `build_*.py`/`fix_*.py`-skript som var engångsverktyg
för att generera kod. **De är inte en del av programmet. Rör dem inte.**

### Våg 2 (aug 2026, Steg 1–8) — MCP:n växer förbi appen

Spiris-täckningen byggdes ut kraftigt: 18 endpoints → **85 verktyg**. En
inventering 2026-08-06 (`UI_OMDESIGN_GENOMFORANDE.md` §12) slog fast att UI:t
halkat efter: nio läsförmågor saknade vy, och av 16 utkasttyper gick 2 att
initiera från appen.

### Våg 3 (aug 2026) — UI-etapp 1–4 hämtar ikapp

Ett UI-omdesignsarbete i fyra etapper genomfördes för att stänga det gapet:
rumsmodellen (11 rum i 5 grupper), snabbvyerna, `parser/atgardsformular.py`
och den delade ritfunktionen `rendera_atgardsformular`. **Uppdraget var att
alla 16 utkasttyper skulle gå att initiera från appen.**

Det uppdraget slutfördes aldrig, och — vilket är värre — det *rapporterades*
som slutfört. Se §8.

### Våg 4 (aug 2026, Etapp 8–17) — MCP:n växer förbi appen igen

`PLAN_SPIRIS_ETAPP8.md` genomfördes: periodiseringar, kontoplansunderhåll,
företagsinställningar, ROT/RUT, utkaständring, order/offert, kvittning,
prislistor, rabattavtal, etiketter, tvåsegmentsuppslag. MCP-ytan gick från 85
till **125 verktyg** och antalet utkasttyper från 16 till 29.

Ingen UI-etapp följde. **Det är där vi står nu.** Gapet har alltså uppstått
två gånger av exakt samma orsak, och det är den orsaken §8 handlar om.

---

## 3. Systemets anatomi

```
                    ┌─────────────────────────┐
                    │  Spiris / Visma eAcc.   │  (externt affärssystem)
                    └───────────┬─────────────┘
                                │ HTTPS, OAuth (BYOK)
                    ┌───────────┴─────────────┐
                    │  parser/spiris_klient   │  transport, retry, 429
                    └───────────┬─────────────┘
                                │
                    ┌───────────┴─────────────┐
                    │  parser/spiris_adapter  │  OMASKERAD domändata
                    └─────┬───────────────┬───┘  + alla skrivfunktioner
                          │               │
        ┌─────────────────┘               └──────────────────┐
        │                                                    │
┌───────┴────────┐                                  ┌────────┴─────────┐
│ parser/        │  MASKERAD, fail-closed           │ parser/          │
│ spiris_rag.py  │  ← läses av MCP-servern          │ rum_render.py    │ ← appen
└───────┬────────┘                                  └────────┬─────────┘
        │                                                    │
┌───────┴────────┐                                  ┌────────┴─────────┐
│ mcp_server/    │  125 verktyg, INGEN skrivförmåga  │ app.py          │
│ server.py      │                                   │ 11 rum, 5 grupper│
└───────┬────────┘                                  └────────┬─────────┘
        │                                                    │
        │  forbered_* lägger ett förslag ──►  parser/utkast.py  ◄── formulär i rummen
        │                                     (lokal kö på disk)
        │                                              │
        │                             människan godkänner i rummet Beslut
        │                                              │
        └──────────────────────────────►  spiris_adapter.utfor_utkast()  ──► Spiris
                                          (den ENDA skrivvägen som finns)
```

### Rummen i appen (`app.py`, `st.navigation`)

| Grupp | Rum | Renderas av |
|---|---|---|
| Dagen | 🏠 Översikt · ⚖️ Beslut | `rendera_oversikt`, `rendera_beslut` |
| Pengar | 📥 Pengar in · 📤 Pengar ut · 🏦 Bank | `rendera_pengar_in/_ut/_bank` |
| Bokföring | 📚 Böckerna · 📇 Register | `rendera_bockerna`, `rendera_register` |
| Analys | 📊 Rapporter · 📈 Investeringskalkyl | `rendera_rapporter`, `rendera_investeringskalkyl` |
| AI-chattar | 💬 Företagsdata · ⚖️ Juridik & Skatt | `rendera_foretags_chatt`, `rendera_juridik` |
| Data | 🔄 Data in/ut | `rendera_data` |

### Lagren i UI:t — och var du får skriva kod

```
app.py                      st.navigation, sidregistrering. Håll den kort.
 └ parser/rum/*.py          DEKLARATION av rum. Ingen Streamlit-kod.
 └ parser/rum_render.py     RITNING. En rendera_*-funktion per rum. All Streamlit bor här.
     └ parser/vy_modell.py     KONTRAKT: Vy, Snabbvyresultat, Sektion, Niva. Aldrig Streamlit.
     └ parser/snabbvyer.py     RENA VYBYGGARE: Vydata -> Snabbvyresultat. Aldrig Streamlit, aldrig I/O.
     └ parser/snabbvy_render.py  ritar en Snabbvy med Streamlit.
     └ parser/atgardsformular.py DEKLARATION av åtgärdsformulär. Aldrig Streamlit.
     └ parser/app_tillstand.py   laddar data in i st.session_state.
```

**Den bärande primitiven är att en vy är en ren funktion `Vydata →
Snabbvyresultat`.** Det är därför vyerna går att enhetstesta utan att starta
Streamlit, och det är därför du aldrig lägger affärslogik i ritlagret.

---

## 4. Den regel som är lättast att få katastrofalt fel

**Appen visar OMASKERAD data. MCP-servern visar MASKERAD.**

Det låter bakvänt tills man ser varför:

| Väg | Mottagare | Data |
|---|---|---|
| `mcp_server/server.py` → `spiris_rag` → adapter | en extern AI | **maskerad**, fältallowlistad, fail-closed |
| `app.py` → `rum_render` → **`spiris_adapter` direkt** | människan vid datorn | **omaskerad**, verkliga värden |

Människan **måste** se verkliga värden: hon ska granska en faktura mot sitt
eget underlag och godkänna att den skickas till en verklig mottagare. En
maskerad godkännandevy vore meningslös och farlig.

### Vad det betyder konkret för dig

- `parser/rum_render.py` **får** importera från `spiris_adapter`. Det gör den
  redan (`utfor_utkast`, `hamta_granskad_mottagare`, `skapa_kund`).
- `mcp_server/server.py` får **ALDRIG** importera `spiris_adapter`. Bevakat av
  `test_mcp_servern_gar_aldrig_forbi_spiris_rag`. Rör inte det.
- `parser/spiris_rag.py` får **aldrig** importera en skrivfunktion. Bevakat av
  samma AST-test.
- **UI:t får aldrig hämta data via `spiris_rag`.** Det är den maskerade,
  fail-closed vägen: den byter ut motpartsnamn mot pseudonymer och *utesluter
  helt* verifikationer med olösta maskeringsbehov. En människa som fattar
  beslut på den datan fattar beslut på ett ofullständigt underlag utan att veta
  om det. Se beslut **B4**.

Bryter du någon av de fyra blir sviten röd. Det är avsiktligt.

---

## 5. Utkastgrinden — hela poängen med systemet

Läs `parser/utkast.py`:s modul-docstring. Den är kort och den förklarar allt.
Sammanfattat:

```
  AI:n via MCP  ──┐
                  ├──►  utkast.skapa(typ, nyttolast, sammanfattning)
  Formulär i rum ─┘         │   lokal kö på disk, SHA-256-bunden nyttolast
                            ▼
                    rummet Beslut  ──►  människan ser VERKLIGA värden
                            │
                            │  "✅ Godkänn och skicka"
                            ▼
                    utkast.bekrafta_for_sandning()   fyra fail-closed kontroller
                            ▼
                    spiris_adapter.utfor_utkast()    ──►  Spiris
```

Fyra egenskaper du aldrig får bygga bort:

1. **Hashbindningen.** `nyttolast_hash` är SHA-256 över den kanoniserade
   nyttolasten och räknas om vid godkännandet. Det människan såg är exakt det
   som skickas.
2. **24-timmarsgränsen.** Underlaget i Spiris kan ha ändrats. Ett utgånget
   utkast kan inte godkännas, bara tas bort.
3. **Mottagargrinden.** För `UTATRIKTADE_TYPER` (mejl till tredje man) hämtas
   adressen lokalt, visas för människan, och skickas till `utfor_utkast` som
   `granskad_mottagare`. AI:n kan per konstruktion aldrig se den.
4. **Destinationsvalet.** För `verifikat` och `kundfaktura` väljer människan
   mellan utkast i Spiris (återkalleligt, standard) och direktbokföring.

**En användarinitierad åtgärd och en AI-föreslagen går genom exakt samma väg.**
Bygg aldrig en genväg förbi Beslut — inte ens för en "harmlös" åtgärd, inte ens
med en extra bekräftelseruta. Det finns ingen sådan åtgärd i listan.

MCP-protokollets `elicitation` används medvetet **inte** som godkännande:
specen tillåter en agentklient att besvara den automatiskt, och en grind som kan
passeras av samma modell som lade förslaget är ingen grind. Den används bara som
tidig sammanfattning, med asymmetrisk verkan (ett avböjande stoppar; ett
accepterande godkänner ingenting).

---

## 6. Vad som ÄR driftsatt och fungerar

Det här är sant och ska inte byggas om. Verifierat 2026-08-11.

**MCP-servern.** 125 verktyg (56 läsande, 31 föreslående, 1 villkorsvisning, 37
domänalias), 3 resurser, 1 resursmall, 5 prompter. `python count_tools.py`
bekräftar. `tests/test_mcp_startblock.py` bevakar att allt registreras.

**Godkännandevägen.** `rum_render.rendera_beslut` är **generisk**: den ritar
`u.sammanfattning` för vilken utkasttyp som helst, visar destinationsvalet och
mottagaren där det krävs, och anropar `utfor_utkast`. Alla 29 typer i
`utkast.GILTIGA_TYPER` har en gren i `utfor_utkast`. Rummet ligger dessutom
medvetet **före** `sie`-kontrollen, så en MCP-användare som aldrig laddat en fil
ändå kan granska sina utkast.

**Villkorsspärren.** Programvaran är spärrad tills villkoren godkänts av en
människa på datorn. Godkännandet kan inte lämnas via MCP.

**De rum som finns.** Översikt, Beslut, Pengar in, Pengar ut, Bank, Böckerna,
Register, Rapporter, Investeringskalkyl, två AI-chattrum och Data in/ut, med
snabbvyer, härkomstmärken och tomma lägen enligt UI-arkitekturen.

**Spiris-anslutningen.** OAuth i Data-rummet, räkenskapsårsväljare, hämtning av
SIE4-ögonblicksbild, reskontror och FP&A-dashboard, samt SIE4-export.

---

## 7. Luckorna

Sju luckor, L1–L7. Var och en är verifierad mot koden — kommandona för att
återskapa verifieringen står i bilaga C.

### L1 — `forbered_offertutkast` är dödfött (MCP-sidan, inte UI:t)

`utkast.GILTIGA_TYPER` innehåller **29** typer. `"offertutkast"` är **inte** en
av dem, men `mcp_server/server.py:forbered_offertutkast` anropar
`utkast.skapa("offertutkast", …)`. Varje anrop höjer alltså
`UtkastFel: Okänd utkasttyp: 'offertutkast'`, fångas av
`_kor_utkastverktyg`:s breda `except`, och returnerar
`{"utkast_id": None, "utfort": False, "info": "Kunde inte skapa utkastet…"}`.

`utfor_utkast` har en fullständig, testad gren för `"offertutkast"` som aldrig
kan nås. Verktyget har varit trasigt sedan Etapp 15.

**Varför sviten är grön:** `tests/test_etapp15_order_offert.py::test_forbered_offertutkast_ratt_payload`
hävdar `"bekraftelse" in res or "utkast_id" in res or "utkast" in res`.
Felsvaret *innehåller* nyckeln `utkast_id` (med värdet `None`). Testet passerar
på ett totalt haveri.

### L2 — Sju formulär bygger en nyttolast som `utfor_utkast` inte kan verkställa

`parser/atgardsformular.py` deklarerar 19 formulär. För sju av dem stämmer inte
nycklarna i `bygg_nyttolast` med dem `utfor_utkast` läser. Utkastet skapas,
hamnar i Beslut, ser rätt ut — och havererar när människan trycker på knappen.

| Utkasttyp | Formuläret ger | `utfor_utkast` läser | Följd |
|---|---|---|---|
| `betalningsregistrering` | `bankkonto` | `bankkonto_id` | `KeyError` vid godkännande |
| `leverantorsbetalning` | `bankkonto` | `bankkonto_id` | `KeyError` |
| `saljdokumentutskick` | `nummer_eller_id` | `nummer` | `KeyError` |
| `saljdokumentatgard` | `nummer_eller_id` | `nummer` | `KeyError` |
| `leverantorsfakturautkast` | `leverantor`, `datum`, `kreditflagga` | `leverantor_id`, `fakturadatum`, `kreditfaktura` | `KeyError` på id; datum och kreditflagga tappas **tyst** |
| `utkastandring` | *(inget)* | `andringar` | `KeyError` |
| `periodisering` | `kopplingspar` (en sträng) | ett av paren `VoucherId`+`VoucherRow`, `SupplierInvoiceId`+`SupplierInvoiceRow`, `SupplierInvoiceDraftId`+`SupplierInvoiceDraftRow` | `ValueError: exakt ett kopplingspar krävs` |

Dessutom `sie4import`: formuläret erbjuder fyra kryssrutor
(`skriv_over_saldon`, `tillat_obrukade_konton`, `ignorera_varningsflaggor`,
`invertera_tecken_pa_resultat`) som **ingen läser**. `utfor_utkast` läser
`ingaende_balans`, `kontonamn`, `mappa_konton`, `arsavslut`. En import via
appen körs alltså alltid med alla flaggor avstängda, samtidigt som användaren
tror att hon styrt dem. (MCP-vägens `forbered_sie4import` sätter rätt nycklar.
Det är bara formuläret som är fel.)

### L3 — Två formulär kraschar innan de hinner skapa något

| Fel | Plats | Följd |
|---|---|---|
| `json` importeras lokalt i två funktioner men används globalt i en tredje | `atgardsformular.py:513` | `NameError: name 'json' is not defined` i `BETALNINGSVERIFIKAT.bygg_nyttolast` |
| `from sie_parser import parse_sie4` — modulen heter `sie4_parser` | `atgardsformular.py:_sie4import_sammanfattning` | `ModuleNotFoundError` varje gång någon försöker skapa ett SIE4-importutkast från appen |

Fälttyperna `"decimal"` och `"heltal"` i `PERIODISERING` finns dessutom inte i
`rendera_atgardsformular`:s renderare (som kan `text`, `tal`, `datum`, `kryss`,
`val`). Fälten ritas aldrig ut, och den obligatoriska-fält-kontrollen slår då
alltid till.

### L4 — Fem formulär ritas aldrig ut någonstans

`ALLA_FORMULAR` har 19 poster. `rum_render.py` importerar 14 av dem. Dessa fem
existerar bara som död kod:

`betalningsverifikat` · `periodisering` · `utkastandring` ·
`utkastborttagning` · `utkastbokforing`

### L5 — Tio utkasttyper saknar formulär helt

`kund` · `kundfaktura` · `kvittning` · `underlagskoppling` · `konto` ·
`kontoandring` · `periodiseringsandring` · `periodiseringsborttagning` ·
`bokforingslas` · `rotrut`

`kund` och `kundfaktura` är ett specialfall: de **har** ett fullständigt,
välskrivet flöde — `rum_render._rendera_fakturautkast_formular` (rad 84) och
`_rendera_fakturautkast` (rad 147), tillsammans ~340 rader med kundsökning,
ROT-fält, byggmomsgrind och granskningsvy. **Ingen rum-funktion anropar
`_rendera_fakturautkast`.** Flödet blev föräldralöst i rumsomdesignen.

Det gör mer skada än att bara vara död kod: `parser/assistent.py` (rad 264 och
271) sätter `st.session_state.aktivt_fakturautkast` när AI-assistenten i rummet
Företagsdata anropar sina verktyg `skapa_kund`/`skapa_kundfaktura`, och kör
`st.rerun()`. Ingenting ritar ut tillståndet. **Användaren ber assistenten
skapa en faktura, sidan laddas om, och ingenting händer.**

#### Nettoresultatet av L2–L5

Av 29 utkasttyper fungerar **8** hela vägen från appens formulär till Spiris:
`verifikat`, `fakturautskick`, `betalningspaminnelse`, `makulering`,
`efakturautskick`, `attest`, `masterdataandring`, `masterdataborttagning`.

### L6 — Trettio av 56 läsande verktyg saknar yta i appen

| Domän | MCP-verktyg utan någon vy i appen |
|---|---|
| Huvudbok | `spiris_ingaende_balans`, `spiris_kontotransaktioner`, `spiris_verifikationer_alla`, `spiris_verifikation`, `spiris_kontosaldo`, `spiris_kontoplan_alla` |
| Periodisering | `spiris_periodiseringar` |
| Moms | `spiris_momsrapporter`, `spiris_momskoder` |
| Säljdokument | `spiris_order`, `spiris_offerter`, `spiris_offertutkast` |
| Reskontra | `spiris_kundreskontraposter`, `spiris_kvittningskandidater` |
| Underlag | `spiris_underlag`, `spiris_hamta_underlag` |
| Masterdata | `spiris_prislistor`, `spiris_rabattavtal`, `spiris_etiketter`, `spiris_anlaggningstillgangar` |
| Företag | `spiris_foretagsinfo`, `spiris_anvandare`, `spiris_bokforingslas`, `spiris_valutakurs` |
| Bank | `spiris_bankhandelse` (enskild) |
| Generellt | `spiris_hamta_ett` |
| Rapport | `spiris_kassaflodesanalys`, `spiris_resultatrapport`, `spiris_balansrapport` (finns som FP&A-vy, men räknad ur SIE-ögonblicksbilden — inte live ur Spiris) |

**En nyans som spelar roll:** flera av de vyer som *finns* i Böckerna
(kontosaldon, verifikationer, momsöversikt) räknas fram ur den SIE4-
ögonblicksbild som hämtades när användaren kopplade upp sig, inte live ur
Spiris. Det är inte fel — men vyn måste säga det med sitt härkomstmärke, och i
dag gör inte alla det. Se beslut **B10**.

En känd följd: Spiris SIE4-export saknar `#KTYP`. `granska_kontotyper` och
snabbvyn Kontotypavvikelser blir därför tysta i Spiris-läge, eftersom
`kontotyp_vakt` bara bedömer konton där `konto.typ is not None`. Vyn ser grön
ut fast den inte har tittat. Se **B11**.

### L7 — Asymmetrin: initiativet ligger hos AI:n

Sammanräknat betyder L2–L5 att en användare som vill periodisera en kostnad,
kvitta en kreditfaktura, lägga upp ett konto, flytta bokföringslåset eller
koppla ett underlag **måste be AI-assistenten göra det**. Hon kan inte göra det
själv.

Det drar åt fel håll mot `RISKREGISTER.md` **R-13**: om varje åtgärd i
praktiken måste initieras av AI:n blir människans roll att godkänna det AI:n
föreslagit, inte att styra. Grinden håller — men initiativet har flyttat.
*(Shneiderman 7: användaren ska känna kontroll, inte reagera.)*

Detta är uppdragets egentliga mål. Allt annat är medel.

---

## 8. Rotorsaken — och varför den är viktigare än luckorna

Gapet har uppstått två gånger av samma orsak, och det kommer att uppstå en
tredje gång om bara luckorna lagas. **Rotorsaken är att de metatester som skulle
ha fångat driften försvagades i stället för att uppfyllas.**

### 8.1 Metatestet med undantagslistan

`hantverksbok/UI_ETAPP_3_atgardsinitiering.md` beställde uttryckligen:

> Varje `Atgardsformular.utkasttyp` måste finnas i `utkast.GILTIGA_TYPER`, och
> varje typ i `GILTIGA_TYPER` utom `kund` och `kundfaktura` måste ha ett
> formulär. **Glider de isär blir en åtgärd oåtkomlig utan att något går
> sönder.**

Testet skrevs — `tests/test_atgardsformular.py::test_metatest_at_bada_hallen` —
men fick en undantagsmängd som växte varje gång en ny utkasttyp landade:

```python
undantagna = {"kund", "kundfaktura", "underlagskoppling",
              "periodiseringsandring", "periodiseringsborttagning",
              "konto", "kontoandring", "bokforingslas", "rotrut", "kvittning"}
```

Det är exakt de tio typerna i lucka L5. Testet skyddar alltså inte mot
någonting — det dokumenterar gapet och kallar det godkänt. Konstitutionens
regel *"du ändrar aldrig ett befintligt test för att få det grönt"* bröts, en
typ i taget.

### 8.2 Kontraktstestet som aldrig skrevs

Samma dokument beställde:

> **Tester (18):** ett per formulär som prövar att `bygg_nyttolast` producerar
> **de nycklar `utfor_utkast` läser**.

De 18 testerna finns, men inte ett enda av dem jämför mot `utfor_utkast`. De
hävdar saker som `assert "fakturanummer" in res`. Därför är alla sju
missmatchningarna i L2 osedda i en grön svit.

### 8.3 Den svaga assertionen

`test_forbered_offertutkast_ratt_payload` accepterar tre olika nycklar med
`or`, varav en finns i **felsvaret**. Ett fullständigt haveri passerar.

### 8.4 Slutsatsen

Enhetstester som mockar bort motparten kan inte se att två lager talar olika
språk. Det som behövs är **kontraktstester som härleder kravet ur den ena sidan
och prövar den andra mot det**, utan en handskriven lista som kan urholkas.
Etapp U2 i planen bygger tre sådana. **De ska byggas före det mesta av det nya
— annars byggs nästa gap in i samma stund som det här stängs.**

---

## 9. Arkitekturbeslut

Fattade. Ompröva dem inte; om något av dem verkar omöjligt, stanna och fråga.

**B1 — Ingen genväg förbi Beslut.** Varje ny åtgärd i UI:t skapar ett utkast
via `utkast.skapa` och ingenting annat. Ritfunktionen anropar aldrig
`utfor_utkast`. Bevakat av befintligt test; utvidga det, ta aldrig bort det.

**B2 — Åtgärden bor där data visas.** En "Attestera"-knapp hör hemma på
leverantörsfakturaraden, inte i en meny eller ett åtgärdsrum. Varje rum har en
`st.expander("➕ Ny åtgärd")` under sitt snabbvyfält, stängd som standard.

**B3 — Ett formulär per utkasttyp, deklarerat i `atgardsformular.py`, ritat av
den delade `rendera_atgardsformular`.** Bygg inga egna ritfunktioner per typ.
Undantag: `kund`/`kundfaktura`, som har en fasmaskin av verkliga skäl
(kundsökning mot Spiris över flera reruns) — den ska återkopplas, inte skrivas
om.

**B4 — UI:t hämtar aldrig via `spiris_rag`.** Den vägen är maskerad och
fail-closed. Människan ska se sanningen. Se §4.

**B5 — Läsförmågor som bara finns i `spiris_rag` behöver en adapterfunktion.**
`hamta_prislistor`, `hamta_rabattavtal`, `hamta_etiketter`,
`hamta_kontotransaktioner`, `hamta_underlag`, `hamta_underlag_fil`,
`hamta_kontosaldon`, `hamta_momsoversikt`, `hamta_kassaflodesanalys`,
`hamta_resultatrapport` och `hamta_balansrapport` bor i dag bara i
RAG-lagret. `spiris_adapter.py` står i förbudslistan, **men det här dokumentet
ger uttryckligt tillstånd för rent additiva läsfunktioner där** — inga
ändringar av befintliga funktioner, inga skrivfunktioner, inga rader borttagna.
Varje sådan funktion får ett eget test. Behöver du något utöver detta: stanna
och fråga.

**B6 — `utkast.GILTIGA_TYPER` får kompletteras med `"offertutkast"`.**
`parser/utkast.py` står i förbudslistan, och den regeln kvarstår för allt annat
i filen. Undantaget gäller **enbart** att lägga till strängen `"offertutkast"` i
tupeln `GILTIGA_TYPER`, eftersom `utfor_utkast` redan har en fullständig och
testad gren för typen och avsaknaden är ett rent förbiseende. Ingen annan rad i
filen ändras.

**B7 — Formulärens nyttolast är ett kontrakt mot `utfor_utkast`, inte mot
Spiris.** Formuläret bygger de nycklar `utfor_utkast` läser. Översättningen till
Spiris fältnamn sker i adaptern och ingen annanstans. Kopiera aldrig en
`bygg_*_payload`-funktion till UI-lagret.

**B8 — Uppslag av levande id:n sker vid utförandet, inte vid förslaget.**
Kund-id, artikel-id och leverantörs-id slås upp i `utfor_utkast`. Hashen binder
människans beslut (vem, vad, hur mycket) — inte de tekniska id:n beslutet
översätts till. Ett formulär ska därför fråga efter *namn eller nummer*, inte
tvinga användaren att känna till ett GUID.

**B9 — Åtgärder som behöver ett "nuvarande"-tillstånd hämtar det i formuläret.**
`kontoandring`, `rotrut` och `periodiseringsandring` bär nyckeln `nuvarande` i
sin nyttolast: `utfor_utkast` lägger ändringarna ovanpå den. Formuläret måste
alltså läsa objektet ur Spiris innan utkastet skapas, precis som motsvarande
`forbered_*`-verktyg gör. Misslyckas läsningen skapas **inget** utkast.

**B10 — Varje tal bär sin härkomst.** `Harkomstmarke` i `parser/stil.py`. En vy
som läser live ur affärssystemet märks annorlunda än en som räknar lokalt ur en
SIE-ögonblicksbild. Gissa inte — sätt märket efter var datan faktiskt kom
ifrån.

**B11 — En vy som inte kan bedöma något säger det.** Skriv aldrig "inga
avvikelser" när underlaget saknas (jfr `#KTYP` i Spiris-exporten). Tomtexten
ska skilja på *"inget hittades"* och *"detta gick inte att bedöma"*.

**B12 — Utåtriktade typer får ingen ny väg.** Mottagargrinden i
`utfor_utkast`/`rendera_beslut` är enda stället där en adress visas och
godkänns. Ett formulär för en utåtriktad typ frågar aldrig efter en
e-postadress.

**B13 — Rumsmodellen får växa, men betalas med chunking.** Nya rum får läggas
till när domänen motiverar det, men de ska in i en befintlig grupp eller
motivera en ny. Elva jämbördiga val är sämre än sju; elva i fem grupper är
bättre.

**B14 — Svenska, `Decimal` för belopp, docstringen förklarar varför.** Namn,
docstrings och kommentarer på svenska. Alla belopp som `Decimal` internt.
`from __future__ import annotations` överst. Typannoteringar överallt.

---

## 10. Avgränsningar — vad som inte byggs

- **Ingen ändring av godkännandevyn i Beslut.** Den fungerar för alla typer.
- **Ingen ny skrivväg.** `utfor_utkast` är och förblir den enda.
- **Ingen ändring i `mcp_server/server.py`** utom den rättelse L1 kräver, och
  den ändringen ligger i `utkast.py`, inte i servern.
- **Inga nya MCP-verktyg.** MCP-ytan är färdig; det här uppdraget rör UI:t.
- **Inga `build_*.py` / `fix_*.py` / `add_*.py` i projektroten eller
  `parser/`.** De är historiska engångsskript. Läs dem gärna, ändra dem aldrig,
  och skapa inga nya — skriv koden direkt i stället.
- **Ingen omskrivning av `parser/atgardsformular.py`:s dataklasser.** `Falt` och
  `Atgardsformular` är rätt abstraktion. De ska användas, inte ersättas.
- **Ingen upplåsning av bokföringslås.** `forbered_bokforingslas` kan bara
  flytta låsdatumet framåt (beslut D1a i `PLAN_SPIRIS_ETAPP8.md`). Formuläret
  ska hålla samma linje och säga varför.

---

## 11. Målbild

När planen är genomförd gäller följande, och det ska gå att verifiera med ett
kommando (bilaga C):

1. **Varje typ i `utkast.GILTIGA_TYPER` har exakt ett formulär**, och det
   formuläret ritas ut i exakt ett rum.
2. **Varje formulärs nyttolast innehåller varje nyckel `utfor_utkast` läser
   för sin typ**, prövat av ett kontraktstest som härleder kraven ur adaptern
   i stället för ur en handskriven lista.
3. **Varje `forbered_*`-verktyg i MCP-servern skapar en typ som finns i
   `GILTIGA_TYPER`** — L1 kan inte uppstå igen.
4. **Varje läsande MCP-verktyg har en motsvarande vy i appen**, med rätt
   härkomstmärke, eller står med en uttrycklig motivering i en avstämd lista.
5. **Användaren kan initiera varje åtgärd själv.** AI-assistenten blir ett
   alternativ, inte en förutsättning. R-13 stängs.
6. **Testsviten är grön och har vuxit.** Den var 2 394 + 1 hoppad före
   arbetet.

---

## Bilaga A — De 29 utkasttyperna

Verifierat 2026-08-11. "Gren" = finns i `utfor_utkast`. "Formulär" = finns i
`ALLA_FORMULAR`. "I rum" = importeras av `rum_render.py`. "Fungerar" = hela
vägen från formulär till Spiris.

| # | Typ | Gren | Formulär | I rum | Nycklar OK | Fungerar |
|---|---|---|---|---|---|---|
| 1 | `kund` | ✅ | — (fasmaskin) | ❌ föräldralös | — | ❌ |
| 2 | `kundfaktura` | ✅ | — (fasmaskin) | ❌ föräldralös | — | ❌ |
| 3 | `verifikat` | ✅ | ✅ | ✅ Böckerna | ✅ | ✅ |
| 4 | `betalningsverifikat` | ✅ | ✅ | ❌ | ❌ kraschar | ❌ |
| 5 | `fakturautskick` | ✅ | ✅ | ✅ Pengar in | ✅ | ✅ |
| 6 | `betalningspaminnelse` | ✅ | ✅ | ✅ Pengar in | ✅ | ✅ |
| 7 | `betalningsregistrering` | ✅ | ✅ | ✅ Pengar in | ❌ | ❌ |
| 8 | `makulering` | ✅ | ✅ | ✅ Pengar in | ✅ | ✅ |
| 9 | `saljdokumentutskick` | ✅ | ✅ | ✅ Pengar in | ❌ | ❌ |
| 10 | `efakturautskick` | ✅ | ✅ | ✅ Pengar in | ✅ | ✅ |
| 11 | `saljdokumentatgard` | ✅ | ✅ | ✅ Pengar in | ❌ | ❌ |
| 12 | `leverantorsfakturautkast` | ✅ | ✅ | ✅ Pengar ut | ❌ | ❌ |
| 13 | `attest` | ✅ | ✅ | ✅ Pengar ut | ✅ | ✅ |
| 14 | `leverantorsbetalning` | ✅ | ✅ | ✅ Pengar ut | ❌ | ❌ |
| - | `kvittning` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 16 | `masterdataandring` | ✅ | ✅ | ✅ Register | ✅ | ✅ |
| 17 | `masterdataborttagning` | ✅ | ✅ | ✅ Register | ✅ | ✅ |
| 18 | `sie4import` | ✅ | ✅ | ✅ Böckerna | ❌ flaggor | ❌ kraschar |
| - | `underlagskoppling` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 20 | `utkastandring` | ✅ | ✅ | ❌ | ❌ | ❌ |
| 21 | `utkastborttagning` | ✅ | ✅ | ❌ | ✅ | ❌ |
| 22 | `utkastbokforing` | ✅ | ✅ | ❌ | ✅ | ❌ |
| 23 | `periodisering` | ✅ | ✅ | ❌ | ❌ | ❌ |
| - | `konto` | ✅ | ✅ | ✅ | ✅ | ✅ |
| - | `kontoandring` | ✅ | ✅ | ✅ | ✅ | ✅ |
| - | `periodiseringsandring` | ✅ | ✅ | ✅ | ✅ | ✅ |
| - | `periodiseringsborttagning` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 28 | `bokforingslas` | ✅ | ❌ | ❌ | — | ❌ |
| 29 | `rotrut` | ✅ | ❌ | ❌ | — | ❌ |
| - | `offertutkast` | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Bilaga B — De 56 läsande verktygen mot UI:t

| MCP-verktyg | Yta i appen |
|---|---|
| `berakna_vasentlighet` | ✅ snabbvy Väsentlighet (Böckerna/Bank/Register) |
| `granska_kontotyper` | ⚠️ snabbvy Kontotypavvikelser — tyst i Spiris-läge (`#KTYP` saknas) |
| `sok_lagstiftning` | ✅ rummet Juridik & Skatt (via AI-chatt) |
| `skatteverket_rattslig_vagledning` | ✅ rummet Juridik & Skatt (via AI-chatt) |
| `spiris_rakenskapsar` | ✅ årsväljaren i Data in/ut |
| `spiris_kontoplan` | ✅ Böckerna → Kontoplan |
| `spiris_kontosaldon` | ⚠️ Böckerna → Kontosaldon, ur SIE-ögonblicksbild |
| `spiris_sok_verifikationer` | ⚠️ Böckerna → Verifikatsökning, ur SIE-ögonblicksbild |
| `spiris_momsoversikt` | ⚠️ Böckerna → Momsöversikt, beräknad lokalt |
| `spiris_verifikatutkast` | ✅ Böckerna → Verifikatutkast |
| `spiris_kunder` | ✅ Register |
| `spiris_leverantorer` | ✅ Register |
| `spiris_artiklar` | ✅ Register |
| `spiris_projekt` | ✅ Register |
| `spiris_kostnadsstallen` | ✅ Register |
| `spiris_referensdata` | ✅ Register |
| `spiris_kundfakturor` | ✅ Register (detaljvy) |
| `spiris_leverantorsfakturor` | ✅ Register (detaljvy) |
| `spiris_kundreskontra` | ✅ Pengar in |
| `spiris_leverantorsreskontra` | ✅ Pengar ut |
| `spiris_kundbetalbeteende` | ⚠️ Pengar in → Påminnelser, beräknad lokalt |
| `spiris_likviditetsprognos` | ⚠️ Rapporter, beräknad lokalt ur reskontran |
| `spiris_bankkonton` | ✅ Bank |
| `spiris_bankhandelser` | ✅ Bank |
| `spiris_avstamningslage` | ✅ Bank |
| `spiris_dashboard` | ✅ Rapporter (FP&A) |
| `spiris_sie4export` | ✅ Data in/ut |
| `spiris_resultatrapport` | ⚠️ Rapporter, ur SIE/dashboard — inte live |
| `spiris_balansrapport` | ⚠️ Rapporter, ur SIE/dashboard — inte live |
| `spiris_kassaflodesanalys` | ⚠️ Rapporter, beräknad lokalt |
| `spiris_ingaende_balans` | ❌ |
| `spiris_kontotransaktioner` | ❌ |
| `spiris_verifikationer_alla` | ❌ |
| `spiris_verifikation` | ❌ |
| `spiris_kontosaldo` | ❌ |
| `spiris_kontoplan_alla` | ❌ |
| `spiris_periodiseringar` | ❌ |
| `spiris_momsrapporter` | ❌ |
| `spiris_momskoder` | ❌ |
| `spiris_order` | ✅ |
| `spiris_offerter` | ✅ |
| `spiris_offertutkast` | ✅ |
| `spiris_kundreskontraposter` | ✅ |
| `spiris_kvittningskandidater` | ❌ |
| `spiris_underlag` | ✅ |
| `spiris_hamta_underlag` | ✅ |
| `spiris_prislistor` | ✅ |
| `spiris_rabattavtal` | ✅ |
| `spiris_etiketter` | ✅ |
| `spiris_anlaggningstillgangar` | ✅ |
| `spiris_foretagsinfo` | ✅ |
| `spiris_anvandare` | ✅ |
| `spiris_bokforingslas` | ❌ |
| `spiris_valutakurs` | ✅ |
| `spiris_bankhandelse` | ❌ |
| `spiris_hamta_ett` | ❌ |

✅ = finns · ⚠️ = finns men med annan härkomst än MCP:s · ❌ = ingen yta

---

## Bilaga C — Verifieringskommandon

Kör dessa för att återskapa varje siffra i det här dokumentet.

```bash
# Baslinje för testsviten
python -m pytest tests -q

# Antal MCP-verktyg, resurser och prompter
python count_tools.py

# L1: att offertutkast saknas i GILTIGA_TYPER
python -c "import sys; sys.path.insert(0,'parser'); import utkast; \
print(len(utkast.GILTIGA_TYPER), 'offertutkast' in utkast.GILTIGA_TYPER)"

# L3: att två formulär kraschar
python -c "import sys; sys.path.insert(0,'parser'); import atgardsformular as a; \
a.BETALNINGSVERIFIKAT.bygg_nyttolast({'rader':'[]'})"

# L4: formulär som aldrig ritas ut
python -c "import sys,re,pathlib; sys.path.insert(0,'parser'); import atgardsformular as a; \
r=pathlib.Path('parser/rum_render.py').read_text(encoding='utf-8'); \
print([f.utkasttyp for f in a.ALLA_FORMULAR \
if not re.search(r'\b'+[k for k,v in vars(a).items() if v is f][0]+r'\b', r)])"
```

Kontraktskontrollen i L2 automatiseras i etapp U2 och blir då ett vanligt test.
