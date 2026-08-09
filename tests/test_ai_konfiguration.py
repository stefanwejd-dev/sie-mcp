"""Tester för ai_konfiguration.py — leverantörsoberoende AI-konfigurations-
skikt (modellhämtning, ingen analys). Inga riktiga nätverksanrop: Anthropic
mockas via en injicerad fejkklient (samma mönster som test_haiku_klient.py),
OpenAI/Google via httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from ai_konfiguration import (
    LEVERANTÖRER,
    AIKonfiguration,
    ModellhämtningsFel,
    hamta_modeller_for_leverantor,
    leverantör_giltig,
    uppdatera_med_hamtade_modeller,
)


class _FejktModell:
    def __init__(self, id_: str) -> None:
        self.id = id_


class _FejktSvar:
    def __init__(self, data: list[_FejktModell]) -> None:
        self.data = data


class _FejkAnthropicKlient:
    """Minimal stand-in för anthropic.Anthropic — injiceras explicit,
    speglar bara .models.list().data[i].id som hamta_modeller_for_leverantor
    faktiskt läser."""

    def __init__(self, modeller: list[str] | None = None, fel: Exception | None = None) -> None:
        self._modeller = modeller
        self._fel = fel
        self.models = self

    def list(self):
        if self._fel is not None:
            raise self._fel
        return _FejktSvar([_FejktModell(m) for m in (self._modeller or [])])


def _http_klient(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestLeverantorValidering:
    @pytest.mark.parametrize("leverantör", ["Anthropic", "OpenAI", "Google"])
    def test_kanda_leverantorer_ar_giltiga(self, leverantör):
        assert leverantör_giltig(leverantör)
        assert leverantör in LEVERANTÖRER

    def test_okand_leverantor_ar_ogiltig(self):
        assert not leverantör_giltig("Mistral")

    def test_okand_leverantor_i_hamta_modeller_ger_statiskt_meddelande(self):
        """Regressionsskydd: meddelandet ska vara statiskt/generiskt, precis
        som modulens övriga ModellhämtningsFel — inte bygga in det
        anropande, ovaliderade leverantörsnamnet."""
        with pytest.raises(ModellhämtningsFel) as exc_info:
            hamta_modeller_for_leverantor("Mistral", "vilken-nyckel-som-helst")

        assert str(exc_info.value) == "Okänd leverantör."
        assert "Mistral" not in str(exc_info.value)


class TestHamtaModellerAnthropic:
    def test_lyckad_hamtning_ger_modellista(self):
        klient = _FejkAnthropicKlient(modeller=["claude-haiku-4-5-20251001", "claude-opus-4-8"])

        modeller = hamta_modeller_for_leverantor("Anthropic", "sk-ant-test", anthropic_klient=klient)

        assert modeller == ["claude-haiku-4-5-20251001", "claude-opus-4-8"]

    def test_fel_vid_anrop_ger_fail_closed(self):
        klient = _FejkAnthropicKlient(fel=Exception("ogiltig nyckel"))

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("Anthropic", "sk-ant-test", anthropic_klient=klient)

    def test_tom_modellista_ger_fail_closed(self):
        klient = _FejkAnthropicKlient(modeller=[])

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("Anthropic", "sk-ant-test", anthropic_klient=klient)


class TestHamtaModellerOpenAI:
    def test_lyckad_hamtning_ger_modellista(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer sk-test-nyckel"
            return httpx.Response(200, json={"data": [{"id": "gpt-4.1"}, {"id": "gpt-4o"}]})

        modeller = hamta_modeller_for_leverantor(
            "OpenAI", "sk-test-nyckel", http_klient=_http_klient(handler)
        )

        assert modeller == ["gpt-4.1", "gpt-4o"]

    def test_401_ger_fail_closed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_api_key"})

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("OpenAI", "fel-nyckel", http_klient=_http_klient(handler))

    def test_timeout_ger_fail_closed(self):
        def handler(request: httpx.Request):
            raise httpx.TimeoutException("timeout", request=request)

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("OpenAI", "sk-test", http_klient=_http_klient(handler))

    def test_ovantat_svarsformat_ger_fail_closed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("OpenAI", "sk-test", http_klient=_http_klient(handler))

    def test_tom_modellista_ger_fail_closed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("OpenAI", "sk-test", http_klient=_http_klient(handler))


class TestHamtaModellerGoogle:
    def test_lyckad_hamtning_ger_modellista_utan_prefix(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-goog-api-key"] == "google-test-nyckel"
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/gemini-2.5-pro"},
                        {"name": "models/gemini-2.5-flash"},
                    ]
                },
            )

        modeller = hamta_modeller_for_leverantor(
            "Google", "google-test-nyckel", http_klient=_http_klient(handler)
        )

        assert modeller == ["gemini-2.5-pro", "gemini-2.5-flash"]

    def test_api_nyckeln_skickas_i_header_inte_i_url(self):
        """Nyckeln ska ALDRIG hamna i URL:en — annars riskerar den att synas
        i loggar/exception-URL:er. Header, inte query-param."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "google-test-nyckel" not in str(request.url)
            return httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-pro"}]})

        hamta_modeller_for_leverantor(
            "Google", "google-test-nyckel", http_klient=_http_klient(handler)
        )

    def test_403_ger_fail_closed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": "forbidden"})

        with pytest.raises(ModellhämtningsFel):
            hamta_modeller_for_leverantor("Google", "fel-nyckel", http_klient=_http_klient(handler))


