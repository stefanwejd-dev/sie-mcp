"""Lager 1b, steg 4 — test av avstamning.kontroller (A-01 … A-05).

Se hantverksbok/BOKSLUTSPROGRAMMET.md §4.5 steg 4. Registreras i samma
motor och samma register som lager 1 — testerna kör därför både de enskilda
kontrollfunktionerna direkt (samma stil som test_bokslutskontroll_
integritet.py) och en fullständig runda genom kor_kontroller för att bevisa
att A-* verkligen delar motor med K-*."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

import avstamning  # noqa: F401  — fyller KONTROLLER-registret (A-01…A-05)
from _sie_fixtures import bygg_sie

from avstamning.camt053 import Utdrag, Utdragsrad
from avstamning.kontroller import (
    kontroll_a01,
    kontroll_a02,
    kontroll_a03,
    kontroll_a04,
    kontroll_a05,
)
from bokslutskontroll.modell import Kontext
from bokslutskontroll.motor import kor_kontroller

_KONTO = "1930"


def _kontext(sie, *, utdrag=None, avstamningskonto=_KONTO, tolerans=Decimal("1.00")) -> Kontext:
    return Kontext(sie=sie, idag=date(2026, 8, 14), tolerans=tolerans, utdrag=utdrag, avstamningskonto=avstamningskonto)


def _utdrag(rader=(), period_start=None, period_slut=None, utgaende_saldo=None, kontonr=_KONTO):
    return Utdrag(
        kontonr=kontonr,
        period_start=period_start,
        period_slut=period_slut,
        ingaende_saldo=None,
        utgaende_saldo=utgaende_saldo,
        rader=tuple(rader),
    )


# --- Grindar: utan utdrag/avstämningskonto/rätt konto ger [] ---------------


def test_alla_kontroller_ger_tomt_utan_utdrag():
    sie = bygg_sie()
    kontext = _kontext(sie, utdrag=None)
    for kontroll in (kontroll_a01, kontroll_a02, kontroll_a03, kontroll_a04, kontroll_a05):
        assert kontroll(kontext) == []


def test_alla_kontroller_ger_tomt_utan_avstamningskonto():
    sie = bygg_sie()
    kontext = _kontext(sie, utdrag=_utdrag(), avstamningskonto=None)
    for kontroll in (kontroll_a01, kontroll_a02, kontroll_a03, kontroll_a04, kontroll_a05):
        assert kontroll(kontext) == []


def test_konto_utanfor_avstamningsbara_konton_ger_tomt():
    sie = bygg_sie()
    kontext = _kontext(sie, utdrag=_utdrag(), avstamningskonto="4010")  # inte ett likvidkonto
    assert kontroll_a01(kontext) == []
    assert kontroll_a02(kontext) == []
    assert kontroll_a03(kontext) == []


# --- A-01: banktransaktion saknas i bokföringen -----------------------------


def test_a01_flaggar_ren_utdragsrad_utan_bokford_motsvarighet():
    sie = bygg_sie()
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"), text="Insättning")])
    fynd = kontroll_a01(_kontext(sie, utdrag=utdrag))

    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "A-01"
    assert fynd[0].allvarlighet == "avvikelse"
    assert fynd[0].belopp == Decimal("1000")
    assert "Insättning" in fynd[0].motivering


def test_a01_ger_inget_fynd_nar_raden_ar_bokford():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2026-06-05",
                "rader": [
                    {"kontonr": _KONTO, "belopp": "1000", "transdat": "2026-06-05"},
                    {"kontonr": "3010", "belopp": "-1000", "transdat": "2026-06-05"},
                ],
            }
        ]
    )
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))])
    assert kontroll_a01(_kontext(sie, utdrag=utdrag)) == []


# --- A-02: bokförd post saknas på kontoutdraget -----------------------------


def test_a02_flaggar_bokford_post_utan_utdragsrad():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "7",
                "verdatum": "2026-06-05",
                "rader": [
                    {"kontonr": _KONTO, "belopp": "-500", "transdat": "2026-06-05"},
                    {"kontonr": "4010", "belopp": "500", "transdat": "2026-06-05"},
                ],
            }
        ]
    )
    fynd = kontroll_a02(_kontext(sie, utdrag=_utdrag()))

    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "A-02"
    assert fynd[0].allvarlighet == "observation"
    assert fynd[0].verifikationer == ("A/7",)
    assert fynd[0].belopp == Decimal("-500")


def test_a02_ger_inget_fynd_nar_matchad():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2026-06-05",
                "rader": [{"kontonr": _KONTO, "belopp": "1000", "transdat": "2026-06-05"}],
            }
        ]
    )
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))])
    assert kontroll_a02(_kontext(sie, utdrag=utdrag)) == []


# --- A-03: beloppet skiljer -------------------------------------------------


def test_a03_flaggar_par_med_samma_datum_men_olika_belopp():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "3",
                "verdatum": "2026-06-05",
                "rader": [{"kontonr": _KONTO, "belopp": "998", "transdat": "2026-06-05"}],
            }
        ]
    )
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))])
    fynd = kontroll_a03(_kontext(sie, utdrag=utdrag))

    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "A-03"
    assert fynd[0].allvarlighet == "observation"
    assert fynd[0].verifikationer == ("A/3",)
    assert fynd[0].belopp == Decimal("-2")  # 998 - 1000


def test_a03_par_rapporteras_inte_ocksa_som_a01_eller_a02():
    """Ett par som blivit A-03 ska vara konsumerat — inte dyka upp igen som
    en A-01-rad och en A-02-post."""
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "3",
                "verdatum": "2026-06-05",
                "rader": [{"kontonr": _KONTO, "belopp": "998", "transdat": "2026-06-05"}],
            }
        ]
    )
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))])
    kontext = _kontext(sie, utdrag=utdrag)

    assert kontroll_a01(kontext) == []
    assert kontroll_a02(kontext) == []
    assert len(kontroll_a03(kontext)) == 1


def test_a03_parkopplar_inom_matchningsfonstret_inte_bara_samma_datum():
    """§4.3.1: parkopplingen (pass 3) använder SAMMA fönster som pass 2
    (matchningsfonster_dagar), inte ett snävare krav på exakt samma datum."""
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "3",
                "verdatum": "2026-06-01",
                "rader": [{"kontonr": _KONTO, "belopp": "998", "transdat": "2026-06-01"}],
            }
        ]
    )
    # 3 dagars mellanrum — innanför registrets matchningsfonster_dagar (5).
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 4), belopp=Decimal("1000"))])
    kontext = _kontext(sie, utdrag=utdrag)

    assert len(kontroll_a03(kontext)) == 1
    assert kontroll_a01(kontext) == []
    assert kontroll_a02(kontext) == []


def test_a03_parkopplar_inte_utanfor_matchningsfonstret():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "3",
                "verdatum": "2026-06-01",
                "rader": [{"kontonr": _KONTO, "belopp": "998", "transdat": "2026-06-01"}],
            }
        ]
    )
    # 10 dagars mellanrum — utanför registrets matchningsfonster_dagar (5).
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 11), belopp=Decimal("1000"))])
    kontext = _kontext(sie, utdrag=utdrag)

    assert kontroll_a03(kontext) == []
    assert len(kontroll_a01(kontext)) == 1
    assert len(kontroll_a02(kontext)) == 1


def test_a03_ingen_parkoppling_over_registrets_beloppsgrans():
    """En skillnad som överstiger BÅDE kron- och andelsgränsen i registret
    (50 kr respektive 2 %) ska inte parkopplas — paret blir A-01 + A-02
    i stället."""
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2026-06-05",
                "rader": [{"kontonr": _KONTO, "belopp": "500.00", "transdat": "2026-06-05"}],
            }
        ]
    )
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000.00"))])
    kontext = _kontext(sie, utdrag=utdrag)

    assert kontroll_a03(kontext) == []
    assert len(kontroll_a01(kontext)) == 1
    assert len(kontroll_a02(kontext)) == 1


def test_a03_olika_tecken_parkopplas_aldrig():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2026-06-05",
                "rader": [{"kontonr": _KONTO, "belopp": "-998", "transdat": "2026-06-05"}],
            }
        ]
    )
    utdrag = _utdrag(rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))])
    assert kontroll_a03(_kontext(sie, utdrag=utdrag)) == []


# --- A-04: utgående saldo stämmer inte --------------------------------------


def test_a04_flaggar_saldoskillnad():
    sie = bygg_sie(ub={_KONTO: "10000"})
    utdrag = _utdrag(utgaende_saldo=Decimal("10500"))
    fynd = kontroll_a04(_kontext(sie, utdrag=utdrag))

    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "A-04"
    assert fynd[0].allvarlighet == "avvikelse"
    assert fynd[0].belopp == Decimal("-500")


def test_a04_ger_inget_fynd_nar_saldona_stammer():
    sie = bygg_sie(ub={_KONTO: "10000"})
    utdrag = _utdrag(utgaende_saldo=Decimal("10000"))
    assert kontroll_a04(_kontext(sie, utdrag=utdrag)) == []


def test_a04_ger_inget_fynd_utan_utgaende_saldo_pa_utdraget():
    sie = bygg_sie(ub={_KONTO: "10000"})
    utdrag = _utdrag(utgaende_saldo=None)
    assert kontroll_a04(_kontext(sie, utdrag=utdrag)) == []


def test_a04_behandlar_saknat_bokfort_saldo_som_noll():
    sie = bygg_sie()  # inget UB alls för kontot
    utdrag = _utdrag(utgaende_saldo=Decimal("100"))
    fynd = kontroll_a04(_kontext(sie, utdrag=utdrag))
    assert len(fynd) == 1
    assert fynd[0].belopp == Decimal("-100")


# --- A-05: kontoutdraget täcker inte hela räkenskapsåret --------------------


def test_a05_flaggar_ofullstandig_period():
    sie = bygg_sie(rakenskapsar=("2026-01-01", "2026-12-31"))
    utdrag = _utdrag(period_start=date(2026, 6, 1), period_slut=date(2026, 6, 30))
    fynd = kontroll_a05(_kontext(sie, utdrag=utdrag))

    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "A-05"
    assert fynd[0].allvarlighet == "upplysning"


def test_a05_ger_inget_fynd_nar_hela_aret_tacks():
    sie = bygg_sie(rakenskapsar=("2026-01-01", "2026-12-31"))
    utdrag = _utdrag(period_start=date(2026, 1, 1), period_slut=date(2026, 12, 31))
    assert kontroll_a05(_kontext(sie, utdrag=utdrag)) == []


def test_a05_flaggar_okand_period():
    sie = bygg_sie(rakenskapsar=("2026-01-01", "2026-12-31"))
    utdrag = _utdrag(period_start=None, period_slut=None)
    fynd = kontroll_a05(_kontext(sie, utdrag=utdrag))
    assert len(fynd) == 1
    assert "kunde inte fastställas" in fynd[0].motivering


# --- Integration genom motorn -----------------------------------------------


def test_a_kontroller_gar_genom_samma_motor_som_k_kontroller():
    """Bevisar att lager 1b delar motor med lager 1 (§4.5): kor_kontroller
    körd med utdrag/avstamningskonto ger både A- och K-fynd, och A-fynden
    får regel/vasentlig ifyllt centralt precis som K-fynden."""
    sie = bygg_sie(
        ub={_KONTO: "10000"},
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2026-06-05",
                "rader": [{"kontonr": _KONTO, "belopp": "1000", "transdat": "2026-06-05"}],
            }
        ],
    )
    utdrag = _utdrag(
        rader=[Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))],
        utgaende_saldo=Decimal("10500"),
    )

    fynd = kor_kontroller(
        sie, idag=date(2026, 8, 14), utdrag=utdrag, avstamningskonto=_KONTO
    )

    a04_fynd = [f for f in fynd if f.kontroll_id == "A-04"]
    assert len(a04_fynd) == 1
    assert a04_fynd[0].regel is not None
    assert a04_fynd[0].regel.beteckning == "5 kap. 4 §"


def test_kor_kontroller_utan_utdrag_paverkar_inte_k_kontroller():
    """Bakåtkompatibilitet: kor_kontroller utan utdrag/avstamningskonto
    (lager 1:s befintliga anropsform) ger inga A-fynd alls."""
    sie = bygg_sie()
    fynd = kor_kontroller(sie, idag=date(2026, 8, 14))
    assert all(not f.kontroll_id.startswith("A-") for f in fynd)
