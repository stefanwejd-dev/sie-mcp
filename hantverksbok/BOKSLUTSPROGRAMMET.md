# Bokslutsprogrammet — lagerkarta och genomförande

**Status:** lager 1 klart (steg 1–8 av 9 i `BOKSLUTSKONTROLLER.md`; steg 9
valfritt) — alla sexton kontroller finns i motorn, nåbara via MCP
(`bokslutskontroll`/`spiris_bokslutskontroll`) och via appen (🧮 Bokslut,
se `UI_ATGARDER_I_VYN.md`). Lager 1b, 2, 3 och 4 är fortfarande bara
specificerade.
**Skriven:** 2026-08-14 · **Uppdaterad:** 2026-08-14
**Arkitekt:** Claude · **Utförare:** kod-AI · **Granskare:** Claude, efteråt

**Systerdokument:**
`BOKSLUTSKONTROLLER.md` — lager 1 i detalj (läs den först; datamodellen `Fynd`
och motorn definieras där och återanvänds av hela detta dokument).
`UI_ATGARDER_I_VYN.md` — knapparna och hur förslag visas där användaren står.

---

## 1. Målbilden

Kravlistan kommer från en verklig företagare som på en kväll gjorde bokslut,
årsredovisning, inkomstdeklaration och stämmoprotokoll med en AI-agent. Hans
arbetsgång, uppdelad i det som är vår uppgift och det som inte är det:

| | Vad han gjorde | Vår sak? |
|---|---|---|
| A | Löpande bokföring automatiskt i affärssystemet, kort med kvittoflöde | nej — affärssystemets jobb |
| B | AI letade upp och laddade upp saknade kvitton | delvis — `spiris_hamta_underlag`, `forbered_underlagskoppling` |
| C | Tog ut kontoutdrag från alla konton, inklusive kort och skattekonto | **ja — lager 1b** |
| D | Tog ut SIE-export och kopplade en MCP till affärssystemet | **finns** |
| E | AI hittade fel: gamla skvalpsummor, felkategoriserade inköp, saknade underlag | **ja — lager 1 + 1b** |
| F | Resonerade kring avvikelserna tillsammans med AI:n | **ja — `Fynd.motivering` + regelhänvisning** |
| G | AI presenterade rättelser som bokfördes efter godkännande | **finns — utkastkön; men fel plats i UI, se `UI_ATGARDER_I_VYN.md`** |
| H | Bokslut | **ja — lager 2** |
| I | Årsredovisning, digitalt inlämnad och signerad | **ja — lager 3, med förbehåll (§2)** |
| J | Inkomstdeklaration | **ja — lager 4** |
| K | Stämmoprotokoll | **ja — §8, litet** |

Det som gjorde störst intryck i hans berättelse var inte bokslutet utan **E**:
fel som både han och en tidigare redovisningsassistent hade missat. Notera
varifrån de kom. "Saker jag missat att exportera" är per definition sådant som
*inte finns i bokföringen* — det kan bara hittas genom att jämföra mot en
utomstående källa. Det är lager 1b, och det är därför det ligger tidigt.

---

## 2. De två myndighetsgrindarna

Avgörande för vad som alls är möjligt, och de är olika. Båda kontrollerade
2026-08-14.

### 2.1 Skatteverket — öppet

Inkomstdeklaration 2 lämnas som två SRU-filer (`INFO.SRU` + `BLANKETTER.SRU`)
via e-tjänsten **Filöverföring**, varefter firmatecknare, deklarationsombud
eller vd signerar på Mina sidor. **Vilket program som helst får skapa
filerna** — ingen godkänd integration, inget certifikat, ingen registrering.

Detta passar utkastgrinden exakt: filen är förslaget, signeringen hos
Skatteverket är godkännandet, och det är en människa som gör den. sie-mcp
skickar aldrig något; den skriver två filer till disk.

### 2.2 Bolagsverket — stängt

