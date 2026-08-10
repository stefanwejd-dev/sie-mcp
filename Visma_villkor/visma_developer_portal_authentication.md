# Visma Developer Portal – Authentication and Authorization

Källsidan är Visma Developer Portal-sidan "Authentication and Authorization".[cite:1]

## Sidhuvud och navigation

**Titel:** Visma Developer Portal.[cite:1]

**Övergripande navigation:**
- Start page.[cite:1]
- APIs.[cite:1]
- Webhooks.[cite:1]
- My Applications.[cite:1]
- Help.[cite:1]

**Meny:**
- Overview — <https://oauth.developers.visma.com/service-registry/documentation/overview>.[cite:1]
- Getting Started — <https://oauth.developers.visma.com/service-registry/documentation/gettingStarted>.[cite:1]
- Authentication and Authorization — <https://oauth.developers.visma.com/service-registry/documentation/authentication>.[cite:1]
- OpenID Connect.[cite:1]
- Discovery Document.[cite:1]
- Server-Side Web Applications.[cite:1]
- Native Applications.[cite:1]
- Single Page Applications.[cite:1]
- Service Applications.[cite:1]
- UserInfo Endpoint.[cite:1]
- Make Your First Request.[cite:1]
- Offline Access.[cite:1]
- Session Management — <https://oauth.developers.visma.com/service-registry/documentation/sessionManagement>.[cite:1]
- Tokens — <https://oauth.developers.visma.com/service-registry/documentation/tokens>.[cite:1]
- Best practices — <https://oauth.developers.visma.com/service-registry/documentation/bestPractices>.[cite:1]
- Show/Hide Menu.[cite:1]

## Authentication and Authorization

OAuth 2.0 beskrivs som ett öppet auktorisationsprotokoll som gör det möjligt för applikationer att få åtkomst till användarkonton på en HTTP-tjänst genom att delegera användarautentisering till tjänsten som hostar användarkontot och auktorisera tredjepartsapplikationer att komma åt användarkontot.[cite:1]

Applikationen använder OAuth-bibliotek eller endpoints för att implementera OAuth 2.0-auktorisering så att appar kan få åtkomst till Visma API:er.[cite:1]

OAuth 2.0 gör det möjligt för applikationer att komma åt specifik användardata utan att kräva åtkomst till användarens privata inloggningsuppgifter.[cite:1]

Det innebär att en applikation kan använda OAuth 2.0 för att få tillstånd från en Visma-företagsadministratör att läsa och skriva data till företagets Visma-miljö.[cite:1]

Flödet är utformat så att appen kan få åtkomst till Visma API:er oavsett om användaren interagerar med applikationen eller inte.[cite:1]

Mer information om OAuth hänvisas till RFC 6749: <https://tools.ietf.org/html/rfc6749>.[cite:1]

## OpenID Connect

OpenID Connect 1.0 beskrivs som ett enkelt identitetslager ovanpå OAuth 2.0-protokollet.[cite:1]

Det gör att klienter kan verifiera slutanvändarens identitet baserat på autentisering utförd av en auktorisationsserver och hämta nödvändig profilinformation om slutanvändaren på ett interoperabelt och REST-liknande sätt.[cite:1]

OpenID Connect gör det möjligt för klienter av alla typer, inklusive webbaserade, mobila och JavaScript-klienter, att begära och ta emot information om autentiserade sessioner och slutanvändare.[cite:1]

Specifikationssviten är utbyggbar och möjliggör valfria funktioner som kryptering av identitetsdata, discovery av OpenID-providers och sessionshantering.[cite:1]

OpenID Connect (OIDC) beskrivs som ett autentiseringsprotokoll baserat på OAuth 2.0-familjen av specifikationer och använder JSON Web Tokens (JWT) som kan erhållas via flöden som följer OAuth 2.0-specifikationerna.[cite:1]

Medan OAuth 2.0 handlar om resursåtkomst och delning handlar OIDC om användarautentisering; när OIDC läggs ovanpå OAuth2 blir OAuth2 identitetsmedvetet och möjliggör bland annat single sign-on och delning av personlig profilinformation.[cite:1]

### Authenticating the user

Att autentisera användaren innebär att hämta en ID-token och validera den.[cite:1]

ID-tokens beskrivs som en standardiserad funktion i OpenID Connect för delning av identitetsassertioner på internet.[cite:1]

