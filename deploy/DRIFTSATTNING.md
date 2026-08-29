# Driftsättning av sie-mcp

## Vem gör vad

Tre lager, tre ägare. Att blanda ihop dem är den vanligaste orsaken till att en
driftsättning «inte tar».

| Lager | Vad det är | Vad du gör där |
|---|---|---|
| **Hostup.se** | DNS för `quiet.nu` | A-poster. Rörs bara när ett nytt värdnamn tillkommer. |
| **Netcup** | Själva servern — CPU, RAM, disk, nät | Skala upp maskinen. Ingen programvara installeras för hand. |
| **Coolify** | All programvara: applikationer, byggen, containrar, hemligheter, TLS | Här sker allt som rör den här appen. |

Netcup är alltså **järnet**. Coolify är **allt annat**. Behöver appen mer minne
är det Netcup; ska den köra ny kod är det Coolify.

> **Historisk not.** Tidigare versioner av det här dokumentet beskrev manuell
> driftsättning på servern med `git clone`, `docker compose up`, egen
> nginx-konfiguration och certbot. Det speglar inte hur appen körs. Instruktionen
> ledde 2026-08-29 till rådet «kör `git pull` på servern», vilket är fel i en
> Coolify-driven miljö. `deploy/nginx.conf` och `deploy/sie-mcp.service` ligger
> kvar som referens för den som vill köra utan Coolify — de används inte i drift.

---

## 1. Att driftsätta ny kod

Applikationen i Coolify är bunden till GitHub-repot och en gren. Coolify hämtar
koden själv.

1. Öppna applikationen i Coolify (`sie-mcp:main-…`).
2. Tryck **Redeploy**.
3. Läs byggloggen. Den ska sluta grönt — se §3 om varför det inte alltid betydde
   något förut.

Har du auto-deploy via webhook påslaget bygger Coolify om sig självt vid push.
Kontrollera i så fall bara att senaste deployen bär rätt commit.

**Kör inte `git pull` i Coolifys Terminal.** Den terminalen ger ett skal *inuti
den körande containern*. Två saker går fel: ändringen försvinner vid nästa
deploy, och fram till dess kör produktionen något som inte står i git.

Terminalen är däremot rätt plats för att **kontrollera** efter en deploy — §4.

---

## 2. Hemligheter

I Coolify, under applikationens **Environment Variables**. Aldrig i en fil på
disk, aldrig i `docker-compose.yml`, aldrig i repot.

| Variabel | Behövs för |
|---|---|
| `BOLAGSVERKET_CLIENT_ID` | Bolagsverkets fria API |
| `BOLAGSVERKET_CLIENT_SECRET` | samma |
| `ANTHROPIC_API_KEY` | syntesmotorn bakom `fraga_myndighetskallor` |

---

## 3. Den privata beroendekedjan

**Det här är fällan som kostade mest.**

`requirements.txt` hämtar `quiet-oppen-data` från
`git+https://github.com/stefanwejd-dev/quiet_chatt.git`. **Det repot är privat.**
Docker-bygget har inga GitHub-uppgifter, så installationen misslyckas.

Fram till 2026-08-29 fångades det av en reservgren i `Dockerfile`:

```dockerfile
RUN pip install -r requirements.txt || pip install streamlit plotly httpx …
```

Reservlistan innehöll **inte** `quiet-oppen-data`. Bygget lyckades, avbilden såg
frisk ut, och paketet saknades — vilket upptäcktes först när Coolifys terminal
svarade `ModuleNotFoundError: No module named 'quiet_oppen_data'`. Alla
myndighetsverktyg var trasiga i drift utan att något sagt ifrån.

Reservgrenen är borttagen. Bygget faller nu i stället, och en extra `RUN`
kontrollerar att paketet går att importera innan avbilden blir färdig.

### Så gör du det installerbart

Ge bygget en läsbehörig token som **BuildKit-hemlighet**:

