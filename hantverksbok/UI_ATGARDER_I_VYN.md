# Åtgärder i vyn — knapparna och förslagen på samma ställe

**Status:** genomförande klart — steg 1–6 av §8 utförda, 23 nya metatest
(`tests/test_ui_atgardstackning.py`), hela sviten grön. Bokslutsrummet är
nåbart i den körande appen (`app.py` → `rendera_bokslut` → 🧮 Bokslut) med
🔍 och 🧾 byggda, fem knappar spärrade och låsmärkta. Se §9 för en nyans:
godkännandeknappen visas bara för fynd som bär ett `Rattelseforslag`, vilket
med rätta ingen av dagens femton kontroller gör (I-2).
**Skriven:** 2026-08-14 · **Uppdaterad:** 2026-08-14
**Arkitekt:** Claude · **Utförare:** kod-AI · **Granskare:** Claude, efteråt

**Systerdokument:** `BOKSLUTSKONTROLLER.md` (lager 1), `BOKSLUTSPROGRAMMET.md`
(lagerkartan).

---

## 1. Problemet

Två saker fattas i gränssnittet, och de hänger ihop.

**Det första: förmågorna syns inte.** MCP-ytan kan mer än appen visar. En
användare som inte läst dokumentationen har ingen väg att upptäcka att
programmet kan granska bokföringen — det finns ingen knapp som säger det. Detta
är samma täckningsgap som redan är känt, och rotorsaken var urholkade
metatester: när bindningen mellan förmåga och gränssnitt inte testas glider de
isär tyst. §6 stänger det.

**Det andra: förslagen ligger på fel ställe.** Utkastgrinden är rätt — MCP:n
föreslår, en människa godkänner i appen, `elicitation` är förkastat. Men i dag
hamnar varje förslag i **Beslut**-rummet, medan användaren står i det rum där
hen tryckte på knappen. En bokslutsgenomgång med trettio fynd blir trettio
rumsbyten.

Företagaren i förlagan beskrev sitt arbetsflöde som "vilket flyt vi fick". Det
flytet kommer av att fyndet, förklaringen och godkännandet ligger på samma yta.
Grinden ska behållas; platsen ska flyttas.

### 1.1 Vad som *inte* ändras

* Ingenting utförs utan att en människa tryckt på godkänn.
* Godkännandet sker i appen, aldrig via MCP.
* Utkastet skapas fortfarande i kön (`utkast.skapa`) och går fortfarande genom
  `bekrafta_for_sandning`. Livslängden gäller som förut.
* **Beslut**-rummet finns kvar och visar alla utkast oavsett var de skapades.
  Det förblir den fullständiga listan; vyn blir en genväg, inte en ersättning.

Ändringen är alltså *var knappen ritas*, inte *vad som krävs för att gå vidare*.

---

## 2. Ändringen i vy-modellen

### 2.0 Två parallella modeller — läs detta först

Projektet har **två** vy-modeller med nästan samma form, och bara den ena
renderas. Det här är avgörande för var ändringarna nedan ska läggas.

| | `parser/vy_modell.py` | `parser/snabbvyer.py` |
|---|---|---|
| Typer | `Rum`, `Vy`, `Vyresultat` | `Snabbvy`, `Snabbvyresultat` |
| Etikett | `begrepp: Begrepp` — bunden till ordboken | `etikett: str` — fritext |
| Renderas? | **Nej.** Inget ritlager läser `Vy` | **Ja.** `rendera_knapprad` läser `vy.etikett`, `rendera_resultat` tar `Snabbvyresultat` |
| Används av | `parser/rum/*.py` | `SNABBVYER_*`-tuplerna, som `rum_render.py` skickar till `rendera_snabbvyfalt` |

