# Arkitektur — driftsättning utan friktion

**Datum:** 2026-08-10
**Syfte:** göra sie-mcp installerbart av någon som inte vet vad en terminal är
**Läs före:** `PLAN_INSTALLATION.md`

---

## 1. Nuläget: tolv steg

Så här ser vägen ut i dag, från att någon hittar repot till att verktygen svarar
i Claude. Varje rad är ett tillfälle att ge upp.

| # | Steg | Var det går fel |
|---|---|---|
| 1 | Installera Python | Finns inte förinstallerat på Windows |
| 2 | Klona eller ladda ner repot | "Vad är git?" |
| 3 | Skapa och aktivera venv | Plattformsspecifik kommandorad |
| 4 | `pip install -r requirements.txt` | Fel Python i PATH |
| 5 | Godkänna villkoren | Kräver en bekräftelsefras i terminal |
| 6 | Registrera sig hos Spiris självbetjäning | Väntan på mejl |
| 7 | Ange callback-URL vid registreringen | Värdet står bara hårdkodat i källkoden |
| 8 | Klistra in client_id och secret | — |
| 9 | Logga in mot Spiris | **Webbläsaren landar på en sida som inte finns.** Användaren ska kopiera adressfältet tillbaka in i appen |
| 10 | Handredigera `claude_desktop_config.json` | Sökvägar med bakstreck, JSON-syntax |
| 11 | Starta om Claude Desktop | Odokumenterat |
| 12 | Hitta rätt bland 120 verktyg | — |

Steg 9 är det värsta. `REDIRECT_URI` i `spiris_auth_vy.py` pekar på
`https://localhost:44300/callback`, men **ingenting i kodbasen lyssnar på den
porten**. OAuth-flödet är alltså konstruerat kring att användaren manuellt
klipper ut en auktoriseringskod ur en felsida.

---

## 2. Tre väggar

**V1 — Vismas registreringsmodell.** Självbetjäningen
(`selfservice.developer.vismaonline.com`) ger sandbox-uppgifter via mejl. Men
produktionsåtkomst kräver enligt Vismas egen guide att man kontaktar
API-supporten: *"When you're ready to go live with your application, please
contact API support to get access to the production environment."* Steg 6–7
kan därför **inte** automatiseras bort så länge användaren äger registreringen.
De kan bara guidas.

**V2 — Windows-låset.** `saker_lagring.dpapi_skydda` är Windows-DPAPI utan
fallback, med flit ("ingen osäker fallback"). OAuth-sessionen kan alltså inte
sparas på macOS eller Linux. Spiris-vägen är Windows-exklusiv redan i dag, och
det står ingenstans i README.

**V3 — allt annat.** Steg 1–5 och 9–11 är självförvållade och rivs i den här
planen.

---

## 3. Beslut

**N1 — BYOK behålls.** Användaren registrerar sig själv hos Spiris och äger
avtalet. Quiet Numbers registrerar ingen app och distribuerar ingen
`client_secret`. Hela ansvarsmodellen i `DISCLAIMER_AND_TERMS.md` och
`DATASKYDD.md` står därmed oförändrad, och ingen token passerar någon server
som projektet driver.

Priset är att steg 6–7 finns kvar. De blir guidade, inte borttagna.

**N2 — Distributionen är en Windows-installer.** En `.exe` byggd med Inno
Setup, installerad **per användare** i `%LOCALAPPDATA%\Programs\sie-mcp`.
Per-användarinstallation betyder att **UAC aldrig visas** — inget
administratörslösenord, ingen företagsspärr. Det är den enskilt största
friktionsvinsten i valet av installationsform.

Installern är osignerad tills vidare. Windows SmartScreen visar då en varning
första gången ("Mer info → Kör ändå"). Det ska stå i `KOM_IGANG.md` med
skärmbildstext, inte döljas. Kodsignering är ett senare beslut.

**N3 — Ingen paketering till wheel.** `parser/`-modulerna importerar varandra
platt (`from spiris_klient import …`) och förutsätter att katalogen ligger i
`sys.path`. Ett wheel skulle kräva att ~90 filer och 2400 tester rörs, med
motsvarande regressionsrisk, för noll synlig nytta.

Installern kopierar i stället källträdet och bygger miljön på plats med `uv`.
Genvägarna sätter `PYTHONPATH` innan de startar Python. Resultatet för
användaren är identiskt.

**N4 — Guiden är Streamlit-appen, inte ett nytt program.** Projektet har redan
ett testat UI-lager (Sju-rums-modellen). Onboardingen blir ett nytt rum,
`Kom igång`, som appen öppnar automatiskt när konfigurationen är ofullständig.
Ingen andra UI-verktygslåda införs, och guiden ärver befintlig
sessionshantering, felhantering och stil.

**N5 — OAuth får en lokal lyssnare.** Steg 9 försvinner. En kortlivad
HTTP-server på `localhost:44300` tar emot återanropet, plockar `code` och
`state`, visar en klarsida och stänger sig själv.

Två ovillkorliga regler: lyssnaren binder **enbart** `127.0.0.1`, aldrig
`0.0.0.0`, och den lever bara under inloggningen med en timeout på 180
sekunder. En öppen port som står kvar är en attackyta, inte en bekvämlighet.