För att hämta token krävs ett autentiseringssteg där användaren loggar in med sitt Visma-konto och därefter tillfrågas om användaren vill ge de behörigheter som applikationen begär; processen kallas **user consent**.[cite:1]

Om den inloggade användaren ger tillstånd skickar Visma Connect Authorization Server en authorization code till applikationens callback-endpoint som definierats i Redirect URI-delen av appen.[cite:1]

Denna authorization code kan växlas in för att erhålla en ID-token och en Access Token.[cite:1]

## Discovery Document

Discovery Document beskrivs som ett JSON-dokument med nyckel-värde-par som innehåller detaljer om kärnauktorisationsservern.[cite:1]

Informationen omfattar bland annat authorization URLs, token, endpoints, scopes och userinfo.[cite:1]

## Server-Side Web Applications

En server-side web application måste implementera OAuth 2.0 grant type **authorization_code**.[cite:1]

För att följa OAuth 2.1-specifikationerna kan en webbapplikation också konfigureras att använda PKCE, vilket kan aktiveras eller inaktiveras i applikationens detaljsida.[cite:1]

För att autentisera användare i en server-side web application anges följande steg.[cite:1]

### Step 1: Authorization request

Applikationer med PKCE aktiverat skapar först en **code verifier**, beskriven som en kryptografiskt slumpmässig sträng med tecknen A-Z, a-z, 0-9 samt tecknen -._~, mellan 43 och 128 tecken lång.[cite:1]

Därefter skapas en **code challenge**, definierad som en Base64-URL-kodad sträng av SHA256-hashen av code verifier.[cite:1]

Auktorisationsprocessen initieras genom att användaren omdirigeras till Visma Connect authorization endpoint, som endast är tillgänglig över HTTPS, medan vanlig HTTP nekas.[cite:1]

Sidans tabell över stödda query-parametrar återges nedan.[cite:1]

| Name | Example Value | Required | Description |
|---|---|---|---|
| client_id | isv_demoapp | yes | Client ID som sattes när applikationen registrerades; kom ihåg prefixet `isv_`; identifierar vilken app som gör begäran.[cite:1] |
| scope | openid email profile offline_access | yes | Identifierar vilken användarinformation som applikationen begär; scopet `openid` krävs; parametrarna informerar consent-skärmen; om Offline Access är konfigurerat kan `offline_access` inkluderas för att få en refresh token.[cite:1] |
| redirect_uri | https://demoapp.example.com/oauthcallback | yes | Anger vart OAuth-callback-svaret skickas; värdet måste exakt matcha det som registrerats, inklusive `https` och bokstavsstorlek.[cite:1] |
| code_challenge | The code challenge generated | yes, when PKCE enabled | Base64-URL-kodad SHA256-hash av Code Verifier.[cite:1] |
| code_challenge_method | S256 or plain | yes, when PKCE enabled | Anger om challenge är SHA256-hash av strängen eller den rena verifier-strängen.[cite:1] |
| response_type | "code" or "code id_token" | yes | Avgör om endpointen returnerar authorization code och eventuellt `id_token`; om Hybrid Flow är aktiverat måste värdet vara `code id_token`.[cite:1] |
| nonce | qksKW97hcv | yes, for Hybrid Flow | Engångsvärde som inkluderas i svaret och används för att förhindra replay-attacker; om nonce finns i ID-token måste applikationen verifiera att värdet matchar autentiseringsbegäran; krävs för Hybrid Flow.[cite:1] |
| state | This field can be a Base64 encoded JSON object that can hold multiple values | no | Returneras oförändrat av Authorization Server och kan användas för att säkerställa att svaret hör till en begäran initierad av samma användare, vilket hjälper mot CSRF-attacker samt återställer tidigare applikationsstatus.[cite:1] |
| response_mode | form_post or query | no | Anger om svar parametrar returneras via postat formulär eller i query string; standard och rekommenderat är `form_post`.[cite:1] |
| ui_locales | nb-NO sv-SE en-GB | no | Slutanvändarens föredragna språk och skript som en blankstegsseparerad lista av BCP47-taggar; stödda värden är da-DK, en-GB, en-US, fi-FI, nb-NO, nl-NL, sv-SE och lv-LV.[cite:1] |