`rum_render.py` anropar alltid `snabbvy_render.rendera_snabbvyfalt(st,
snabbvyer.SNABBVYER_X, …)` — aldrig `RUM_X.vyer`. En `Vy` som läggs i ett rum
blir därför **aldrig ritad**. `Vy` saknar dessutom `.etikett`, som
`rendera_knapprad` läser, så den kan inte ens skickas dit som den ser ut i dag.

**Det som däremot ÄR bundet är rummen.** `tests/test_rum.py:92` jämför
`{r.id for r in rum.RUM}` mot samtliga `url_path` i `app.py` och kräver
likhet. Ett rum kan alltså inte registreras utan att också få en sida i appen —
testsviten faller annars. Registret är inte dött; det är vy-nivån som är det.

**Följd för denna spec:** allt som ska synas läggs på `snabbvyer`-typerna.
`vy_modell`-typerna speglas för att den deklarativa tvillingen inte ska ruttna,
men det är `Snabbvy` och `Snabbvyresultat` som är normativa. En ändring som bara
görs i `vy_modell.py` är per definition osynlig.

En sammanslagning av de två modellerna är rätt på sikt och **ligger utanför
detta arbete**. Gör den inte här.

### 2.1 Åtgärdstyperna

I dag kan ett vyresultat bära rubrik, nyckeltal, sektioner och fotnot — allt är
läsbart, ingenting är handlingsbart. Lägg till en tredje sorts innehåll.

Typerna definieras i `parser/vy_modell.py` (de är rena dataklasser utan
beroenden) och **importeras av `snabbvyer.py`**, så att båda modellerna talar om
samma sak:

```python
@dataclass(frozen=True)
class Atgardsknapp:
    """En handling användaren kan begära från vyn.

    UI-fri: detta är en BESKRIVNING av en knapp, inte en knapp. Ritlagret
    avgör hur den ser ut; vy-lagret avgör att den finns och vad den betyder."""
    etikett: str
    utkasttyp: str                  # måste finnas i utkast.GILTIGA_TYPER
    nyttolast: dict                 # färdig, validerad — vyn har redan räknat
    bekraftelsetext: str            # vad användaren godkänner, i klartext
    varning: str | None = None


@dataclass(frozen=True)
class Atgardsforslag:
    """Ett fynd med en möjlig åtgärd, redo att visas där användaren står."""
    rubrik: str
    allvarlighet: str               # samma tre nivåer som Fynd
    motivering: str
    belopp: str | None = None       # redan formaterad
    konton: tuple[str, ...] = ()
    regel_text: str | None = None
    regel_lank: str | None = None
    rader: tuple[tuple[str, str, str], ...] = ()   # konto, debet, kredit
    knapp: Atgardsknapp | None = None               # None = inget att göra
```

Fältet läggs på **båda** resultattyperna, med `Snabbvyresultat` som den som
faktiskt renderas (§2.0):

```python
# snabbvyer.Snabbvyresultat  — NORMATIV, det är denna som ritas
atgarder: tuple[Atgardsforslag, ...] = ()

# vy_modell.Vyresultat       — spegling, så tvillingen inte ruttnar
atgarder: tuple[Atgardsforslag, ...] = ()
```

Default tom tuple — **alla befintliga vyer fortsätter fungera oförändrade.**

### 2.2 Varför nyttolasten byggs i vy-lagret

Knappen bär en färdig `nyttolast`. Ritlagret ska inte behöva räkna ut något för
att kunna skicka den vidare, och det ska inte finnas två ställen där en
konteringsrad kan konstrueras. Vyn har redan `Fynd` med belopp och konton; den
bygger nyttolasten en gång, och ritlagret bara vidarebefordrar den.

Följden är att nyttolasten går att testa utan Streamlit — vilket är hela poängen
med skiktningen.

### 2.3 Var fynden kommer ifrån

En byggfunktion är ren och får inte läsa filer eller anropa Spiris. Kontrollmotorn
körs därför av ritlagret och läggs i `Vydata`, precis som `vasentlighet` och
`kontotyp_avvikelser` redan görs:

```python
# snabbyer.Vydata
fynd: list | None = None          # list[Fynd] från bokslutskontroll.motor
avstamningsfynd: list | None = None
```

`None` betyder "inte kört", inte "inga fynd". Vyn måste skilja på de två och
säga vilket det är — en tom lista som ser ut som ett rent bokslut när
kontrollen aldrig kördes är precis den sortens tysta fel som gör att någon
lämnar in fel siffror.

---

## 3. Ritlagret

### 3.1 `rendera_resultat`

`snabbvy_render.rendera_resultat` ritar i dag nyckeltal, sektioner och fotnot.
Lägg till åtgärderna efter sektionerna, före fotnoten.

Den funktionen tar emot både `Snabbvyresultat` och `Vyresultat` — de är olika
dataklasser med samma form. Läs därför fältet defensivt:

```python
for forslag in getattr(resultat, "atgarder", ()):
    _rendera_atgardsforslag(st, forslag)
```

Utan `getattr` faller varje befintlig snabbvy. Detta är den enda platsen i
ändringen där ett slarv ger ett fel som syns direkt — de andra är tysta.

### 3.2 `_rendera_atgardsforslag`

Per förslag, i denna ordning:

1. Rubrik med allvarlighetsmarkering (samma färgnivåer som `Sektion.niva`:
   `avvikelse` → röd, `observation` → gul, `upplysning` → neutral).
2. Belopp och konton.
3. Motiveringen, i klartext.
4. Regelhänvisningen som klickbar länk, när den finns.
5. Konteringsraderna som tabell, när de finns.
6. Knappen — bara om `knapp is not None`.

Ett förslag utan knapp är fullt giltigt och vanligt: `A-05`, `K-11` och `K-13`
pekar ut något att titta på utan att ha en självklar rättelse. **Hitta aldrig på
en åtgärd för att fylla ut ytan.**

### 3.3 Knappen och grinden

```
[Godkänn och lägg i kön]
```

Vid tryck: `utkast.skapa(utkasttyp, nyttolast)`, och sedan **visas resultatet på
samma plats** — utkast-id, status och en rad om att det ligger i kön. Ingen
omdirigering, ingen rumsväxling, ingen `st.rerun()` som kastar bort var
användaren var.

Före tryck ska `bekraftelsetext` stå intill knappen. Användaren ska kunna läsa
exakt vad som läggs i kön utan att expandera något.

Grinden är oförändrad: utkastet ligger i kön tills det bekräftas för sändning.
Knappen i vyn skapar ett utkast — den skickar det inte.

---

## 4. Bokslutsrummet

Rummet använder det knappradsmönster som redan finns:
`snabbvy_render.rendera_knapprad` ritar raden, `rendera_resultat` ritar utfallet
under den. Det är precis "klicka på en funktion, se svaret på samma ställe" —
mönstret behöver inte uppfinnas, bara användas.

### 4.0 Fem ändringar krävs för att rummet ska finnas på riktigt

Det räcker inte att lägga en fil i `parser/rum/`. Följ §2.0: rummen är bundna
till appen, vyerna renderas via `snabbvyer`. Alla fem behövs, annars blir
rummet antingen onåbart eller så faller testsviten.

1. **`parser/rum/bokslut.py`** — `RUM_BOKSLUT = Rum(id="bokslut", namn="Bokslut",
   ikon="🧮", vyer=())`. **Tom `vyer`-tupel**, exakt som `RUM_OVERSIKT` redan
   gör. Lägg inte `Vy`-objekt här: de skulle aldrig ritas och skulle bli en
   andra sanning om samma knappar.
2. **`parser/rum/__init__.py`** — importera och lägg `RUM_BOKSLUT` i `RUM`.
3. **`parser/snabbvyer.py`** — `SNABBVYER_BOKSLUT: tuple[Snabbvy, ...]` med de
   sju knapparna enligt §4.1. **Här bor knapparna.**
