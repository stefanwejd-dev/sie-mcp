# Visma Developer Portal – Tokens

Källsidan är Visma Developer Portal-sidan "Tokens".[cite:7]

## Sidhuvud och navigation

**Titel:** Visma Developer Portal.[cite:7]

**Övergripande navigation:**
- Start page.[cite:7]
- APIs.[cite:7]
- Webhooks.[cite:7]
- My Applications.[cite:7]
- Help.[cite:7]

**Meny:**
- Overview — <https://oauth.developers.visma.com/service-registry/documentation/overview>.[cite:7]
- Getting Started — <https://oauth.developers.visma.com/service-registry/documentation/gettingStarted>.[cite:7]
- Authentication and Authorization — <https://oauth.developers.visma.com/service-registry/documentation/authentication>.[cite:7]
- Session Management — <https://oauth.developers.visma.com/service-registry/documentation/sessionManagement>.[cite:7]
- Tokens — <https://oauth.developers.visma.com/service-registry/documentation/tokens>.[cite:7]
- ID Token.[cite:7]
- Access Token.[cite:7]
- Refresh Token.[cite:7]
- Token Revocation.[cite:7]
- Best practices — <https://oauth.developers.visma.com/service-registry/documentation/bestPractices>.[cite:7]
- Show/Hide Menu.[cite:7]

## Visma Tokens

Visma Connect OAuth 2.0 Authorization Server utfärdar JSON Web Tokens (JWT), det vill säga tokens som följer JSON Web Token-standarden och innehåller information i form av claims.[cite:7]

Sidan anger att dessa är self-contained, vilket innebär att applikationer eller API:er inte behöver anropa servern för att validera token.[cite:7]