Exempel på request.[cite:1]

```text
GET https://connect.visma.com/connect/authorize?client_id=isv_demoapp&response_type=code+id_token&response_mode=form_post&scope=openid+email+profile&redirect_uri=http://demoapp.example.com/oauthcallback&nonce=qksKW97hcv&state=CfDJ8NbGuiMeKnBKlosjbaGWcBzxsyHJjSmlXdcP5HT0Jp_qH...tE8u1Ws&ui_locales=nb-NO+sv-SE+en-GB
```

### Step 2: User consent

I detta steg avgör användaren om applikationen ska få den begärda åtkomsten eller inte.[cite:1]

Visma Connect visar då ett consent-fönster med applikationens namn och organisationens namn för att begära tillstånd att använda användarens auktorisationsuppgifter.[cite:1]

Användaren kan därefter godkänna eller neka åtkomst.[cite:1]

Applikationen behöver inte göra något i detta steg utan väntar på svar från Visma Connect Authentication server om åtkomst beviljades eller inte.[cite:1]

Om applikationen ingår i Visma Partner Programme visas inte varningen om när applikationen skapades och hur många Visma-användare som använder den; i stället visas Certified Partner-logotypen.[cite:1]

### Step 3: Authentication Response

När `response_mode=form_post` användes skickar authorization server följande svar tillbaka till applikationen.[cite:1]

```text
POST https://demoapp.example.com/oauthcallback Content-Type: application/x-www-form-urlencoded code: 94c99b73c13c1e39f7b0a7d259628338 &id_token:eyJhbGciOiJSUzI1NiIsImtpZCI6IjZCN0FDQzUyMDMwNUJGREI0R...ZBMEu6dA &scope:openid email profile &state:CfDJ8NbGuiMeKnBKlosjbaGWcBzxsyHJjSmlXdcP5HT0Jp_qH...tE8u1Ws &session_state:u9pDw26xhANhsj5vmg9aClWqWPRx8OdbyScowPzd8d0.4febcb64e04a793c4ab1aec3f1392257
```

Mottagna parametrar beskrivs så här.[cite:1]
- `code`: authorization code som ska användas för att hämta access token.[cite:1]
- `id_token`: JWT-token som innehåller användarens identitet; nonce från requesten finns i denna token och kan valideras.[cite:1]
- `scope`: scope-värden som angavs i requesten.[cite:1]
- `state`: state-värdet som angavs i requesten.[cite:1]
- `session_state`: session state som tillsammans med `client_id` kan skickas till `/connect/checksession` för att validera sessionen hos identitetsleverantören.[cite:1]

### Step 4: Exchange Authorization Code for Tokens

Efter att applikationen tagit emot authorization response växlar den in `code` mot en Access Token och ID Token.[cite:1]

Exempel på request.[cite:1]

```text
curl --request POST --url https://connect.visma.com/connect/token --header 'content-type: application/x-www-form-urlencoded' --data 'grant_type=authorization_code&redirect_uri=https%3A%2F%2Fdemoapp.example.com/oauthcallback%2Fcallback&code=94c99b73c13c1e39f7b0a7d259628338&client_id=isv_demoapp&client_secret=SECRET'
```

| Name | Example Value | Required | Description |
|---|---|---|---|
| grant_type | authorization_code | yes | Måste innehålla värdet `authorization_code` enligt OAuth 2.0-specifikationen.[cite:1] |
| redirect_uri | https://demoapp.example.com/oauthcallback | yes | Samma värde som användes i authorization request.[cite:1] |
| code | 94c99b73c13c1e39f7b0a7d259628338 | yes | Authentication code som returnerades från den initiala begäran.[cite:1] |
| client_id | isv_demoapp | yes | Registrerat Client ID; kom ihåg prefixet `isv_`; identifierar vilken app som gör begäran.[cite:1] |
| client_secret | The secret obtained when registering the application | yes | Applikationens Client Secret.[cite:1] |
| code_verifier | The generated verifier | yes, when PKCE enabled | Den verifier som appen genererade före authorization request.[cite:1] |

Vid lyckat anrop returneras ett tokenpaket med fälten `access_token`, `id_token`, `expires_in`, `token_type` och `scope`.[cite:1]

När Identity Scopes används kan applikationen hämta ytterligare användarinformation via UserInfo Endpoint.[cite:1]