4. **`parser/rum_render.py`** — `rendera_bokslut()`, byggd efter mönstret i
   `rendera_bockerna`: fyll `Vydata`, anropa
   `snabbvy_render.rendera_snabbvyfalt(st, snabbvyer.SNABBVYER_BOKSLUT,
   "snabbvy_bokslut", vydata)`.
5. **`app.py`** — `st.Page(rum_render.rendera_bokslut, title="Bokslut",
   icon="🧮", url_path="bokslut")` i rätt grupp i `sidor`. Gruppen är
   **Bokföring**, intill Böckerna.

Följdändringar i `tests/test_rum.py`, som i dag hårdkodar antalet rum:

* `test_rum_i_ratt_ordning` — lägg `"bokslut"` i listan, på rätt plats.
* `test_app_py_navigering_grupper` — `total_pages` 13 → 14.

Att den testen måste ändras är inte ett besvär utan beviset på att bindningen
finns: det går inte att registrera ett rum utan att också ge det en sida.

### 4.1 Knapparna

**Hela raden ritas från dag ett.** De som ännu inte är byggda ritas spärrade.
Raden är alltså både en meny och en karta över vad programmet ska kunna.

| Knapp | Vad den gör | Byggd i |
|---|---|---|
| 🔍 **Granska bokföringen** | Kör hela kontrollkatalogen och listar fynden med förslag | lager 1 |
| 🧾 **Kontrollera underlag** | Verifikationer utan kopplat underlag | nu (bygger på befintliga `underlag`) |
| 🏦 **Stäm av kontoutdrag** | Läser kontoutdrag och listar avstämningsfynden | lager 1b |
| 🧮 **Inkomstdeklaration** | Räknar fram INK2R, frågar om INK2S, skriver SRU-filerna | lager 4 |
| 📐 **Bokslutsposter** | Avskrivningar, periodiseringar, skatt, årets resultat | lager 2 |
| 📄 **Årsredovisning** | K2-uppställning, noter, flerårsöversikt | lager 3 |
| 📋 **Stämmoprotokoll** | Mall att fylla i och signera själv | sist |

Ordningen i raden är arbetsgången, inte byggordningen — användaren ska läsa den
uppifrån och ner som en kväll framför sig.

### 4.2 Två sorters spärr, som aldrig får se likadana ut

Det här är den regel som gör spärrade knappar försvarbara i stället för
vilseledande. En knapp kan vara otillgänglig av **två helt olika skäl**, och en
användare som inte kan skilja dem åt tror att programmet är trasigt.

| Läge | Betyder | Hur den ska läsas |
|---|---|---|
| `kommande` | Funktionen finns inte i programmet än | "Det här är inte byggt än." |
| `kraver_data` | Funktionen finns, men underlaget saknas | "Läs in en SIE-fil först." |

`kraver_data` finns redan i modellen: `Vy.kraver` är en mängd förmåger som
källan måste ha, och `rendera_snabbvyfalt` visar redan ett `st.info` när de
saknas. Rör inte den mekaniken — bygg vidare på den.

`kommande` är nytt. Lägg till på **`Snabbvy`** — det är den typ `rendera_knapprad`
faktiskt läser (§2.0) — och spegla på `Vy`:

```python
# snabbvyer.Snabbvy   — NORMATIV
status: Literal["byggd", "kommande"] = "byggd"

# vy_modell.Vy        — spegling
status: Literal["byggd", "kommande"] = "byggd"
```

Default `"byggd"` gör att alla befintliga snabbvyer i alla rum är oförändrade.

### 4.3 Hur en spärrad knapp ska ritas

I `rendera_knapprad`, defensivt läst så att `Snabbvy` utan fältet fortsätter
fungera:

```python
kommande = getattr(vy, "status", "byggd") == "kommande"
kolumn.button(
    etikett,
    disabled=kommande,
    help=hjalptext,
    key=...,
)
```

