# Kunskapsunderlag för quiet.nu

Den här filen är skriven för **chatten på quiet.nu**, inte för utvecklare. Den
fångar det som `README.md` inte har plats för, och som en besökare kan tänkas
fråga om. Den bor i kodförrådet, inte i sidans databas, av två skäl: den
versioneras tillsammans med koden den beskriver, och den följer med den som
klonar projektet.

---

## Vad sie-mcp är, i en mening

Ett svenskt hobbyprojekt i Python som låter en AI-modell läsa och sammanställa
bokföring — antingen ur en SIE4-fil eller direkt ur ett affärssystem — och som
föreslår åtgärder utan att någonsin utföra dem själv.

Det finns i två skepnader ovanpå en delad kärna: en **Streamlit-app** som en
människa sitter framför, och en **MCP-server** som en AI-assistent talar med.
Samma kod, samma spärrar, två gränssnitt.

## Vem det är till för

Den som redan förstår siffrorna: redovisningskonsulten, revisorn,
ekonomiansvarige i ett litet bolag. Verktyget avlastar räknandet och
sammanställandet — det ersätter inte bedömningen. En användare som inte kan
avgöra om ett resultat är rimligt är fel användare, eftersom hela
ansvarsmodellen bygger på att någon granskar det som visas.

Det är också byggt för att vara läsbart av en utvecklare som vill se hur en
MCP-server kan hantera känsliga data utan att exponera skrivande verktyg.

## Vad det uttryckligen INTE gör

- **Bokför inte åt dig.** De verktyg som heter `forbered_*` lägger ett förslag i
  en lokal kö. En människa granskar och godkänner i Streamlit-appen innan något
  skickas vidare. MCP-servern exponerar inga skrivande verktyg alls.
- **Är ingen momsdeklaration.** `momsoversikt` är en beräkning, inte en
  inlämning till Skatteverket.
- **Lämnar inga garantier** om riktighet, säkerhet eller GDPR-efterlevnad.
  Siffror och AI-svar kan vara felaktiga, ofullständiga eller påhittade.
  Ansvaret för att verifiera varje uppgift mot originalkällan är användarens.
- **Är inte professionell rådgivning** — inte revisions-, redovisnings-,
  skatte- eller juridisk rådgivning, och ersätter inte egen bedömning enligt
  ISA, god revisionssed eller BFN:s allmänna råd.
- **Är inte säkerhetsgranskat** av tredje part.

Programvaran är dessutom **spärrad** tills villkoren godkänts punkt för punkt av
en människa på den dator där den körs. Godkännandet kan inte lämnas via MCP — en
AI-assistent får inte godkänna villkor åt någon.

## Vanliga frågor

**Skickas min bokföring till en AI-leverantör?**
Bara det du väljer att skicka, och först efter att ett pseudonymiseringslager
försökt byta ut identifierande uppgifter mot tokens. Lokala vyer — reskontra,
åldersanalys, rapporter — beräknas helt utan AI-anrop och fungerar utan
API-nyckel. Men pseudonymiseringen är **inte** ett skydd att förlita sig på: den
är ofullständig, och personuppgifter kan nå en extern leverantör i klartext utan
varning. Vill man undvika det helt finns stöd för en lokal modell via Ollama, då
lämnar inget datorn.

**Måste jag ha Spiris/Visma?**
Nej. SIE4-vägen fungerar helt fristående — det räcker med en exportfil från
vilket svenskt bokföringsprogram som helst. Affärssystemsintegrationen är ett
tillval, och den kräver ett eget utvecklarkonto hos leverantören.

**Vad kostar det?**
Programvaran är gratis och öppen källkod. Kostnaderna som kan uppstå är dina
egna: eventuella AI-anrop debiteras på din egen API-nyckel, och
affärssystemsåtkomsten sker under ditt eget avtal med leverantören. Det kallas
BYOK — *bring your own key*. Ingen betalning går genom projektet, och projektet
ser aldrig dina uppgifter.

**Vem ligger bakom?**
Utgivet av Quiet Numbers, som är ett hobbyprojekt och inte ett företag. Det är
en avsiktlig framställning: ett hobbyprojekt som är ärligt om sina brister är
mer trovärdigt än en produktsida som inte är det.

**Kan jag använda det i skarp drift?**
Det är inget som hindrar dig, och inget som rekommenderar det. Läs
`DISCLAIMER_AND_TERMS.md` först — hela det juridiska ansvaret för användningen
och för allt den leder till bärs av den som använder programvaran.

## Ord som förekommer

**SIE4** — svenskt standardformat för att exportera bokföring mellan program. En
textfil med poster som `#KONTO`, `#VER` och `#TRANS`. Nästan alla svenska
bokföringsprogram kan exportera det.

**MCP** — Model Context Protocol. En standard för hur en AI-modell får tillgång
till verktyg och data. En MCP-server erbjuder verktyg; AI-modellen anropar dem.

**Reskontra** — förteckningen över vad enskilda kunder ska betala
(kundreskontra) och vad företaget ska betala sina leverantörer
(leverantörsreskontra). Alltså huvudboken uppdelad per motpart.

**Väsentlighet** — i revision, tröskeln för hur stort ett fel måste vara för att
spela roll för den som läser bokslutet. Räknas fram ur omsättning, resultat,
balansomslutning och eget kapital enligt ISA 320, och används sedan för att
bedöma funna fel enligt ISA 450.

**Pseudonymisering** — att byta ut namn och identifierande uppgifter mot tokens
så att en text kan behandlas utan att peka ut en person. Skiljer sig från
anonymisering: kopplingen finns kvar hos den som har nyckeln, och uppgifterna är
därför fortfarande personuppgifter i GDPR:s mening.

**Fail-closed** — en spärr som säger nej när något är oklart, i stället för att
släppa igenom. Om en kontroll inte kan avgöra om en uppgift är säker att skicka,
skickas den inte.

**Utkast** — ett förslag som ligger i kö och väntar på en människas godkännande.
Grundmönstret i hela projektet: programvaran föreslår, människan bestämmer.

**BYOK / BYOA** — *bring your own key* / *bring your own account*. Alla
anslutningar sker med användarens egna nycklar och konton, under användarens
egna avtal.