Om scopet `offline_access` används innehåller svaret även en `refresh_token` som kan användas för att uppdatera en utgången access token.[cite:1]

## Native Applications

Native applications installeras på användarens enheter, mobil eller desktop, och skiljer sig därför från webbapplikationer som körs i webbläsaren.[cite:1]

Eftersom apparna körs på användarens enheter anges bästa praxis vara att använda en extern user-agent, det vill säga webbläsare, för OAuth 2.0 authorization requests, med OAuth 2.0 Authorization Code Grant och PKCE rekommenderat för publika klienter.[cite:1]

PKCE beskrivs som en teknik för att minska hotet att authorization code kapas genom att klienten först skapar en hemlighet och sedan använder samma hemlighet när authorization code byts mot access token.[cite:1]

### Step 1: Authorization request

Publika applikationer skapar en **code verifier**, en kryptografiskt slumpmässig sträng med tecknen A-Z, a-z, 0-9 och -._~, mellan 43 och 128 tecken lång.[cite:1]

Appen använder sedan verifiern för att skapa en **code challenge**, en Base64-URL-kodad SHA256-hash av verifiern.[cite:1]

Code challenge inkluderas sedan i authorization request tillsammans med en parameter som anger metoden för att generera challenge.[cite:1]

| Name | Example Value | Required | Description |
|---|---|---|---|
| client_id | isv_demoapp | yes | Registrerat Client ID med prefixet `isv_`.[cite:1] |
| response_type | code | yes | Avgör att endpointen returnerar authorization code och ska alltid sättas till `code`.[cite:1] |
| scope | openid email profile | yes | Identifierar begärd användarinformation; `openid` krävs.[cite:1] |
| redirect_uri | myapp:/oauthcallback | yes | Anger vart OAuth Callback skickas; måste exakt matcha det registrerade värdet; native apps kan använda custom scheme eller localhost HTTP URI:er.[cite:1] |
| code_challenge | The code challenge generated | yes | Base64-URL-kodad SHA256-hash av Code Verifier.[cite:1] |
| code_challenge_method | S256 or plain | yes | Anger om challenge är SHA256-hash eller plain verifier string.[cite:1] |
| state | This field can be a Base64 encoded JSON object that can hold multiple values | no | Returneras oförändrat och hjälper till att koppla svar till ursprunglig begäran och minska CSRF-risk.[cite:1] |
| response_mode | query | no | Anger att svar returneras i query string.[cite:1] |
| ui_locales | nb-NO sv-SE en-GB | no | Lista över användarens föredragna språk; stödda värden är da-DK, en-GB, en-US, fi-FI, nb-NO, nl-NL, sv-SE och lv-LV.[cite:1] |

Exempel.[cite:1]

```text
GET https://connect.visma.com/connect/authorize?client_id=isv_demoapp&response_type=code&response_mode=query&scope=openid+email+profile&redirect_uri=myapp:/oauthcallback&code_challenge=YOUR_CODE_CHALLENGE&code_challenge_method=S256&state=CfDJ8NbGuiMeKnBKlosjbaGWcBzxsyHJjSmlXdcP5HT0Jp_qH...tE8u1Ws&ui_locales=nb-NO+sv-SE+en-GB
```

### Step 2: User consent

Användaren avgör om den begärda åtkomsten ska ges eller inte och Visma Connect visar ett consent-fönster med applikationens namn.[cite:1]

Användaren kan därefter ge eller neka åtkomst.[cite:1]

Applikationen väntar endast på svar från Visma Connect Authentication server.[cite:1]

Om applikationen ingår i Visma Partner Programme visas Certified Partner-logotypen i stället för varningen om appens skapandedatum och användarantal.[cite:1]

### Step 3: Authentication Response

För native applications med `response_mode=query` skickas följande svar tillbaka till applikationen.[cite:1]

```text
myApp:/oauthcallback?code=94c99b73c13c1e39f7b0a7d259628338&state=CfDJ8NbGuiMeKnBKlosjbaGWcBzxsyHJjSmlXdcP5HT0Jp_qH...tE8u1Ws
```

### Step 4: Exchange Authorization Code for Tokens

Token request måste innehålla parametern **code_verifier** som genererades innan authorization process startade.[cite:1]

Exempel på request.[cite:1]

