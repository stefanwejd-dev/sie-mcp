# Bokslutskontroller — arkitektur och genomförande

**Status:** genomförande klart — samtliga nio steg utförda (modell, register,
motor, fixturbyggare, grupp A, grupp B, grupp C, väsentlighets-/regeltest,
MCP-verktygen, vyn, regeltextuppslaget). `bokslutskontroll`/
`spiris_bokslutskontroll`/`hamta_regeltext` finns i MCP-ytan; Bokslutsrummet
(🧮, `UI_ATGARDER_I_VYN.md`) är nåbart i den körande appen med 🔍 Granska
bokföringen byggd. Steg 9b (Skatteverkets tal maskinellt in i registret) är
medvetet ogjort — specen begär det först när lager 2 påbörjas.
**Skriven:** 2026-08-14 · **Uppdaterad:** 2026-08-14
**Arkitekt:** Claude · **Utförare:** kod-AI · **Granskare:** Claude, efteråt

**Levereras med specen:** `regelverk/regelregister.toml` är redan skriven. Den
innehåller samtliga sexton kontroll-id, deras laghänvisningar med ordagrann
lydelse, och de parametrar kontrollerna jämför mot. Varje paragraf är hämtad
och läst i Riksdagens öppna data 2026-08-14. **Skriv inte om den filen och lägg
inte till egna paragrafer i den** — laghänvisningar är precis den sorts uppgift
en kod-AI inte ska producera. Behövs en ändring: rapportera vad som fattas.

---

## 0. Läsanvisning

Detta dokument är både arkitektur och arbetsorder. Det är skrivet för att kunna
utföras av en implementerande kod-AI utan att den behöver fråga om designval.

* **§1–§4** är *varför* och *vad*. Läs dem innan du rör en fil. De innehåller
  ställningstaganden som inte får omprövas under genomförandet.
* **§5** är kontrollkatalogen — den normativa definitionen av varje kontroll.
  Formlerna där är bindande. Uppfinn inga egna gränsvärden.
* **§6–§7** är filkarta och de nio stegen med acceptanskriterier. Utför ett steg
  i taget, i ordning, och kör hela testsviten efter varje steg.
* **§8** beskriver kopplingen till systerprojektet `quiet_chatt`.
* **§9** listar vad som medvetet *inte* ingår. Bygg det inte.

När specen och koden säger emot varandra vinner specen — men rapportera
motsägelsen i stället för att tysta den.

---

## 1. Vad detta är

Ett **deterministiskt kontrollskikt** som går igenom ett räkenskapsår och
producerar en lista av *fynd*: sådant som avviker, saknas eller inte stämmer,
med belopp, berörda konton, en motivering på svenska och en hänvisning till den
regel som gör saken till en avvikelse.

Det är lager 1 i utbyggnaden mot bokslutsstöd. Hela lagerkartan och ordningen
mellan lagren finns i `BOKSLUTSPROGRAMMET.md`:

| Lager | Innehåll | Detta dokument |
|---|---|---|
| **1** | **Bokslutskontroller på bokförd data** | **ja** |
| 1b | Kontoutdragsavstämning mot utomstående källa | nej — `BOKSLUTSPROGRAMMET.md` §4 |
| 4 | Inkomstdeklaration 2 via SRU | nej — §5 |
| 2 | Bokslutstransaktioner som utkast | nej — §6 |
| 3 | Årsredovisning enligt K2 | nej — §7 |

Lager 1b delar `Fynd`, motor, register och vy med lager 1 — bygg dem som ett
system. Allt som står här om datamodell, motor och invarianter gäller därför
lika hårt där.

### 1.1 Vad det inte är

* Det är **inte en AI-analys.** Ingen språkmodell är inblandad i att avgöra om
  något är ett fynd. Motorn räknar; modellen får bara förklara det räknade för
  användaren. Detta är samma princip som bär `quiet_chatt`: kravet är
  arkitektur, inte instruktion. En modell som *kan* hitta på ett fynd kommer
  förr eller senare att göra det.
* Det är **inte en rättningsmotor.** Ett fynd får bära ett *förslag* i form av
  text och konteringsrader, men lager 1 skriver ingenting — varken till Spiris
  eller till utkastkön. Se §3, invariant I-2.
* Det är **inte revisionsrådgivning.** Utfallet ärver hela ansvarsfriskrivningen
  i `DISCLAIMER_AND_TERMS.md` och ska formuleras därefter i verktygens
  docstrings, precis som `granska_kontotyper` redan gör.

### 1.2 Varför det är rätt sak att bygga först

Kontrollerna nedan går att räkna fram ur data som redan finns i `SIEFil`.
De kräver ingen ny extern anslutning, ingen ny behörighet och ingen ny
rättslig bedömning utöver den som redan är gjord. Samtidigt är det de som ger
den upplevda nyttan — "den går igenom min bokföring och hittar felen" — som
lager 3 annars skulle få bära ensamt till tiodubbla kostnaden.

