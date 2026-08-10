# Exekverbar plan — driftsättning utan friktion

**Datum:** 2026-08-10
**Mottagare:** den AI som utför hantverket (Gemini 3.1 Pro)
**Läs först:** `ARKITEKTUR_INSTALLATION.md`, sedan
`hantverksbok/00_KONSTITUTION.md`

Besluten N1–N7 står i arkitekturdokumentet och ska inte omprövas av dig.

---

## 0. Förutsättningar

### 0.1 Vad som gäller

Konstitutionen gäller i sin helhet. Särskilt:

- **Filer du aldrig ändrar:** `saker_lagring.py`, `compliance.py`,
  `sekretesslager.py`, `utkast.py`, `reskontra_tvatt.py`, `revisionslogg.py`,
  `namnreferens.py`, `masking_memory.py`, `spiris_session.py`, `.env*`.
  Onboardingen **anropar** dem, den ändrar dem inte.
- **Svenska** i namn, docstrings och kommentarer.
- **Docstringen förklarar varför**, inte vad.
- Du ändrar aldrig ett befintligt test för att få det grönt.

Ett tillägg som gäller just den här planen: `parser/spiris_auth_vy.py` och
`parser/kalla_vy.py` är inte skyddade, men de bär OAuth-flödet. Varje ändring
där ska vara additiv — det befintliga inklistringsläget ska finnas kvar som
reservväg (se A2).

### 0.2 Baslinje

```
python -m pytest tests -q
```

Notera talet innan du börjar. Det ska öka, aldrig minska.

### 0.3 Grindar

Etapperna körs i ordning. Efter varje etapp: rapportera och **stanna**.
Etapp A är dessutom spärrad av A0, som utförs av arkitekten eller användaren.

---

## Etapp A — OAuth utan klipp och klistra

Steg 9 i nulägestabellen. Den största enskilda vinsten.

### A0 — Verifiera callback-protokollet (utförs INTE av dig)

Arkitekten eller användaren kontrollerar i Spiris registreringsformulär om
`http://localhost:44300/callback` godtas som callback-URL, eller om `https`
krävs.

Utfallet skrivs in här innan A1 påbörjas:

```
CALLBACK-PROTOKOLL: (fylls i)   http | https
```

Står raden tom: **stanna och fråga.** Att gissa ger en lyssnare som aldrig tar
emot något, och felet visar sig först i användarens webbläsare.

### A1 — `parser/oauth_lyssnare.py`

**Filer:** `parser/oauth_lyssnare.py` (ny), `tests/test_oauth_lyssnare.py` (ny)

En kortlivad lokal HTTP-server som tar emot Spiris återanrop.

```python
def vanta_pa_aterkoppling(
    *, port: int = 44300, timeout_sekunder: float = 180.0
) -> str:
    """Startar en lyssnare på 127.0.0.1 och returnerar den fullständiga
    callback-URL:en som Spiris omdirigerade till."""
```

Ovillkorliga regler:

- Bind **enbart** `127.0.0.1`. Aldrig `0.0.0.0`, aldrig `localhost` som
  namn — en namnuppslagning kan ge en extern adress.
- Servern stängs alltid, även vid timeout och vid undantag. Använd `finally`.
- Timeout ger `OAuthLyssnarFel`, ett eget fail-closed-fel i samma form som
  `SpirisAuthFel`. Inget `socket`- eller `http.server`-undantag når ut.
- Är porten upptagen: `OAuthLyssnarFel` med en text som säger vilken port och
  att ett annat program håller den. Gissa inte en annan port — då matchar den
  inte längre den registrerade callback-URL:en.
- Servern svarar med en enkel svensk HTML-sida: "Klart. Du kan stänga
  fliken och gå tillbaka till sie-mcp." Ingen extern resurs, ingen CSS-länk,
  inget JavaScript.
- **Frågesträngen loggas aldrig och skrivs aldrig ut.** Den innehåller
  auktoriseringskoden.
- Endast `GET` på callback-sökvägen besvaras. Allt annat ger `404` utan att
  avbryta väntan.

