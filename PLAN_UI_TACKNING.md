# Exekverbar plan — UI-täckning för sie-mcp:s verktygsyta

**Datum:** 2026-08-11
**Mottagare:** Gemini 3.1 Pro, som utför hantverket
**Läs först:** `ARKITEKTUR_UI_TACKNING.md` i sin helhet, sedan
`_arkiv/sie-mcp-2026-08-09/hantverksbok/00_KONSTITUTION.md` och
`.../hantverksbok/UI_ARKITEKTUR.md`.

Arkitekturbesluten **B1–B14** står i arkitekturdokumentet och ska inte omprövas
av dig. Där planen säger *"se B7"* menar den det bokstavligt: gå tillbaka och
läs beslutet innan du skriver koden.

---

## 0. Förutsättningar

### 0.1 Startprompt (för den som startar dig)

> Genomför etapp U*n* i projektet `sie-mcp`. Arbetsordern står i
> `PLAN_UI_TACKNING.md` och arkitekturen i `ARKITEKTUR_UI_TACKNING.md`. Läs
> båda innan du rör koden. En uppgift i taget, `python -m pytest tests -q`
> mellan varje. Rapportera enligt mallen i §12 och **stanna** efter varje
> etapp. Stanna och fråga hellre än att gissa.

### 0.2 Baslinje

```bash
python -m pytest tests -q
```

**Baslinje 2026-08-11: `2394 passed, 1 skipped`.**

Kör före och efter varje uppgift. **Antalet passerade tester ska öka, aldrig
minska.** Ett rött test är ett problem med din kod tills arkitekten säger annat.

### 0.3 Filer du får ändra

```
app.py                          sidregistrering
parser/rum/*.py                 rumsdeklarationer (nya filer tillåtna)
parser/rum_render.py            all Streamlit-ritning
parser/snabbvyer.py             rena vybyggare + Vydata-fält
parser/snabbvy_render.py        endast om ett nytt fälttypsfall krävs
parser/atgardsformular.py       formulärdeklarationer
parser/vy_modell.py             endast om kontraktet måste utökas
parser/ordbok.py                nya begrepp
parser/app_tillstand.py         datainladdning till session_state
parser/stil.py                  endast nya härkomstmärken
tests/**                        nya testfiler; befintliga får utökas
```

### 0.4 Filer du ALDRIG ändrar

```
parser/sekretesslager.py   parser/reskontra_tvatt.py   parser/revisionslogg.py
parser/namnreferens.py     parser/saker_lagring.py     parser/masking_memory.py
parser/compliance.py       parser/spiris_klient.py     parser/spiris_rag.py
parser/spiris_session.py   mcp_server/server.py        .env / .env.example
parser/*build_*.py  parser/*fix_*.py  parser/*add_*.py  parser/*_lines.py
```

**Två uttryckliga och avgränsade undantag, båda beslutade i
arkitekturdokumentet:**

- `parser/utkast.py` — **enbart** för att lägga till strängen `"offertutkast"`
  i `GILTIGA_TYPER` (uppgift U1.1). Ingen annan rad. Se **B6**.
- `parser/spiris_adapter.py` — **enbart** rent additiva **läsfunktioner**
  (uppgifterna U6.1, U7.1, U8.1). Inga ändringar av befintliga funktioner,
  inga borttagna rader, aldrig en skrivfunktion. Se **B5**.

Allt annat i dessa två filer är fortsatt förbjudet. Behöver du något utöver
undantagen: **stanna och fråga.**

### 0.5 Regler som gäller varje uppgift

1. **Du ändrar aldrig ett befintligt test för att få det grönt.** Är ett test
   fel, stanna och fråga. Det här projektets största kvalitetsproblem uppstod
   just så — läs §8 i arkitekturdokumentet innan du frestas.
2. **Formuläret skapar bara ett utkast.** Ritfunktionen anropar aldrig
   `utfor_utkast`. Se **B1**.
3. **Svenska** i namn, docstrings och kommentarer. Docstringen förklarar
   **varför**, inte vad.
4. **`from __future__ import annotations` överst. Typannoteringar överallt.
   `Decimal` för belopp.**
5. **Ingen ny fil i projektroten.** Skriv koden direkt, inte via ett
   generatorskript.
6. Streamlit-ritningen går inte att enhetstesta meningsfullt. Testa
   **vybyggarna** och **formulärdeklarationerna** (rena funktioner) samt
   **strukturen** (att rätt formulär är kopplat till rätt rum). Mönstret finns
   i `tests/test_rum_render_atgard.py`.
7. Efter varje etapp: kör `streamlit run app.py`, öppna de rum du rört, och
   skriv i rapporten vilka. Det ersätter inte testerna, men testerna ersätter
   inte det heller.

### 0.6 Grindar

Etapperna körs **i ordning**. U1 och U2 är spärrar: ingenting nytt byggs innan
de är gröna. Rapportera och **stanna** efter varje etapp.

### 0.7 Kvalitetsgrind — gäller varje uppgift, varje etapp

Införd 2026-08-11 efter en avstämning av U1–U5.2. **Bakgrund:** U1, U3 och U4
levererades korrekt, men U2.2 hoppades över, nio formulär deklarerades utan att
någonsin renderas i ett rum, och fem `egen_ritare` pekade på funktioner som inte
fanns. Testsviten var grön hela tiden. Det är exakt den felmekanism §8 i
arkitekturdokumentet beskriver: **testet uppfylls, inte kravet.**

Grinden nedan är mekanisk. Gå igenom den innan du rapporterar en uppgift som
klar, och besvara varje punkt i rapporten.

#### K1 — Ett formulär deklareras när det byggs, aldrig innan

