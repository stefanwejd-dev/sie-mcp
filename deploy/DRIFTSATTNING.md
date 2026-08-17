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
