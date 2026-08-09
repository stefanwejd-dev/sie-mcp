"""spiris_auth_vy — testbara OAuth2-hjälpare bakom Sektion 1:s Spiris-
inloggning.

Isolerad från Streamlit med flit (samma princip som app_vy.py och
ai_konfiguration.py): all logik som annars skulle ligga inbäddad i app.py:s
UI-kod ligger här som rena funktioner, så den kan beteendetestas utan
UI-runtime. app.py blir därmed ett tunt lager som bara anropar dessa och
skriver session_state.

Authorization Code-flödet: bygg_auktoriserings_url -> användaren loggar in ->
extrahera_kod (med CSRF-skydd via state) -> vaxla_kod_mot_token.

Fail-closed genomgående: allt som går fel — tomt/ogiltigt värde, fel state,
HTTP-fel, timeout, svar utan access_token — blir vårt eget SpirisAuthFel med
ett tydligt, ärligt meddelande. Inget httpx-specifikt undantag och ingen rå
exception-text når UI:t.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from spiris_klient import TOKEN_URL

AUTH_URL = "https://identity.vismaonline.com/connect/authorize"
REDIRECT_URI = "https://localhost:44300/callback"

# Beslut c: ea:sales krävs för /companysettings (företagsnamn/orgnr till
# sekretesslagret), ea:accounting för konton/verifikat/saldon, offline_access
# för refresh-token.
SPIRIS_SCOPES = "ea:api ea:accounting ea:sales ea:purchase offline_access"

_TIMEOUT_SEKUNDER = 30.0


class SpirisAuthFel(Exception):
    """Fail-closed-fel i OAuth-flödet — ogiltig inmatning, fel state, eller
    misslyckad token-växling. Aldrig rå exception-text eller ett
    httpx-undantag ut till UI:t."""


@dataclass
class SpirisTokens:
    access_token: str
    refresh_token: str


def generera_state() -> str:
    """Ett oförutsägbart state för CSRF-skydd. Lagras i session_state innan
    användaren skickas iväg och verifieras mot redirect-svaret."""
    return secrets.token_urlsafe(24)


def generera_pkce() -> tuple[str, str]:
    """Genererar ett PKCE-par (code_verifier, code_challenge) med metod S256
    (RFC 7636). Rekommenderas för publika klienter (granskningens fynd 7):
    även om en auktoriseringskod fångas kan den inte växlas mot ett token utan
    verifieraren, som aldrig lämnar den här sessionen. code_verifier lagras i
    session_state, code_challenge skickas i auktoriserings-URL:en."""
    code_verifier = secrets.token_urlsafe(64)
    urledigest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(urledigest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def bygg_auktoriserings_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: str = SPIRIS_SCOPES,
    code_challenge: str | None = None,
) -> str:
    """Bygger auktoriserings-URL:en för Authorization Code-flödet. Anges ett
    code_challenge (PKCE, fynd 7) läggs det till tillsammans med
    code_challenge_method=S256 — bakåtkompatibelt: utan challenge byggs URL:en
    exakt som förut."""
    parametrar = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state,
    }
    if code_challenge:
        parametrar["code_challenge"] = code_challenge
        parametrar["code_challenge_method"] = "S256"
    return f"{AUTH_URL}?{urlencode(parametrar)}"


def extrahera_kod(inmatning: str, förväntat_state: str | None = None) -> str:
    """Plockar ut auktoriseringskoden ur det användaren klistrar in — antingen
    hela redirect-URL:en eller enbart koden.

    CSRF-skydd (fynd 7): förväntas ett state (förväntat_state satt) och
    inmatningen är en redirect-URL, är kontrollen OBLIGATORISK — en URL med kod
    men utan (eller med fel) state avvisas. Förr passerade ett SAKNAT state tyst
    (state_i_svar is not None), vilket gjorde CSRF-skyddet kringgåbart genom att
    bara stryka state-parametern. En rå kod utan URL (medveten 'klistra in bara
    koden'-väg) har inget state att verifiera och tillåts som förut."""
    värde = (inmatning or "").strip()
    if not värde:
        raise SpirisAuthFel("Klistra in redirect-länken eller koden först.")

    if "code=" in värde:
        # Full redirect-URL eller en rå query-sträng — parse_qs klarar båda.
        fråga = parse_qs(urlparse(värde).query or värde)
        koder = fråga.get("code")
        if not koder:
            raise SpirisAuthFel("Hittade ingen kod i den inklistrade länken.")
        state_i_svar = fråga.get("state", [None])[0]
        if förväntat_state is not None and state_i_svar != förväntat_state:
            raise SpirisAuthFel("Fel eller saknat state i svaret — börja om inloggningen (säkerhetskontroll).")
        return koder[0]

    if värde.lower().startswith("http"):
        # Det är en URL, men utan code-parameter (t.ex. ett error-svar).
        raise SpirisAuthFel("Länken innehåller ingen kod. Godkände du åtkomsten?")

    # Ingen URL och inget code= -> tolka hela värdet som en rå kod.
    return värde


def vaxla_kod_mot_token(
    kod: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str = REDIRECT_URI,
    *,
    code_verifier: str | None = None,
    klient: httpx.Client | None = None,
) -> SpirisTokens:
    """Växlar en auktoriseringskod mot access- och refresh-token. Anges en
    code_verifier (PKCE, fynd 7) skickas den med — den binder token-växlingen
    till den ursprungliga auktoriseringsbegäran. Fail-closed: HTTP-fel, timeout,
    nätverksfel eller ett svar utan access_token ger SpirisAuthFel — inget
    httpx-undantag läcker ut."""
    aktiv_klient = klient if klient is not None else httpx.Client(timeout=_TIMEOUT_SEKUNDER)
    data = {
        "grant_type": "authorization_code",
        "code": kod,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    try:
        try:
            svar = aktiv_klient.post(TOKEN_URL, data=data)
            svar.raise_for_status()
            data = svar.json()
        except httpx.TimeoutException as e:
            raise SpirisAuthFel("Tidsgräns överskreds mot Spiris inloggning.") from e
        except httpx.HTTPError as e:
            raise SpirisAuthFel("Kunde inte byta koden mot ett token (fel eller utgången kod).") from e
    finally:
        if klient is None:
            aktiv_klient.close()

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token or not refresh_token:
        raise SpirisAuthFel("Ofullständigt svar från Spiris vid inloggning.")
    return SpirisTokens(access_token=access_token, refresh_token=refresh_token)
