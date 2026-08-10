# Exekverbar plan — inför publicering på GitHub

**Datum:** 2026-08-10
**Mottagare:** den AI som utför hantverket (Gemini 3.1 Pro)
**Avsändare:** arkitekten
**Omfattning:** tre uppgifter, P1–P3. Ingenting annat.

Bakgrund: kodförrådet ska publiceras öppet och länken skickas till Vismas
API-support som underlag för en ansökan om produktionsåtkomst. Granskningen
sker mot utvecklarvillkorens punkt 2.2.4 — säkerhetsnivå, professionell
standard, regelefterlevnad och nytta. De tre uppgifterna nedan är de som
annars skulle tala emot oss.

---

## 0. Förutsättningar

### 0.1 Vad som gäller

`hantverksbok/00_KONSTITUTION.md` gäller i sin helhet. Särskilt:

- Filer du aldrig ändrar: `sekretesslager.py`, `utkast.py`, `compliance.py`,
  `saker_lagring.py`, `spiris_session.py`, `revisionslogg.py`, `.env*`.
- Svenska i namn, docstrings och kommentarer.
- Du ändrar aldrig ett befintligt test för att få det grönt.

### 0.2 Baslinje

```
python -m pytest tests -q
```

Notera talet innan du börjar. Det ska öka med exakt de nya testerna i P1 och
inget får gå från grönt till rött.

### 0.3 Vad du INTE får göra

**Du kör inga git-kommandon som skriver historik.** Inget `commit`, `push`,
`rebase`, `filter-branch` eller `filter-repo`. P2 innehåller ett steg som
kräver historikomskrivning — det utförs av användaren, inte av dig, och står
markerat som sådant.

Du får köra läsande git-kommandon (`status`, `ls-files`, `log`) för att
kontrollera ditt arbete.

---

## P1 — Servern registrerar bara hälften av sina verktyg

Den allvarligaste av de tre. Åtgärda den först.

### Felet

`mcp_server/server.py` rad 2201:

```python
if __name__ == "__main__":
    mcp.run()
```

Efter den raden definieras ytterligare **63 verktyg**, samtliga resurser,
samtliga resursmallar och samtliga prompter.

När servern startas som README och Claude Desktop-konfigurationen anger —
`python -m mcp_server.server` — läses filen uppifrån och ner. På rad 2201
anropas `mcp.run()`, som börjar servera och **aldrig återvänder**. Allt som
står efter körs aldrig.

Uppmätt 2026-08-10:

```
Verktyg registrerade när mcp.run() anropades:        62
Verktyg registrerade efter att modulen kört klart:  125
```

Bland de 63 som tappas finns hela utfallet av Etapp 8–17:
`forbered_utkastandring`, `forbered_utkastborttagning`,
`forbered_utkastbokforing`, `forbered_kvittning`,
`spiris_kvittningskandidater`, `forbered_betalningsverifikat`,
`forbered_periodiseringsandring`, `forbered_periodiseringsborttagning`,
`forbered_konto`, `forbered_kontoandring`, `forbered_bokforingslas`,
`forbered_rotrut`, `spiris_bokforingslas`, `spiris_kontoplan_alla`,
`spiris_hamta_ett`, `spiris_valutakurs`, `spiris_anlaggningstillgangar`,
`spiris_kundreskontraposter`, `spiris_anvandare`, `spiris_prislistor`,
`spiris_rabattavtal`, `spiris_etiketter`, `spiris_verifikation`,
`spiris_bankhandelse` — plus `sok_lagstiftning`,
`skatteverket_rattslig_vagledning` och samtliga domänalias.

Testsviten missar det eftersom `pytest` **importerar** modulen. Då är
`__name__` inte `"__main__"`, guarden hoppas över, allt registreras, och
sviten blir grön. Det är samma klass av fel som periodiseringens döda skrivväg:
grönt betyder inte färdigt.

### P1.1 — Flytta startblocket sist

**Filer:** `mcp_server/server.py`

Ta bort de två raderna på rad 2201–2202 och lägg dem **allra sist i filen**,
efter den sista definitionen. Ingenting annat i filen ändras — inga verktyg
flyttas, inga rader skrivs om.

Lägg en kommentar ovanför som förklarar varför placeringen är kritisk, så att
nästa person inte lägger till ett verktyg efter den:

```python
# Startblocket MÅSTE ligga sist i filen. mcp.run() återvänder aldrig — allt
# som definieras efter det anropet registreras aldrig när servern körs som
# __main__, bara när modulen importeras (t.ex. av testsviten). Ett verktyg som
# hamnar under den här raden är osynligt för varje riktig klient, och sviten
# blir grön ändå. Uppmätt 2026-08-10: 62 av 125 verktyg nådde klienten.
if __name__ == "__main__":
    mcp.run()
```