Krav på utseendet och texten:

* **Låsmarkering i etiketten**, före ikonen: `🔒 🧮 Inkomstdeklaration`.
  Utgråning ensam räcker inte — den betyder "just nu inte" i de flesta
  gränssnitt, inte "finns inte".
* **`help` säger vad den ska göra och att den inte är byggd.** Exempel:
  *"Räknar fram inkomstdeklaration 2 och skriver SRU-filer du själv laddar upp
  hos Skatteverket. Inte byggd än."*
* **Ingen datumutfästelse.** Aldrig "kommer i höst", aldrig ett versionsnummer.
  En karta får visa vägen utan att lova ankomsttid.
* **Icke-klickbar.** `disabled=True`, inte en klickbar knapp som visar ett
  meddelande. En halvfungerande väg är värre än ingen väg.
* **Ingen spärrad knapp får räknas som en förmåga någon annanstans** — inte i
  `README.md`, inte i verktygsbeskrivningar, inte i MCP-ytan. Raden är en karta
  inuti appen, inte en marknadsföringstext.

### 4.4 Vad detta inte ändrar

Spärrade knappar är tillåtna **för funktioner som ska byggas i den här
lagerkartan**. Det öppnar ingenting annat:

* `BOKSLUTSPROGRAMMET.md` §7.3 gäller ordagrant och oförändrat. Det får inte
  finnas någon knapp — spärrad eller inte — för inlämning till Bolagsverket,
  och ingen text som nämner den vägen. En spärrad knapp för något som ligger
  bakom en myndighetsregistrering vi inte har vore en utfästelse om att vi tänkt
  skaffa den.
* En funktion som avförs ur planen ska ha sin knapp **borttagen**, inte
  permanent spärrad. En låst dörr som aldrig öppnas är ett löfte som bryts
  långsamt.

### 4.5 Årsredovisningsknappen

Spärrad tills lager 3 landar, som övriga. När 📄 byggs visar den **bara den
färdiga uppställningen**. Ingen inlämning, ingen länk, inget omnämnande av någon
inlämningstjänst — se `BOKSLUTSPROGRAMMET.md` §7.3, som gäller ordagrant.

Dess `help`-text i spärrat läge får därför säga att den ställer upp
årsredovisningen enligt K2 — inte att den lämnar in den.

---

## 5. Åtgärdsbadgen

`parser/navigering.py:90`, `hitta_verifikationsavvikelser`, är redan en seam:
den returnerar alltid tom lista och dokumenterar sig själv som platsen där
"obalanserade verifikat, saknad vertext, kontotypavvikelser" ska kopplas in.
Det är exakt kontrollmotorn.

Koppla in den. Varje `Fynd` med allvarlighet `avvikelse` blir en
`Verifikationsavvikelse`, så att den röda badgen på **Åtgärder** tänds när
bokföringen har fel i sig.

Två krav ur seamens egen docstring, som fortfarande gäller:

* **Kasta aldrig.** Ett fel i sökningen får inte tyst tömma listan och måla
  badgen grön. Fånga, returnera det som gick att räkna fram, logga lokalt.
* **Räkna bara det obehandlade.** Ett fynd som användaren redan gjort något åt
  ska inte fortsätta lysa rött.

Bara `avvikelse` räknas in i badgen. `observation` och `upplysning` syns i
rummet men gör inte navigeringen röd — annars är badgen alltid röd och slutar
betyda något.

---

## 6. Metatester

Täckningsgapet uppstod för att bindningen mellan förmåga och gränssnitt inte
testades. Dessa test är därför en del av leveransen, inte en efterrätt.

`tests/test_ui_atgardstackning.py`:

1. **Varje byggd kontroll når gränssnittet.** Iterera över
   `bokslutskontroll.motor.KONTROLLER` och visa att varje `kontroll_id` kan
   nå en vy i bokslutsrummet. En ny kontroll som ingen vy visar ska fälla testet.