---

## 2. Ställningstaganden

Beslut som är fattade. Skäl anges för att de ska gå att ompröva medvetet
senare, inte för att de ska omprövas nu.

**B-1. Motorn arbetar på `SIEFil`, inte på ett nytt mellanformat.**
`parser/spiris_adapter.py:160` (`hamta_siefil_fran_spiris`) bygger redan en
`SIEFil` ur Spiris. En motor som tar `SIEFil` täcker därmed båda vägarna —
SIE4-fil och affärssystem — utan en rad extra kod. Ett nytt mellanformat vore
en tredje sanning om samma data.

**B-2. En kontroll är en ren funktion `SIEFil -> list[Fynd]`.**
Inga sidoeffekter, ingen I/O, ingen klocka, inget nätverk. Det är det som gör
dem testbara med syntetiska `SIEFil`-objekt och det som gör utfallet
reproducerbart. En kontroll som behöver "dagens datum" tar det som argument.

**B-3. Kontrollerna registreras i en katalog, inte i en if-sats.**
Motorn känner inte till någon enskild kontroll. Den itererar över ett register.
Att lägga till kontroll nummer 16 ska vara att skriva en funktion och en rad i
registret — inget annat.

**B-4. Gränsvärden och regelhänvisningar bor i en datafil, inte i Python.**
`regelverk/regelregister.toml` är enda sanningen om vilka paragrafer och vilka
parametrar (t.ex. arbetsgivaravgiftens procentsats) som gäller. Samma invariant
som `quiet_chatt` håller för sitt lagregister, och av samma skäl: ett tal som
ändras varje år får inte ligga inbakat i en funktionskropp där ingen hittar det.
Filen läses med `tomllib` ur standardbiblioteket — **ingen ny dependency.**

Registret är skrivet och verifierat (se sidhuvudet). Länkarna härleds ur
`sfs`-fältet på samma sätt som `quiet_chatt`:s `LagPost` gör det; en post utan
`sfs` måste i stället ange `lank_manniska` explicit — det gäller i dag bara
`K-00`, som inte har någon rättslig grund och inte ska ges någon.

**B-5. Maskering sker före kontrollen, inte efter.**
MCP-vägen kör `maskera_siefil` (`parser/sekretesslager.py:803`) och låter
motorn arbeta på `Maskeringsresultat.maskerad_siefil`. Alternativet — att
maskera fynden efteråt — kräver att varje ny kontroll kommer ihåg att maskera
sin motiveringstext, och den sortens regel bryts alltid till slut. Maskeringen
rör bara fritext (kontonamn, vertext, transtext, sign); kontonummer, belopp och
datum är orörda, så inget kontrollutfall påverkas.

**B-6. Modulen blir ett paket, inte en flat fil.**
Övriga `parser/`-moduler är flata filer. Här görs undantag: femton kontroller i
fyra ämnesgrupper plus modell, motor och regelkälla blir 700+ rader som ingen
vill läsa i en fil. Paketet ligger under `parser/` och importerar flatt
(`from domain_model import SIEFil`) eftersom `pyproject.toml` har
`pythonpath = ["parser", "tools"]`.

**B-7. Allvarlighet är tre nivåer, inte en poängskala.**
`avvikelse` (något är bevisligen fel), `observation` (mönstret är ovanligt och
bör kontrolleras) och `upplysning` (inget fel, men värt att veta inför
bokslutet). En numerisk riskpoäng vore ett påstående om sannolikhet som vi inte
kan belägga.

**B-8. Väsentlighet flaggar, den filtrerar inte bort.**
Ett fynd under väsentlighetsgränsen döljs aldrig — det får `vasentlig=False`.
Att tysta små fel automatiskt vore ett bedömningsbeslut som tillhör människan.

---

## 3. Invarianter

Dessa ska hållas av kod och bevakas av test. Ett test per invariant, namngivet
efter den.

**I-1. Motorn läser, den skriver aldrig.**
Ingen modul under `parser/bokslutskontroll/` får importera `utkast`,
`spiris_klient`, `spiris_adapter` eller någon funktion vars namn börjar med
`skapa_`, `utfor_`, `bygg_*_payload`. Bevakas av AST-test, i samma anda som det
befintliga skyddet av `mcp_server/server.py`.

**I-2. Ett förslag är text, aldrig en handling.**
`Rattelseforslag` innehåller beskrivning och konteringsrader. Ingenting i lager
1 lägger något i utkastkön. Vägen till utkastkön öppnas i lager 2, och då
genom `forbered_verifikat` med människan i grinden — aldrig direkt.

**I-3. MCP-vägen ser maskerad data, app-vägen omaskerad.**
`mcp_server/server.py` anropar alltid motorn med
`maskera_siefil(sie, las_namnreferens()).maskerad_siefil`.
`parser/rum_render.py` (Streamlit) anropar den med den råa `SIEFil`:en.
Detta är projektets lättaste regel att få katastrofalt fel — testa den först.

