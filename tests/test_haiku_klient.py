"""Tester för haiku_klient.py — den riktiga Anthropic-integrationen bakom
haiku_anropare-kontraktet i kontomatchning.py.

RÖD fas (TDD). Se ARCHITECTURE.md, avsnittet om Modul 5 (Gap 3b).

Dessa tester kräver ALDRIG en riktig API-nyckel eller ett riktigt nätverksanrop
— den fejkade Anthropic-klienten injiceras alltid explicit via
skapa_verklig_haiku_anropare(kontoplan, klient=...), aldrig monkeypatchad
globalt. Samma disciplin som resten av Modul 4:s testsvit.
"""

from __future__ import annotations

import inspect
import json

import pytest

from domain_model import Konto
from haiku_klient import MODELL, SYSTEMPROMPT, skapa_verklig_haiku_anropare

KONTON = {
    "5611": Konto(kontonr="5611", namn="Drivmedel personbilar"),
    "6110": Konto(kontonr="6110", namn="Kontorsmaterial"),
}


class _FejktTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FejktSvar:
    def __init__(self, text: str) -> None:
        self.content = [_FejktTextBlock(text)]


class _FejkAnthropicKlient:
    """Minimal stand-in för anthropic.Anthropic — injiceras explicit,
    monkeypatchar aldrig ett globalt SDK-objekt. Speglar bara den del av
    svarsformen (.messages.create(...).content[0].text) som
    skapa_verklig_haiku_anropare faktiskt läser."""

    def __init__(self, svarstext: str | None = None, fel: Exception | None = None) -> None:
        self._svarstext = svarstext
        self._fel = fel
        self.senaste_anrop: dict | None = None
        self.messages = self  # client.messages.create(...) -> self.create(...)

    def create(self, **kwargs) -> _FejktSvar:
        self.senaste_anrop = kwargs
        if self._fel is not None:
            raise self._fel
        return _FejktSvar(self._svarstext)


class _FejktThinkingBlock:
    """Speglar anthropic.ThinkingBlock: har .thinking men INGET .text."""

    def __init__(self, thinking: str) -> None:
        self.thinking = thinking


class _FejkThinkingKlient:
    """Extended-thinking-modell: content[0] är ett ThinkingBlock (utan .text),
    JSON-svaret ligger i det efterföljande TextBlocket."""

    def __init__(self, text: str) -> None:
        self._svar = _FejktSvar.__new__(_FejktSvar)
        self._svar.content = [_FejktThinkingBlock("resonemang"), _FejktTextBlock(text)]
        self.senaste_anrop: dict | None = None
        self.messages = self

    def create(self, **kwargs):
        self.senaste_anrop = kwargs
        return self._svar


def _bunt() -> list[dict]:
    return [
        {
            "bunt_id": "T1",
            "kontonr": "6110",
            "kontonamn": "Kontorsmaterial",
            "transtext": "Drivmedel Circle K",
            "vertext": None,
            "plats": "serie=A vernr=1 radindex=0",
            "text_analyserad": "Drivmedel Circle K",
            "belopp": "500",
        }
    ]


class TestAnropskonfiguration:
    def test_skickar_ratt_modell_och_systemprompt(self):
        klient = _FejkAnthropicKlient(svarstext="[]")
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        anropare(_bunt(), None)

        assert klient.senaste_anrop["model"] == MODELL
        assert klient.senaste_anrop["model"] == "claude-haiku-4-5-20251001"
        assert klient.senaste_anrop["system"] == SYSTEMPROMPT

    def test_angiven_modell_overstyr_standardkonstanten(self):
        """Bakåtkompatibel utökning: ges ett explicit modell-argument ska
        det användas i det faktiska API-anropet istället för MODELL-
        konstanten — det är vad som gör ai_konfiguration.vald_modell
        verkligt styrande via det centrala adapterlagret (ai_adapter.py)."""
        klient = _FejkAnthropicKlient(svarstext="[]")
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient, modell="claude-opus-4-8")

        anropare(_bunt(), None)

        assert klient.senaste_anrop["model"] == "claude-opus-4-8"

    def test_temperature_skickas_inte(self):
        """Samma orsak som chatt_klient: nyare (thinking-)modeller har fasat
        ut temperature och avvisar anropet med HTTP 400. Utan denna fix
        maskeras 400:et tyst till "osäker" för hela bunten."""
        klient = _FejkAnthropicKlient(svarstext="[]")
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        anropare(_bunt(), None)

        assert "temperature" not in klient.senaste_anrop

    def test_kontoplan_och_bunt_naar_anropet(self):
        klient = _FejkAnthropicKlient(svarstext="[]")
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        anropare(_bunt(), None)

        meddelanden = klient.senaste_anrop["messages"]
        innehall = meddelanden[0]["content"]

        # Kontoplanen (bunden via stängning) syns i innehållet
        assert "5611" in innehall
        assert "Drivmedel personbilar" in innehall
        assert "6110" in innehall
        assert "Kontorsmaterial" in innehall

        # Den skickade bunten syns i innehållet
        assert "T1" in innehall
        assert "Drivmedel Circle K" in innehall


