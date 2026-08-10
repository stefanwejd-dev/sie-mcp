# Visma Developer Portal – Getting Started

Källsidan är Visma Developer Portal-sidan "Getting Started".[cite:3]

## Sidhuvud och navigation

**Titel:** Visma Developer Portal.[cite:3]

**Övergripande navigation:**
- Start page.[cite:3]
- APIs.[cite:3]
- Webhooks.[cite:3]
- My Applications.[cite:3]
- Help.[cite:3]

**Meny:**
- Overview — <https://oauth.developers.visma.com/service-registry/documentation/overview>.[cite:3]
- Getting Started — <https://oauth.developers.visma.com/service-registry/documentation/gettingStarted>.[cite:3]
- OAuth Debugger.[cite:3]
- Create Your Application.[cite:3]
- Get Your Client Secret.[cite:3]
- Add an API integration.[cite:3]
- Visma Home.[cite:3]
- Partner Programme.[cite:3]
- Visma App Store.[cite:3]
- Authentication and Authorization — <https://oauth.developers.visma.com/service-registry/documentation/authentication>.[cite:3]
- Session Management — <https://oauth.developers.visma.com/service-registry/documentation/sessionManagement>.[cite:3]
- Tokens — <https://oauth.developers.visma.com/service-registry/documentation/tokens>.[cite:3]
- Best practices — <https://oauth.developers.visma.com/service-registry/documentation/bestPractices>.[cite:3]
- Show/Hide Menu.[cite:3]

## Getting Started

För att en applikation ska kunna få åtkomst till data som exponeras av Visma API:er måste den implementera OAuth 2.0-protokollet för auktorisering.[cite:3]

Sidan beskriver att det kan vara utmanande att komma i gång med nya API:er och att Visma därför har skapat en systematisk guide som leder användaren genom processen att skapa sin första applikation i Visma Developer Portal och mer därtill.[cite:3]

Efter att onboarding-processen slutförts omdirigeras användaren till Visma Developer Portals startsida, som innehåller genvägar till olika funktioner i portalen.[cite:3]

## OAuth Debugger

OAuth Debugger används för att testa och felsöka OAuth-förfrågningar genom att klistra in det Error-ID som kan erhållas under implementation mot endpointen `/connect/authorize`.[cite:3]

Från sidan **My Applications** finns åtkomst till Debugger.[cite:3]

Texten `create account` visas i anslutning till detta avsnitt.[cite:3]

## Create Your Application

Sidan anger att alla applikationer visas under sidan **My Applications**, där användaren kan skapa, uppdatera och ta bort applikationer.[cite:3]

Det finns också en genväg på Start Page som kan användas för att trigga registrering av en ny applikation.[cite:3]

### Steg 1

Alla applikationer visas under **My Applications** page och därifrån kan de hanteras.[cite:3]

### Steg 2

Användaren ska välja applikationstyp.[cite:3]

Texten `create account` visas i anslutning till detta steg.[cite:3]

| Application Type | OAuth Grant Types | Description |
|---|---|---|
| Web | `authorization_code`, med eller utan PKCE; `client_credentials`, typiskt machine-to-machine; `refresh_token`, för stöd för offline access.[cite:3] | En applikation som körs på en webbserver; dessa applikationer betraktas som **confidential** eftersom de kan upprätthålla konfidentialiteten för sina hemligheter och tokens.[cite:3] |
| Native | `authorization_code`, med PKCE; `refresh_token`, för stöd för offline access.[cite:3] | Native applications installeras av användare på deras enheter, mobil eller desktop; dessa betraktas som **public** och inga secrets utfärdas till dem.[cite:3] |
| Single-Page App | `authorization_code`, med PKCE; `refresh_token`, för stöd för offline access.[cite:3] | Browser-baserade appar körs helt i webbläsaren efter att JavaScript- och HTML-källkod laddats från en webbsida; de betraktas som **public** och inga secrets utfärdas till dem.[cite:3] |
| Service | `client_credentials`, typiskt machine-to-machine use case.[cite:3] | En applikation som körs på en server eller hos kund på plats; dessa betraktas som **confidential** och används vanligtvis i backend-baserade machine-to-machine-integrationer.[cite:3] |
| Marketing | Dessa applikationer är inte OAuth-applikationer.[cite:3] | Ingen ytterligare beskrivning anges i tabellen utöver att de inte är OAuth-applikationer.[cite:3] |

### Steg 3

Användaren ska fylla i applikationens uppgifter och både Name och Client ID måste vara unika i portalen.[cite:3]

Texten `create account` visas även här i anslutning till formuläret.[cite:3]

När applikationen har sparats kan användaren välja **Create**; detta är tidpunkten då applikationen skapas i Visma Connect Authorization Server och kan användas i OAuth 2.0/OpenID Connect-flöden.[cite:3]

Vid konfigurationsändringar bör användaren vänta en eller två minuter innan ändringen slår igenom på Authorization Server eftersom en cache används.[cite:3]