**I-4. Inget fynd utan kontroll-id.**
Varje `Fynd` bär det `kontroll_id` som producerade det, och varje `kontroll_id`
finns i `regelverk/regelregister.toml`. En kontroll vars id saknas i registret
får motorn att kasta vid uppstart, inte att tyst hoppa över. Fail-closed.

**I-5. Determinism.**
Två körningar på samma `SIEFil` ger identiska fynd i identisk ordning. Ingen
mängd- eller dict-iteration får läcka ut i utfallsordningen; sortera explicit
(§4.4).

**I-6. Ingen kontroll kraschar hela körningen.**
Motorn kör varje kontroll i en `try`. En kontroll som kastar ger ett
`upplysning`-fynd med id `K-00` som säger vilken kontroll som fallerade —
aldrig ett tomt resultat som ser ut som "allt är bra".

**I-7. Decimal hela vägen.**
Inga `float` i beräkningarna. Jämförelser sker mot en tolerans ur registret,
aldrig med `==` på beräknade belopp.

---

## 4. Datamodell

Fil: `parser/bokslutskontroll/modell.py`

### 4.1 Fynd

```python
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Allvarlighet = Literal["avvikelse", "observation", "upplysning"]


@dataclass(frozen=True)
class Konteringsrad:
    kontonr: str
    debet: Decimal = Decimal("0")
    kredit: Decimal = Decimal("0")
    text: str | None = None


@dataclass(frozen=True)
class Rattelseforslag:
    """Ett förslag i text och konteringsrader. Utförs aldrig av lager 1 (I-2)."""
    beskrivning: str
    rader: tuple[Konteringsrad, ...] = ()
    forbehall: str | None = None   # t.ex. "kräver att underlaget kontrolleras"


@dataclass(frozen=True)
class Regelhanvisning:
    """Speglar quiet_chatts Faktapost-disciplin: en hänvisning utan både en
    läsbar och en maskinell länk är ingen hänvisning."""
    kalla: str              # "SFS 1999:1078", "BFNAR 2016:10", "Skatteverket"
    beteckning: str         # "5 kap. 6 §"
    lank_manniska: str
    lank_maskin: str | None = None
    kommentar: str | None = None


@dataclass(frozen=True)
class Fynd:
    kontroll_id: str                     # "K-01"
    rubrik: str                          # kort, en rad
    allvarlighet: Allvarlighet
    motivering: str                      # varför detta är ett fynd, med tal
    konton: tuple[str, ...] = ()
    verifikationer: tuple[str, ...] = () # "A/12" — serie/vernr
    belopp: Decimal | None = None
    vasentlig: bool | None = None        # None = väsentlighet ej beräknbar
    regel: Regelhanvisning | None = None
    forslag: Rattelseforslag | None = None
```

### 4.2 Kontrollkontext

En kontroll får aldrig läsa klockan eller filsystemet själv (B-2). Allt den
behöver kommer i en kontext:

```python
@dataclass(frozen=True)
class Kontext:
    sie: SIEFil
    idag: date
    arsnr: int = 0                          # 0 = innevarande räkenskapsår
    vasentlighetstal: Decimal | None = None
    utfallsvasentlighet: Decimal | None = None
    parametrar: dict[str, object] = field(default_factory=dict)  # ur registret
    tolerans: Decimal = Decimal("1.00")     # kronor; ur registret
```

### 4.3 Kontrollsignatur

```python
Kontroll = Callable[[Kontext], list[Fynd]]
```

### 4.4 Sorteringsordning (I-5)

Motorn sorterar det samlade resultatet med nyckeln:

```python
(allvarlighetsrang, -abs(belopp or 0), kontroll_id, konton, verifikationer)
```

där `allvarlighetsrang` är `{"avvikelse": 0, "observation": 1, "upplysning": 2}`.
Alltså: allvarligast först, störst belopp först inom nivån, därefter stabilt.

---

## 5. Kontrollkatalogen

Normativ. Kontonummerintervall enligt BAS. Alla belopp är `Decimal`. Alla
jämförelser sker mot `Kontext.tolerans` om inget annat anges.

Varje kontrolls **rättsliga grund står i `regelverk/regelregister.toml`**, inte
här. Läs den posten innan du skriver kontrollen — dess `kommentar` säger ofta
vad kontrollen *inte* får påstå, och den formuleringen ska återspeglas i
`Fynd.motivering`.

Teckenkonvention i SIE4, som all logik nedan förutsätter: tillgångar är
positiva i `#UB`, skulder och eget kapital negativa; intäkter är negativa i
`#RES`, kostnader positiva. Detta är samma antagande som
`parser/vasentlighet.py` redan bygger på.

### Grupp A — bokföringsteknisk integritet