class TestSvarstolkning:
    def test_parsear_giltigt_json_svar_korrekt(self):
        svar_json = json.dumps([
            {"bunt_id": "T1", "status": "avvikelse", "motivering": "Fel konto",
             "föreslaget_kontonr": "5611"},
        ])
        klient = _FejkAnthropicKlient(svarstext=svar_json)
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        resultat = anropare(_bunt(), None)

        assert resultat == [
            {"bunt_id": "T1", "status": "avvikelse", "motivering": "Fel konto",
             "föreslaget_kontonr": "5611"},
        ]

    def test_hoppar_over_thinking_block_vid_json_tolkning(self):
        """Extended-thinking-modeller lägger ett ThinkingBlock (utan .text)
        före JSON-textblocket. content[0].text kraschar då, vilket fail-closed
        maskerar hela bunten som osäker. JSON:en ska istället läsas ur första
        blocket som faktiskt har text."""
        svar_json = json.dumps([
            {"bunt_id": "T1", "status": "matchning", "motivering": None,
             "föreslaget_kontonr": None},
        ])
        klient = _FejkThinkingKlient(svar_json)
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        resultat = anropare(_bunt(), None)

        assert resultat == [
            {"bunt_id": "T1", "status": "matchning", "motivering": None,
             "föreslaget_kontonr": None},
        ]

    def test_api_fel_ger_hela_bunten_osaker(self):
        """Ingen rad försvinner tyst: kraschar det underliggande API-anropet
        ska ANDRA raden i bunten också komma tillbaka som osäker, inte bara
        den som "orsakade" felet — hela bunten delar samma anrop."""
        bunt = _bunt() + [
            {**_bunt()[0], "bunt_id": "T2", "kontonr": "5611"},
        ]
        klient = _FejkAnthropicKlient(fel=ConnectionError("nätverksfel"))
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        resultat = anropare(bunt, None)

        assert len(resultat) == len(bunt) == 2
        assert {r["bunt_id"] for r in resultat} == {"T1", "T2"}
        assert all(r["status"] == "osäker" for r in resultat)

    def test_trasigt_json_svar_ger_hela_bunten_osaker(self):
        bunt = _bunt() + [
            {**_bunt()[0], "bunt_id": "T2", "kontonr": "5611"},
        ]
        klient = _FejkAnthropicKlient(svarstext="det här är inte JSON {{{")
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        resultat = anropare(bunt, None)

        assert len(resultat) == len(bunt) == 2
        assert {r["bunt_id"] for r in resultat} == {"T1", "T2"}
        assert all(r["status"] == "osäker" for r in resultat)

    def test_giltig_json_med_fel_toppnivatyp_ger_hela_bunten_osaker(self):
        """json.loads(...) kan lyckas men ändå ge fel form — t.ex. ett
        objekt istället för en array. Samma fail-closed-väg som API-fel
        och trasig JSON: hela bunten blir osäker, ingen rad försvinner
        tyst."""
        bunt = _bunt() + [
            {**_bunt()[0], "bunt_id": "T2", "kontonr": "5611"},
        ]
        klient = _FejkAnthropicKlient(svarstext=json.dumps({"bunt_id": "T1"}))
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        resultat = anropare(bunt, None)

        assert len(resultat) == len(bunt) == 2
        assert {r["bunt_id"] for r in resultat} == {"T1", "T2"}
        assert all(r["status"] == "osäker" for r in resultat)


class TestKontrakt:
    def test_funktionssignatur_matchar_kontraktet(self):
        """Inga extra parametrar som skulle kunna smyga in en bakväg till
        rådata — exakt (bunt, prosa_kontext), inget mer."""
        klient = _FejkAnthropicKlient(svarstext="[]")
        anropare = skapa_verklig_haiku_anropare(KONTON, klient=klient)

        parametrar = list(inspect.signature(anropare).parameters.values())

        assert len(parametrar) == 2
        assert all(
            p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD for p in parametrar
        )
