# Bidra till sie-mcp

Tack för att du vill bidra till **sie-mcp**! Projektet är öppen källkod under MIT-licens. För att bevara projektets säkerhets-, integritets- och arkitekturinvarianter gäller följande riktlinjer för alla ändringar.

---

## 1. Regler för ändringar

* **Hela testsviten måste förbli grön:** Kör `python -m pytest -q` innan du öppnar en pull request. Antalet passerade tester får inte sjunka.
* **Inga hemligheter eller känsliga data:** Lägg aldrig in API-nycklar, tokens, lösenord eller riktiga person- eller företagsdata i kod, tester, loggar eller exempel (använd fiktiva organisationsnummer och testbolag i stil med `samples/`).
* **Inga ändringar i juridiska villkor:** [DISCLAIMER_AND_TERMS.md](DISCLAIMER_AND_TERMS.md), [ANSVAR.md](ANSVAR.md) och [LICENSE](LICENSE) fastställer det juridiska ramverket och ändras enbart efter uttryckligt beslut av projektets utgivare.

---

## 2. Arkitekturkrav

* **Lokal först & Fail-closed:** Systemet nekar hellre än att gissa eller exponera råfel. Inga tysta nätverksanrop vid start.
* **Inga dolda beroenden:** Alla beroenden ska vara explicit deklarerade i `requirements.txt` / `pyproject.toml`.
* **Skydda egress-gränsen:** Inga bokföringsdata eller fritext får lämna maskinen till externa AI-modeller utan föregående maskering/pseudonymisering via säkerhetslagret.
* **Utkastvägen:** En AI-agent får aldrig ges förmåga att utföra direkta skrivningar i affärssystem. Skrivande åtgärder måste alltid gå via utkastkön (`parser/utkast.py`) för mänsklig granskning.

---

## 3. Hur man rapporterar fel

* Skapa ett ärende på [GitHub Issues](https://github.com/stefanwejd-dev/sie-mcp/issues).
* Beskriv felet, förväntat kontra faktiskt beteende, samt steg för att reproducera det.
* **Bifoga aldrig personuppgifter, känsliga företagshemligheter eller API-nycklar i felrapporter.** Rensa alla loggutdrag och SIE-rader från personnamn, personnummer och skarpa organisationsnummer innan du postar.