### Identity Scopes

När OpenID Connect är aktiverat kan applikationen konfigureras med ytterligare Identity Scopes som ger åtkomst till mer information om autentiserade användare.[cite:3]

Tabellen på sidan visar tillgängliga scopes och motsvarande claims om den autentiserade användaren.[cite:3]

| Scope | Claim | Description |
|---|---|---|
| openid | sub | Subject; innehåller unikt userID i Visma Connects användarkatalog.[cite:3] |
| email | email | Användarens e-postadress.[cite:3] |
| email | email_verified | True/False; användaren har verifierat åtkomst till e-postadressen.[cite:3] |
| profile | name | Användarens fullständiga namn.[cite:3] |
| profile | given_name | Användarens förnamn.[cite:3] |
| profile | family_name | Användarens efternamn.[cite:3] |
| profile | locale | Användarens föredragna språk i formatet `en-US`.[cite:3] |
| profile | picture | URI till användarens profilbild.[cite:3] |
| address | address | Returnerar attributet `country` som ISO2-kod i JSON-format, exempelvis `{"country":"DK"}`.[cite:3] |
| phone | phone_number | Användarens mobiltelefonnummer.[cite:3] |
| phone | phone_number_verified | True/False; användaren har verifierat åtkomst till telefonnumret.[cite:3] |

## Get Your Client Secret

Client secrets behövs endast för applikationstyperna **Web** och **Service**.[cite:3]

Applikationshemligheter hanteras från sidan **Credentials**.[cite:3]

Som standard genereras ingen secret för applikationer efter publicering; för att skapa en secret ska användaren klicka på **Generate secret**.[cite:3]

När en secret har genererats visas den en gång och måste kopieras direkt eftersom den inte är tillgänglig i efterhand.[cite:3]

Texten `credentials` visas i anslutning till detta avsnitt.[cite:3]

## Add an API integration

API-integrationskonfiguration är valfri och behövs inte om applikationen endast använder Sign in with Visma-funktionalitet.[cite:3]

När applikationen har publicerats och en secret har erhållits är nästa steg att konfigurera integration med ett API.[cite:3]

Listan över tillgängliga API:er finns under sidan **APIs**, där varje API har en detaljsida med information om namn, Base URL, dokumentation, permission type och permissions (OAuth Scopes).[cite:3]

Integration med API:et kan initieras direkt från denna sida.[cite:3]

### Steg 1

Användaren ska välja en av sina applikationer för vilken integrationen ska konfigureras.[cite:3]

Texten `integrations new` visas i anslutning till detta steg.[cite:3]

### Steg 2

Användaren ska välja de API permissions som applikationen behöver.[cite:3]

Texten `integrations scopes` visas i anslutning till detta steg.[cite:3]

### Steg 3

Användaren kan lägga till ett valfritt meddelande och bekräfta integrationsförfrågan.[cite:3]

Texten `integrations summary` visas i anslutning till detta steg.[cite:3]

Beroende på API-konfigurationen läggs scopes automatiskt till i applikationen eller går igenom en godkännandeprocess.[cite:3]

Status för varje integration kan kontrolleras under applikationens sida **Integrations**.[cite:3]

## Visma Home

