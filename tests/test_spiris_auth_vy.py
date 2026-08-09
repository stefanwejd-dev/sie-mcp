"""Tester för spiris_auth_vy.py — de testbara OAuth-hjälparna bakom
Sektion 1:s Spiris-inloggning. All logik som annars skulle ligga inbäddad i
app.py:s Streamlit-kod flyttas hit så den kan beteendetestas utan UI-runtime
(samma princip som app_vy.py och ai_konfiguration.py).

Aldrig riktigt nätverk: token-växlingen testas med injicerad httpx-fejk-
transport (httpx.MockTransport). Fail-closed: allt som går fel blir vårt eget
SpirisAuthFel — aldrig en rå exception-text eller ett httpx-undantag ut till
UI:t.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import base64
import hashlib

from spiris_auth_vy import (
    REDIRECT_URI,
    SpirisAuthFel,
    SpirisTokens,
    bygg_auktoriserings_url,
    extrahera_kod,
    generera_pkce,
    generera_state,
    vaxla_kod_mot_token,
)


class _FejkToken:
    """Injicerad fejk-transport för identity-token-endpointen."""

    def __init__(self, svar) -> None:
        self._svar = svar
        self.anrop: list[httpx.Request] = []

    def klient(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handler))

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.anrop.append(request)
        if isinstance(self._svar, Exception):
            raise self._svar
        status, kropp = self._svar
        if isinstance(kropp, dict):
            return httpx.Response(status, json=kropp)
        return httpx.Response(status, text=kropp)


class TestByggAuktoriseringsUrl:
    def _params(self) -> dict[str, list[str]]:
        url = bygg_auktoriserings_url(
            client_id="xsandbox", redirect_uri=REDIRECT_URI, state="S123"
        )
        return url, parse_qs(urlparse(url).query)

    def test_pekar_pa_identity_authorize_endpoint(self):
        url, _ = self._params()
        delar = urlparse(url)
        assert delar.hostname == "identity.vismaonline.com"
        assert delar.path == "/connect/authorize"

    def test_innehaller_alla_scopes(self):
        _, p = self._params()
        scope = p["scope"][0]
        # ea:purchase krävs för leverantörsreskontran (/suppliers, /supplierinvoices).
        for krävt in ("ea:api", "ea:accounting", "ea:sales", "ea:purchase", "offline_access"):
            assert krävt in scope, krävt

    def test_response_type_ar_code(self):
        _, p = self._params()
        assert p["response_type"] == ["code"]

    def test_innehaller_client_id_redirect_och_state(self):
        _, p = self._params()
        assert p["client_id"] == ["xsandbox"]
        assert p["redirect_uri"] == [REDIRECT_URI]
        assert p["state"] == ["S123"]


class TestGeneraState:
    def test_state_ar_icketomt(self):
        assert generera_state().strip() != ""

    def test_tva_anrop_ger_olika_state(self):
        # CSRF-skyddet är verkningslöst om state är förutsägbart.
        assert generera_state() != generera_state()


class TestExtraheraKod:
    REDIRECT = (
        "https://localhost:44300/callback?code=ABC-1"
        "&scope=ea%3Aapi%20ea%3Aaccounting&state=S123"
        "&iss=https%3A%2F%2Fidentity.vismaonline.com"
    )

    def test_extraherar_kod_ur_full_redirect_url(self):
        assert extrahera_kod(self.REDIRECT, förväntat_state="S123") == "ABC-1"

    def test_accepterar_ra_kod_direkt(self):
        # Användaren får klistra in enbart koden — då finns inget state att
        # verifiera, och det ska inte blockera.
        assert extrahera_kod("ABC-1") == "ABC-1"

    def test_trimmar_omgivande_blanksteg(self):
        assert extrahera_kod("  ABC-1  ") == "ABC-1"

    def test_state_mismatch_ger_fel(self):
        # CSRF-skydd: fel state -> fail-closed.
        with pytest.raises(SpirisAuthFel):
            extrahera_kod(self.REDIRECT, förväntat_state="FEL_STATE")

    def test_tomt_varde_ger_fel(self):
        with pytest.raises(SpirisAuthFel):
            extrahera_kod("   ")

    def test_url_utan_kod_ger_fel(self):
        with pytest.raises(SpirisAuthFel):
            extrahera_kod("https://localhost:44300/callback?state=S123&error=access_denied")

    def test_url_med_kod_men_utan_state_avvisas_nar_state_forvantas(self):
        # Fynd 7: förr passerade ett SAKNAT state tyst CSRF-kontrollen — att bara
        # stryka state-parametern kringgick skyddet. Nu är kontrollen obligatorisk.
        url_utan_state = "https://localhost:44300/callback?code=ABC-1&scope=ea%3Aapi"
        with pytest.raises(SpirisAuthFel):
            extrahera_kod(url_utan_state, förväntat_state="S123")

    def test_url_med_kod_utan_state_ok_utan_forvantat_state(self):
        # Ingen förväntan -> inget att verifiera (t.ex. användaren klistrar in en
        # länk innan state hunnit sättas). Ska inte blockera.
        url = "https://localhost:44300/callback?code=ABC-1"
        assert extrahera_kod(url) == "ABC-1"


class TestPKCE:
    def test_generera_pkce_ger_giltig_s256_challenge(self):
        verifierare, challenge = generera_pkce()
        assert verifierare and challenge
        # challenge = base64url(sha256(verifier)) utan padding (RFC 7636).
        förväntat = base64.urlsafe_b64encode(
            hashlib.sha256(verifierare.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert challenge == förväntat
        assert "=" not in challenge

    def test_tva_anrop_ger_olika_verifierare(self):
        assert generera_pkce()[0] != generera_pkce()[0]

    def test_url_innehaller_code_challenge_nar_angivet(self):
        url = bygg_auktoriserings_url(
            client_id="x", redirect_uri=REDIRECT_URI, state="S1", code_challenge="CH1",
        )
        params = parse_qs(urlparse(url).query)
        assert params["code_challenge"] == ["CH1"]
        assert params["code_challenge_method"] == ["S256"]

    def test_url_utan_challenge_saknar_pkce_parametrar(self):
        url = bygg_auktoriserings_url(client_id="x", redirect_uri=REDIRECT_URI, state="S1")
        params = parse_qs(urlparse(url).query)
        assert "code_challenge" not in params
        assert "code_challenge_method" not in params

    def test_vaxla_skickar_code_verifier(self):
        fejk = _FejkToken((200, {"access_token": "AT", "refresh_token": "RT"}))
        vaxla_kod_mot_token(
            "ABC-1", client_id="x", client_secret="s", redirect_uri=REDIRECT_URI,
            code_verifier="VER123", klient=fejk.klient(),
        )
        assert b"code_verifier=VER123" in fejk.anrop[0].content

    def test_vaxla_utan_verifier_skickar_ingen_pkce(self):
        fejk = _FejkToken((200, {"access_token": "AT", "refresh_token": "RT"}))
        vaxla_kod_mot_token(
            "ABC-1", client_id="x", client_secret="s", redirect_uri=REDIRECT_URI,
            klient=fejk.klient(),
        )
        assert b"code_verifier" not in fejk.anrop[0].content


class TestVaxlaKodMotToken:
    def _växla(self, fejk: _FejkToken):
        return vaxla_kod_mot_token(
            "ABC-1",
            client_id="xsandbox",
            client_secret="hemlis",
            redirect_uri=REDIRECT_URI,
            klient=fejk.klient(),
        )

    def test_lyckad_vaxling_ger_tokens(self):
        fejk = _FejkToken((200, {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}))
        tokens = self._växla(fejk)

        assert isinstance(tokens, SpirisTokens)
        assert tokens.access_token == "AT"
        assert tokens.refresh_token == "RT"

    def test_skickar_grant_type_authorization_code_och_koden(self):
        fejk = _FejkToken((200, {"access_token": "AT", "refresh_token": "RT"}))
        self._växla(fejk)

        kropp = fejk.anrop[0].content
        assert b"grant_type=authorization_code" in kropp
        assert b"ABC-1" in kropp

    def test_http_fel_ger_spirisauthfel(self):
        fejk = _FejkToken((400, {"error": "invalid_grant"}))
        with pytest.raises(SpirisAuthFel):
            self._växla(fejk)

    def test_timeout_ger_spirisauthfel(self):
        fejk = _FejkToken(httpx.TimeoutException("tidsgräns"))
        with pytest.raises(SpirisAuthFel):
            self._växla(fejk)

    def test_saknat_access_token_ger_spirisauthfel(self):
        fejk = _FejkToken((200, {"refresh_token": "RT"}))  # inget access_token
        with pytest.raises(SpirisAuthFel):
            self._växla(fejk)

    def test_inget_httpx_undantag_lacker_ut(self):
        fejk = _FejkToken(httpx.ConnectError("nere"))
        try:
            self._växla(fejk)
        except SpirisAuthFel:
            pass
        except httpx.HTTPError as e:
            pytest.fail(f"httpx-undantag läckte ut: {type(e).__name__}")