class TestFailClosedFelmeddelandeUtanApiNyckel:
    @pytest.mark.parametrize(
        "leverantör,api_nyckel,status_kod",
        [
            ("OpenAI", "hemlig-openai-nyckel-123", 401),
            ("Google", "hemlig-google-nyckel-456", 403),
        ],
    )
    def test_openai_google_felmeddelande_innehaller_aldrig_nyckeln(
        self, leverantör, api_nyckel, status_kod
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_kod)

        try:
            hamta_modeller_for_leverantor(
                leverantör, api_nyckel, http_klient=_http_klient(handler)
            )
        except ModellhämtningsFel as fel:
            assert api_nyckel not in str(fel)
        else:
            pytest.fail("Förväntade ModellhämtningsFel")

    def test_anthropic_felmeddelande_innehaller_aldrig_nyckeln(self):
        hemlig_nyckel = "sk-ant-hemlig-nyckel-789"
        klient = _FejkAnthropicKlient(fel=Exception(f"Fel för nyckel {hemlig_nyckel}"))

        try:
            hamta_modeller_for_leverantor("Anthropic", hemlig_nyckel, anthropic_klient=klient)
        except ModellhämtningsFel as fel:
            assert hemlig_nyckel not in str(fel)
        else:
            pytest.fail("Förväntade ModellhämtningsFel")


class TestUppdateraMedHamtadeModeller:
    def test_lyckad_hamtning_uppdaterar_status_och_modeller(self):
        konfiguration = AIKonfiguration(leverantör="Anthropic", api_nyckel="sk-ant-test")
        klient = _FejkAnthropicKlient(modeller=["claude-haiku-4-5-20251001"])

        resultat = uppdatera_med_hamtade_modeller(konfiguration, anthropic_klient=klient)

        assert resultat.status == "modeller_hämtade"
        assert resultat.tillgängliga_modeller == ["claude-haiku-4-5-20251001"]
        assert resultat.felmeddelande is None

    def test_misslyckad_hamtning_ger_fel_status_och_tomt(self):
        konfiguration = AIKonfiguration(leverantör="Anthropic", api_nyckel="sk-ant-test")
        klient = _FejkAnthropicKlient(fel=Exception("nätverksfel"))

        resultat = uppdatera_med_hamtade_modeller(konfiguration, anthropic_klient=klient)

        assert resultat.status == "fel"
        assert resultat.tillgängliga_modeller == []
        assert resultat.felmeddelande is not None
        assert resultat.vald_modell is None

    def test_ursprunglig_konfiguration_muteras_inte(self):
        konfiguration = AIKonfiguration(leverantör="Anthropic", api_nyckel="sk-ant-test")
        klient = _FejkAnthropicKlient(modeller=["claude-haiku-4-5-20251001"])

        uppdatera_med_hamtade_modeller(konfiguration, anthropic_klient=klient)

        assert konfiguration.status == "ingen_hämtning"
        assert konfiguration.tillgängliga_modeller == []