### P1.2 — Regressionstest

**Filer:** `tests/test_mcp_startblock.py` (ny)

Ett test som kör modulen som `__main__` med `mcp.run()` ersatt, och jämför
antalet registrerade verktyg i det ögonblicket med antalet efter att modulen
kört klart.

Formen, som är prövad och fungerar:

```python
import asyncio
import runpy

import mcp.server.fastmcp as fastmcp


def test_alla_verktyg_registrerade_nar_servern_startar(monkeypatch):
    """Startblocket måste ligga sist i server.py.

    mcp.run() återvänder aldrig. Ett verktyg som definieras efter anropet
    registreras därför bara vid import — alltså i testsviten — och aldrig när
    servern faktiskt kör. Felet är osynligt för varje annat test i sviten,
    eftersom de importerar modulen i stället för att köra den.
    """
    fangat = {}

    def fejkad_run(self, *args, **kwargs):
        fangat["vid_start"] = len(asyncio.run(self.list_tools()))
        fangat["server"] = self

    monkeypatch.setattr(fastmcp.FastMCP, "run", fejkad_run)
    runpy.run_module("mcp_server.server", run_name="__main__")

    server = fangat["server"]
    efter = len(asyncio.run(server.list_tools()))
    assert fangat["vid_start"] == efter, (
        f"{efter - fangat['vid_start']} verktyg definieras efter mcp.run() och "
        "når aldrig en klient. Flytta startblocket sist i server.py."
    )
```

Skriv **tre** tester i samma form: ett för verktyg, ett för resurser
(`list_resources` och `list_resource_templates`) och ett för prompter
(`list_prompts`).

Kontrollvärden efter rättningen, uppmätta 2026-08-10:

| | Antal |
|---|---|
| Verktyg | 125 |
| Resurser | 3 |
| Resursmallar | 1 |
| Prompter | 5 |

Får du andra tal: **stanna och rapportera.** Antalet kan ha ändrats sedan
mätningen, men en avvikelse ska förklaras, inte antas.

**Tester (exakt 3 nya).**

---

## P2 — Städa kodförrådet

Repot innehåller filer som inte hör hemma i en publik publicering, och två av
dem talar direkt emot oss i granskningen.

### P2.1 — Vismas dokumentation ur repot

**Filer:** `.gitignore`

Följande är spårade i git:

```
Visma_villkor/pdf_text.txt
Visma_villkor/visma_developer_portal_authentication.md
Visma_villkor/visma_developer_portal_getting_started.md
Visma_villkor/visma_developer_portal_session_management.md
Visma_villkor/visma_developer_portal_tokens.md
```

Det är Vismas eget, upphovsrättsskyddade dokumentationsmaterial. Att
republicera det i ett publikt kodförråd — och sedan be Visma granska det
kodförrådet — är både en juridisk fråga och ett onödigt dåligt intryck.

Lägg till i `.gitignore`, under en egen rubrik med motivering:

```
# Vismas egen dokumentation och avtalstext. Arbetsmaterial, inte vårt att
# publicera vidare. Ligger kvar lokalt men ska aldrig till ett publikt repo.
Visma_villkor/
```

Kör sedan `git rm -r --cached Visma_villkor` så att filerna slutar spåras men
**ligger kvar på disk**. Detta är ett indexkommando, inte en
historikomskrivning, och du får köra det.

Radera **inte** katalogen från filsystemet.

### P2.2 — Rökprovsskripten ur roten

**Filer:** `probe.py`, `probe_u7.py`, `probe_u16.py`,
`update_handover_final.py`, `.gitignore`

Fyra skript ligger i repots rot. `probe_u7.py` inleder med att koppla ur
projektets egen villkorsspärr:

```python
compliance.godkann_compliance = lambda: None
compliance._VILLKOR_GODKANDA = True
```

Det är rimligt i ett rökprov, men den som ska bedöma om vår säkerhet är
"appropriate to the risk" ska inte hitta ett skript i roten vars första
handling är att stänga av skyddet.

Gör så här:

1. Flytta `probe.py`, `probe_u7.py` och `probe_u16.py` till `tools/` och döp om
   dem till `prov_lasbredd.py`, `prov_paginering.py` respektive
   `prov_etapp16.py` — eller de namn som motsvarar vad de faktiskt provar. Läs
   dem innan du döper om.
2. Ge var och en en docstring i husets form som säger: vad provet gör, att det
   kräver en levande Spiris-session, och **varför** villkorsspärren kopplas ur
   (ett rökprov körs av utvecklaren på en maskin där villkoren redan är
   godkända; urkopplingen är en teknisk genväg förbi en interaktiv grind, inte
   ett kringgående av kravet).