1. Skapa en fine-grained PAT på GitHub med **Contents: Read** för `quiet_chatt`.
2. I Coolify: applikationen → **Build** → **Secrets** → ny hemlighet med id
   **`github_token`** och tokenet som värde.
3. Redeploy.

Hemligheten monteras bara under `pip install` och hamnar aldrig i ett
avbildslager — till skillnad från ett `ARG`, som ligger kvar i `docker history`.

**Nästa deploy faller om du inte gör det här först.** Det är avsiktligt: en
avbild utan sina beroenden ska inte gå i drift, och det gamla beteendet dolde
just det.

*Alternativ som slipper token helt:* gör `quiet_chatt` publikt. Paketet bär ingen
hemlighet — chatten det driver är redan öppen på quiet.nu. Det är ett beslut för
uppdragsgivaren, inte en teknisk fråga.

---

## 4. Kontrollera efter deploy

I Coolifys Terminal för applikationen:

```bash
python -c "import quiet_oppen_data.adaptrar.bolagsverket; print('adaptern finns')"
python -c "import quiet_oppen_data.motor.syntes as s; print('form' in s.SVARSSCHEMA['properties']['stycken']['items']['properties'])"
```

Andra raden ska skriva `True`. Skriver den `False` kör containern en äldre
`quiet-oppen-data` — bygg om utan cache (§5).

---

## 5. Cachefällan

`requirements.txt` låser inte `quiet-oppen-data` till en commit. Ändras inte
filen återanvänder Docker det cachade `pip install`-lagret, och du får **gammal
kod i en ny container** utan att något ser fel ut.

Efter en ändring i `quiet_chatt`: använd **Redeploy utan cache** («Force
rebuild» / «Rebuild without cache») i Coolify.

---

## 6. Bolagsverket — tre verktyg mot myndighetens fria API

`bolagsverket_organisation`, `bolagsverket_arsredovisningar` och
`bolagsverket_arsredovisning_innehall`. Källan är API:et för **värdefulla
datamängder** — gratis, utan avtal.

### Vad som INTE syns på quiet.nu

Verktygen ligger i `mcp_server/server.py` och körs av en **MCP-klient**.
`app.py` importerar inte MCP-servern, och `Dockerfile` startar bara Streamlit.
Att driftsätta dem ändrar alltså ingenting i webbgränssnittet. Ska funktionen
synas där krävs en vy i `app.py` — den är inte skriven.

Det betyder också att `BOLAGSVERKET_*` bara behövs där MCP-servern faktiskt
körs.

### Två sökvägsvariabler som verktygen sätter själva

Inget att konfigurera — men värt att känna till om något ändå går fel.
`_bolagsverket_adapter()` sätter `QUIET_OPPEN_DATA_ROOT` till sie-mcps rot och
primar `konfig.las()` med `quiet_config.toml`. Biblioteket letar annars efter
`kallor/kallregister.yaml` inne i `.venv` och efter `config.toml` i roten, och
båda saknas.

Symptomet är karakteristiskt: `bolagsverket_organisation` ger **noll fakta**
medan `bolagsverket_arsredovisning_innehall` fungerar — dokumenthämtningen går
medvetet förbi den delade transporten (svaret är en binär zip) och drabbas
därför inte.

### Gränsen som inte får flyttas i drift

Verktygen rör bara `vardefulla-datamangder/v1`. `/foretagsinformation/v4` är
avtalsbundet och avgiftsbelagt. `/verkliga-huvudman/v1` bär personuppgifter om
fysiska personer och är spärrad i `kallor/kallregister.yaml`
(`blockerad: true`). Att öppna någon av dem är ett beslut som ska skrivas, inte
en miljövariabel som ändras.

---

## 7. DNS hos Hostup.se

Rörs **inte** av vanliga driftsättningar. Bara när ett nytt värdnamn tillkommer:

| Typ | Namn | Innehåll | TTL |
|---|---|---|---|
| A | `app` | Netcup-serverns IP | 300 |

TLS sköter Coolify.