```text
curl --request POST --url https://connect.visma.com/connect/token --header 'content-type: application/x-www-form-urlencoded' --data 'grant_type=authorization_code&redirect_uri=myApp%3A%2F/oauthcallbac&code=94c99b73c13c1e39f7b0a7d259628338&client_id=isv_demoapp&code_verifier=YOUR_CODE_VERIFIER'
```

| Name | Example Value | Required | Description |
|---|---|---|---|
| grant_type | authorization_code | yes | Måste innehålla värdet `authorization_code`.[cite:1] |
| redirect_uri | myapp:/oauthcallback | yes | Samma värde som i authorization request.[cite:1] |
| code | 94c99b73c13c1e39f7b0a7d259628338 | yes | Authentication code från den initiala requesten.[cite:1] |
| client_id | isv_demoapp | yes | Registrerat Client ID med prefixet `isv_`.[cite:1] |
| code_verifier | The generated verifier | yes | Verifiern som appen genererade före authorization request.[cite:1] |

Vid lyckat anrop returneras `access_token`, `id_token`, `expires_in`, `token_type` och `scope`.[cite:1]

När Identity Scopes används kan ytterligare användarinformation hämtas från UserInfo Endpoint.[cite:1]

## Single Page Applications

Single-page apps körs helt i webbläsaren efter att JavaScript- och HTML-kod laddats från en webbsida.[cite:1]

Eftersom hela källkoden är tillgänglig i webbläsaren kan dessa appar inte upprätthålla sekretessen för ett client secret och använder därför inte något sådant.[cite:1]

I stället måste dessa applikationer implementera PKCE, rekommenderat för publika klienter.[cite:1]

PKCE beskrivs återigen som en metod att reducera risken att authorization code kapas genom att token request kräver den tidigare skapade hemligheten.[cite:1]

### Step 1: Authorization request

Publika applikationer skapar en code verifier och därefter en code challenge som är en Base64-URL-kodad SHA256-hash av verifiern.[cite:1]

Code challenge och metod inkluderas därefter i authorization request.[cite:1]

| Name | Example Value | Required | Description |
|---|---|---|---|
| client_id | isv_demoapp | yes | Registrerat Client ID med prefixet `isv_`.[cite:1] |
| response_type | code | yes | Ska alltid vara `code`.[cite:1] |
| scope | openid email profile | yes | Begärd användarinformation; `openid` krävs.[cite:1] |
| redirect_uri | https://demoapp.example.com/oauthcallback | yes | Callback-URI som exakt måste matcha registreringen, inklusive `https` och bokstavsstorlek.[cite:1] |
| code_challenge | The code challenge generated | yes | Base64-URL-kodad SHA256-hash av Code Verifier.[cite:1] |
| code_challenge_method | S256 or plain | yes | Anger om challenge är hash eller plain verifier.[cite:1] |
| state | This field can be a Base64 encoded JSON object that can hold multiple values | no | Kan användas för att säkerställa att svaret tillhör samma användares initierade request och för att minska CSRF-risk.[cite:1] |
| response_mode | query | no | Returnerar svar i query string.[cite:1] |
| ui_locales | nb-NO sv-SE en-GB | no | Föredragna språk; stödda värden är da-DK, en-GB, en-US, fi-FI, nb-NO, nl-NL, sv-SE och lv-LV.[cite:1] |

Exempel.[cite:1]

```text
GET https://connect.visma.com/connect/authorize?client_id=isv_demoapp&response_type=code&response_mode=query&scope=openid+email+profile&redirect_uri=http://demoapp.example.com/oauthcallback&code_challenge=YOUR_CODE_CHALLENGE&code_challenge_method=S256&state=CfDJ8NbGuiMeKnBKlosjbaGWcBzxsyHJjSmlXdcP5HT0Jp_qH...tE8u1Ws&ui_locales=nb-NO+sv-SE+en-GB
```

### Step 2: User consent

Användaren avgör om åtkomst ska beviljas; Visma Connect visar ett consent-fönster med applikationens namn och organisationens namn.[cite:1]

Användaren kan ge eller neka åtkomst och applikationen väntar under tiden på svar från Visma Connect Authentication server.[cite:1]

För appar i Visma Partner Programme visas Certified Partner-logotypen i stället för standardvarningen.[cite:1]

### Step 3: Authentication Response

