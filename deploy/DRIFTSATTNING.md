# 🚀 Driftsättning av sie-mcp på Netcup-servern (quiet.nu)

Detta dokument beskriver hur du driftsätter **sie-mcp** på din Netcup-server bredvid befintliga `api.quiet.nu`, så att allmänheten kan nå systemet på t.ex. `https://app.quiet.nu` eller `https://sie.quiet.nu`.

---

## 1. DNS-inställning hos Hostup.se

Logga in hos **Hostup.se** och lägg till ett A-record för din domän:

| Typ | Namn / Värd | Innehåll / IP-adress | TTL |
| :--- | :--- | :--- | :--- |
| **A** | `app` | `DIN_NETCUP_SERVER_IP` | 300 / Standard |

*(Detta gör att anrop till `app.quiet.nu` styrs till din Netcup-server).*

---

## 2. Alternativ A: Driftsättning med Docker (Rekommenderat)

Om du har Docker och Docker Compose installerat på din Netcup-server:

```bash
# 1. Klona repot till servern
cd /var/www
git clone https://github.com/ditt-konto/sie-mcp.git
cd sie-mcp

# 2. Bygg och starta containern i bakgrunden
docker compose up -d --build

# 3. Kontrollera att appen körs
docker compose ps
docker compose logs -f
```

---

## 3. Alternativ B: Driftsättning med Systemd & Python venv

Om du föredrar direkt körning i Linux:

```bash
# 1. Klona och installera beroenden
cd /var/www
git clone https://github.com/ditt-konto/sie-mcp.git
cd sie-mcp
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. Installera och starta systemd-tjänsten
cp deploy/sie-mcp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable sie-mcp
systemctl start sie-mcp

# 3. Kontrollera status
systemctl status sie-mcp
```

---

## 4. Nginx Reverse Proxy & Gratis HTTPS (Certbot)

På Netcup-servern skapar du en Nginx-konfiguration för `app.quiet.nu`:

```bash
# 1. Kopiera Nginx-konfigurationen
cp /var/www/sie-mcp/deploy/nginx.conf /etc/nginx/sites-available/app.quiet.nu

# 2. Aktivera sajten
ln -s /etc/nginx/sites-available/app.quiet.nu /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# 3. Skapa gratis SSL-certifikat med Certbot
certbot --nginx -d app.quiet.nu
```

---

## 5. Klart! 🎉

Appen är nu live på **`https://app.quiet.nu`**!

* Besökare möts automatiskt av en snabb, snygg och professionell granskning av SIE-data och MCP-verktyg.
* Inbyggt demoläge (`SIE_MCP_DEMO=1`) säkerställer att publiken omedelbart kan klicka runt och se alla 19 avvikelser, tidslinjer, ISA 450-analys och bokslutskontroller utan att behöva ladda upp filer själva.

---

## 6. Bolagsverkets värdefulla datamängder (tillagt 2026-08-29)

Tre MCP-verktyg — `bolagsverket_organisation`, `bolagsverket_arsredovisningar`
och `bolagsverket_arsredovisning_innehall` — slår upp svenska organisationer
i Bolagsverkets **fria** API och läser innehållet i deras årsredovisningar. Innan du
driftsätter: läs vilket av två spår du faktiskt vill ha, för de rör olika filer.

### Spår A — verktygen i en MCP-klient (det som är byggt)

Verktygen ligger i `mcp_server/server.py`. Den processen startas av
MCP-klienten (Claude Desktop och liknande), **inte** av Streamlit-appen på
quiet.nu. `app.py` importerar inte MCP-servern, och `Dockerfile` startar bara
Streamlit. Ingenting på quiet.nu ändras av att verktygen finns.

Att driftsätta dem betyder därför:

| Fil | Ändring |
|---|---|
| `mcp_server/server.py` | **klar** — de tre verktygen är tillagda |
| MCP-klientens konfiguration | inget att ändra, verktygen upptäcks automatiskt vid omstart |
| Klientens venv | `quiet_oppen_data` måste uppdateras, se nedan |

### Spår B — funktionen synlig på quiet.nu

