"""Steg 4 — test av grupp B (saldologik och avstämning): K-07–K-10.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5 grupp B och §7 steg 4 (acceptans)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from _sie_fixtures import bygg_sie

import bokslutskontroll.regelkalla as regelkalla
from bokslutskontroll.kontroller.saldologik import (
    kontroll_k07,
    kontroll_k08,
    kontroll_k09,
    kontroll_k10,
)
from bokslutskontroll.modell import Kontext


def _kontext(sie, *, arsnr: int = 0, tolerans: Decimal = Decimal("1.00")) -> Kontext:
    return Kontext(sie=sie, idag=date(2026, 8, 14), arsnr=arsnr, tolerans=tolerans)


# --- K-08 ------------------------------------------------------------------


def test_k08_flaggar_kvarvarande_saldo_pa_avrakningskonto():
    sie = bygg_sie(ub={"1630": "5000"})
    fynd = kontroll_k08(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-08"
    assert fynd[0].allvarlighet == "observation"
    assert fynd[0].konton == ("1630",)
    assert fynd[0].belopp == Decimal("5000")


def test_k08_ger_inget_fynd_nar_avrakningskonto_ar_nollstallt():
    sie = bygg_sie(ub={"1630": "0"})
    assert kontroll_k08(_kontext(sie)) == []


def test_k08_ignorerar_konton_utanfor_listan():
    sie = bygg_sie(ub={"1930": "5000"})
    assert kontroll_k08(_kontext(sie)) == []


# --- K-09 ------------------------------------------------------------------


def test_k09_flaggar_debetnormalt_konto_med_kreditsaldo():
    sie = bygg_sie(ub={"1510": "-2000"})
    fynd = kontroll_k09(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].konton == ("1510",)
    assert fynd[0].belopp == Decimal("-2000")


def test_k09_flaggar_kreditnormalt_konto_med_debetsaldo():
    sie = bygg_sie(ub={"2440": "3000"})
    fynd = kontroll_k09(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].konton == ("2440",)
    assert fynd[0].belopp == Decimal("3000")


def test_k09_ger_inget_fynd_for_saldo_pa_ratt_sida():
    sie = bygg_sie(ub={"1510": "2000", "2440": "-3000"})
    assert kontroll_k09(_kontext(sie)) == []


# --- K-07 ------------------------------------------------------------------


def test_k07_flaggar_moms_i_orimlig_proportion():
    sie = bygg_sie(ub={"2610": "-50000"}, res={"3010": "-100000"})
    fynd = kontroll_k07(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-07"
    assert fynd[0].allvarlighet == "observation"


def test_k07_ger_inget_fynd_for_normal_momsproportion():
    sie = bygg_sie(ub={"2610": "-25000"}, res={"3010": "-100000"})
    assert kontroll_k07(_kontext(sie)) == []


def test_k07_ger_noll_fynd_utan_omsattning():
    sie = bygg_sie(ub={"2610": "-25000"})
    assert kontroll_k07(_kontext(sie)) == []


# --- K-10 ------------------------------------------------------------------


def test_k10_flaggar_arbetsgivaravgift_i_orimlig_proportion():
    sie = bygg_sie(
        res={"7010": "100000", "7510": "50000"},
        rakenskapsar=("2026-01-01", "2026-12-31"),
    )
    fynd = kontroll_k10(_kontext(sie))
    assert len(fynd) == 1
    assert fynd[0].kontroll_id == "K-10"
    assert fynd[0].allvarlighet == "observation"


def test_k10_ger_inget_fynd_for_normal_avgiftsproportion():
    sie = bygg_sie(
        res={"7010": "100000", "7510": "31420"},
        rakenskapsar=("2026-01-01", "2026-12-31"),
    )
    assert kontroll_k10(_kontext(sie)) == []


def test_k10_ger_noll_fynd_utan_lon():
    sie = bygg_sie(res={"7510": "31420"}, rakenskapsar=("2026-01-01", "2026-12-31"))
    assert kontroll_k10(_kontext(sie)) == []


def test_k10_sager_ifran_for_okant_ar():
    """Registret har bara ett procenttal för 2026. Default-räkenskapsåret
    (2025) ska varken gissa på närmaste år ELLER tiga.

    Fail-closed är rätt, men tystnad är fel: noll fynd betyder i alla andra
    kontroller "kontrollerat och inget hittat", och kontrollen skulle då se ut
    att ha godkänt lönekostnaderna utan att ha körts."""
    sie = bygg_sie(res={"7010": "100000", "7510": "50000"})

    fynd = kontroll_k10(_kontext(sie))

    assert len(fynd) == 1
    assert fynd[0].allvarlighet == "upplysning"
    assert "2025" in fynd[0].motivering
    assert "utfördes inte" in fynd[0].motivering


def test_k10_foljer_registret_nar_parametern_andras(tmp_path, monkeypatch):
    """Bevisar B-4: ändras arbetsgivaravgift_procent i registret följer
    kontrollens utfall med, utan att koden ändras."""
    sie = bygg_sie(
        res={"7010": "100000", "7510": "31420"},
        rakenskapsar=("2025-01-01", "2025-12-31"),
    )

    # Med det riktiga registret (som saknar år 2025) blir det en upplysning om
    # att kontrollen inte kunde utföras — inte ett tyst godkännande.
    innan = kontroll_k10(_kontext(sie))
    assert [f.allvarlighet for f in innan] == ["upplysning"]

    trasigt_register = tmp_path / "temporart_register.toml"
    trasigt_register.write_text(
        """
[parametrar]
arbetsgivaravgift_marginal = "0.05"

[parametrar.arbetsgivaravgift_procent]
2025 = "0.5000"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(regelkalla, "_STANDARDSOKVAG", trasigt_register)

    fynd = kontroll_k10(_kontext(sie))
    assert len(fynd) == 1
    # Nu FINNS satsen i registret, så fyndet är den riktiga kontrollen
    # (31,42 % mot registrets 50 %), inte upplysningen om att den uteblev.
    assert fynd[0].allvarlighet == "observation"
