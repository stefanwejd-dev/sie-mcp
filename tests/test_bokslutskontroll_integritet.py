"""Steg 3 — test av grupp A (bokföringsteknisk integritet): K-01–K-06, K-13, K-15.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5 grupp A och §7 steg 3 (acceptans)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from _sie_fixtures import bygg_sie

from bokslutskontroll.kontroller.integritet import (
    kontroll_k01,
    kontroll_k02,
    kontroll_k03,
    kontroll_k04,
    kontroll_k05,
    kontroll_k06,
    kontroll_k13,
    kontroll_k15,
)
from bokslutskontroll.modell import Kontext


def _kontext(sie, *, arsnr: int = 0, tolerans: Decimal = Decimal("1.00")) -> Kontext:
    return Kontext(sie=sie, idag=date(2026, 8, 14), arsnr=arsnr, tolerans=tolerans)


# --- K-01 --------------------------------------------------------------


def test_k01_flaggar_obalanserad_balansrakning():
    sie = bygg_sie(ub={"1930": "1000"}, res={"3010": "-500"})
    fynd = kontroll_k01(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-01"
    assert fynd[0].allvarlighet == "avvikelse"
    assert fynd[0].belopp == Decimal("500")


def test_k01_ger_inget_fynd_nar_balanserad():
    sie = bygg_sie(ub={"1930": "1000"}, res={"3010": "-1000"})
    assert kontroll_k01(_kontext(sie)) == []


def test_k01_respekterar_tolerans():
    sie_under = bygg_sie(ub={"1930": "1000.50"}, res={"3010": "-1000.00"})
    assert kontroll_k01(_kontext(sie_under)) == []

    sie_over = bygg_sie(ub={"1930": "1001.50"}, res={"3010": "-1000.00"})
    fynd = kontroll_k01(_kontext(sie_over))
    assert len(fynd) == 1
    assert fynd[0].belopp == Decimal("1.50")


# --- K-02 --------------------------------------------------------------


def test_k02_flaggar_verifikation_i_obalans():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "1930", "belopp": "-100"},
                    {"kontonr": "4000", "belopp": "50"},
                ],
            }
        ]
    )
    fynd = kontroll_k02(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].verifikationer == ("A/1",)
    assert fynd[0].belopp == Decimal("-50")


def test_k02_ger_inget_fynd_for_balanserad_verifikation():
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
    assert kontroll_k02(_kontext(sie)) == []


# --- K-03 --------------------------------------------------------------


def test_k03_flaggar_brytning_mot_foregaende_ub():
    sie = bygg_sie(ib={"1930": "1000"}, foregaende_ub={"1930": "900"})
    fynd = kontroll_k03(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].konton == ("1930",)
    assert fynd[0].belopp == Decimal("100")


def test_k03_ger_inget_fynd_nar_ib_stammer_med_foregaende_ub():
    sie = bygg_sie(ib={"1930": "1000"}, foregaende_ub={"1930": "1000"})
    assert kontroll_k03(_kontext(sie)) == []


def test_k03_ger_noll_fynd_utan_foregaende_ub():
    sie = bygg_sie(ib={"1930": "1000"})
    assert kontroll_k03(_kontext(sie)) == []


# --- K-04 --------------------------------------------------------------


def test_k04_flaggar_balanskonto_som_inte_stammer():
    sie = bygg_sie(
        ib={"1930": "0"},
        ub={"1930": "100"},
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "1930", "belopp": "50"},
                    {"kontonr": "4000", "belopp": "-50"},
                ],
            }
        ],
    )
    fynd = kontroll_k04(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].konton == ("1930",)
    assert fynd[0].belopp == Decimal("50")


def test_k04_ger_inget_fynd_nar_saldot_stammer():
    sie = bygg_sie(
        ib={"1930": "0"},
        ub={"1930": "50"},
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "1930", "belopp": "50"},
                    {"kontonr": "4000", "belopp": "-50"},
                ],
            }
        ],
    )
    assert kontroll_k04(_kontext(sie)) == []


def test_k04_ger_noll_fynd_utan_verifikationer():
    sie = bygg_sie(ib={"1930": "0"}, ub={"1930": "100"})
    assert kontroll_k04(_kontext(sie)) == []


# --- K-05 --------------------------------------------------------------


def test_k05_flaggar_felaktigt_arets_resultat():
    sie = bygg_sie(ub={"2099": "1000"}, res={"3010": "-500"})
    fynd = kontroll_k05(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].konton == ("2099",)
    assert fynd[0].belopp == Decimal("500")


def test_k05_ger_inget_fynd_nar_resultatet_stammer():
    sie = bygg_sie(ub={"2099": "500"}, res={"3010": "-500"})
    assert kontroll_k05(_kontext(sie)) == []


def test_k05_ger_inget_fynd_nar_2099_saknar_saldo():
    sie = bygg_sie(res={"3010": "-500"})
    assert kontroll_k05(_kontext(sie)) == []


# --- K-06 --------------------------------------------------------------


def test_k06_flaggar_ett_fynd_per_verifikation_aven_med_flera_fel_rader():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "1930", "belopp": "-100", "transdat": "2024-12-31"},
                    {"kontonr": "4000", "belopp": "100", "transdat": "2026-01-15"},
                ],
            }
        ]
    )
    fynd = kontroll_k06(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].verifikationer == ("A/1",)


def test_k06_ger_inget_fynd_for_datum_inom_rakenskapsaret():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "1930", "belopp": "-100", "transdat": "2025-06-01"},
                    {"kontonr": "4000", "belopp": "100", "transdat": "2025-06-01"},
                ],
            }
        ]
    )
    assert kontroll_k06(_kontext(sie)) == []


# --- K-13 ----------------------------------------------------------------


def test_k13_flaggar_lucka_i_verifikationsserie():
    sie = bygg_sie(
        verifikationer=[
            {"serie": "A", "vernr": "1", "verdatum": "2025-01-01", "rader": []},
            {"serie": "A", "vernr": "3", "verdatum": "2025-01-02", "rader": []},
        ]
    )
    fynd = kontroll_k13(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-13"


def test_k13_ger_inget_fynd_for_sammanhangande_serie():
    sie = bygg_sie(
        verifikationer=[
            {"serie": "A", "vernr": "1", "verdatum": "2025-01-01", "rader": []},
            {"serie": "A", "vernr": "2", "verdatum": "2025-01-02", "rader": []},
        ]
    )
    assert kontroll_k13(_kontext(sie)) == []


def test_k13_hoppar_over_ickenumeriska_vernr_utan_att_kasta():
    sie = bygg_sie(
        verifikationer=[
            {"serie": "A", "vernr": "X1", "verdatum": "2025-01-01", "rader": []},
            {"serie": "A", "vernr": "X2", "verdatum": "2025-01-02", "rader": []},
        ]
    )
    assert kontroll_k13(_kontext(sie)) == []


def test_k13_flaggar_ordningsbrott_i_datum():
    sie = bygg_sie(
        verifikationer=[
            {"serie": "A", "vernr": "1", "verdatum": "2025-06-01", "rader": []},
            {"serie": "A", "vernr": "2", "verdatum": "2025-01-01", "rader": []},
        ]
    )
    fynd = kontroll_k13(_kontext(sie))
    assert len(fynd) == 1


# --- K-15 ----------------------------------------------------------------


def test_k15_flaggar_mojlig_dubbelbokforing():
    rader = [
        {"kontonr": "1930", "belopp": "-100"},
        {"kontonr": "4000", "belopp": "100"},
    ]
    sie = bygg_sie(
        verifikationer=[
            {"serie": "A", "vernr": "1", "verdatum": "2025-06-01", "rader": rader},
            {"serie": "A", "vernr": "2", "verdatum": "2025-06-01", "rader": rader},
        ]
    )
    fynd = kontroll_k15(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].allvarlighet == "observation"
    assert fynd[0].verifikationer == ("A/1", "A/2")


def test_k15_ger_inget_fynd_for_olika_verifikationer():
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
            },
            {
                "serie": "A",
                "vernr": "2",
                "verdatum": "2025-06-02",
                "rader": [
                    {"kontonr": "1930", "belopp": "-200"},
                    {"kontonr": "4000", "belopp": "200"},
                ],
            },
        ]
    )
    assert kontroll_k15(_kontext(sie)) == []
