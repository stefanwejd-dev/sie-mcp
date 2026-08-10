# Visma Developer Portal – Session Management

Källsidan är Visma Developer Portal-sidan "Session Management".[cite:5]

## Sidhuvud och navigation

**Titel:** Visma Developer Portal.[cite:5]

**Övergripande navigation:**
- Start page.[cite:5]
- APIs.[cite:5]
- Webhooks.[cite:5]
- My Applications.[cite:5]
- Help.[cite:5]

**Meny:**
- Overview — <https://oauth.developers.visma.com/service-registry/documentation/overview>.[cite:5]
- Getting Started — <https://oauth.developers.visma.com/service-registry/documentation/gettingStarted>.[cite:5]
- Authentication and Authorization — <https://oauth.developers.visma.com/service-registry/documentation/authentication>.[cite:5]
- Session Management — <https://oauth.developers.visma.com/service-registry/documentation/sessionManagement>.[cite:5]
- Check Session Iframe.[cite:5]
- Single Sign Out.[cite:5]
- Tokens — <https://oauth.developers.visma.com/service-registry/documentation/tokens>.[cite:5]
- Best practices — <https://oauth.developers.visma.com/service-registry/documentation/bestPractices>.[cite:5]
- Show/Hide Menu.[cite:5]

## OpenID Connect Session Management

Visma Connect som OpenID Provider erbjuder funktionalitet till applikationer för verifiering av en användares sessionsstatus.[cite:5]

Visma Connect-sessionens livslängd anges till **10 timmar**.[cite:5]

Om ingen interaktion sker med Visma Connect löper användarens session ut efter **8 timmar**.[cite:5]

## Check Session Iframe

Under Sign In Flow returneras värdet **session_state** av Visma Connect som en del av klientens callback response från `/connect/authorize`.[cite:5]

Session state beskrivs som en opaque string där Visma Connect IdP har kodat användarens autentiseringsstatus vid den tidpunkt då OpenID-autentiseringsbegäran behandlades.[cite:5]

Klientapplikationen behöver inte känna till innehållet i strängen.[cite:5]

Klientappen kan kontrollera om användarens autentiseringsstatus har ändrats genom att ladda en dold iframe som pekar mot URL:en **check_session_iframe** och skicka en begäran dit via `window.postMessage`.[cite:5]

## Exempel på dold iframe

Källsidan avslutas i det tillgängliga innehållet med texten att ett exempel på en dold iframe mot endpointen `check_session_iframe` följer, men själva exempelkoden eller det efterföljande innehållet fanns inte med i den hämtade sidtexten.[cite:5]