| Id | Rubrik | Definition | Allvarlighet |
|---|---|---|---|
| **K-01** | Balansräkningen går inte ihop | `Σ UB(konto 1000–2999, årsnr) + Σ RES(konto 3000–8999, årsnr) ≠ 0` | avvikelse |
| **K-02** | Verifikation i obalans | För varje `Verifikation`: `Σ transaktion.belopp ≠ 0` | avvikelse |
| **K-03** | Ingående balans bryter mot föregående års utgående | För konto i 1000–2999: `IB(årsnr=0, k) ≠ UB(årsnr=-1, k)`. Hoppas helt om filen saknar `#UB` för årsnr −1. | avvikelse |
| **K-04** | Saldot stämmer inte med årets transaktioner | Balanskonto: `UB(0,k) ≠ IB(0,k) + Σ TRANS(k)`. Resultatkonto: `RES(0,k) ≠ Σ TRANS(k)`. Hoppas helt om `sie.verifikationer` är tom (SIE-typ 1–3 saknar verifikationer). | avvikelse |
| **K-05** | Årets resultat stämmer inte mot resultaträkningen | Om konto 2099 har `UB ≠ 0`: `UB(2099) ≠ -Σ RES(3000–8999)` sedan 8999 exkluderats. | avvikelse |
| **K-06** | Transaktionsdatum utanför räkenskapsåret | `transdat < räkenskapsår[0].start` eller `> räkenskapsår[0].slut`. Ett fynd per verifikation, inte per rad. | avvikelse |
| **K-13** | Lucka eller ordningsbrott i verifikationsserie | Per serie: numeriska `vernr` sorterade ska vara sammanhängande — lucka ⇒ fynd. Dessutom: `verdatum` ska vara icke-avtagande i nummerordning inom serien. Serier med icke-numeriska `vernr` hoppas. | avvikelse |
| **K-15** | Möjlig dubbelbokförd verifikation | Två verifikationer med samma `verdatum` och identisk multimängd av `(kontonr, belopp)` | observation |

**K-13:s rättsliga grund** är den enda i grupp A som är en direkt lagregel
(BFL 5 kap. — verifikationer ska ordnas så att sambandet mellan verifikation
och bokförd post kan följas). Övriga i gruppen är bokföringstekniska
identiteter; deras `regel` får peka på BFL 5 kap. 2–3 §§ med kommentaren att
hänvisningen avser den löpande bokföringens innehåll, inte kontrollen i sig.

### Grupp B — saldologik och avstämning

| Id | Rubrik | Definition | Allvarlighet |
|---|---|---|---|
| **K-08** | Avräkningskonto har kvarvarande saldo | `UB ≠ 0` på något av: 1630, 1650, 2510, 2512, 2514, 2518, 2650, 2710, 2730, 2731. Kontolistan ligger i registret, inte i koden. | observation |
| **K-09** | Saldo på fel sida | Debetnormalt konto med kreditsaldo eller tvärtom, för de intervall som registret listar: 1500–1599 och 1900–1999 (förväntas ≥ 0), 2400–2499 och 2600–2699 (förväntas ≤ 0). | observation |
| **K-07** | Utgående moms i orimlig proportion | `utgående_moms = -Σ UB(2610–2639)`, `omsattning = -Σ RES(3000–3799)`. Fynd om `omsattning > 0` och kvoten `utgående_moms / omsattning` ligger utanför `[0, 0.25 + marginal]`. Marginal ur registret. | observation |
| **K-10** | Arbetsgivaravgift i orimlig proportion till lön | `avgift = Σ RES(7510–7519)`, `lon = Σ RES(7000–7399)`. Fynd om `lon > 0` och `avgift / lon` avviker mer än `marginal` från registrets `arbetsgivaravgift_procent` för räkenskapsårets år. | observation |

**K-07 och K-10 är avsiktligt grova.** En riktig momsavstämning per skattesats
kräver momskoder per transaktion, vilka SIE4 inte bär och som i Spiris ligger i
`hamta_momskoder`/`hamta_momsrapporter`. Den avstämningen tillhör lager 2.
Bygg inte en finare variant här — en finkornig kontroll på grovt underlag
producerar falska träffar, och en kontrollmotor som ropar varg blir avstängd.

### Grupp C — bokslutsposter

| Id | Rubrik | Definition | Allvarlighet |
|---|---|---|---|
| **K-11** | Kostnad nära årsskiftet utan periodiseringsmotpart | Verifikation med `verdatum` inom `periodiseringsfonster_dagar` före räkenskapsårets slut, med rad på konto 4000–7999 vars belopp ≥ `utfallsvasentlighet`, och utan någon rad på 1700–1799 eller 2900–2999. | upplysning |
| **K-12** | Anläggningstillgång utan årets avskrivning | Konto i 1200–1299 med `UB ≠ 0` medan `Σ RES(7810–7839) = 0`. | observation |
| **K-14** | Kontotypavvikelse | Brygga till befintliga `analysera_kontotyper` (`parser/kontotyp_vakt.py:129`). Varje `Kontotypavvikelse` blir ett `Fynd`. | observation |