Under utveckling kan [jwt.io](https://jwt.io/) användas för att verifiera ett JWT:s claims.[cite:7]

Det finns olika typer av tokens som utfärdas till applikationer under autentiserings- och auktoriseringsprocessen.[cite:7]

## ID Token

En ID Token beskrivs som en JWT, det vill säga ett kryptografiskt signerat Base64-kodat JSON-objekt.[cite:7]

ID-token innehåller användarprofilattribut i form av claims, och dessa påståenden om användaren kan litas på om tokenkonsumenten kan verifiera signaturen.[cite:7]

Applikationen använder ID-token för att hämta användarinformation som namn och e-postadress, typiskt för visning i användargränssnittet.[cite:7]

En ID Token kan erhållas efter att användaren har autentiserat sig framgångsrikt.[cite:7]

Sidan anger att applikationen måste verifiera ID-tokenens signatur innan den lagras och används.[cite:7]

Token måste avkodas för att claims eller användarattribut ska kunna läsas.[cite:7]

JWT-webbplatsen uppges tillhandahålla en lista över bibliotek som kan användas för att dekryptera ID-token.[cite:7]

Sidan beskriver att ID-token lades till i OIDC-specifikationen som en optimering så att applikationen kan känna till användarens identitet utan att göra ytterligare en nätverksförfrågan.[cite:7]

ID-token följer en industristandard och består av tre delar.[cite:7]

Följande tabell beskriver de claims som returneras i ID-token för alla användare.[cite:7]

| Claim | Description | Example |
|---|---|---|
| idp | Identity Provider.[cite:7] | Visma Connect.[cite:7] |
| acr | Authentication Context Class Reference.[cite:7] | 2.[cite:7] |
| amr | Authentication Methods References.[cite:7] | `["pwd"]`.[cite:7] |
| auth_time | Time when the authentication occured. Number representing seconds since 01.01.1970.[cite:7] | 1498217219.[cite:7] |
| sub | Visma Connect Unique User ID of authenticated user.[cite:7] | 1072cd43-d99a-4d44-84a2-5f80720c1a19.[cite:7] |
| sid | Visma Connect Session ID of users current active session.[cite:7] | 11474d36-22a3-40d8-925d-21af17826e38.[cite:7] |
| aud | Client ID of the client who requested the authentication the ID Token belongs to.[cite:7] | demoapp.[cite:7] |
| llt | Last Login Time in Unix Time Stamp (Epoch time).[cite:7] | 1501591804.[cite:7] |

## Access Token

Access Tokens beskrivs som credentials som används av applikationer för att få åtkomst till API:ers skyddade resurser.[cite:7]

En Access Token är en sträng som representerar en auktorisering utfärdad till klienten.[cite:7]

Tokens representerar specifika scopes och giltighetstider för åtkomst, som har beviljats av resursägaren och upprätthålls av både API:et och authorization servern.[cite:7]

Syftet är att informera API:et om att innehavaren av token har auktoriserats att komma åt API:et och utföra specifika åtgärder enligt beviljade scopes.[cite:7]

Access Token ska användas som bearer credential och skickas i en HTTP Authorization-header till API:et.[cite:7]

Följande tabell beskriver de claims som returneras i Access Token.[cite:7]

| Claim | Description | Example |
|---|---|---|
| client_id | Client identity of the client that requested the authentication (your applications client_id). [cite:7] | demoapp.[cite:7] |
| scope | A list of scopes that the user has access to.[cite:7] | `[ "openid", "profile", "email" ]`.[cite:7] |
| tenant_id | Current Tenant ID context (only present for tenant enabled applications).[cite:7] | 9ea83b40-1ce9-4f2d-a1ac-2b0f28001bb6.[cite:7] |
| auth_time | Time when the authentication occured. Number representing seconds since 01.01.1970.[cite:7] | 1498217219.[cite:7] |
| sub | Visma Connect Unique User ID of authenticated user.[cite:7] | 1072cd43-d99a-4d44-84a2-5f80720c1a19.[cite:7] |
| aud | Audiences. A list of API URIs that have scopes in the Access Token.[cite:7] | `["https://api1.visma.com/resources", "https://api2.visma.com"]`.[cite:7] |
| nbf | Not before Time in Unix Time Stamp (Epoch time).[cite:7] | 1501591804.[cite:7] |
| iss | Issuer.[cite:7] | https://connect.visma.com.[cite:7] |
| exp | Expiration Time in Unix Time Stamp (Epoch time).[cite:7] | 1501601800.[cite:7] |
| jti (optional; must be enabled for your Application) | Json Web Token ID. A unique identifier for the JWT.[cite:7] | 234hhjfhjk342hkh4hkj324hkjh42343khfs1jf.[cite:7] |

## Refresh Token

Refresh tokens beskrivs som credentials som används för att erhålla nya Access Tokens.[cite:7]

En Refresh Token är en sträng som representerar den auktorisering som resursägaren har beviljat klienten.[cite:7]

Strängen är vanligtvis opaque för klienten och token representerar en identifierare som används för att hämta auktorisationsinformation.[cite:7]

Till skillnad från Access Tokens är Refresh Tokens endast avsedda att användas med authorization servers och inte med API:er.[cite:7]

Refresh Tokens omfattas av strikta lagringskrav för att säkerställa att de inte läcker.[cite:7]

Refresh Tokens kan också återkallas av Authorization Server.[cite:7]

En Refresh Token gör det möjligt för applikationer att begära att Visma Connect authorization server utfärdar en ny Access Token direkt, utan att användaren behöver autentisera sig på nytt.[cite:7]

Det fungerar så länge Refresh Token inte har återkallats eller löpt ut.[cite:7]

Sidan hänvisar till [Offline Access](https://oauth.developers.visma.com/service-registry/documentation/authentication#offlineAccess) för mer information.[cite:7]

### Refresh Token security considerations

Refresh Tokens beskrivs som högvärdiga mål för angripare eftersom de vanligtvis har betydligt längre livslängd än Access Tokens.[cite:7]

Sidan anger att flera tekniker kan användas för att minska attackytan för Refresh Tokens.[cite:7]

#### Consent

Det anges vara en god idé att begära användarsamtycke så att appen gör användaren medveten om vad som sker med offline access.[cite:7]

#### Sliding expiration

Refresh Tokens har vanligtvis mycket längre livslängd än Access Tokens, men exponeringen kan minskas genom att lägga till en glidande livslängd utöver den absoluta livslängden.[cite:7]

Detta möjliggör scenarier där en Refresh Token kan användas tyst så länge användaren regelbundet använder klienten, men kräver en ny authorize request om klienten inte har använts under en viss tid.[cite:7]

Detta sammanfattas på sidan som att tokens annars auto-expire snabbare utan att i normalfallet störa det typiska användningsmönstret.[cite:7]

Alternativet `But will expire if not used in ... days` anges användas för att aktivera denna funktion.[cite:7]

#### One-time Refresh Tokens

Ett annat alternativ som anges är att rotera Refresh Tokens vid varje användning.[cite:7]

Detta minskar också exponeringen och ökar sannolikheten att äldre Refresh Tokens, exempelvis exfiltrerade från lagring eller nätverksspår/loggfiler, blir oanvändbara.[cite:7]

#### Replay detection

När one-time tokens används är replay detection aktiverat.[cite:7]

Det innebär att om samma Refresh Token används mer än en gång återkallas all åtkomst för kombinationen klient/användare.[cite:7]

Sidan anger att nackdelen är att det kan uppstå fler scenarier där en legitim Refresh Token blir oanvändbar, till exempel på grund av nätverksproblem under förnyelsen.[cite:7]

## Token Revocation

Denna mekanism gör det möjligt för klienter att meddela authorization server att en tidigare erhållen refresh- eller access-token inte längre behövs.[cite:7]

En revocation request ogiltigförklarar själva token och, om tillämpligt, andra tokens som bygger på samma authorization grant.[cite:7]

Sidan hänvisar till [RFC 7009](https://tools.ietf.org/html/rfc7009) för mer detaljer.[cite:7]

OAuth 2.0 Token Revocation endpoint kräver autentisering.[cite:7]

Autentisering sker med `client_id` och `client_secret`.[cite:7]

Klienten måste skicka dessa i Authorization-headern som HTTP basic auth, där `client_id` används som användarnamn och `client_secret` som lösenord.[cite:7]

Credentials måste vara Base64-kodade.[cite:7]

Authorization-headern återges på sidan som följande sträng.[cite:7]

```text
Authorization: Basic base64encode("client_id:client_secret")
```

Sidan noterar att om klienten inte behöver använda `client_secret`, till exempel när klienten använder PKCE flow, krävs inte `client_secret` och kan lämnas tomt i Authorization-headern som `"client_id:"`.[cite:7]

Exempel på request.[cite:7]

```text
curl --request POST --url https://connect.visma.com/connect/revocation --header 'authorization: Basic base64encode("client_id:client_secret")' --header 'content-type: application/x-www-form-urlencoded' --data 'token=token_value&token_type_hint=refresh_token'
```

### Parameters

| Name | Example Value | Required | Description |
|---|---|---|---|
| token | 45ghiukldjahdnhzdauz.[cite:7] | yes.[cite:7] | token string.[cite:7] |
| token_type_hint | refresh_token.[cite:7] | no.[cite:7] | access_token OR refresh_token.[cite:7] |

### Possible HTTP status code responses

- `200 OK` — if Token is removed successfully.[cite:7]
- `400 Bad Request` — if the client is invalid.[cite:7]
- `401 Unauthorized` — if the client is not authorized to remove the token.[cite:7]