Om A0 gav `https`: servern lindas i en TLS-kontext med ett självsignerat
certifikat för `localhost`, genererat med `cryptography` (redan ett beroende)
i en funktion `_sjalvsignerat_certifikat()`. Certifikatet skrivs till
`saker_lagring`-katalogen, aldrig till projektmappen, och återanvänds om det
finns och är giltigt.

**Tester (minst 10):** lyckad mottagning returnerar hela URL:en; timeout ger
`OAuthLyssnarFel`; upptagen port ger `OAuthLyssnarFel`; servern är stängd
efter både lyckat och misslyckat utfall; bindning sker mot `127.0.0.1`;
`POST` avvisas; okänd sökväg ger 404 utan att avbryta; koden förekommer inte i
någon loggutskrift.

### A2 — Koppla in lyssnaren i inloggningsvyn

**Filer:** `parser/kalla_vy.py`, `tests/`

Den levande inloggningen är `rendera_anslutning()` i `parser/kalla_vy.py`
(rad ~42–130). `parser/build_phase3.py` är ett gammalt byggskript och ska
**inte** röras.

Nytt flöde:

1. Användaren klickar "Anslut till Spiris".
2. Auktoriserings-URL byggs som i dag med `bygg_auktoriserings_url`.
3. Lyssnaren startas.
4. Webbläsaren öppnas mot URL:en med `webbrowser.open`.
5. `vanta_pa_aterkoppling` returnerar callback-URL:en.
6. Den matas in i den **befintliga** `extrahera_kod` med samma
   `förväntat_state` — CSRF-kontrollen ändras inte.
7. `vaxla_kod_mot_token` som i dag.

**Reservvägen behålls.** Under den automatiska knappen ska det finnas en
hopfällbar sektion "Fungerar det inte? Klistra in adressen manuellt" med
exakt dagens inmatningsfält. En användare bakom en brandvägg som blockerar
lokala portar måste ha en väg framåt, och den vägen finns redan och är testad.

Misslyckas lyssnaren fälls reservvägen ut automatiskt med en förklarande text.

**Tester (minst 6).** Vyn testas som de övriga vyerna i projektet — genom
funktionerna, inte genom Streamlit-runtime.

**GRIND A.** Rapportera och stanna.

---

## Etapp B — Claude Desktops konfiguration

### B1 — `parser/klientkonfig.py`

**Filer:** `parser/klientkonfig.py` (ny), `tests/test_klientkonfig.py` (ny)

```python
def config_sokvag() -> Path:
    """%APPDATA%\\Claude\\claude_desktop_config.json."""

def las_config(sokvag: Path | None = None) -> dict:
    """Läser konfigurationen. En saknad fil ger {} — inte ett fel."""

def bygg_serverpost(*, python: Path, projektrot: Path) -> dict:
    """Bygger posten för mcpServers['sie-mcp']."""

def skriv_in_sie_mcp(
    post: dict, sokvag: Path | None = None, *, sakerhetskopiera: bool = True
) -> Path:
    """Slår ihop posten i konfigurationen och skriver atomiskt.
    Returnerar sökvägen till säkerhetskopian."""
```

Ovillkorliga regler (N6):

- **Bara** `mcpServers["sie-mcp"]` sätts. Alla andra nycklar på alla nivåer
  bevaras exakt, inklusive nycklar vi inte känner till. Filen ägs av ett annat
  program.
- Säkerhetskopian skapas **före** skrivningen, med tidsstämpel i namnet
  (`claude_desktop_config.json.sie-mcp-backup-<ISO>`), i samma katalog.
- Skrivningen är atomisk: skriv till en temporärfil i samma katalog, `flush`,
  `os.fsync`, sedan `os.replace`. Ett halvskrivet JSON gör att Claude Desktop
  tappar **alla** användarens MCP-servrar, inte bara vår.
- En befintlig fil som inte går att tolka som JSON → `KlientkonfigFel`. Skriv
  **inte** över den och reparera den inte. En trasig fil kan vara halvfärdig
  handredigering som användaren håller på med.
- Filen är UTF-8 utan BOM. Bakstreck i Windows-sökvägar hanteras av
  `json.dump`, aldrig av strängformatering.