Digital inlämning av årsredovisning kräver att man är registrerad
**programvaruleverantör** med certifikat, brandväggsöppningar och prenumeration
på händelser. Grinden sitter på *överföringen*, inte på *dokumentet*.

**Beslut: sie-mcp blir inte programvaruleverantör.** Det är certifikathantering,
BankID-integration och ett löpande ansvar mot en myndighet — en helt annan sorts
åtagande än det friskrivningen i `DISCLAIMER_AND_TERMS.md` beskriver.

Vägen blir i stället att producera underlaget och låta användaren lämna in via
en tjänst som redan är godkänd. Se §7.3 om hur den förberedelsen ska se ut —
och särskilt om att den **inte får synas i gränssnittet**.

---

## 3. Lagerkartan

| Lager | Innehåll | Dokument | Ordning |
|---|---|---|---|
| **1** | Bokslutskontroller på bokförd data | `BOKSLUTSKONTROLLER.md` | 1 |
| **1b** | Kontoutdragsavstämning mot utomstående källa | §4 här | 2 |
| **4** | Inkomstdeklaration 2 via SRU | §5 här | 3 |
| **2** | Bokslutstransaktioner som utkast | §6 här | 4 |
| **3** | K2-årsredovisning | §7 här | 5 |

**Ordningen är inte lagernumren.** Den följer nytta delat med kostnad:

* **1b före 4** därför att den hittar fel som inget annat hittar, och därför att
  ett bokslut som bygger på en oavstämd bank är värdelöst hur fint det än ser ut.
* **4 före 2 och 3** därför att myndighetsvägen är öppen (§2.1), SRU-koderna
  redan ligger i parsern (§5.1), och nyttan är omedelbart mätbar i kronor för
  användaren.
* **3 sist** därför att den är störst och den enda som stöter i en grind.

---

## 4. Lager 1b — kontoutdragsavstämning

Den enda kontrollen som ser något bokföringen inte innehåller.

### 4.1 Vad den gör

Läser ett kontoutdrag från en utomstående källa och jämför det, rad för rad, mot
de bokförda transaktionerna på motsvarande konto. Tre sorters fynd:

| Id | Rubrik | Betyder |
|---|---|---|
| **A-01** | Banktransaktion saknas i bokföringen | Raden finns på utdraget men inte bokförd — det här är "saker jag missat att exportera" |
| **A-02** | Bokförd post saknas på kontoutdraget | Bokförd men aldrig genomförd, eller bokförd på fel konto |
| **A-03** | Beloppet skiljer | Matchad på datum och motpart, men olika belopp |
| **A-04** | Utgående saldo stämmer inte | Kontoutdragets slutsaldo ≠ kontots `#UB` |
| **A-05** | Kontoutdraget täcker inte hela räkenskapsåret | Upplysning: avstämningen är ofullständig och får inte tolkas som ren |

`A-04` är den viktigaste och den billigaste. Stämmer slutsaldot är resten
detaljer; stämmer det inte finns det med säkerhet något att hitta.

### 4.2 Format

**Beslut: två vägar in, ingen gissning.**

1. **camt.053** (ISO 20022 XML) — bankernas standardiserade kontoutdrag.
   Strukturerat, självbeskrivande, går att tolka utan konfiguration. Bygg denna
   först och gör den till den rekommenderade vägen.
2. **CSV med en kolumnprofil** — varje bank har sitt eget format. Användaren
   anger en gång vilken kolumn som är datum, belopp, text och saldo; profilen
   sparas per konto. **Kolumnerna gissas aldrig automatiskt.** En felgissad
   beloppskolumn producerar en avstämning som ser ut att stämma och inte gör det,
   vilket är värre än ingen avstämning alls.

Skattekontot och kortleverantörer (Pleo och liknande) omfattas av samma två
vägar — deras exporter är CSV. Skatteverket har inget öppet API för det enskilda
företagets skattekonto; utdraget måste hämtas av användaren. Säg det rakt ut i
gränssnittet i stället för att låta användaren leta efter en knapp som inte finns.