För SPA med `response_mode=query` returnerar authorization server följande svar.[cite:1]

```text
https://demoapp.example.com/oauthcallback?code=94c99b73c13c1e39f7b0a7d259628338&state=CfDJ8NbGuiMeKnBKlosjbaGWcBzxsyHJjSmlXdcP5HT0Jp_qH...tE8u1Ws
```

### Step 4: Exchange Authorization Code for Tokens

Token request måste innehålla `code_verifier` som genererades innan authorization process startade.[cite:1]

Exempel på request.[cite:1]

```text
curl --request POST --url https://connect.visma.com/connect/token --header 'content-type: application/x-www-form-urlencoded' --data 'grant_type=authorization_code&redirect_uri=https%3A%2F%2Fdemoapp.example.com/oauthcallback%2Fcallback&code=94c99b73c13c1e39f7b0a7d259628338&client_id=isv_demoapp&code_verifier=YOUR_CODE_VERIFIER'
```

| Name | Example Value | Required | Description |
|---|---|---|---|
| grant_type | authorization_code | yes | Måste innehålla värdet `authorization_code`.[cite:1] |
| redirect_uri | https://demoapp.example.com/oauthcallback | yes | Samma värde som i authorization request.[cite:1] |
| code | 94c99b73c13c1e39f7b0a7d259628338 | yes | Authentication code från initial request.[cite:1] |
| client_id | isv_demoapp | yes | Registrerat Client ID med prefixet `isv_`.[cite:1] |
| code_verifier | The generated verifier | yes | Den verifier som genererades före authorization request.[cite:1] |

Vid lyckat anrop returneras `access_token`, `id_token`, `expires_in`, `token_type` och `scope`.[cite:1]

SPA-applikationer kan inte ha offline access support och refresh tokens utfärdas därför aldrig till dessa applikationer.[cite:1]

När Identity Scopes används kan ytterligare användarinformation hämtas från UserInfo Endpoint.[cite:1]

## Service Applications

En service application involverar inte slutanvändaren i authorization process.[cite:1]

Dessa applikationer används strikt för att anropa API:er och använder OAuth2 grant type **client_credentials** för att hämta access tokens från Authorization Server genom att ange sina credentials och de scopes som begärs.[cite:1]

### Token request

Service applications använder **client_credentials** grant type för att hämta access tokens.[cite:1]

Exempel.[cite:1]

```text
curl --request POST --url https://connect.visma.com/connect/token --header 'content-type: application/x-www-form-urlencoded' --data 'grant_type=client_credentials&scope=visma_api:read&client_id=isv_demoapp&client_secret=SECRET&tenant_id=af1140c1-52e0-46c7-b684-df894d4b8a5a'
```

| Name | Example Value | Required | Description |
|---|---|---|---|
| grant_type | client_credentials | yes | Måste innehålla värdet `client_credentials` enligt OAuth 2.0-specifikationerna.[cite:1] |
| scope | visma_api:read | yes | Identifierar den Visma API-åtkomst som applikationen begär.[cite:1] |
| client_id | isv_demoapp | yes | Registrerat Client ID med prefixet `isv_`.[cite:1] |
| client_secret | The secret obtained when registering the application | yes | Applikationens Client Secret.[cite:1] |
| tenant_id | af1140c1-52e0-46c7-b684-df894d4b8a5a | no | Identifierar tenant vars API-data ska nås; parametern krävs för tenant-baserade API:er och applikationen måste ha fått tillstånd av tenant-administratören innan `tenant_id` används i token request.[cite:1] |

Vid lyckat anrop returneras `access_token`, `expires_in`, `token_type` och `scope`.[cite:1]

Refresh tokens utfärdas aldrig till service applications eftersom applikationen kan hämta en ny token när det behövs utan att involvera slutanvändaren.[cite:1]

## UserInfo Endpoint

När Identity Scopes används i authentication request kan applikationen hämta ytterligare information om den autentiserade användaren från userinfo endpoint.[cite:1]

Applikationen måste använda den erhållna Access Token när endpointen anropas.[cite:1]

Exempel.[cite:1]

```text
curl --request GET --url https://connect.visma.com/connect/userinfo --header 'authorization: Bearer [YOUR_ACCESS_TOKEN]'
```