`bygg_serverpost` producerar:

```json
{
  "command": "<sökväg till pythonw.exe i den installerade miljön>",
  "args": ["-m", "mcp_server.server"],
  "env": {"PYTHONPATH": "<projektrot>;<projektrot>\\parser"}
}
```

Inga hemligheter i `env`. Servern läser redan `secrets\.env` via
`saker_lagring` vid import (`mcp_server/server.py` rad 25–58) — client_id och
secret ska aldrig hamna i en fil som andra program läser.

**Tester (minst 12):** saknad fil ger `{}`; främmande servrar bevaras;
främmande toppnycklar bevaras; säkerhetskopia skapas före skrivning; trasig
JSON ger fel och rör inte filen; skrivningen är atomisk (temporärfil finns
inte kvar); ingen hemlighet i posten; sökvägar med mellanslag och bakstreck
överlever rundturen.

**GRIND B.** Rapportera och stanna.

---

## Etapp C — Guiden

### C1 — `parser/onboarding.py`

**Filer:** `parser/onboarding.py` (ny), `tests/test_onboarding.py` (ny)

Ren logik, ingen Streamlit, ingen I/O utöver de anrop som anges.

```python
@dataclass(frozen=True)
class Steg:
    nyckel: str
    rubrik: str
    klart: bool
    atgard: str      # vad användaren ska göra härnäst
```

```python
def las_status() -> list[Steg]:
    """Fem steg, i ordning: villkor, Spiris-uppgifter, Spiris-inloggning,
    Claude-konfiguration, klart."""
```

Statuskällorna, samtliga befintliga:

| Steg | Källa | Klart när |
|---|---|---|
| `villkor` | `compliance` | Villkoren är godkända |
| `uppgifter` | `app_config.las_config` | client_id och secret är ifyllda |
| `inloggning` | `spiris_session` | En session finns och går att avskydda |
| `klient` | `klientkonfig.las_config` | `mcpServers["sie-mcp"]` finns |
| `klar` | de fyra ovan | Alla fyra är klara |

Fail-closed: varje kontroll som kastar undantag räknas som **inte klar**, med
en `atgard` som säger vad som gick fel i klartext. En guide som påstår att ett
steg är klart när kontrollen inte kunde köras är värre än ingen guide.

**`las_status` får aldrig läsa eller returnera ett hemligt värde** — bara
`True`/`False` för om det finns.

**Tester (minst 10),** varav minst ett per steg och ett som låser att inget
hemligt värde läcker ut i `Steg`-objekten.

### C2 — `parser/rum/kom_igang.py`

**Filer:** `parser/rum/kom_igang.py` (ny), rumsregistrering, `tests/`

Ett nytt rum i Sju-rums-modellen. Följ formen i ett befintligt rum, förslagsvis
`parser/rum/foretagsdata.py`, i sin helhet innan du skriver.

Vyn visar de fem stegen som en checklista och öppnar det första som inte är
klart.

**Steg 1, villkor:** återanvänd den befintliga villkorsvyn. Bygg ingen ny
kryssruteuppsättning — godkännandet är en juridisk handling och dess
utformning är redan bestämd.

**Steg 2, Spiris-uppgifter:** sidan ska innehålla, i den här ordningen:

1. En klickbar länk till `https://selfservice.developer.vismaonline.com/`.
2. Texten att uppgifterna kommer med **mejl** och att det kan dröja.
3. Den exakta callback-URL:en, i ett fält med kopieringsknapp, med texten
   "Klistra in denna som callback-URL i registreringen. Den måste stämma
   tecken för tecken."
4. Fält för client_id och client_secret, som sparas via
   `app_config.spara_falt`.
5. En upplysning om att sandbox-uppgifter fungerar direkt, men att
   produktionsåtkomst kräver att man kontaktar Vismas API-support.

Punkt 3 och 5 är de två som avgör om användaren lyckas. Utelämna dem inte.

**Steg 3, inloggning:** knappen från A2.