2. **Statusen är sann i båda riktningarna.** För varje knapp i bokslutsrummet:
   * `status == "byggd"` ⇒ dess `bygg`-funktion är implementerad och returnerar
     ett `Vyresultat` för tom `Vydata` utan att kasta.
   * `status == "kommande"` ⇒ dess `bygg` är platshållaren, **inte** en färdig
     funktion.

   Andra halvan är den som är lätt att glömma och som återskapar täckningsgapet:
   en funktion som byggts men vars knapp lämnats kvar som `kommande` är osynlig
   för användaren trots att den finns. Testet ska fälla på det.
3. **Varje `utkasttyp` i en `Atgardsknapp` finns i `utkast.GILTIGA_TYPER`.**
   En felstavad typ ger annars ett utkast som aldrig kan utföras.
4. **Nyttolasten validerar.** För varje åtgärdsknapp som en vy kan producera:
   nyttolasten passerar motsvarande `bygg_nyttolast` utan att kasta.
5. **`rendera_resultat` tål ett `Snabbvyresultat` utan `atgarder`.** Skyddar
   §3.1.
6. **En `kommande` knapp går inte att trycka på.** Ritlagret sätter
   `disabled=True` för varje vy med `status == "kommande"`, och etiketten bär
   låsmarkeringen. Skyddar §4.3.
7. **De två spärrlägena skiljs åt.** En vy som är `byggd` men saknar data ger
   `kraver_data`-beteendet (`st.info` om saknad förmåga), inte låsmarkeringen.
   Skyddar §4.2 — det är den förväxling som får programmet att se trasigt ut.
8. **Hela kedjan från knapptupel till sida.** AST-test i tre led:
   * varje `SNABBVYER_*`-tupel i `snabbvyer.py` refereras från `rum_render.py`,
   * varje `rendera_*` som `rum_render.py` definierar och som ritar en knapprad
     förekommer som `st.Page(...)` i `app.py`,
   * varje `st.Page`-`url_path` motsvarar ett id i `RUM` (finns redan som
     `test_rum.py:92` — låt den vara, hänvisa till den).

   **Detta är testet som saknades.** Gapet mellan `parser/rum/`s `Vy`-objekt och
   det som faktiskt ritas kunde uppstå just för att inget test följde kedjan hela
   vägen ut till `app.py`. Skriv det generellt, för alla rum — inte bara för
   bokslutsrummet. Det får gärna fälla på befintliga rum; rapportera i så fall
   vad det hittar i stället för att undanta dem.

Test 1 och 2 är de som faktiskt håller gapet stängt. Skriv dem först, och skriv
dem så att de går sönder när någon lägger till en förmåga utan gränssnitt eller
bygger en funktion utan att låsa upp den — inte så att de går att tillfredsställa
med en tom lista.

---

## 7. Invarianter

**U-1. Ingen Streamlit-import i `vy_modell.py`, `snabbyer.py` eller vy-modulerna.**
Bevakas av AST-test, som i dag.

**U-2. Appen visar omaskerad data.** Bokslutsrummet kör motorn på den råa
`SIEFil`:en. MCP-vägen maskerar först. Samma invariant som `BOKSLUTSKONTROLLER.md`
I-3, och den ska testas i båda riktningarna.

**U-3. Knappen skapar utkast, aldrig mer.** Ingen vy-modul och inget ritlager
får anropa `bekrafta_for_sandning`, `utfor_utkast` eller någon skrivfunktion i
`spiris_adapter`. AST-test.

**U-4. `None` och tom lista betyder olika saker.** `Vydata.fynd is None` →
"kontrollen har inte körts". `[] ` → "kontrollen kördes och hittade inget".
Vyn säger vilket. Testa båda.