3. `update_handover_final.py` är ett engångsskript för att redigera ett
   dokument. Det har inget värde för någon annan. Ta bort det ur spårningen med
   `git rm --cached update_handover_final.py` och lägg `update_handover_final.py`
   i `.gitignore`. Radera inte filen från disk.

`tools/prov_grind10.py` finns redan och visar formen. Följ den.

### P2.3 — Historiken (utförs INTE av dig)

Filerna i P2.1 och P2.2 finns kvar i tidigare commits. `git rm --cached` tar
bort dem ur framtida commits men inte ur historiken.

Kodförrådet har 13 commits och **inget remote** — ingenting har publicerats
än. En historikomskrivning är därför gratis och riskfri just nu, och omöjlig
senare.

Skriv en ruta i din rapport som talar om detta för användaren, med förslaget
att köra `git filter-repo --path Visma_villkor --path update_handover_final.py
--invert-paths` innan första push. **Kör det inte själv.**

---

## P3 — README speglar inte verkligheten

**Filer:** `README.md`

### P3.1 — Verktygsantalet

README säger i dag:

> "exponerar 54 primära verktyg över `stdio` — 37 läsande, 16 som föreslår
> åtgärder utan att utföra dem, och `visa_anvandarvillkor` (samt 31
> domänspecifika alias, totalt 85)"

Verkligt antal, uppmätt 2026-08-10 efter P1: **125 verktyg, 3 resurser, 1
resursmall, 5 prompter.**

Räkna om själv och skriv rätt tal. Behåll uppdelningen README redan gör —
läsande, föreslående, alias — men härled den ur koden, inte ur den gamla
texten. Aliasen ligger under rubriken `ALIASER` i `mcp_server/server.py`.

Lägg också till resurserna och prompterna. De nämns inte alls i dag trots att
de är två av MCP-protokollets tre ytor.

### P3.2 — Verktygstabellen

Tabellen under rubriken listar ett tjugotal verktyg och saknar allt från Etapp
8–17. Den ser fullständig ut men är det inte.

Välj ett av två:

- **Komplettera** den med de nya grupperna: utkastvägen (`forbered_utkast*`),
  periodiseringar, kontoplansunderhåll, bokföringslås och ROT/RUT, kvittning,
  underlag och bilagor, prislistor och etiketter.
- **Ersätt** den med grupprubriker utan fullständig uppräkning, plus en mening
  om att klienten listar verktygen själv.

Låt den inte stå kvar ofullständig. Ett dokument som ljuger om ett
kontrollerbart tal blir inte trott om resten heller.

### P3.3 — Windows-kravet

README säger ingenting om plattform. `saker_lagring.dpapi_skydda` använder
Windows DPAPI och fail-closar på allt annat, uttryckligen utan osäker
fallback. Spiris-inloggningen kan alltså inte sparas på macOS eller Linux.

Lägg till, i avsnittet om installation:

> **Spiris-anslutningen kräver Windows.** OAuth-sessionen skyddas med Windows
> DPAPI (per användare) och har medvetet ingen fallback på andra plattformar —
> en osäker lagring vore värre än ingen. SIE4-vägen är inte beroende av detta.

### P3.4 — Kom-igång-hänvisning

Lägg **en** rad allra högst upp, före varningsrutan:

```markdown
> **Vill du bara komma igång?** → [KOM_IGANG.md](KOM_IGANG.md)
```

Finns `KOM_IGANG.md` inte än — den ligger i `PLAN_INSTALLATION.md` etapp E —
hoppa över den här punkten och skriv det i rapporten. Lägg **inte** en länk
till en fil som inte finns.

### P3.5 — Vad du inte rör

Varningsrutan, ansvarsfriskrivningarna och varumärkesavsnittet lämnas
**oförkortade och oförändrade**. De är avsiktligt formulerade och deras längd
är inte ett misstag.

---

## Rapportmall

```
UPPGIFT: <P1.1, P1.2, P2.1, …>
STATUS:  klar | stoppad

TESTER:  före N passed → efter M passed  (+K nya, 0 nya röda)
KOMMANDO: python -m pytest tests -q

VERKTYGSRÄKNING (efter P1):
  vid mcp.run(): __   efter full körning: __   (ska vara lika)

FILER SOM ÄNDRATS:
  <sökväg>  (+rader/-rader, kort beskrivning)

AVVIKELSER FRÅN SPECIFIKATIONEN:
  <ingen | beskrivning>

TILL ANVÄNDAREN:
  <historikomskrivningen enligt P2.3, och annat som kräver beslut>
```

Rapportera aldrig "klar" om sviten inte är grön.