**Steg 4, Claude-konfiguration:** en knapp "Skriv in i Claude Desktop" som
anropar `klientkonfig.skriv_in_sie_mcp`, visar sökvägen till säkerhetskopian,
och därefter texten "Starta om Claude Desktop så dyker verktygen upp." Hittas
ingen `claude_desktop_config.json` visas JSON-posten att kopiera för hand i
stället — Claude Desktop kanske inte är installerat.

**Steg 5:** en kort text om vad man kan fråga om, och en länk till
`KUNSKAP.md`.

Rummet ska öppnas automatiskt när `las_status()` visar att något steg
återstår. En användare som redan är klar ska inte mötas av en guide.

**Tester (minst 8).**

**GRIND C.** Rapportera och stanna.

---

## Etapp D — Installern

Ingen Python-kod. Bygger på N2 och N3.

### D1 — Miljöbygge och startare

**Filer:** `installer/skapa_miljo.cmd`, `installer/starta_app.cmd`,
`installer/starta_mcp.cmd` (alla nya)

`skapa_miljo.cmd` körs en gång vid installation:

```
uv venv "%~dp0.venv"
uv pip install --python "%~dp0.venv\Scripts\python.exe" -r "%~dp0app\requirements.txt"
```

Regler:

- `uv.exe` ligger bredvid skriptet, levererat av installern. Ingen nedladdning
  vid installationstillfället utöver Python-paketen själva.
- Misslyckas installationen ska skriptet skriva ett läsbart svenskt felmeddelande
  och returnera en nollskild kod, så att installern kan visa det.
- Inga sökvägar hårdkodas. `%~dp0` genomgående — användaren kan ha valt en
  annan installationskatalog.

`starta_app.cmd` sätter `PYTHONPATH` till `app;app\parser` och kör
`streamlit run app.py`. `starta_mcp.cmd` gör detsamma men startar
`python -m mcp_server.server`.

### D2 — Inno Setup-skriptet

**Filer:** `installer/sie-mcp.iss` (ny)

| Inställning | Värde | Varför |
|---|---|---|
| `PrivilegesRequired` | `lowest` | **Ingen UAC-ruta.** Den enskilt största friktionsvinsten |
| `DefaultDirName` | `{localappdata}\Programs\sie-mcp` | Per användare |
| `ArchitecturesInstallIn64BitMode` | `x64compatible` | — |
| `OutputDir` | `..\dist` | — |
| `OutputBaseFilename` | `sie-mcp-setup` | — |

Filer som ingår: hela källträdet till `{app}\app` (utom `.git`, `tests`,
`__pycache__`, `.venv`, `dist`), `uv.exe`, och de tre `.cmd`-filerna.

Efter kopieringen körs `skapa_miljo.cmd` som ett `[Run]`-steg med
`StatusMsg: "Förbereder miljön — det tar en stund första gången"`.

Genvägar på Start-menyn:

- **sie-mcp** → `starta_app.cmd` (öppnar appen och därmed guiden)
- **sie-mcp — kom igång** → samma, men dokumenterad som ingången

Ingen genväg till MCP-servern. Den startas av Claude Desktop, aldrig av
användaren.

`[UninstallDelete]` tar bort `{app}` men **aldrig** `%LOCALAPPDATA%\sie-mcp`.
Lägg i stället en avinstallationsfråga: "Vill du även radera dina sparade
inloggningar och loggar?" med **Nej** som förval. Skälet står i
arkitekturdokumentet 7.

### D3 — Byggskriptet

**Filer:** `installer/bygg.ps1` (ny)

Hämtar `uv.exe` för Windows x64 till `installer/verktyg/`, verifierar dess
SHA-256 mot ett värde som står i skriptet, och kör Inno Setup-kompilatorn.

Hashkontrollen är inte formalia: `uv.exe` körs på användarens dator med
användarens rättigheter. Ett obekräftat binärt beroende i en installer är
precis den leveranskedjerisk projektets riskregister finns för.

Misslyckas hashen: avbryt, radera filen, skriv ut båda hasharna.

**Tester:** inga automatiska. Manuellt godkännandeprov i D4.

### D4 — Installationsprov (utförs INTE av dig)