**K-11 är en upplysning, inte en avvikelse.** Frånvaron av en
periodiseringsmotpart bevisar ingenting — den flaggar bara var en människa bör
titta. Formuleringen i `motivering` ska säga det rakt ut.

**K-14 skriver ingen ny logik.** Den mappar bara `Kontotypavvikelse` →
`Fynd`. Ändra inte `kontotyp_vakt.py`.

### K-00 — reserverat

Id för det fynd som I-6 producerar när en kontroll kastar. Får aldrig användas
av en riktig kontroll.

---

## 6. Filkarta

```
parser/bokslutskontroll/
    __init__.py              publikt API: kor_kontroller, Fynd, Allvarlighet, Kontext
    modell.py                §4 — dataklasser, inga beroenden utom domain_model
    motor.py                 registret, kor_kontroller, sortering, felinneslutning
    regelkalla.py            läser regelverk/regelregister.toml -> Regelhanvisning + parametrar
    kontroller/
        __init__.py          importerar undermodulerna så registret fylls
        integritet.py        K-01–K-06, K-13, K-15
        saldologik.py        K-07–K-10
        bokslutsposter.py    K-11, K-12
        kontotyper.py        K-14

regelverk/
    regelregister.toml       FINNS REDAN — skriv inte om den, se sidhuvudet

tests/
    test_bokslutskontroll_modell.py
    test_bokslutskontroll_motor.py
    test_bokslutskontroll_integritet.py
    test_bokslutskontroll_saldologik.py
    test_bokslutskontroll_bokslutsposter.py
    test_bokslutskontroll_regelkalla.py
    test_bokslutskontroll_invarianter.py     I-1, I-3, I-5
    test_bokslutskontroll_mcp.py
    _sie_fixtures.py                          syntetisk SIEFil-byggare, delad
```

Rörs dessutom: `mcp_server/server.py` (steg 7), `parser/rum_render.py` och
`parser/navigering.py` (steg 8).

---

## 7. Genomförandet

Nio steg. Ett i taget. **Kör `pytest` efter varje steg** — hela sviten, inte
bara de nya testerna. Ett steg är inte klart förrän sviten är grön och
acceptanskriterierna nedan är uppfyllda. Rapportera efter varje steg vad som
gjordes och vad testet visade.

### Steg 1 — Modell, register och motor

Skapa `modell.py` enligt §4 ordagrant, `regelkalla.py` och `motor.py`.

`regelkalla.py`:

```python
def las_register(sokvag: Path | None = None) -> Register
def hamta_regel(kontroll_id: str) -> Regelhanvisning | None
def hamta_parameter(namn: str, ar: int | None = None) -> object
def kontroll_ider() -> set[str]
```

Registret läses en gång och cachas i modulen. `las_register` kastar `ValueError`
med kontroll-id:t i meddelandet om en post saknar `rubrik`, eller saknar både
`sfs` och `lank_manniska`.

Filens faktiska form (läs den innan du skriver läsaren):

* `[parametrar]` — skalärer som strängar (`tolerans_kronor = "1.00"`), utom
  `periodiseringsfonster_dagar` som är heltal. **Beloppssträngar konverteras
  till `Decimal`, aldrig till `float`** (I-7).
* `[parametrar.arbetsgivaravgift_procent]` — nyckel är årtal som sträng
  (`"2026"`). `hamta_parameter("arbetsgivaravgift_procent", ar=2026)` slår upp
  där; okänt år ger `None`, inte närmaste år, och K-10 ger då noll fynd.
* `[kontolistor]` — `avrakningskonton` är en lista av kontonummer;
  `anlaggningstillgangar_avskrivningsbara` och `avskrivningskonton` är
  `{fran, till}`; `debetnormala` och `kreditnormala` är listor av
  `{fran, till, benamning}`.
* `[kontroll.K-xx]` — `rubrik`, `sfs`, `lag`, `beteckning`, valfri `lydelse`,
  valfri `kommentar`, `verifierad`. `lydelse` är den ordagranna lagtexten och
  ska returneras som `Regelhanvisning.kommentar` bara när `kommentar` saknas —
  annars går den i ett eget fält om du väljer att lägga till ett. Ändra inte
  texten.

Länkhärledningen: `"1999:1078"` → `sfs-1999-1078` →
`https://www.riksdagen.se/sv/dokument-och-lagar/dokument/_sfs-1999-1078/`
respektive `https://data.riksdagen.se/dokument/sfs-1999-1078`.

`motor.py`:

```python
KONTROLLER: dict[str, Kontroll] = {}

def registrera(kontroll_id: str):
    """Dekorator. Kastar vid dubblettregistrering."""

def kor_kontroller(
    sie: SIEFil,
    *,
    idag: date,
    arsnr: int = 0,
    endast: set[str] | None = None,
) -> list[Fynd]
```

