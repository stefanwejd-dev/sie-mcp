"""Tester för ai_adapter.py — det centrala fabriks-/adapterlagret som
bygger rätt analysanropare utifrån aktiv AIKonfiguration.

Enda stället i kodbasen där "vilken leverantör gör vad" avgörs för
FAKTISK analys (inte modellistning — det sköter ai_konfiguration.py).
app.py och analysflode.py ska aldrig behöva special-hantera en specifik
leverantör själva.

Inga riktiga nätverksanrop: att bygga en anropare (anthropic.Anthropic(...)
+ skapa_verklig_haiku_anropare(...)) gör aldrig ett API-anrop i sig själv
— bara att FAKTISKT KALLA den returnerade anroparen skulle göra det, och
det gör inget test här.
"""

from __future__ import annotations

import inspect

import pytest

from ai_konfiguration import AIKonfiguration

from ai_adapter import (
    AnalysanropareFel,
    SamtalanropareFel,
    bygg_agentanropare,
    bygg_analysanropare,
    bygg_chattanropare,
    leverantor_har_analysstod,
    leverantor_har_samtalsstod,
)


def _konfiguration(**overrides) -> AIKonfiguration:
    bas = dict(
        leverantör="Anthropic",
        api_nyckel="fake-nyckel",
        vald_modell="claude-haiku-4-5-20251001",
        tillgängliga_modeller=["claude-haiku-4-5-20251001"],
        status="modeller_hämtade",
    )
    bas.update(overrides)
    return AIKonfiguration(**bas)


class TestLeverantorHarAnalysstod:
    def test_anthropic_har_stod(self):
        assert leverantor_har_analysstod("Anthropic") is True

    @pytest.mark.parametrize("leverantör", ["OpenAI", "Google"])
    def test_openai_och_google_saknar_annu_stod(self, leverantör):
        assert leverantor_har_analysstod(leverantör) is False

    def test_okand_leverantor_saknar_stod(self):
        assert leverantor_har_analysstod("Mistral") is False


class TestLeverantorHarSamtalsstod:
    def test_anthropic_har_stod(self):
        assert leverantor_har_samtalsstod("Anthropic") is True

    @pytest.mark.parametrize("leverantör", ["OpenAI", "Google"])
    def test_openai_och_google_saknar_annu_stod(self, leverantör):
        assert leverantor_har_samtalsstod(leverantör) is False

    def test_okand_leverantor_saknar_stod(self):
        assert leverantor_har_samtalsstod("Mistral") is False


class TestByggAnalysanropare:
    def test_bygger_riktig_anropare_for_anthropic(self):
        konfiguration = _konfiguration()

        anropare = bygg_analysanropare(konfiguration, kontoplan={})

        assert callable(anropare)
        parametrar = list(inspect.signature(anropare).parameters.values())
        assert len(parametrar) == 2

    @pytest.mark.parametrize("leverantör", ["OpenAI", "Google"])
    def test_ej_stodd_leverantor_ger_fail_closed(self, leverantör):
        konfiguration = _konfiguration(leverantör=leverantör)

        with pytest.raises(AnalysanropareFel) as exc_info:
            bygg_analysanropare(konfiguration, kontoplan={})

        assert leverantör in str(exc_info.value)

    def test_saknad_api_nyckel_ger_fail_closed(self):
        konfiguration = _konfiguration(api_nyckel="")

        with pytest.raises(AnalysanropareFel):
            bygg_analysanropare(konfiguration, kontoplan={})

    def test_ingen_vald_modell_ger_fail_closed(self):
        konfiguration = _konfiguration(vald_modell=None)

        with pytest.raises(AnalysanropareFel):
            bygg_analysanropare(konfiguration, kontoplan={})

    def test_okand_leverantor_ger_fail_closed(self):
        konfiguration = _konfiguration(leverantör="Mistral")

        with pytest.raises(AnalysanropareFel):
            bygg_analysanropare(konfiguration, kontoplan={})


class TestByggChattanropare:
    def test_bygger_riktig_anropare_for_anthropic(self):
        konfiguration = _konfiguration()

        anropare = bygg_chattanropare(konfiguration)

        assert callable(anropare)
        parametrar = list(inspect.signature(anropare).parameters.values())
        assert len(parametrar) == 2

    @pytest.mark.parametrize("leverantör", ["OpenAI", "Google"])
    def test_ej_stodd_leverantor_ger_fail_closed(self, leverantör):
        konfiguration = _konfiguration(leverantör=leverantör)

        with pytest.raises(SamtalanropareFel) as exc_info:
            bygg_chattanropare(konfiguration)

        assert leverantör in str(exc_info.value)

    def test_saknad_api_nyckel_ger_fail_closed(self):
        konfiguration = _konfiguration(api_nyckel="")

        with pytest.raises(SamtalanropareFel):
            bygg_chattanropare(konfiguration)

    def test_ingen_vald_modell_ger_fail_closed(self):
        konfiguration = _konfiguration(vald_modell=None)

        with pytest.raises(SamtalanropareFel):
            bygg_chattanropare(konfiguration)

    def test_okand_leverantor_ger_fail_closed(self):
        konfiguration = _konfiguration(leverantör="Mistral")

        with pytest.raises(SamtalanropareFel):
            bygg_chattanropare(konfiguration)


class TestByggAgentanropare:
    """Fas 9: samma fail-closed-kontroller och leverantörslista som
    bygg_chattanropare — agentläget är en form av samtal, inget nytt
    stödbehov i sig."""

    def test_bygger_riktig_anropare_for_anthropic(self):
        konfiguration = _konfiguration()

        anropare = bygg_agentanropare(konfiguration)

        assert callable(anropare)
        parametrar = list(inspect.signature(anropare).parameters.values())
        assert len(parametrar) == 2

    def test_bygger_riktig_anropare_for_ollama(self):
        konfiguration = _konfiguration(
            leverantör="Ollama", api_nyckel="", vald_modell="llama3.1:8b",
        )

        anropare = bygg_agentanropare(konfiguration)

        assert callable(anropare)
        parametrar = list(inspect.signature(anropare).parameters.values())
        assert len(parametrar) == 2

    @pytest.mark.parametrize("leverantör", ["OpenAI", "Google"])
    def test_ej_stodd_leverantor_ger_fail_closed(self, leverantör):
        konfiguration = _konfiguration(leverantör=leverantör)

        with pytest.raises(SamtalanropareFel) as exc_info:
            bygg_agentanropare(konfiguration)

        assert leverantör in str(exc_info.value)

    def test_saknad_api_nyckel_ger_fail_closed(self):
        konfiguration = _konfiguration(api_nyckel="")

        with pytest.raises(SamtalanropareFel):
            bygg_agentanropare(konfiguration)

    def test_ingen_vald_modell_ger_fail_closed(self):
        konfiguration = _konfiguration(vald_modell=None)

        with pytest.raises(SamtalanropareFel):
            bygg_agentanropare(konfiguration)