Lägg aldrig in ett `Atgardsformular` i `ALLA_FORMULAR` "på förhand". Antingen
bygger du ritaren och placerar formuläret i ett rum i **samma uppgift**, eller
så rör du det inte alls.

En `egen_ritare` som pekar på en funktion som inte finns i `rum_render.py` är en
landmina: den sprängs med `AttributeError` i det ögonblick någon placerar
formuläret i ett rum. En `egen_ritare=lambda st: None` är värre — den ritar
ingenting och ser ut att fungera.

#### K2 — Varje formulär i `ALLA_FORMULAR` renderas i exakt ett rum

Ett formulär som inte importeras av `rum_render.py` når inte användaren. Då är
uppgiften inte klar, oavsett hur många tester som är gröna.

Kontrollera själv innan du rapporterar:

```bash
python -c "import sys,re,pathlib; sys.path.insert(0,'parser'); \
import atgardsformular as a; \
r=pathlib.Path('parser/rum_render.py').read_text(encoding='utf-8'); \
n={id(f):[k for k,v in vars(a).items() if v is f][0] for f in a.ALLA_FORMULAR}; \
print('EJ RENDERADE:', [f.utkasttyp for f in a.ALLA_FORMULAR \
if not re.search(r'\b'+n[id(f)]+r'\b', r)])"
```

Listan ska vara tom, eller innehålla **enbart** typer som en aktiv
`xfail(strict=True)` uttryckligen väntar på med en kommentar som pekar på rätt
etapp.

#### K3 — `bygg_sammanfattning` får aldrig returnera en tom lista

Sammanfattningen är det **enda** människan ser i rummet Beslut. Den ska räcka
för att fatta beslutet utan att öppna något annat. En tom sammanfattning gör
grinden meningslös — särskilt för en oåterkallelig åtgärd.

Se `mcp_server/server.py:forbered_*` för nivån: åtgärd, motpart eller objekt,
belopp, datum, och en uttrycklig varningsrad när åtgärden inte går att ångra.

#### K4 — `bygg_nyttolast` är fail-closed

Mönstret `{k: v[k] for k in [...] if k in v}` är **förbjudet**. Det utelämnar en
saknad obligatorisk nyckel i tystnad och skapar ett utkast som havererar först
vid godkännandet — efter att människan tagit ansvar för det.

Saknas en obligatorisk uppgift: kasta `ValueError` med en läsbar svensk text.
Valfria fält utelämnas medvetet och dokumenterat.

#### K5 — Testantalet ska öka i proportion till arbetet

Varje etapp anger sina tester. Levererar du sex nya tester där etappen begär
tjugofem har du inte prövat det du byggt. Ange i rapporten hur många tester
varje uppgift tillförde, inte bara sviten totalt.

#### K6 — Inga nya filer i projektroten

Inga `debug.py`, `scratch/`, `tmp*`, `*_test.py` utanför `tests/`. Behöver du
klottra: gör det i en fil du raderar innan du rapporterar. Roten är städad och
ska förbli det.

#### K7 — Rapporten ska vara sann

- **Rapportera aldrig en uppgift som klar innan formuläret går att nå i
  appen**, provat i `streamlit run app.py`.
- Raden *"BEFINTLIGA TESTER SOM RÖRTS"* i rapportmallen (§12) är obligatorisk.
  Skriv `ingen` om inget rörts — lämna den aldrig tom.
- Har du hoppat över en deluppgift: säg det, med skäl. En överhoppad uppgift är
  ett hanterbart problem. En överhoppad uppgift som rapporterats klar är det
  inte.

#### K8 — Utestående skuld som ska betalas först

Följande upptäcktes vid avstämningen och ska åtgärdas **innan** någon ny
uppgift i U5 påbörjas:

1. **U2.2 är inte gjord.** `undantagna`-mängden i
   `test_atgardsformular.py::test_metatest_at_bada_hallen` är oförändrad, med
   samma tio typer. Bygg testet enligt U2.2, utan undantagsmängd.
2. **Nio formulär renderas i inget rum:** `kund`, `kundfaktura`,
   `offertutkast`, `kvittning`, `underlagskoppling`, `konto`, `kontoandring`,
   `periodiseringsandring`, `periodiseringsborttagning`. Antingen levereras de
   enligt K1–K2, eller så tas deklarationerna bort tills deras uppgift körs.
   `kund` och `kundfaktura` är undantagna från kravet på egen rendering — de
   täcks av fasmaskinen som U4 kopplade in i Pengar in — men deras
   `bygg_sammanfattning` måste ändå uppfylla K3.
3. **Fem `egen_ritare` pekar på obefintliga funktioner** i `rum_render.py`
   (`_rendera_kvittning_formular`, `_rendera_konto_formular`,
   `_rendera_kontoandring_formular`, `_rendera_periodiseringsandring_formular`,
   `_rendera_periodiseringsborttagning_formular`).
4. **Nio `bygg_sammanfattning` returnerar `[]`.** Bryter mot K3.
5. **`debug.py` och `scratch/` ligger i projektroten.** Bryter mot K6.
6. **`makulering` samlar in `motivering` och kastar den.** Fältet finns i
   formuläret, men nyckeln togs bort ur nyttolasten (riktigt — `utfor_utkast`
   läste den aldrig) och visas inte i sammanfattningen. Antingen in i
   sammanfattningen eller bort ur formuläret.

---

## Etapp U1 — Rättningar

Åtta fel som gör att funktioner som ser färdiga ut inte fungerar. **Bygg
ingenting nytt innan den här etappen är klar.**

### U1.1 — `offertutkast` saknas i `GILTIGA_TYPER`