`kor_kontroller` ska: bygga `Kontext` (inkl. väsentlighetstal via
`berakna_vasentlighet` + `berakna_standardtroskelvarden`, med `None` om
omsättningen är 0), kontrollera I-4 vid start, köra varje registrerad kontroll
i `try` enligt I-6, och sortera enligt §4.4.

**Acceptans**
* `test_bokslutskontroll_motor.py` visar: dubbelregistrering kastar; en kontroll
  som kastar ger exakt ett `K-00`-fynd och stoppar inte de övriga; `endast`
  begränsar körningen; sorteringen följer §4.4 för ett konstruerat fyndurval.
* `test_bokslutskontroll_regelkalla.py` visar: giltigt register läses; post utan
  `lank_manniska` kastar `ValueError` som nämner kontroll-id:t; okänt
  kontroll-id ger `None`, inte `KeyError`.
* Motorn med tomt kontrollregister returnerar `[]` utan att kasta.

### Steg 2 — Fixturbyggaren

`tests/_sie_fixtures.py`: en byggare som gör syntetiska `SIEFil`-objekt utan
att någon fil läses.

```python
def bygg_sie(
    *,
    konton: dict[str, str] | None = None,          # kontonr -> namn
    ib: dict[str, str] | None = None,              # kontonr -> belopp
    ub: dict[str, str] | None = None,
    res: dict[str, str] | None = None,
    verifikationer: list[dict] | None = None,
    rakenskapsar: tuple[str, str] = ("2025-01-01", "2025-12-31"),
    foregaende_ub: dict[str, str] | None = None,   # årsnr -1
) -> SIEFil
```

Belopp anges som strängar och konverteras till `Decimal` — aldrig `float`.
Byggaren ska som standard producera en **balanserad** bokföring, så att ett
test som prövar K-01 måste göra den obalanserad med avsikt.

**Acceptans**
* En default-`bygg_sie()` ger noll fynd från hela motorn när steg 3–5 är klara.
  Skriv testet nu och låt det vara `xfail` tills dess.

### Steg 3 — Grupp A

`kontroller/integritet.py`: K-01–K-06, K-13, K-15 enligt §5.

**Acceptans** — minst två test per kontroll: ett som utlöser fyndet med känt
belopp och känt konto, ett som inte gör det. Dessutom:
* K-03 och K-04 ger **noll** fynd när underlaget saknas (ingen `#UB` för årsnr
  −1 respektive inga verifikationer) — inte ett fynd som säger att något är fel.
* K-06 ger ett fynd per verifikation även när flera rader ligger fel.
* K-13 hoppar över serier med icke-numeriska `vernr` utan att kasta.
* Toleransen respekteras: en differens på 0,50 kr flaggas inte vid tolerans
  1,00 kr; 1,50 kr flaggas.

### Steg 4 — Grupp B

`kontroller/saldologik.py`: K-07–K-10. Kontolistor och marginaler hämtas ur
registret via `hamta_parameter` — inga literaler i koden.

**Acceptans**
* K-07 och K-10 ger noll fynd när nämnaren är 0 (ingen division med noll,
  ingen `ZeroDivisionError`, inget fynd som bygger på ett odefinierat tal).
* Ett test ändrar `arbetsgivaravgift_procent` i ett temporärt register och visar
  att utfallet följer med — det bevisar B-4.

### Steg 5 — Grupp C

`kontroller/bokslutsposter.py` (K-11, K-12) och `kontroller/kontotyper.py`
(K-14).

**Acceptans**
* K-11 använder `Kontext.utfallsvasentlighet`; när den är `None` ger kontrollen
  noll fynd i stället för att välja ett eget gränsvärde.
* K-14 producerar exakt lika många fynd som `analysera_kontotyper` ger
  avvikelser, med samma konton, och `kontotyp_vakt.py` är oförändrad.
* `xfail`-testet från steg 2 vänds till ett vanligt test och är grönt.

### Steg 6 — Väsentlighet och regelhänvisningar

Koppla in `vasentlig` på varje fynd och fyll `regel` ur registret. Detta sker
**centralt i motorn**, inte i varje kontroll: efter att en kontroll returnerat
sina fynd sätter motorn `regel` från `hamta_regel(kontroll_id)` och `vasentlig`
från `belopp >= utfallsvasentlighet` när båda finns.

**Acceptans**
* En kontroll som själv sätter `regel` får behålla sin (motorn skriver bara över
  `None`) — det behövs för K-14, vars hänvisning skiljer sig från de övrigas.
* `vasentlig` är `None`, inte `False`, när väsentlighetstalet inte gick att
  beräkna. Testa båda vägarna.
* Varje id i `KONTROLLER` har en post i registret (I-4), verifierat av ett test
  som itererar över registret och katalogen åt båda hållen.

### Steg 7 — MCP-verktyget

I `mcp_server/server.py`, i samma mönster som `granska_kontotyper`
(`mcp_server/server.py:272`):

```python
@mcp.tool()
def bokslutskontroll(sokvag: str) -> dict
```

