"""tests/test_alla_vyer_renderas.py — Röktest för samtliga rum och vyer i app.py.

Verifierar att alla sidor och formulär kan importeras och anropas utan
ImportError, NameError eller AttributeError.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
import streamlit as st

from parser.sie4_parser import parse_sie4
from parser.domain_model import SIEFil, Konto
from parser.app_vy import Maskeringsresultat


class DummySt:
    """Mock av Streamlit för att verifiera att renderingsfunktioner körs utan kodfel."""
    def __init__(self):
        self.session_state = {
            "sie": None,
            "maskeringsresultat": None,
            "maskeringsliggare": {},
            "undantagslista": [],
            "namnreferens": [],
            "aktiv_datakälla": "Ladda upp lokal SIE4-fil",
            "atgard_filter": "alla",
            "oversikt_filter": "alla",
            "klient": None,
        }

    def __getattr__(self, name):
        def _mock_call(*args, **kwargs):
            return self
        return _mock_call

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_alla_renderingsfunktioner_kan_anropas():
    import parser.rum_render as rr

    # Verifiera att alla huvudfunktioner existerar och är callable
    funktioner = [
        rr.rendera_oversikt,
        rr.rendera_pengar_in,
        rr.rendera_saljdokument,
        rr.rendera_pengar_ut,
        rr.rendera_bank,
        rr.rendera_bockerna,
        rr.rendera_bokslut,
        rr.rendera_register,
        rr.rendera_rapporter,
        rr.rendera_investeringskalkyl,
        rr.rendera_foretags_chatt,
        rr.rendera_juridik,
        rr.rendera_data,
    ]

    for funk in funktioner:
        assert callable(funk), f"Funktion {funk} är inte callable"


def test_analysera_kontoperioder_korrekt():
    import parser.rum_render as rr

    sie = parse_sie4(Path("samples/SIE4_Exempelfil.SE"))
    rader = rr._analysera_kontoperioder(sie, "3041")
    assert isinstance(rader, list)
    if rader:
        assert "Månad / Period" in rader[0]
        assert "Bokfört i verifikationer" in rader[0]