**Fel:** `mcp_server/server.py:forbered_offertutkast` anropar
`utkast.skapa("offertutkast", …)`, men `"offertutkast"` finns inte i
`utkast.GILTIGA_TYPER`. Varje anrop höjer `UtkastFel`, fångas av
`_kor_utkastverktyg` och returneras som *"Kunde inte skapa utkastet"*.
Verktyget har aldrig fungerat. `utfor_utkast` har redan en fullständig gren för
typen.

**Åtgärd:** lägg till `"offertutkast"` i tupeln `GILTIGA_TYPER` i
`parser/utkast.py`, i blocket för Steg 5b tillsammans med de andra
offert-/orderposterna. Ingen annan rad i filen ändras. Se **B6**.

**Åtgärd 2:** `tests/test_etapp15_order_offert.py::test_forbered_offertutkast_ratt_payload`
hävdar i dag `"bekraftelse" in res or "utkast_id" in res or "utkast" in res`
och passerar därför på felsvaret, som *innehåller* `utkast_id: None`. Skärp
assertionen så att den kräver `res["utkast_id"]` **sant** och
`res["utfort"] is False`. Det är inte att "ändra ett test för att få det
grönt" — det är att uppfylla det testet redan påstod sig pröva. Notera
ändringen uttryckligen i rapporten.

**Tester (2):** att `utkast.skapa("offertutkast", …)` lyckas; att
`forbered_offertutkast` returnerar ett sant `utkast_id`.

### U1.2 — `json` importeras inte där det används

**Fel:** `parser/atgardsformular.py` importerar `json` lokalt i två funktioner,
men `_betalningsverifikat_nyttolast` (rad ~513) använder det utan import →
`NameError`.

**Åtgärd:** flytta upp `import json` till modulens toppimportsblock och ta bort
de två lokala importerna. Samma sak gäller `import os` i
`_sie4import_sammanfattning`.

**Test (1):** `BETALNINGSVERIFIKAT.bygg_nyttolast` med balanserade rader
returnerar en dict.

### U1.3 — Fel modulnamn i SIE4-importens sammanfattning

**Fel:** `_sie4import_sammanfattning` gör `from sie_parser import parse_sie4`.
Modulen heter `sie4_parser`. Varje försök att skapa ett SIE4-importutkast från
appen ger `ModuleNotFoundError`, som ritfunktionens breda `except` förvandlar
till *"Ett fel uppstod: No module named 'sie_parser'"*.

**Åtgärd:** rätta importen till `from sie4_parser import parse_sie4`. Kontrollera
funktionens verkliga namn och signatur i `parser/sie4_parser.py` innan du
skriver — den tar en **sökväg**, inte bytes. (Exakt det felet har gjorts en gång
förr, se kommentaren i `forbered_sie4import`.)

**Test (1):** sammanfattningen för `samples/SIE4_Exempelfil.SE` innehåller
bolag, orgnr, antal verifikationer och antal konton.

### U1.4 — SIE4-importens fyra flaggor läses aldrig

**Fel:** formuläret bygger `skriv_over_saldon`, `tillat_obrukade_konton`,
`ignorera_varningsflaggor`, `invertera_tecken_pa_resultat`. `utfor_utkast`
läser `ingaende_balans`, `kontonamn`, `mappa_konton`, `arsavslut`. Importen
körs alltså alltid med allt avstängt medan användaren tror att hon styr det.

**Åtgärd:** byt formulärets fält och nyttolastnycklar till de fyra
`utfor_utkast` faktiskt läser, med etiketter som säger vad de gör:

| Nyckel | Etikett | Hjälptext |
|---|---|---|
| `ingaende_balans` | Importera ingående balanser | Skriver in ingående balanser i bolaget. |
| `kontonamn` | Importera kontonamn | Skriver över befintliga kontonamn. |
| `mappa_konton` | Mappa konton | Låter Spiris matcha filens konton mot bolagets. |
| `arsavslut` | Utför årsavslut | Utför ett årsavslut. Kan inte ångras. |

Alla fyra `False` som standard — det är ett säkerhetsval, inte en
bekvämlighet (se docstringen i `bygg_sie4import_payload`).

**Test (1):** `SIE4IMPORT.bygg_nyttolast` producerar exakt de fyra nycklarna
och inga andra flaggnycklar.

### U1.5 — Sex formulär med nyckelmissmatch mot `utfor_utkast`

**Åtgärd:** rätta `bygg_nyttolast` i vart och ett. Nyckeln till vänster är den
`utfor_utkast` läser — den är facit. Se **B7**.

| Utkasttyp | Nyckel som krävs | Formuläret ger i dag |
|---|---|---|
| `betalningsregistrering` | `bankkonto_id` | `bankkonto` |
| `leverantorsbetalning` | `bankkonto_id` | `bankkonto` |
| `saljdokumentutskick` | `nummer` | `nummer_eller_id` |
| `saljdokumentatgard` | `nummer` | `nummer_eller_id` |
| `leverantorsfakturautkast` | `leverantor_id`, `fakturadatum`, `kreditfaktura` | `leverantor`, `datum`, `kreditflagga` |
| `utkastandring` | `andringar` (dict) | *(saknas helt)* |

Två anmärkningar:

- **`bankkonto_id` och `leverantor_id` är Spiris-id:n.** Tvinga inte användaren
  att kunna dem utantill. Fyll en `st.selectbox` från
  `spiris_adapter.hamta_bankkonton` respektive `hamta_leverantorer`, visa namnet
  och lagra id:t. Går listan inte att hämta: låt fältet vara ett textfält med en
  förklarande hjälptext, och skapa inget utkast på ett tomt id.