Ordningen är bindande: `_villkor_godkanda` → `_tillaten_siefil` → `parse_sie4`
→ **`maskera_siefil(sie, las_namnreferens()).maskerad_siefil`** → `kor_kontroller`.
Fel hanteras med `_fel_vid_inlasning` och `_logga_lokalt` precis som befintliga
verktyg. Svaret:

```python
{"fynd": [...], "sammanfattning": {"avvikelse": n, "observation": n, "upplysning": n},
 "tolkningsbehov_antal": int, "fel": None}
```

Lägg också till `spiris_bokslutskontroll()` som hämtar via
`hamta_siefil_fran_spiris` och går genom samma maskering och samma motor.

Docstringen ska bära samma förbehåll som `granska_kontotyper`: indikation utan
garanti, inte revisions- eller redovisningsrådgivning, kan innehålla både
falska träffar och missade avvikelser, varje post ska bedömas självständigt.

**Acceptans**
* `test_bokslutskontroll_mcp.py`: spärrat läge (villkor ej godkända) ger
  fail-closed-svar utan att filen ens läses; sökvägsvakten avvisar en fil utanför
  `SIE_KATALOG`; ett fynd vars motivering skulle ha innehållit ett personnamn ur
  fritext innehåller det inte i MCP-svaret (I-3).
* De befintliga metatesterna för läsverktygens bredd och för `id` i objektlistor
  passerar för det nya verktyget. Kontrollera `test_mcp_lasande_bredd.py` och
  `test_mcp_startblock.py` — lägg till verktyget där de kräver det.

### Steg 8 — Vyn i appen

**Följ `UI_ATGARDER_I_VYN.md`.** Den specen äger gränssnittsdelen: knappraden i
det nya bokslutsrummet, `Atgardsforslag` i `Vyresultat`, godkännandet på samma
plats som fyndet visas, och åtgärdsbadgen. Bygg inte en egen vy vid sidan av
den.

Det som gäller härifrån och som inte får förhandlas i UI-specen:

* Fynden visas **omaskerade** i appen (I-3). Motorn anropas med den råa
  `SIEFil`:en; MCP-vägen maskerar först.
* Ingen knapp i vyn utför något (I-2). Den kan skapa ett utkast — inget mer.

**Acceptans**
* Ett test visar att app-vägen anropar motorn med den råa `SIEFil`:en och att
  MCP-vägen inte gör det (I-3, båda riktningarna).
* AST-test: ingen vy-modul och inget ritlager anropar `bekrafta_for_sandning`,
  `utfor_utkast` eller en skrivfunktion i `spiris_adapter`.

### Steg 9 — Regelhänvisningarnas kvalitet (valfritt, sist)

Se §8. Gör inte detta steg förrän 1–8 är gröna.

---

## 8. Kopplingen till quiet_chatt

`quiet_chatt` (paketet `quiet_oppen_data`) har byggt just det som sie-mcp:s
juridikverktyg saknar. Jämförelsen:

| | sie-mcp idag | quiet_chatt |
|---|---|---|
| Lagtext | `parser/juridik_api.py` — nyckelordssökning mot Riksdagens dokumentlista, tre träffar, utdrag ur `summary`-fältet | lokalt index över konsoliderad SFS med kapitel, rubrik och ändringsnotiser (`adaptrar/lagtext.py`), filtrerbart på IL/ML/SFL/BFL/ÅRL |
| Skatteverket | `skapa_lank_skatteverket` — en söklänk, eftersom Rättslig vägledning blockerar maskinell läsning | åtta verifierade öppna datamängder under `skatteverket_rowstore` (skattesatser, skattetabeller, traktamenten, kostförmån), anropade och bekräftade 2026-08-14 |
| Källdisciplin | fri text i `instruktion`-fältet | `Faktapost` kan inte konstrueras utan både `lank_manniska` och `lank_maskin`; validator faller stängt |

### 8.1 Vad som tas över nu — mönstret

`Regelhanvisning` (§4.1) är avsiktligt formad som `Faktapost`: en hänvisning
utan både läsbar och maskinell länk är ingen hänvisning. `regelregister.toml`
är avsiktligt formad som `lagar/lagregister.yaml`: SFS-nummer in, länkar
härledda, ingen laglista i Python. Härledningen är densamma —
`1999:1078` → `sfs-1999-1078` → `https://www.riksdagen.se/sv/dokument-och-lagar/dokument/_sfs-1999-1078/`
för människan och `https://data.riksdagen.se/dokument/sfs-1999-1078` för maskinen.

Detta kostar ingenting och ger sie-mcp samma disciplin utan något beroende.

### 8.2 Vad som *inte* kopplas ihop nu — och varför

**Ingen körtidskoppling mellan projekten i lager 1.** Skälen, i ordning:

1. En kontrollmotor som ska vara deterministisk (§1.1) får inte vänta på ett
   HTTP-anrop som kan svara långsamt, falla, eller — i `quiet_chatt`:s fall —
   gå genom en språkmodell. Hänvisningen till BFL 5 kap. ändrar sig inte mellan
   körningar och hör därför hemma i en lokal fil.
2. `quiet_chatt` är en tjänst med kvoter, egen frontend och egen
   distributionsväg. sie-mcp är ett publikt kodförråd som installeras lokalt.
   Ett hårt beroende gör att den ena inte kan släppas utan den andra.
3. Fyndens rättsliga grund är känd i förväg — det är alltid samma paragraf för
   samma kontroll. Det är inte en fråga som behöver ställas.

### 8.3 Steg 9 — den koppling som faktiskt är värd något

Två saker, båda som *berikning*, aldrig som förutsättning:

**9a. Paragraftext på begäran.** Ett separat MCP-verktyg —
`hamta_regeltext(kontroll_id)` — som slår upp den paragraf som fyndet redan
hänvisar till och returnerar dess faktiska lydelse. Implementeras mot
`quiet_chatt`:s lagtextindex om det är nåbart, annars mot det befintliga
`sok_svensk_lagstiftning`. Fyndet är fullständigt utan detta; verktyget gör
bara att användaren slipper öppna Riksdagens webbplats.

Interfacet ska vara ett protokoll med två implementationer, så att sie-mcp
aldrig importerar `quiet_oppen_data` direkt:

```python
class Regeltextkalla(Protocol):
    def hamta(self, sfs: str, beteckning: str) -> str | None: ...
```

Fail-closed: källan som inte svarar ger `None`, och verktyget säger att
lydelsen inte kunde hämtas. Den hittar aldrig på en paragraftext.

**9b. Skatteverkets tal som registerparametrar.** `K-10`:s
`arbetsgivaravgift_procent` är i dag ett tal i `regelregister.toml` som någon
måste uppdatera för hand varje år. Att det behövs syns redan i registret: talet
31,42 % är summan av två procentsatser som ändras i **olika lagar vid olika
tillfällen** — 18,80 % enligt socialavgiftslagen 2 kap. 26 § i lydelsen enligt
Lag (2025:1362), och 12,62 % enligt lagen om allmän löneavgift 3 § i lydelsen
enligt Lag (2025:1360). Ett handskrivet tal som beror på två lagändringar per
år är precis den sortens uppgift som tyst blir fel. Samma sak gäller de kontroller som lager 2
kommer att behöva: traktamentsbelopp, kostförmånsvärden, skattesatser. Det är
exakt de datamängder `quiet_chatt` redan har verifierat under
`skatteverket_rowstore`.

Rätt konstruktion är ett litet skript — inte ett körtidsanrop — som hämtar
talen och **skriver in dem i `regelregister.toml` med källa, datum och länk**.
Registret förblir enda sanningen och motorn förblir offline. Kör skriptet när
året byter; granska diffen som vilken kodändring som helst.

Bygg 9b först om något av lager 2 ska påbörjas — då blir det lönsamt. För
lager 1 ensamt räcker ett handskrivet tal med en kommentar om när det ska ses
över.

---

## 9. Vad som inte ingår

Bygg inte detta nu, oavsett hur nära det ligger:

* **Skrivning av något slag.** Inte till Spiris, inte till utkastkön, inte till
  SIE-filen. (I-2)
* **Momsavstämning per skattesats.** Kräver momskoder per transaktion — lager 2.
* **Avskrivningsberäkning.** K-12 konstaterar att avskrivning saknas; den räknar
  inte fram vad den borde vara. Lager 2.
* **Skatteberäkning och årets resultat.** Lager 2.
* **Årsredovisning, noter, förvaltningsberättelse, SRU-mappning.** Lager 3, och
  först efter en egen juridisk genomgång — en årsredovisning undertecknas av
  styrelsen och lämnas till Bolagsverket.
* **En språkmodell någonstans i motorn.** (§1.1)
* **Riskpoäng, betyg eller "bokföringshälsa i procent".** (B-7)

---

## 10. Klart

Genomförandet är klart när:

1. Steg 1–8 är utförda och hela `pytest`-sviten är grön, med minst 40 nya test.
2. Varje invariant I-1 … I-7 har ett test som är namngivet efter den.
3. `bokslutskontroll` och `spiris_bokslutskontroll` finns i MCP-ytan och
   passerar de befintliga metatesterna.
4. En default-`bygg_sie()` ger noll fynd, och en avsiktligt trasig bokföring ger
   fynd från minst fem olika kontroller.
5. `regelverk/regelregister.toml` är **oförändrad** bortsett från eventuella
   tillägg som uttryckligen begärts och godkänts. `git diff` på den filen ska
   vara tom vid inlämning om inget sådant begärts.

Därefter granskar Claude koden. Granskningen börjar med I-3 — vilken väg som ser
maskerad data — eftersom det är den regel som är lättast att få katastrofalt fel
och svårast att upptäcka i efterhand.