Vid lyckat anrop returneras ett JSON-objekt som innehåller user claims, inklusive exempelvis `sub`, `name`, `given_name`, `family_name`, `email`, `email_verified`, `idp`, `auth_time` och `sid`.[cite:1]

Vilka claims som returneras beror på vilka Identity Scopes som användes i authentication request.[cite:1]

## Make Your First Request

Efter att applikationen erhållit en Access Token kan den använda denna för att anropa Visma API-resurser genom att inkludera token i HTTP-headern `authorization: Bearer`.[cite:1]

Exempel.[cite:1]

```text
curl --request GET --url https://api.visma.com/api/resource --header 'accept: application/json' --header 'authorization: Bearer [YOUR_ACCESS_TOKEN]'
```

## Offline Access

Offline access, även kallat Refresh Token grant type, används för att byta en refresh token mot en access token när access token har gått ut.[cite:1]

Detta gör att applikationer kan fortsätta ha en giltig access token utan användarinteraktion.[cite:1]

Offline access stöds endast för web applications.[cite:1]

För att aktivera detta måste **Offline Access** först kryssas i för applikationen under fliken Details.[cite:1]

Det andra steget är att inkludera scopet **offline_access** i authentication/authorization request.[cite:1]

I slutet av authorization får applikationen då också en `refresh_token` som kan användas för att hämta en ny access token.[cite:1]

### Refreshing Access Tokens

För att uppdatera en token görs en POST-request till `/connect/token` med följande parametrar.[cite:1]

| Name | Example Value | Required | Description |
|---|---|---|---|
| client_id | isv_demoapp | yes | Registrerat Client ID med prefixet `isv_`.[cite:1] |
| client_secret | The secret obtained when registering the application | yes | Applikationens Client Secret.[cite:1] |
| grant_type | refresh_token | yes | Anger att grant-typen som begärs är `refresh_token`.[cite:1] |
| refresh_token | 7990438c99d8158108ab225a4c21f3156ed2b8596a46195ae9fa7c3e88d61e65 | yes | Den refresh token som mottogs under authorization.[cite:1] |

Exempel på request.[cite:1]

```text
curl --request POST --url https://connect.visma.com/connect/token --header 'content-type: application/x-www-form-urlencoded' --data 'client_id=isv_demoapp&client_secret=SECRET&grant_type=refresh_token&refresh_token=7990438c99d8158108ab225a4c21f3156ed2b8596a46195ae9fa7c3e88d61e65'
```

Vid lyckat anrop returneras ett tokenpaket med `id_token`, `access_token`, `expires_in`, `token_type` och `refresh_token`.[cite:1]

För att återkalla en refresh token hänvisar sidan till token revocation-dokumentationen: <https://oauth.developers.visma.com/service-registry/documentation/tokens#revocationEndpoint>.[cite:1]

### Refresh Token security considerations

Refresh Tokens beskrivs som högvärdiga mål för angripare eftersom de vanligtvis har mycket längre livslängd än Access Tokens.[cite:1]

Sidan anger flera tekniker för att minska attackytan.[cite:1]

#### Consent

Det anges vara en god idé att be om användarsamtycke så att användaren görs medveten om vad som händer med offline access.[cite:1]

#### Sliding expiration

Refresh Tokens har vanligtvis betydligt längre livslängd än Access Tokens, men exponeringen kan minskas genom att lägga till en glidande livstid ovanpå den absoluta livstiden.[cite:1]

Detta möjliggör scenarier där en Refresh Token kan användas tyst så länge användaren regelbundet använder klienten, men kräver en ny authorize request om klienten inte använts under en viss tid.[cite:1]

Sidan anger att alternativet "But will expire if not used in ... days" används för att aktivera detta.[cite:1]

#### One-time Refresh Tokens

Ett annat alternativ som anges är att rotera Refresh Tokens vid varje användning, vilket minskar exponeringen och ökar sannolikheten att äldre exfiltrerade tokens blir oanvändbara.[cite:1]

#### Replay detection

När one-time tokens används är replay detection aktiverat, vilket innebär att om samma Refresh Token används mer än en gång återkallas all åtkomst för kombinationen klient/användare.[cite:1]

Sidan anger också att nackdelen är att legitima Refresh Tokens kan bli oanvändbara i fler scenarier, exempelvis på grund av nätverksproblem under tokenförnyelse.[cite:1]