### 4.3 Matchningen

Deterministisk, i tre pass, och **aldrig med en språkmodell**:

1. **Exakt:** samma datum och samma belopp → matchad.
2. **Nära i tid:** samma belopp inom ± `matchningsfonster_dagar` → matchad,
   men markerad som osäker och visad som sådan.
3. **Rest:** allt omatchat blir A-01 respektive A-02.

Ett belopp får matchas mot **exakt en** motpart. Två bokförda poster på 1 000 kr
och en utdragsrad på 1 000 kr ger en match och en A-02 — inte två matcher.
Detta är den lättaste buggen att skriva och den svåraste att upptäcka: skriv
testet först.

### 4.4 Sekretess — läs detta innan du rör en rad

**Ett kontoutdrag är det mest personuppgiftstäta materialet i hela systemet.**
Varje rad bär en motparts namn, ofta en privatpersons. Det är värre än SIE-filen.

* Filerna läses genom en sökvägsvakt av samma slag som `_tillaten_siefil`, med
  en egen miljövariabel (`SIE_MCP_KONTOUTDRAG_KATALOG`). Fail-closed: utan
  konfiguration tillåts ingenting.
* MCP-vägen maskerar **före** kontrollen, precis som lager 1 (invariant I-3).
  Utdragets fritextfält går genom `_maskera_fritext`.
* Kontoutdragsfiler får aldrig kopieras, cachas eller loggas av systemet.
  Läs, jämför, släpp.
* `.gitignore` utökas med de format som kan innehålla utdrag.

### 4.5 Genomförande

Modulen är `parser/avstamning/` med samma form som `parser/bokslutskontroll/`.
Den producerar **samma `Fynd`-typ** och registreras i **samma motor** — en
avstämningsavvikelse och en bokslutsavvikelse är samma sak för användaren och
ska visas på samma sätt.

Steg, ett i taget, testsvit grön efter varje:

1. `camt053.py` — parser till en neutral `Utdragsrad` (datum, belopp, text,
   motpart, referens) plus `Utdrag` (konto, period, ingående och utgående saldo).
2. `csvprofil.py` — kolumnprofil, sparad per konto; ingen autodetektering.
3. `matchning.py` — de tre passen i §4.3, ren funktion, inga sidoeffekter.
4. `kontroller.py` — A-01 … A-05 som vanliga kontroller i motorns register.
5. Poster för `A-01` … `A-05` i `regelverk/regelregister.toml`.
   **Laghänvisningarna skriver Claude, inte utföraren** — samma regel som i
   `BOKSLUTSKONTROLLER.md`. Rapportera att posterna behövs; skriv dem inte.
6. Sökvägsvakt, maskering och `.gitignore` enligt §4.4, med test per punkt.

---

## 5. Lager 4 — Inkomstdeklaration 2 via SRU

### 5.1 Utgångsläget är bättre än det ser ut

`parser/sie4_parser.py:470` läser redan `#SRU` in i `Konto.sru_koder` — och
ingenting använder dem. SRU-koden **är** mappningen från BAS-konto till fält i
räkenskapsschemat. Halva arbetet ligger färdigt i parsern.

### 5.2 Vad som produceras

Två filer, som användaren själv laddar upp i Filöverföring:

* `INFO.SRU` — uppgiftslämnaren.
* `BLANKETTER.SRU` — huvudblankett INK2 plus bilagorna INK2R (räkenskapsschema)
  och INK2S (skattemässiga justeringar).

**sie-mcp skickar ingenting och signerar ingenting.** Filerna skrivs till disk;
uppladdning och signering gör människan hos Skatteverket. Det är utkastgrinden,
i myndighetsversion.

### 5.3 Den bindande begränsningen

**Fältkoderna får inte gissas.** SRU-koder och blankettidentiteter fastställs av
Skatteverket och ändras per taxeringsår. En felaktig kod ger en deklaration som
går igenom filkontrollen och innehåller fel siffra i fel ruta.

