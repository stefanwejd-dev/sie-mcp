"""Steg 2 — test av tests._sie_fixtures.bygg_sie.

Se hantverksbok/BOKSLUTSKONTROLLER.md §7, steg 2 (acceptans)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from _sie_fixtures import bygg_sie
from domain_model import SIEFil


def test_default_ger_tom_men_giltig_siefil():
    sie = bygg_sie()
    assert isinstance(sie, SIEFil)
    assert sie.konton == {}
    assert sie.ingående_balanser == []
    assert sie.utgående_balanser == []
    assert sie.resultat == []
    assert sie.verifikationer == []
    assert sie.räkenskapsår[0].start == date(2025, 1, 1)
    assert sie.räkenskapsår[0].slut == date(2025, 12, 31)


def test_belopp_ar_decimal_aldrig_float():
    sie = bygg_sie(ib={"1930": "1000.50"}, ub={"1930": "2000.75"}, res={"3010": "-500.25"})
    assert sie.ingående_balanser[0].saldo == Decimal("1000.50")
    assert isinstance(sie.ingående_balanser[0].saldo, Decimal)
    assert sie.utgående_balanser[0].saldo == Decimal("2000.75")
    assert sie.resultat[0].saldo == Decimal("-500.25")


def test_konton_som_forekommer_i_saldon_hamnar_i_kontoplanen():
    sie = bygg_sie(ib={"1930": "100"}, ub={"2091": "-100"})
    assert "1930" in sie.konton
    assert "2091" in sie.konton


def test_konton_som_forekommer_bara_i_verifikationsrader_hamnar_i_kontoplanen():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "1930", "belopp": "-100"},
                    {"kontonr": "4000", "belopp": "100"},
                ],
            }
        ]
    )
    assert set(sie.konton) == {"1930", "4000"}
    verifikation = sie.verifikationer[0]
    assert verifikation.serie == "A"
    assert verifikation.vernr == "1"
    assert len(verifikation.transaktioner) == 2
    assert all(isinstance(t.belopp, Decimal) for t in verifikation.transaktioner)


def test_foregaende_ub_ger_rakenskapsar_minus_ett():
    sie = bygg_sie(foregaende_ub={"1930": "500"})
    assert -1 in sie.räkenskapsår
    assert sie.räkenskapsår[-1].start == date(2024, 1, 1)
    assert sie.räkenskapsår[-1].slut == date(2024, 12, 31)
    poster = [p for p in sie.utgående_balanser if p.årsnr == -1]
    assert len(poster) == 1
    assert poster[0].kontonr == "1930"
    assert poster[0].saldo == Decimal("500")


def test_konton_namn_kan_anges_explicit():
    sie = bygg_sie(konton={"1930": "Bankkonto"}, ib={"1930": "100"})
    assert sie.konton["1930"].namn == "Bankkonto"


@pytest.mark.xfail(
    reason="Väntar på grupp A–C (steg 3–5) — då ska en balanserad default-bokföring "
    "ge noll fynd från hela motorn.",
    strict=False,
)
def test_default_bygg_sie_ger_noll_fynd_fran_hela_motorn():
    import bokslutskontroll.kontroller  # noqa: F401  — fyller registret
    from bokslutskontroll.motor import kor_kontroller

    fynd = kor_kontroller(bygg_sie(), idag=date(2026, 8, 14))
    assert fynd == []