- **`utkastandring`:s `andringar`** är en dict vars tillåtna nycklar bestäms av
  ändringsallowlisten i adaptern (Etapp 14). Rendera fälten dynamiskt ur den
  källan, precis som `masterdataandring` gör med `_MASTERDATA`. Lägg inte en
  andra kopia av listan i UI-lagret.

**Tester:** täcks av kontraktstestet i U2.1 — men skriv dessutom ett
riktat test per formulär som visar den rättade nyckeln.

### U1.6 — Fälttyperna `decimal` och `heltal` renderas inte

**Fel:** `PERIODISERING` deklarerar fälttyperna `"decimal"` och `"heltal"`.
`rendera_atgardsformular` känner bara `text`, `tal`, `datum`, `kryss`, `val`.
Fälten ritas aldrig ut, och obligatoriska-fält-kontrollen slår alltid till.

**Åtgärd:** använd `"tal"` för belopp och `"tal"` för heltalsfält i
deklarationen. Utöka **inte** renderaren med nya fälttyper i den här uppgiften —
`Falt.typ`-mängden är ett kontrakt, och en utökning ska motiveras separat.

**Test (1):** varje `Falt.typ` i varje formulär i `ALLA_FORMULAR` ligger i den
mängd `rendera_atgardsformular` hanterar. Testet ska härleda mängden ur en
konstant, inte ur en handskriven lista i testet.

**Grind U1:** sviten grön, `2394 + minst 8` passerade.

---

## Etapp U2 — Regressionsspärren

**Den här etappen är viktigare än allt som följer.** Den bygger de
kontraktstester som skulle ha förhindrat hela situationen. Läs §8 i
arkitekturdokumentet först.

Gemensam princip för alla tre: **kravet härleds ur koden, aldrig ur en
handskriven lista i testet.** En undantagsmängd som kan växa är exakt det som
gjorde det förra metatestet verkningslöst.

### U2.1 — Kontraktstest: formulärets nyttolast mot `utfor_utkast`

Ny fil `tests/test_utkastkontrakt.py`.

Testet ska, för varje formulär i `ALLA_FORMULAR`:

1. **Extrahera** ur `spiris_adapter.utfor_utkast` vilka nycklar grenen för den
   typen läser. Parsa modulens källkod med `ast` — leta `Subscript` på namnet
   `nyttolast` (obligatoriska) och `nyttolast.get(...)` (valfria) inom grenens
   `If`-nod. Följ även de `bygg_*_payload`-funktioner grenen anropar med hela
   nyttolasten (`_bygg_verifikat_payload`, `_bygg_betalningsverifikat_payload`,
   `bygg_periodiseringspayload`, `bygg_kontopayload`,
   `bygg_bokforingslas_payload`).
2. **Bygga** en nyttolast via `formular.bygg_nyttolast(<giltig exempelindata>)`.
   Exempelindata deklareras per typ i testfilen — den är testdata, inte en
   undantagslista.
3. **Hävda** att varje obligatorisk nyckel finns i utfallet.
4. **Hävda** att ingen nyckel i utfallet är okänd för `utfor_utkast`, så att
   ett fält som `skriv_over_saldon` (U1.4) inte kan smyga tillbaka.

Ett formulär som saknar exempelindata ska få testet att **falla**, inte att
hoppas över.

### U2.2 — Metatest utan undantagslista

Ersätt `tests/test_atgardsformular.py::test_metatest_at_bada_hallen`. Nya
påståenden:

1. Varje `Atgardsformular.utkasttyp` finns i `utkast.GILTIGA_TYPER`.
2. **Varje typ i `GILTIGA_TYPER` har ett formulär i `ALLA_FORMULAR`** — utan
   undantag. `kund` och `kundfaktura` uppfylls av U4 (fasmaskinen registreras
   som formulär med en egen ritare, se U4.2).
3. **Varje formulär i `ALLA_FORMULAR` importeras av `parser/rum_render.py`.**
   Kontrolleras med `ast` mot rum_renders importsatser, inte med en
   regexsökning på variabelnamn.

Punkt 2 och 3 kommer att vara **röda tills etapp U5 är klar**. Det är
avsiktligt och det är hela poängen: en oåtkomlig åtgärd ska synas.

**Hantera det så här:** markera dem `@pytest.mark.xfail(strict=True)` med en
kommentar som pekar på den etapp som stänger dem, och **ta bort markeringen i
den etappen**. En `xfail(strict=True)` som börjar passera gör sviten röd —
alltså kan ingen glömma bort det. Skriv aldrig `skip`.

### U2.3 — Kontraktstest: MCP-serverns utkasttyper

Varje sträng som `mcp_server/server.py` skickar som första argument till
`utkast.skapa` ska finnas i `utkast.GILTIGA_TYPER`, och varje sådan typ ska ha
en gren i `utfor_utkast`. Extraheras med `ast` ur serverkällan. Det testet gör
att lucka L1 inte kan uppstå igen.

**Grind U2:** sviten grön (med de två avsiktliga `xfail`), minst 3 nya
testfunktioner.

---

## Etapp U3 — De fem föräldralösa formulären får ett hem

Fem formulär finns men ritas aldrig ut. Placeringen följer **B2**: åtgärden bor
där data visas.

| Utkasttyp | Rum | Motivering |
|---|---|---|
| `betalningsverifikat` | 🏦 Bank | Ett verifikat för över-/underbetalning hör till betalningsavstämningen. |
| `periodisering` | 📚 Böckerna | Periodisering är en bokföringsåtgärd. |
| `utkastandring` | 📚 Böckerna | Bredvid snabbvyn Verifikatutkast, som visar de utkast åtgärden gäller. |
| `utkastborttagning` | 📚 Böckerna | Samma. |
| `utkastbokforing` | 📚 Böckerna | Samma. Bär varningen "Bokföringen är oåterkallelig". |