[Visma Home](https://home.visma.com/) beskrivs som användarnas landningssida som ger one-click access till alla deras applikationer.[cite:3]

Visma-kunder använder Visma Home som launcher för application Single Sign-On.[cite:3]

Om en applikation ska vara tillgänglig i Visma Home för användarna uppmanas man att kontakta sin Visma Partner Administrator.[cite:3]

## Partner Programme

Visma uppger att de är dedikerade till att skapa starka relationer med partners för att leverera ERP-, HRM- och CRM-lösningar.[cite:3]

Att vara Visma Partner ger en rad förmåner som ska hjälpa partnern att lyckas med sina kunder, inklusive inbjudningar till marknadsföringskampanjer, utbildningar och kundevent.[cite:3]

Mer information hänvisas till [Visma Partner Programme](https://www.visma.com/visma-partner-programme/) portal page.[cite:3]

När en användare loggar in i en applikation skapad av organisationen visas en skärm där användaren ger samtycke till att dela sina Visma-data med applikationen.[cite:3]

Consent-skärmens sidfot skiljer sig för applikationer registrerade av en certifierad partner.[cite:3]

- En varning visas när det inte är en certifierad partner.[cite:3]
- För partnerapplikationer visas ingen varning; i stället visas en certified partner-logo.[cite:3]

Texten `integrations new` visas i anslutning till båda punkterna i källinnehållet.[cite:3]

## Visma App Store

**Visma App Store** beskrivs som en marknadsplats riktad till Visma-kunder för att bläddra bland och köpa appar som kan användas för att förenkla och stärka deras verksamhet.[cite:3]

Visma och tredjepartsutvecklare skapar och publicerar dessa appar från Visma Developer Portal till Visma App Store.[cite:3]

Om applikationen är integrerad med ett **Non-Interactive** tenant enabled API kan kunder ge den rättigheter att få åtkomst till deras organisationsdata från Visma App Store.[cite:3]

När konfigurationen för Visma App Store påbörjas måste applikationen ha **Privacy policy URI** och **Terms of service URI** konfigurerade; annars kan dessa URI:er ställas in på sidan **Details**.[cite:3]

Texten `start` och därefter `setup` visas i anslutning till förklaringen om att applikationens **audience** måste konfigureras först.[cite:3]

Det finns två typer av audience.[cite:3]

- **Publicly available**: applikationer som ska vara synliga för alla användare i Visma App Store; dessa kräver även App Store-filtrering där minst ett Visma-system som appen integrerar med och kategorier måste väljas; applikationerna granskas av Visma innan de blir tillgängliga i App Store.[cite:3]
- **Invite only**: applikationer som inte syns på offentliga sidor i Visma App Store men som kan hittas av Visma-kunder med hjälp av en **invitation code** som tillhandahålls av utvecklaren.[cite:3]

Det andra som måste konfigureras är **Developer website URI**, som ska peka på ett läsbart dokument som beskriver applikationen eller organisationen.[cite:3]

### Publicly available applications

En **Publicly available** application måste ha en logo icon konfigurerad.[cite:3]

Det går att använda logo picker för att välja en av de godkända logotyperna eller ladda upp en annan logotyp.[cite:3]

En publik applikation blir tillgänglig för alla Visma-kunder och setupen startas genom att klicka på **New marketplace**-knappen.[cite:3]

Detta omdirigerar användaren till market selector, vilket i källtexten markeras med texten `marketSelector`.[cite:3]

Applikationen skickas för granskning i **en marknad åt gången** och produktbeskrivning samt priser måste anges på det lokala språket för den valda marknaden, till exempel norska i Norge eller svenska i Sverige.[cite:3]

Efter att marknaden valts omdirigeras användaren till en mallbaserad edit-sida där marknadsspecifikt innehåll kan läggas till; i källtexten markeras detta med `marketInitial`.[cite:3]

Olika delar av mallen aktiverar ett HTML-formulär där detaljer om applikationen kan fyllas i.[cite:3]

- **Short description**: en text på 255 tecken som visas överst på applikationens detaljsida och i applikationens kort; i källtexten markeras detta med `shortDescription`.[cite:3]
- **Description**: en HTML-mall på upp till 65K tecken som stödjer HTML-element som [paragraphs](https://www.w3schools.com/html/html_paragraphs.asp), [text formatting](https://www.w3schools.com/html/html_formatting.asp) och [list](https://www.w3schools.com/html/html_lists.asp); i källtexten markeras detta med `description`.[cite:3]
- **Pricing**: applikationen måste ha minst en definierad prisnivå; Visma App Store visar priserna som tas ut men hanterar inte köp eller betalning, vilket måste skötas på utvecklarens sida; en **Pricing details URI** ska läggas till för att länka till webbplats eller webbshop; i källtexten markeras detta med `price`.[cite:3]

När setupen är klar kan applikationen skickas in för granskning och Visma kommer då att godkänna eller avslå innehållet.[cite:3]

Vid avslag läggs ett meddelande till så att orsaken till avslaget kan identifieras.[cite:3]

I sektionen för Visma App Store-konfiguration visas varje marknad som registrerats för applikationen tillsammans med en status; i källtexten markeras detta med `pendig`.[cite:3]

### Invite only applications

En **Invite only** application syns inte i den publika delen av Visma App Store.[cite:3]

En Visma-kund med rollen Integration administrator kan logga in i Visma App Store och använda en invitation code som utvecklaren utfärdat och delat för att privat ge applikationen åtkomst till kundens data i Visma.[cite:3]

Invite only audience beskrivs som användbart för applikationer med kundspecifik funktionalitet eller för pilotanvändning med specifika kunder.[cite:3]

Efter att **Developer website URI** har satts kan detaljerna sparas och invitation codes börja genereras för kunder.[cite:3]

Detta görs genom att klicka på länken **New invitation code** från Visma App Store-sidan; i källtexten markeras detta med `inviteOnly`.[cite:3]

När en ny invitation code genereras måste en kort beskrivning anges, vilket kan vara användbart för att identifiera koden senare; i källtexten markeras detta med `codeNew`.[cite:3]

När koden har genererats måste den kopieras och skickas till den kund som applikationen ska delas med; i källtexten markeras detta med `codeCreated`.[cite:3]

Listan över invitation codes som genererats för applikationen visas under sektionen för Visma App Store-konfiguration.[cite:3]

Utvecklaren meddelas via e-post när en kund ger applikationen åtkomst till sina Visma-data, och detta återspeglas även i statusen bredvid invitation code; i källtexten markeras detta med `codeList`.[cite:3]