Därför:

* Alla koder ligger i `regelverk/sru_koder_<taxeringsar>.toml`, aldrig i Python.
* Registret fylls **från Skatteverkets publicerade specifikation**, av Claude
  eller av Stefan — inte av utföraren, och inte ur minnet.
* Saknas en kod i registret ska genereringen **avbrytas med besked om vilken
  kod som saknas**. Den får aldrig utelämna fältet tyst och aldrig gissa.

Utföraren bygger alltså filformatet, mappningsmotorn och kontrollerna — men
kodregistret levereras separat. Börja med formatet och en handfull konton, mot
ett register som bara innehåller dem.

### 5.4 Vad som inte går att härleda

INK2R går att räkna fram ur bokföringen via SRU-koderna. **INK2S gör det inte.**
Skattemässiga justeringar — ej avdragsgilla kostnader, ej skattepliktiga
intäkter, periodiseringsfond, outnyttjat underskott — är bedömningar som kräver
uppgifter som inte finns i verifikationerna.

Konstruktionen blir därför: räkna fram det som går, **fråga människan om
resten**, och skriv aldrig en siffra i INK2S som systemet hittat på. Ett fält
som varken är härlett eller besvarat lämnas tomt och redovisas som tomt i
sammanställningen.

Vissa poster är delvis härledbara — konto 6072 (ej avdragsgill representation)
och 7622 (ej avdragsgill sjukvård) är exempel där BAS-praxis pekar rätt. Föreslå
dem som ifyllnadsförslag med kontot som motivering, låt människan bekräfta.

### 5.5 Genomförande

1. `sru/format.py` — skriva och läsa SRU-filformatet. Testas mot ett känt
   exempel innan något mappas.
2. `sru/register.py` — läser kodregistret; avbryter vid saknad kod (§5.3).
3. `sru/ink2r.py` — härleder räkenskapsschemat ur `Konto.sru_koder` + saldon.
4. `sru/ink2s.py` — härleder det härledbara, ställer resten som frågor.
5. `sru/skriv.py` — producerar de två filerna till en katalog användaren valt.
6. Kontroller: summan i INK2R mot resultat- och balansräkningen; konto utan
   SRU-kod i kontoplanen (vanligt och viktigt) blir ett eget fynd.

---

## 6. Lager 2 — bokslutstransaktioner

Allt går genom `forbered_verifikat` och utkastkön. Ingenting bokförs av systemet.

| Post | Underlag | Kommentar |
|---|---|---|
| Avskrivningar enligt plan | Anläggningsregistret (`spiris_anlaggningstillgangar`) | SIE4 bär inget anläggningsregister — vägen finns bara för Spiris. Säg det. |
| Periodiseringar | Lager 1:s K-11-fynd | Fyndet pekar ut posten, lager 2 räknar beloppet |
| Momsavstämning per skattesats | `hamta_momskoder`, `hamta_momsrapporter` | Den finkorniga kontroll som medvetet lämnades utanför lager 1 |
| Beräknad bolagsskatt | Resultat efter justeringar × skattesats ur registret | Bygger på lager 4:s INK2S — därför efter lager 4 |
| Årets resultat | 8999 → 2099 | Sist av allt |

Ordningen mellan posterna är inte valfri: avskrivningar och periodiseringar
påverkar resultatet, resultatet påverkar skatten, skatten påverkar årets
resultat. Motorn ska räkna dem i den ordningen och säga vilken post som beror på
vilken.

---

## 7. Lager 3 — K2-årsredovisning

### 7.1 Omfattning

Årsredovisning enligt K2 (BFNAR 2016:10) för aktiebolag utan revisor:
förvaltningsberättelse, resultaträkning, balansräkning, noter, flerårsöversikt
och förändringar i eget kapital.

### 7.2 Konstruktion