### U3.1 — `periodisering` måste bygga ett riktigt kopplingspar

Formuläret ger i dag en fritextsträng `kopplingspar`, som ingen läser.
`bygg_periodiseringspayload` kräver **exakt ett** av dessa par:

```
VoucherId + VoucherRow
SupplierInvoiceId + SupplierInvoiceRow
SupplierInvoiceDraftId + SupplierInvoiceDraftRow
```

**Åtgärd:** ett `val`-fält för kopplingstyp (verifikat / leverantörsfaktura /
leverantörsfakturautkast), plus ett id-fält och ett radnummerfält. `bygg_nyttolast`
sätter rätt par och kastar `ValueError` med en läsbar svensk text om något
saknas. Nyttolasten ska dessutom bära `startdatum`, `belopp`, `konto` och
`antal_perioder`. Jämför med `mcp_server/server.py:forbered_periodisering` för
nivån — men kopiera inte payloadbygget, se **B7**.

### U3.2 — Placera de fem i rummen

Lägg till dem i respektive rums `st.expander("➕ Ny åtgärd")`.

**Obs:** `tests/test_rum_render_atgard.py` hävdar exakta antal formulär per rum
(7 / 3 / 2 / 2). De ska uppdateras när du lägger till — det är en avsiktlig
strukturkontroll, inte ett test som ska bort. Uppdatera talen och notera det i
rapporten.

**Tester (6):** ett per formulär att `bygg_nyttolast` uppfyller kontraktet
(faller ut ur U2.1), plus ett per rum att rätt antal formulär kopplats dit.

**Grind U3.**

---

## Etapp U4 — Fakturavägen återkopplas

`rum_render._rendera_fakturautkast` (rad ~147, ~340 rader) är fullständig,
välskriven och **anropas av ingen**. `parser/assistent.py` sätter
`st.session_state.aktivt_fakturautkast` och kör `st.rerun()` — varefter
ingenting ritas ut. Användaren ber assistenten skapa en faktura och får inget
svar.

**Skriv inte om flödet.** Det bär kundsökning mot Spiris över flera reruns,
ROT-fälten, byggmomsgrinden och granskningsvyn. Koppla in det.

### U4.1 — Rita ut flödet där det hör hemma

Kalla `_rendera_fakturautkast(client_id, client_secret)` överst i
`rendera_pengar_in`, före snabbvyfältet, och returnera direkt när
`st.session_state.aktivt_fakturautkast` inte är `None` — flödet äger då sidan,
precis som det gjorde i den ursprungliga appen.

