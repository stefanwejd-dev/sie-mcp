"""Steg 5 — test av grupp C: K-11, K-12 (bokslutsposter) och K-14 (kontotyper).

Se hantverksbok/BOKSLUTSKONTROLLER.md §5 grupp C och §7 steg 5 (acceptans)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from _sie_fixtures import bygg_sie

from bokslutskontroll.kontroller.bokslutsposter import kontroll_k11, kontroll_k12
from bokslutskontroll.kontroller.kontotyper import kontroll_k14
from bokslutskontroll.modell import Kontext
from kontotyp_vakt import analysera_kontotyper


def _kontext(
    sie,
    *,
    arsnr: int = 0,
    tolerans: Decimal = Decimal("1.00"),
    utfallsvasentlighet: Decimal | None = None,
) -> Kontext:
    return Kontext(
        sie=sie,
        idag=date(2026, 8, 14),
        arsnr=arsnr,
        tolerans=tolerans,
        utfallsvasentlighet=utfallsvasentlighet,
    )


# --- K-11 --------------------------------------------------------------


def test_k11_flaggar_kostnad_nara_arsskiftet_utan_periodiseringsmotpart():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-12-15",
                "rader": [
                    {"kontonr": "4010", "belopp": "5000"},
                    {"kontonr": "1930", "belopp": "-5000"},
                ],
            }
        ]
    )
    fynd = kontroll_k11(_kontext(sie, utfallsvasentlighet=Decimal("1000")))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-11"
    assert fynd[0].allvarlighet == "upplysning"
    assert fynd[0].verifikationer == ("A/1",)


def test_k11_ger_inget_fynd_med_periodiseringsmotpart():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-12-15",
                "rader": [
                    {"kontonr": "4010", "belopp": "5000"},
                    {"kontonr": "1790", "belopp": "-5000"},
                ],
            }
        ]
    )
    assert kontroll_k11(_kontext(sie, utfallsvasentlighet=Decimal("1000"))) == []


def test_k11_ger_inget_fynd_utanfor_periodiseringsfonstret():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-06-01",
                "rader": [
                    {"kontonr": "4010", "belopp": "5000"},
                    {"kontonr": "1930", "belopp": "-5000"},
                ],
            }
        ]
    )
    assert kontroll_k11(_kontext(sie, utfallsvasentlighet=Decimal("1000"))) == []


def test_k11_ger_noll_fynd_utan_beraknad_utfallsvasentlighet():
    sie = bygg_sie(
        verifikationer=[
            {
                "serie": "A",
                "vernr": "1",
                "verdatum": "2025-12-15",
                "rader": [
                    {"kontonr": "4010", "belopp": "5000"},
                    {"kontonr": "1930", "belopp": "-5000"},
                ],
            }
        ]
    )
    assert kontroll_k11(_kontext(sie, utfallsvasentlighet=None)) == []


# --- K-12 --------------------------------------------------------------


def test_k12_flaggar_anlaggningstillgang_utan_avskrivning():
    sie = bygg_sie(ub={"1220": "10000"})
    fynd = kontroll_k12(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-12"
    assert fynd[0].konton == ("1220",)
    assert fynd[0].belopp == Decimal("10000")


def test_k12_ger_inget_fynd_nar_avskrivning_finns():
    sie = bygg_sie(ub={"1220": "10000"}, res={"7830": "-1000"})
    assert kontroll_k12(_kontext(sie)) == []


def test_k12_ger_inget_fynd_utan_saldo_pa_tillgangskonto():
    sie = bygg_sie(ub={"1220": "0"})
    assert kontroll_k12(_kontext(sie)) == []


# --- K-14 ----------------------------------------------------------------


def test_k14_matchar_analysera_kontotyper_exakt():
    sie = bygg_sie(ub={"3010": "0", "4001": "0", "4002": "0", "4003": "0"})
    # Referensmönster: klass 3 (intäkter) förväntas typ "I", felkodat som "K".
    sie.konton["3010"].typ = "K"
    # Internmönster: serie "400" har majoritet "K" (2 av 3), "4003" avviker.
    sie.konton["4001"].typ = "K"
    sie.konton["4002"].typ = "K"
    sie.konton["4003"].typ = "S"

    direkt = analysera_kontotyper(sie)
    fynd = kontroll_k14(_kontext(sie))

    assert len(fynd) == len(direkt)
    assert {f.konton[0] for f in fynd} == {a.kontonr for a in direkt}
    assert all(f.kontroll_id == "K-14" for f in fynd)
    assert all(f.allvarlighet == "observation" for f in fynd)


def test_k14_ger_ingen_avvikelse_for_korrekt_kodade_konton():
    # Klass 3 (intäkter) förväntas typ "I" enligt referensmönstret.
    sie = bygg_sie(ub={"3010": "0"})
    sie.konton["3010"].typ = "I"
    assert kontroll_k14(_kontext(sie)) == []
    assert analysera_kontotyper(sie) == []