En dataklass `Arsredovisning` som är **helt fri från presentation** — samma
skiktning som `Vyresultat`: innehållet beräknas, ritlagret ritar. Uppställningen
följer ÅRL:s scheman; posterna härleds ur saldon och BAS-intervall på samma sätt
som lager 4:s räkenskapsschema, men efter ÅRL:s indelning, inte SRU:s.

Förvaltningsberättelsens fritext (verksamhetens art, väsentliga händelser)
skrivs av människan. Systemet får föreslå en struktur, aldrig påstå ett
sakförhållande om bolaget.

### 7.3 Gredor-förberedelsen — kod, inte gränssnitt

Inlämningen är gated (§2.2). Förberedelsen som ska finnas i kod, och bara där:

* En serialiseringsseam — `arsredovisning/export.py` — som kan skriva
  `Arsredovisning` till ett strukturerat utbytesformat.
* Ingen kod som anropar Bolagsverket. Ingen certifikathantering. Ingen BankID.
* Ingen inlämningsfunktion, ens avstängd.

**Och uttryckligen: ingenting av detta får synas i gränssnittet.**

* Ingen knapp, ingen flik, ingen vy och ingen text som nämner Gredor eller
  digital inlämning. **Inte heller en spärrad knapp** — spärrade knappar är
  tillåtna för det som ska byggas (`UI_ATGARDER_I_VYN.md` §4.2), och det här
  ska inte byggas.
* Inget omnämnande i `README.md`, i menyer eller i hjälptexter.
* Ingen länk någonstans.

Skälet är inte teknik utan ansvar. En knapp är ett löfte. Så snart användaren
ser något som antyder att programmet kan lämna in en årsredovisning har vi
utfäst en förmåga som ligger bakom en myndighetsregistrering vi inte har.
Förberedelsen finns för att den dagen det blir aktuellt ska arbetet inte behöva
göras om — inte för att antyda att dagen är nära.

Utföraren: om du är osäker på om något hör till gränssnittet eller inte, hör det
till gränssnittet. Fråga.

---

## 8. Stämmoprotokoll

Minst av allt och sist i kedjan. En mall som fylls med bolagets uppgifter,
räkenskapsårets siffror och resultatdispositionen. Produceras som ett dokument
användaren själv signerar.

Systemet fattar inga beslut åt stämman. Utdelningens storlek, ansvarsfrihet och
resultatdisposition är beslut, inte beräkningar — de fylls i av människan, och
mallen ska vara skriven så att det är uppenbart.

---

## 9. Ansvarsgränsen genom hela programmet

Den håller likadant i varje lager, och det är den enda regeln som aldrig får
förhandlas:

1. **Systemet producerar. Människan beslutar och lämnar in.**
   Ingen fil skickas till en myndighet av programmet. Ingen bokföring skrivs utan
   ett utkast som en människa godkänt i appen.
2. **Ingen språkmodell i en beräkning.** Modellen förklarar fynd och formulerar
   text. Den räknar inte, klassificerar inte och avgör inte om något är ett fel.
3. **Ingen gissad siffra.** Ett fält som varken är härlett eller besvarat lämnas
   tomt och redovisas som tomt. Detta gäller SRU-koder, skattesatser,
   deklarationsfält och noter lika hårt.
4. **Alla parametrar i register, aldrig i kod.** Skattesatser, SRU-koder,
   avgiftsprocent och kontolistor ändras utan att koden gör det.

---

## 10. Beroenden

```
lager 1  (kontroller)
   │
   ├── lager 1b (avstämning) ──┐   delar Fynd + motor + UI
   │                           │
   └───────────────────────────┴── UI_ATGARDER_I_VYN.md
                   │
                   ▼
              lager 4 (INK2/SRU)
                   │
                   ▼
              lager 2 (bokslutstransaktioner)
                   │
                   ▼
              lager 3 (årsredovisning) ──► Gredor-seam, ej i UI
                   │
                   ▼
              stämmoprotokoll
```

Lager 1 och 1b delar `Fynd`, motor, register och vy. Bygg dem som ett system,
inte som två.