**Fråga att avgöra och rapportera:** flödet startas i dag också av
AI-assistenten i rummet **Företagsdata**. Om användaren står där när
assistenten anropar `skapa_kundfaktura` ska hon inte tyst hamna någon
annanstans. Lös det med en synlig hänvisning ("Ett fakturautkast väntar i
**Pengar in**") i stället för en automatisk omdirigering. En sida som byter sig
själv under användaren bryter mot Shneiderman 7.

### U4.2 — `kund` och `kundfaktura` i formulärregistret

Metatestet U2.2 kräver att varje typ i `GILTIGA_TYPER` har ett formulär.
Fasmaskinen passar inte i `Atgardsformular`-mallen. Lös det genom att utöka
`Atgardsformular` med ett valfritt fält:

```python
egen_ritare: Callable[[Any], None] | None = None
```

När det är satt hoppar `rendera_atgardsformular` över standardritningen och
delegerar. `bygg_nyttolast` och `bygg_sammanfattning` får då vara de funktioner
fasmaskinen redan använder. Så blir båda typerna registrerade, upptäckbara och
täckta av metatestet, utan att en rad av det fungerande flödet skrivs om.

**Tester (4):** att `_rendera_fakturautkast` anropas från Pengar in; att
`aktivt_fakturautkast = None` inte ritar något; att `kund` och `kundfaktura`
finns i `ALLA_FORMULAR`; att `egen_ritare` används när den är satt.

**Grind U4:** ta bort `xfail`-markeringen på U2.2 punkt 2 för `kund` och
`kundfaktura`.

---

## Etapp U5 — De åtta typerna utan formulär

Nu byggs det som saknas helt. Ett formulär per uppgift, i ordning. Kör testerna
mellan varje.

Kolumnen **"Nyttolastens nycklar"** är facit — det är vad `utfor_utkast` läser.
Kontraktstestet från U2.1 kommer att pröva exakt detta.

### U5.1 — `kvittning` → rummet 📤 Pengar ut

| | |
|---|---|
| Nyttolastens nycklar | `kreditfaktura_id`, `payload` = `{"DebitInvoiceIds": [...], "VoucherDate": "ÅÅÅÅ-MM-DD"}` |
| Fält | Kreditfaktura (nummer eller id), debetfakturor (flerval), verifikatdatum |
| Varning | "Kvittningen kan inte ångras." |

`spiris_adapter.hamta_kvittningskandidater(klient, faktura_id)` ger de
debetfakturor som får kvittas mot en viss kreditfaktura. Använd den för att
fylla flervalet — låt inte användaren gissa. Går den inte att hämta: skapa
inget utkast.

### U5.2 — `underlagskoppling` → rummet 📚 Böckerna

| | |
|---|---|
| Nyttolast | Spiris-kroppen direkt: `DocumentId`, `AttachmentIds`, `DocumentType` |
| Fält | Underlag (val, från `hamta_underlag`), dokument-id, dokumenttyp (val) |

**Undantag från B7, och enda gången det gäller:** `utfor_utkast` skickar
nyttolasten rått till `/attachmentlinks`. Bygg den därför genom att **anropa**
`spiris_adapter.bygg_underlagskopplingspayload(underlag_id, dokument_id,
dokument_typ)` — skriv aldrig Spiris fältnamn för hand i UI-lagret.

`DocumentType` är en sträng (`"SupplierInvoice"` m.fl.) och det är
sandbox-verifierat. Hämta de giltiga värdena ur adaptern om en konstant finns
där; annars: stanna och fråga.

### U5.3 — `konto` → rummet 📇 Register

| | |
|---|---|
| Obligatoriska nycklar | `kontonr`, `kontonamn`, `rakenskapsar_id`, `aktiv` |
| Valfria | `kontotyp`, `momskod_id`, `projekt_tillatet`, `kostnadsstalle_tillatet`, `sparrat_for_manuell_bokning` |

`rakenskapsar_id` finns i `st.session_state.spiris_hamtat_ar`. Visa vilket år
som gäller i klartext — id:t säger användaren ingenting.
`momskod_id` fylls från `hamta_momskoder` (kräver adapterfunktionen i U6.1).

### U5.4 — `kontoandring` → rummet 📇 Register

| | |
|---|---|
| Nycklar | `rakenskapsar_id`, `kontonr`, `nuvarande`, `andringar` |

**Se B9.** `nuvarande` är hela kontoobjektet, läst live ur Spiris innan
utkastet skapas — `utfor_utkast` lägger `andringar` ovanpå det. Läs det med
`spiris_adapter.hamta_ett(klient, "konto", …)` eller motsvarande. Misslyckas
läsningen: **skapa inget utkast**, och säg varför.

`andringar` får bara innehålla nycklar ur `spiris_adapter._KONTO_ALLOWLIST`
(`kontonamn`, `aktiv`, `kontotyp`, …). Rendera fälten dynamiskt ur den
konstanten, som `masterdataandring` gör.

### U5.5 — `periodiseringsandring` → rummet 📚 Böckerna

Samma nyckeluppsättning som `periodisering` (U3.1) plus att den nuvarande
planen ska visas i sammanfattningen. Jämför
`forbered_periodiseringsandring`: den visar nuvarande belopp och antal perioder
bredvid de nya. Gör likadant — en ändring man inte kan jämföra är inte
granskningsbar.

### U5.6 — `periodiseringsborttagning` → rummet 📚 Böckerna

| | |
|---|---|
| Nyckel | `leverantorsfakturautkast_id` |
| Varning | "Tar bort ALLA periodiseringar på utkastet. Oåterkalleligt — det finns ingen väg tillbaka." |

Sammanfattningen ska visa **hur många** perioder som försvinner. Läs dem först.

### U5.7 — `bokforingslas` → nytt rum, se U9

Byggs i etapp U9 tillsammans med läsvyn för företagsinställningar, eftersom
formuläret är meningslöst utan det nuvarande låsdatumet bredvid sig.

### U5.8 — `rotrut` → nytt rum, se U9

Samma skäl: `utfor_utkast` kräver nyckeln `nuvarande`, som måste läsas live.

**Grind U5:** ta bort `xfail` på U2.2 punkt 2 helt. Alla typer utom
`bokforingslas` och `rotrut` har nu formulär — de två sista stängs i U9, och
tills dess står de kvar som de enda posterna i en `xfail` med en kommentar som
pekar hit.

---

## Etapp U6 — Läsvyer, våg 1: Böckerna kompletteras

Nu vänder vi från åtgärder till läsning. Sju MCP-läsförmågor saknar yta i
bokföringsdomänen.

### U6.1 — Adapterfunktioner som saknas

**Se B5.** Följande läsförmågor bor i dag bara i `parser/spiris_rag.py`, som är
den maskerade och fail-closed vägen. UI:t får inte använda den (**B4**).
Lägg additiva, omaskerade läsfunktioner i `parser/spiris_adapter.py`:

```
hamta_kontotransaktioner(klient, rakenskapsar_id, kontonr) -> list[dict]
hamta_kontosaldon(klient, rakenskapsar_id, tom_datum)      -> list[dict]
hamta_momsoversikt(klient, per_datum)                       -> dict
```

Mönstret finns i RAG-versionerna, men **utan** `maskera_siefil`-steget och
**utan** att blockerade verifikationer utesluts — människan ska se allt. Läs
`hamta_leverantorsfakturor` i adaptern för stilen (fältallowlist, `Decimal`,
defensiv mot saknade fält).

**Tester:** ett per funktion mot en mockad klient.

### U6.2 — Nya snabbvyer i 📚 Böckerna

| Snabbvy | MCP-motsvarighet | Datakälla |
|---|---|---|
| Ingående balanser | `spiris_ingaende_balans` | `hamta_ingaende_balans` (finns) |
| Kontotransaktioner | `spiris_kontotransaktioner` | U6.1, kräver kontoval |
| Verifikationer (alla år) | `spiris_verifikationer_alla` | `hamta_verifikationer_alla` (finns) |
| Enskilt verifikat | `spiris_verifikation` | `hamta_en_verifikation` (finns) |
| Periodiseringar | `spiris_periodiseringar` | `hamta_periodiseringar` (finns) |
| Kontoplan (alla år) | `spiris_kontoplan_alla` | `hamta_kontoplan_alla` (finns) |
| Momsrapporter | `spiris_momsrapporter` | `hamta_momsrapporter` (finns) |
| Momskoder | `spiris_momskoder` | `hamta_momskoder` (finns) |

Följ mönstret i `parser/snabbvyer.py`: en ren funktion `Vydata →
Snabbvyresultat`, nya `Vydata`-fält med `None`-default, registrering i
`SNABBVYER_BOCKERNA`, inladdning i `app_tillstand.ladda_bockerna_data`.

### U6.3 — Härkomst och ärliga tomtexter

**Se B10 och B11.** Flera befintliga vyer i Böckerna (Kontosaldon,
Verifikatsökning, Momsöversikt) räknas ur den SIE4-ögonblicksbild som hämtades
vid uppkopplingen, inte live ur Spiris. Gå igenom `SNABBVYER_BOCKERNA` och sätt
`harkomst` efter var datan faktiskt kom ifrån.

Snabbvyn **Kontotypavvikelser** är ett särfall: Spiris SIE4-export saknar
`#KTYP`, så `kontotyp_vakt` bedömer noll konton i Spiris-läge och vyn ser grön
ut fast den inte har tittat. Ge den en tomtext som skiljer *"inga avvikelser
hittades"* från *"kontotyper saknas i underlaget — avvikelser kan inte
bedömas"*.

**Tester:** ett per ny vy (ren funktion, mockad `Vydata`), plus ett som visar
att Kontotypavvikelser säger ifrån när `konto.typ` är `None` överallt.

**Grind U6.**

---

## Etapp U7 — Läsvyer, våg 2: Register kompletteras

### U7.1 — Adapterfunktioner (se B5)

```
hamta_prislistor(klient, prislista_id=None) -> list[dict]
hamta_rabattavtal(klient)                    -> list[dict]
hamta_etiketter(klient, typ)                 -> list[dict]
```

RAG-versionerna är redan rena fältallowlists utan maskering — flytta logiken,
kopiera inte anropet till RAG-lagret.

### U7.2 — Nya snabbvyer i 📇 Register

| Snabbvy | MCP-motsvarighet |
|---|---|
| Prislistor | `spiris_prislistor` |
| Rabattavtal | `spiris_rabattavtal` |
| Etiketter | `spiris_etiketter` |
| Anläggningstillgångar | `spiris_anlaggningstillgangar` |
| Företagsinformation | `spiris_foretagsinfo` |
| Användare | `spiris_anvandare` |
| Valutakurs | `spiris_valutakurs` (kräver datum + valutapar) |
| Kundreskontraposter | `spiris_kundreskontraposter` |

**Registret är appens känsligaste rum.** Det visar motparter. Behåll den
befintliga förklaringsraden om vad som ändras och vad som bevaras, och lägg
inte till fält som adaptern inte redan hämtar. Behöver en vy ett fält som inte
finns i adapterns utdata: **stanna och fråga.**

`spiris_anvandare` visar namngivna personer — det är personuppgifter om
tredje man. Visa bara de fält adaptern redan returnerar, och lägg vyn bakom
"Visa detaljer" i stället för i förstablicken.

**Grind U7.**

---

## Etapp U8 — Nytt rum: Säljdokument, samt underlag

Fem läsförmågor saknar hem eftersom det inte finns något rum för dem.

### U8.1 — Adapterfunktioner (se B5)

```
hamta_underlag(klient, include_matched=False) -> list[dict]
hamta_underlag_fil(klient, underlag_id)       -> bytes | tuple
```

`hamta_underlag_fil` hämtar binärt innehåll. **Ladda aldrig ner filen
automatiskt** — visa metadata, och låt användaren begära nedladdningen med en
`st.download_button`. Ett underlag kan innehålla vad som helst.

### U8.2 — Nytt rum 🧾 Säljdokument, i gruppen **Pengar**

| Snabbvy | MCP-motsvarighet |
|---|---|
| Order | `spiris_order` |
| Offerter | `spiris_offerter` |
| Offertutkast | `spiris_offertutkast` |

Deklarera rummet i `parser/rum/`, rita det i `rum_render.rendera_saljdokument`,
registrera det i `app.py`. Flytta hit formulären `saljdokumentutskick` och
`saljdokumentatgard` från Pengar in — de hör till de dokument rummet visar
(**B2**) — och lägg till `offertutkast` (som blev användbart genom U1.1).

Uppdatera antalen i `tests/test_rum_render_atgard.py` och notera det.

### U8.3 — Underlag och bilagor i 📚 Böckerna

Snabbvyn Underlag (`spiris_underlag`, `spiris_hamta_underlag`) läggs i
Böckerna, bredvid formuläret `underlagskoppling` från U5.2 — man kopplar ett
underlag där man ser det.

**Grind U8.**

---

## Etapp U9 — Företagsinställningar

Det sista rummet, och det känsligaste ur ett bokföringsperspektiv.

### U9.1 — Nytt rum ⚙️ Företagsinställningar, i gruppen **Bokföring**

| Snabbvy | MCP-motsvarighet |
|---|---|
| Bokföringslås | `spiris_bokforingslas` (`hamta_bokforingslas` finns) |
| ROT/RUT-inställningar | läses ur samma `companysettings`-väg som `forbered_rotrut` använder |

### U9.2 — `bokforingslas` (uppskjutet från U5.7)

| | |
|---|---|
| Nyckel | `nytt_datum` |
| Varning | "Oåterkalleligt. Låsdatumet kan bara flyttas framåt." |

**Låsdatumet får bara flyttas framåt, och en upplåsning föreslås aldrig** —
beslut D1a i `PLAN_SPIRIS_ETAPP8.md`. Formuläret ska vägra ett datum som är
tidigare än det nuvarande, med en text som förklarar varför i stället för att
bara neka. Sammanfattningen visar nuvarande och nytt datum bredvid varandra.

### U9.3 — `rotrut` (uppskjutet från U5.8)

| | |
|---|---|
| Nycklar | `nuvarande`, `andringar` |
| Ändringsbara fält | `RutMaxAmountForPersBelow65Year`, `RutMaxAmountForPersOver65Year`, `RutReducedInvoicingPercent`, `RotReducedInvoicingMaxAmount`, `RotReducedInvoicingPercent` |

**Se B9:** `nuvarande` läses live innan utkastet skapas. Rendera fälten ur
`spiris_adapter._ROTRUT_ALLOWLIST` — ingen fjärde kopia av listan.

**Hårdkoda ingen procentsats.** Den är lagstiftning, inte en teknisk konstant.
Samma linje som det befintliga ROT-avsnittet i fakturaformuläret håller.

**Grind U9:** ta bort den sista `xfail`-markeringen. **Varje typ i
`GILTIGA_TYPER` har nu ett formulär, och varje formulär ritas ut i exakt ett
rum.**

---

## Etapp U10 — Slutkontroll och avstämning

### U10.1 — Täckningstest för läsförmågorna

Nytt test som, för varje läsande MCP-verktyg i `mcp_server/server.py`, hävdar
att det finns en motsvarande vy i appen — eller att verktyget står i en
uttrycklig, motiverad undantagslista i en **egen konstant i produktionskoden**
(inte i testet), med en kommentar per post som säger varför.

Skillnaden mot det förra, urholkade metatestet: undantagen blir synliga i
koden, kräver en motivering, och kan granskas — de kan inte tyst växa i en
testfil.

### U10.2 — Uppdatera dokumentationen

- `README.md` — avsnittet om Streamlit-appen beskriver i dag bara snabbvyerna
  under Rapporter. Beskriv rummen som de faktiskt ser ut.
- `HISTORIK.md` — en rad per etapp.
- `AI_HANDOVER.md` — avsnitt 5 påstår att allt är slutfört. Rätta det, och
  skriv vad som gäller efter det här arbetet.
- `RISKREGISTER.md` — **R-13** (initiativet hos AI:n) kan bedömas om när U5 är
  klar. Ta inte bort risken; skriv vad som ändrats och vad som återstår.
- `ARKITEKTUR_UI_TACKNING.md` bilaga A och B — kryssa av tabellerna.

### U10.3 — Manuell genomgång

`streamlit run app.py`. Öppna **varje** rum, öppna varje `➕ Ny åtgärd`, och
skapa ett utkast av varje typ mot sandbox. Godkänn inte utkasten — kontrollera
bara att de dyker upp i Beslut med en läsbar sammanfattning. Rapportera vilka
typer som provats.

**Grind U10.** Etappen är den sista.

---

## 11. Stanna och fråga när

- Du skulle behöva ändra en fil i förbudslistan utöver de två avgränsade
  undantagen i §0.4.
- Du skulle behöva ändra ett befintligt test av annat skäl än att ett nytt
  formulär tillkommit i ett rum (då uppdaterar du antalet och rapporterar det).
- Antalet passerade tester minskar.
- En vy skulle behöva visa ett fält som adaptern inte hämtar.
- Du är osäker på om något är en personuppgift.
- Ett formulär skulle behöva fråga efter en e-postadress (**B12** — det ska det
  aldrig).
- En åtgärd verkar behöva en genväg förbi rummet Beslut (**B1** — den ska den
  aldrig).

---

## 12. Rapportmall

```
ETAPP/UPPGIFT: <nummer>
STATUS:  klar | stoppad
TESTER:  före N passed → efter M passed (+K nya, 0 nya röda)
KOMMANDO: python -m pytest tests -q
FILER SOM ÄNDRATS: <sökväg> (+/- rader, kort beskrivning)
BEFINTLIGA TESTER SOM RÖRTS: <ingen | vilka och varför>
MANUELLT PROVAT: <vilka rum som öppnats i streamlit run app.py>
KVALITETSGRIND §0.7: K1 ✔/✖  K2 ✔/✖  K3 ✔/✖  K4 ✔/✖  K5 ✔/✖  K6 ✔/✖  K7 ✔/✖
  (utfall av K2-kommandot: <klistra in>)
ÖVERHOPPAT: <ingenting | vad och varför>
AVVIKELSER: <ingen | beskrivning>
FRÅGOR TILL ARKITEKTEN: <ingen | frågorna>
```

Rapportera aldrig "klar" om sviten inte är grön, om någon K-punkt är ✖, eller om
formuläret ännu inte går att nå i appen.

---

## 13. Sammanfattad ordning

| Etapp | Innehåll | Spärr |
|---|---|---|
| **U1** | Åtta rättningar, inklusive det dödfödda `forbered_offertutkast` | inget nytt byggs före denna |
| **U2** | Tre kontraktstester som gör att gapet inte kan uppstå igen | inget nytt byggs före denna |
| **U3** | Fem föräldralösa formulär får ett rum | |
| **U4** | Fakturavägen återkopplas | |
| **K8** | Utestående skuld från avstämningen 2026-08-11 (§0.7) | inget nytt i U5 före denna |
| **U5** | Sex nya formulär (två skjuts till U9) | |
| **U6** | Läsvyer: Böckerna | KLAR |
| **U7** | Läsvyer: Register | KLAR |
| **U8** | Nytt rum Säljdokument + underlag | KLAR |
| **U9** | Nytt rum Företagsinställningar + de två sista formulären | |
| **U10** | Täckningstest, dokumentation, manuell genomgång | |
