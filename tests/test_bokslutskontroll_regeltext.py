"""Steg 9a — test av bokslutskontroll.regeltext.

Se hantverksbok/BOKSLUTSKONTROLLER.md §8.3. Fyndet är fullständigt utan
detta — testerna handlar om fail-closed-disciplinen, inte om att lydelsen
alltid går att hämta."""

from __future__ import annotations

import pytest

from bokslutskontroll.regeltext import (
    QuietChattRegeltextkalla,
    RiksdagenRegeltextkalla,
    SammansattRegeltextkalla,
    tolka_beteckning,
)


def test_tolka_beteckning_kapitel_och_paragraf():
    assert tolka_beteckning("5 kap. 1 §") == ("5", "1")


def test_tolka_beteckning_bara_paragraf():
    assert tolka_beteckning("3 §") == (None, "3")


def test_tolka_beteckning_bokstavssuffix():
    assert tolka_beteckning("3 a §") == (None, "3a")


def test_tolka_beteckning_otolkbar_ger_none_none():
    assert tolka_beteckning("något som inte är en paragraf") == (None, None)


def test_tolka_beteckning_tom_strang():
    assert tolka_beteckning("") == (None, None)


class TestRiksdagenRegeltextkalla:
    def test_ger_none_vid_natverksfel(self, monkeypatch):
        import juridik_api

        def _kraschar(sokord):
            raise RuntimeError("nätverket är nere")

        monkeypatch.setattr(juridik_api, "sok_svensk_lagstiftning", _kraschar)
        assert RiksdagenRegeltextkalla().hamta("1999:1078", "5 kap. 1 §") is None

    def test_ger_none_vid_api_fel(self, monkeypatch):
        import juridik_api

        monkeypatch.setattr(
            juridik_api,
            "sok_svensk_lagstiftning",
            lambda sokord: {"status": "error", "meddelande": "x"},
        )
        assert RiksdagenRegeltextkalla().hamta("1999:1078", "5 kap. 1 §") is None

    def test_ger_none_utan_traff_pa_beteckning(self, monkeypatch):
        import juridik_api

        monkeypatch.setattr(
            juridik_api,
            "sok_svensk_lagstiftning",
            lambda sokord: {
                "status": "success",
                "lagstiftning": [{"beteckning": "2000:1", "utdrag_ur_lagtexten": "fel lag"}],
            },
        )
        assert RiksdagenRegeltextkalla().hamta("1999:1078", "5 kap. 1 §") is None

    def test_ger_utdrag_vid_traff(self, monkeypatch):
        import juridik_api

        monkeypatch.setattr(
            juridik_api,
            "sok_svensk_lagstiftning",
            lambda sokord: {
                "status": "success",
                "lagstiftning": [
                    {"beteckning": "1999:1078", "utdrag_ur_lagtexten": "Bokföring skall ske ..."}
                ],
            },
        )
        assert RiksdagenRegeltextkalla().hamta("1999:1078", "5 kap. 1 §") == "Bokföring skall ske ..."


class TestQuietChattRegeltextkalla:
    def test_nabar_ger_false_nar_importet_faller(self, monkeypatch):
        import builtins

        riktig_import = builtins.__import__

        def _blockera(namn, *a, **k):
            if namn.startswith("quiet_oppen_data"):
                raise ImportError("saknas i den här miljön")
            return riktig_import(namn, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _blockera)
        assert QuietChattRegeltextkalla().nabar() is False
        assert QuietChattRegeltextkalla().hamta("1999:1078", "5 kap. 1 §") is None

    def test_hamta_ger_none_utan_paragraf_i_beteckningen(self):
        kalla = QuietChattRegeltextkalla()
        assert kalla.hamta("1999:1078", "något otolkbart") is None

    def test_hamta_kraschar_aldrig_om_sok_lag_kastar(self, monkeypatch):
        import sys
        import types

        fejkmodul = types.ModuleType("quiet_oppen_data.adaptrar.lagtext")

        def _kraschande_sok_lag(**kwargs):
            raise RuntimeError("databasen saknas")

        fejkmodul.sok_lag = _kraschande_sok_lag
        monkeypatch.setitem(sys.modules, "quiet_oppen_data", types.ModuleType("quiet_oppen_data"))
        monkeypatch.setitem(sys.modules, "quiet_oppen_data.adaptrar", types.ModuleType("quiet_oppen_data.adaptrar"))
        monkeypatch.setitem(sys.modules, "quiet_oppen_data.adaptrar.lagtext", fejkmodul)

        assert QuietChattRegeltextkalla().hamta("1999:1078", "5 kap. 1 §") is None


class TestSammansattRegeltextkalla:
    def test_anvander_riksdagen_nar_quiet_chatt_inte_ar_nabar(self, monkeypatch):
        källa = SammansattRegeltextkalla()
        monkeypatch.setattr(källa._quiet_chatt, "nabar", lambda: False)
        anropad_med = {}

        def _spionerande_hamta(sfs, beteckning):
            anropad_med["sfs"] = sfs
            return "riksdagens lydelse"

        monkeypatch.setattr(källa._riksdagen, "hamta", _spionerande_hamta)

        assert källa.hamta("1999:1078", "5 kap. 1 §") == "riksdagens lydelse"
        assert anropad_med["sfs"] == "1999:1078"

    def test_anvander_quiet_chatt_nar_nabart(self, monkeypatch):
        källa = SammansattRegeltextkalla()
        monkeypatch.setattr(källa._quiet_chatt, "nabar", lambda: True)
        monkeypatch.setattr(källa._quiet_chatt, "hamta", lambda sfs, beteckning: "quiet_chatt-lydelse")

        def _far_inte_anropas(sfs, beteckning):
            raise AssertionError("Riksdagen anropades trots att quiet_chatt var nåbar")

        monkeypatch.setattr(källa._riksdagen, "hamta", _far_inte_anropas)

        assert källa.hamta("1999:1078", "5 kap. 1 §") == "quiet_chatt-lydelse"

    def test_quiet_chatt_nabar_men_utan_traff_faller_inte_tillbaka(self, monkeypatch):
        """Nåbarhet avgörs en gång, inte per fråga: en källa som verkligen
        svarat 'hittar inget' ska inte tystas av en sämre källas gissning."""
        källa = SammansattRegeltextkalla()
        monkeypatch.setattr(källa._quiet_chatt, "nabar", lambda: True)
        monkeypatch.setattr(källa._quiet_chatt, "hamta", lambda sfs, beteckning: None)

        def _far_inte_anropas(sfs, beteckning):
            raise AssertionError("Riksdagen anropades trots att quiet_chatt redan svarat")

        monkeypatch.setattr(källa._riksdagen, "hamta", _far_inte_anropas)

        assert källa.hamta("1999:1078", "5 kap. 1 §") is None