**U-5. En knapps status är sann.** `byggd` betyder att funktionen finns och går
att köra; `kommande` betyder att den inte gör det och att knappen är spärrad och
låsmärkt. Ingen knapp får ligga i fel läge åt något håll. §4.2–4.3,
upprätthållen av metatest 2, 6 och 7.

**U-6. Spärr på grund av saknad funktion och spärr på grund av saknad data är
skilda tillstånd.** De renderas olika och testas separat. §4.2.

**U-7. En förmåga är inte byggd förrän den är nåbar i den körande appen.**
Kedjan `Snabbvy` → `SNABBVYER_*` → `rendera_*` i `rum_render.py` → `st.Page` i
`app.py` → id i `RUM` ska vara hel. En vy som bara finns i `parser/rum/` är inte
levererad. §2.0, upprätthållen av metatest 8.

---

## 8. Genomförande

Sex steg. Testsviten grön efter varje.

1. **`Atgardsknapp`, `Atgardsforslag`, `Vyresultat.atgarder`** i `vy_modell.py`,
   plus `fynd` och `avstamningsfynd` i `Vydata`. Inga renderare rörda än.
   *Acceptans:* alla befintliga vytester gröna utan ändring; nya dataklasser
   konstruerbara och frysta.
2. **`_rendera_atgardsforslag` och kopplingen i `rendera_resultat`** enligt §3.
   *Acceptans:* metatest 5; ett förslag utan knapp ritas utan att kasta; ett
   förslag med knapp ritar knappen och bekräftelsetexten.
3. **`Vy.status` och spärrade knappar** enligt §4.2–4.3: fältet i `vy_modell.py`
   med default `"byggd"`, och `disabled`-hanteringen i `rendera_knapprad`.
   *Acceptans:* metatest 6 och 7; alla befintliga knapprader i alla rum ritas
   oförändrade (default gör att inget annat rum påverkas).
4. **Bokslutsrummet med HELA knappraden** enligt §4.0 och §4.1 — alla fem
   ändringar i §4.0, med 🔍 och 🧾 som `byggd` och övriga fem som `kommande`.
   *Acceptans:* rummet är **nåbart i den körande appen** — det finns som
   `st.Page` i `app.py` och `test_rum.py` är uppdaterad; alla sju knappar ritas;
   de fem spärrade är låsmärkta, icke-klickbara och har `help`-text utan
   datumutfästelse; en vald byggd knapp visar sitt resultat under raden;
   metatest 1–2 och 8 gröna.
5. **Godkännandeflödet** enligt §3.3 — utkast skapas, status visas på plats,
   ingen omdirigering.
   *Acceptans:* metatest 3–4; U-3 verifierad med AST-test; ett godkännande
   lämnar användaren kvar i samma rum och samma vy.
6. **Badgen** enligt §5.
   *Acceptans:* en trasig bokföring tänder badgen; ett kastande anrop lämnar
   badgen oförändrad i stället för grön; endast `avvikelse` räknas.

Därefter, per lager: **byt en knapps `status` från `kommande` till `byggd`** och
koppla in dess byggfunktion. Det är hela gränssnittsarbetet för ett nytt lager —
raden ändras inte.

---

## 9. Klart

1. Steg 1–6 utförda, hela sviten grön.
2. Metatest 1–8 finns och fäller vid rätt sorts regression.
3. U-1 … U-7 har varsitt test namngivet efter sig.
4. En användare som aldrig läst dokumentationen kan öppna appen, se
   **Bokslut**, trycka 🔍 och få fynd med förklaring och godkännandeknapp utan
   att lämna rummet — och genom att läsa raden förstå vad programmet ska kunna
   utan att någon spärrad knapp ger sken av att redan kunna det.
5. Ingenting i gränssnittet nämner inlämning till Bolagsverket — varken som
   text, länk eller spärrad knapp.

Granskningen börjar med U-2 och U-3 — vilken väg som ser omaskerad data, och att
ingen knapp kan utföra något.