Arkitekten eller användaren installerar på en dator **utan** Python och
verifierar: ingen UAC-ruta, guiden öppnas, alla fem stegen går att slutföra,
Claude Desktop hittar servern efter omstart, avinstallationen behåller
användardata.

**GRIND D.** Rapportera och stanna.

---

## Etapp E — Dokumentationen

### E1 — `KOM_IGANG.md`

**Filer:** `KOM_IGANG.md` (ny)

Skriven för någon som inte vet vad en terminal är. Krav:

- **Inga kommandon.** Finns ett kommando i texten har den misslyckats.
- SmartScreen-varningen beskrivs i förväg, med exakt de ord Windows visar och
  vad man klickar på. En osignerad installer som överraskar användaren blir
  inte installerad.
- Väntan på Vismas mejl står som ett eget avsnitt, inte som en parentes.
- Ett avsnitt "När något inte fungerar" med de tre troligaste felen: port
  44300 upptagen, callback-URL som inte matchar tecken för tecken, och Claude
  Desktop som inte startats om.
- Sist: vad man faktiskt kan fråga om när det är klart. En användare som
  installerat men inte vet vad hen ska säga har inte kommit fram.

### E2 — README-omdisposition

**Filer:** `README.md`

Problemet i dag är inte vad som står, utan ordningen. Installationsvägen ligger
efter cirka 400 ord juridisk varningstext, och den varningstexten är avsiktlig
och ska stå kvar **oförkortad**.

Lösningen: lägg **en** rad högst upp, före varningsrutan:

> **Vill du bara komma igång?** → [KOM_IGANG.md](KOM_IGANG.md)

Ändra sedan:

- Avsnittet "Snabbstart" blir "Installation för utvecklare" och behåller
  venv-vägen. Den är fortfarande rätt för den som vill läsa koden.
- Lägg till att **Spiris-vägen kräver Windows** (N7), med skälet: OAuth-sessionen
  skyddas med Windows DPAPI och har ingen osäker fallback.
- Rätta verktygsantalet. README säger "54 primära verktyg … totalt 85". Räknat
  2026-08-10 har `mcp_server/server.py` **120** `@mcp.tool`, **4**
  `@mcp.resource` och **5** `@mcp.prompt`. Räkna om själv innan du skriver —
  talet rör sig — och dela upp det som README redan gör, i primära verktyg
  respektive alias. Ett dokument som ljuger om ett kontrollerbart tal blir inte
  trott om resten heller.
- Verktygstabellen i README listar bara ett tjugotal av verktygen och saknar
  allt från Etapp 8–15b. Antingen kompletterar du den eller ersätter den med
  grupprubriker och en hänvisning till att klienten listar verktygen själv.
  Låt den inte stå kvar som en ofullständig lista som ser fullständig ut.

**GRIND E.** Rapportera och stanna.

---

## Etapp F — Diagnos

### F1 — `sie-mcp-doktorn`

**Filer:** `parser/onboarding.py` (utökas), `parser/rum/kom_igang.py`, `tests/`

En knapp "Kontrollera min installation" som kör och visar:

| Kontroll | Visar |
|---|---|
| Python-version | Versionen och om den räcker |
| Beroenden | Vilka som saknas |
| Villkor | Godkända eller ej |
| Spiris-uppgifter | Ifyllda eller ej — **aldrig värdet** |
| Spiris-session | Finns, går att avskydda, och vilket bolag den gäller |
| Port 44300 | Ledig eller upptagen |
| Claude-config | Finns, och om `sie-mcp` står i den |
| Datakatalog | Sökväg och skrivbarhet |

Varje rad har en åtgärdstext. Utdatat ska gå att kopiera som text vid en
felanmälan — och därför får det **aldrig** innehålla client_id, client_secret,
tokens eller filinnehåll.

**Tester (minst 8),** varav minst ett som låser att inget hemligt värde
förekommer i utdatat.

**GRIND F.** Rapportera och stanna.

---

## 2. Rapportmall

```
UPPGIFT: <A1, B1, …>
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

Rapportera aldrig "klar" om sviten inte är grön.