**N6 — Guiden skriver Claude Desktops konfiguration, med säkerhetskopia.**
`%APPDATA%\Claude\claude_desktop_config.json` läses, en tidsstämplad kopia
sparas, **enbart** nyckeln `mcpServers["sie-mcp"]` sätts, resten av filen
lämnas orörd, och resultatet skrivs atomiskt. Filen ägs av ett annat program
och kan innehålla andra användares MCP-servrar — den får aldrig skrivas över.

**N7 — Windows dokumenteras som kravet.** README och `KOM_IGANG.md` säger
uttryckligen att Spiris-vägen kräver Windows. SIE4-vägen fungerar där den
fungerar. `saker_lagring.py` rörs inte.

---

## 4. Målbilden: fyra steg

| # | Steg | Vad användaren gör |
|---|---|---|
| 1 | Ladda ner och kör `sie-mcp-setup.exe` | Dubbelklick. Ingen UAC, ingen terminal |
| 2 | Guiden öppnas i webbläsaren | Godkänn villkoren, punkt för punkt |
| 3 | Anslut till Spiris | Guiden visar exakt callback-URL att klistra in hos Visma, tar emot client_id/secret, öppnar inloggningen och **fångar återanropet själv** |
| 4 | Starta om Claude Desktop | Guiden har redan skrivit konfigurationen och säger till |

Steg 6–7 i nuläget lever kvar inuti steg 3, men som en guidad sida med
klickbar länk, förifylld callback-URL att kopiera, och en tydlig markering av
att man väntar på ett mejl.

Villkorsgodkännandet blir **inte** enklare. Det ska fortfarande vara en
medveten handling — men ceremonin flyttas från en bekräftelsefras i en terminal
till kryssrutor i guiden, vilket är exakt vad `compliance.py` redan stöder via
Streamlit-vägen.

---

## 5. Komponenter

| Komponent | Fil | Ansvar |
|---|---|---|
| Installer | `installer/sie-mcp.iss` | Inno Setup: kopiera träd, bygg miljö, skapa genvägar |
| Byggskript | `installer/bygg.ps1` | Hämta `uv.exe`, kör Inno Setup, lägg utdata i `dist/` |
| Miljöbygge | `installer/skapa_miljo.cmd` | Körs vid installation: `uv venv` + `uv pip install -r requirements.txt` |
| Startare | `installer/starta_app.cmd`, `installer/starta_mcp.cmd` | Sätter `PYTHONPATH`, startar rätt process |
| OAuth-lyssnare | `parser/oauth_lyssnare.py` | Lokal callback-mottagare (N5) |
| Klientkonfiguration | `parser/klientkonfig.py` | Läs/säkerhetskopiera/slå ihop Claude-config (N6) |
| Onboardinglogik | `parser/onboarding.py` | Rena, testbara statuskontroller |
| Onboardingrum | `parser/rum/kom_igang.py` | Streamlit-vyn |
| Dokumentation | `KOM_IGANG.md` | Skriven för en icke-tekniker |

Lagerordningen från konstitutionen gäller: vyn anropar `onboarding.py`, som
anropar `klientkonfig.py` och `oauth_lyssnare.py`. Ingen HTTP-logik i vyn,
ingen Streamlit i logikmodulerna.

---

## 6. Att verifiera innan bygget

**Callback-URL:ens protokoll.** Registreringsformuläret hos Visma kan kräva
`https`. Nuvarande hårdkodade värde är `https://localhost:44300/callback`,
vilket antyder det.

- Godtas `http://localhost:44300/callback` blir lyssnaren en vanlig
  `http.server` och användaren ser ingenting särskilt.
- Krävs `https` måste lyssnaren presentera ett självsignerat certifikat.
  `cryptography` finns redan som beroende och kan generera det. Priset är en
  engångsvarning i webbläsaren ("Din anslutning är inte privat → Avancerat →
  Fortsätt"), vilket fortfarande är mycket bättre än att klippa ut en URL ur en
  felsida.

Detta avgörs mot registreringsformuläret, inte i koden. Uppgift A0 i planen
gör det, och resten av OAuth-arbetet väntar på svaret.

---

## 7. Avgränsningar

**Byggs inte:** kodsignering, automatisk uppdatering, macOS- eller
Linux-installer, MSI (Inno Setup ger `.exe`, vilket räcker), och någon form av
gemensam app-registrering (N1).

**Rörs inte:** `saker_lagring.py`, `compliance.py`, `sekretesslager.py`,
`utkast.py` och övriga filer i konstitutionens §4-lista. Onboardingen anropar
dem, den ändrar dem inte.

**Avinstallationen raderar inte användardata.** `%LOCALAPPDATA%\sie-mcp`
innehåller OAuth-tokens, krypterade liggare och loggar med möjliga
personuppgifter. Att tyst radera dem vid avinstallation vore fel åt båda håll:
det förstör underlag användaren kan behöva, och det ger ett falskt intryck av
att allt är borta. Avinstalleraren frågar, med förvalt "behåll".