Kräver att `app.py` får en vy som anropar adaptern. **Den är inte skriven.**
Utan den syns funktionen inte i webbgränssnittet, hur mycket du än driftsätter.

### Beroendet måste uppdateras — annars finns adaptern inte

`requirements.txt` pekar på `quiet-oppen-data @ git+https://github.com/stefanwejd-dev/quiet_chatt.git`
utan commit-låsning. Den installerade versionen (0.1.0) är en **äldre ögonblicksbild
utan Bolagsverket-adaptern** — kontrollerat 2026-08-29: `adaptrar/bolagsverket.py`
saknas i `.venv`. Adaptern finns i quiet_chatt sedan commit `9efe1df` och är
pushad till origin/main.

```bash
# venv-installationen
pip install --upgrade --force-reinstall --no-deps   "quiet-oppen-data @ git+https://github.com/stefanwejd-dev/quiet_chatt.git"

# eller, i Docker: bygg om utan lager-cache
docker compose build --no-cache && docker compose up -d
```

Kontrollera efteråt:

```bash
python -c "import quiet_oppen_data.adaptrar.bolagsverket; print('adaptern finns')"
```

### Hemligheterna

Adaptern läser `BOLAGSVERKET_CLIENT_ID` och `BOLAGSVERKET_CLIENT_SECRET` ur
miljön. Saknas de returnerar verktygen ett fel — de gissar inte och de kraschar
inte servern.

**Docker** — lägg dem i en `.env` bredvid `docker-compose.yml` (och i
`.gitignore`), och peka ut den i `docker-compose.yml`:

```yaml
services:
  sie-mcp:
    env_file:
      - .env
```

Skriv dem **inte** i `environment:`-listan — den ligger i git.

**Systemd** — `deploy/sie-mcp.service` bär i dag bara `Environment="SIE_MCP_DEMO=1"`.
Lägg hemligheterna i en fil som bara root läser, och peka på den:

```ini
EnvironmentFile=/etc/sie-mcp/hemligheter.env
```

```bash
install -d -m 700 /etc/sie-mcp
printf 'BOLAGSVERKET_CLIENT_ID=...
BOLAGSVERKET_CLIENT_SECRET=...
'   > /etc/sie-mcp/hemligheter.env
chmod 600 /etc/sie-mcp/hemligheter.env
systemctl daemon-reload && systemctl restart sie-mcp
```

### Villkorsspärren gäller

Båda verktygen ligger bakom `_villkor_godkanda()`, precis som
`fraga_myndighetskallor`. Är villkoren inte godkända returnerar de spärrtexten i
stället för att göra ett utgående anrop. Det är avsiktligt: verktygen skickar ett
organisationsnummer som kommer från AI-klienten till en myndighet.

### Vad som INTE ändras

* **DNS hos Hostup.se** — ingen ny post. Funktionen bor på befintlig värd.
* **`deploy/nginx.conf`** — ingen ny route, ingen ny port.
* **Certifikat** — ingen ny hostname, ingen ny certbot-körning.
* **`quiet_chatt`** — adaptern finns redan där och är pushad. Inget att göra.

### Gränsen som inte får flyttas i drift

Adaptern rör **bara** `vardefulla-datamangder/v1`. Bolagsverkets
`/verkliga-huvudman/v1` bär personuppgifter om fysiska personer och är spärrad i
`kallor/kallregister.yaml` (`bolagsverket_verkliga_huvudman`, `blockerad: true`).
Att öppna den är ett beslut som ska skrivas, inte en miljövariabel som ändras.

### Två sökvägsvariabler som verktygen sätter själva

Ingenting att konfigurera i drift — men värt att känna till om något går fel:
`_bolagsverket_adapter()` sätter `QUIET_OPPEN_DATA_ROOT` till sie-mcps rot och
primar `konfig.las()` med `quiet_config.toml`. Biblioteket letar annars efter
`kallor/kallregister.yaml` inne i `.venv` och efter `config.toml` i roten, och
båda saknas. Symptomet är att `bolagsverket_organisation` ger noll fakta medan
`bolagsverket_arsredovisning_innehall` fungerar — dokumenthämtningen går
medvetet förbi den delade transporten och drabbas därför inte.
