"""Tests för Fas C: #IB, #UB, #RES, #OIB, #OUB, #PSALDO, #PBUDGET."""
from decimal import Decimal
from pathlib import Path

from sie4_parser import Periodsaldo, Saldopost, SIEFil, parse_sie4


def _parse(tmp_path: Path, content: str) -> SIEFil:
    f = tmp_path / "test.SE"
    f.write_bytes(content.encode("cp437"))
    return parse_sie4(f)


# ---------------------------------------------------------------------------
# #IB
# ---------------------------------------------------------------------------

def test_ib_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#IB 0 1910 1000.00\n")
    assert len(sie.ingående_balanser) == 1
    sp = sie.ingående_balanser[0]
    assert isinstance(sp, Saldopost)
    assert sp.årsnr == 0
    assert sp.kontonr == "1910"
    assert sp.saldo == Decimal("1000.00")
    assert sp.objektreferenser == {}
    assert sp.kvantitet is None


def test_ib_ogiltigt_arsnr_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#IB OGILTIGT 1910 1000.00\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#IB"]
    assert tb
    assert not sie.ingående_balanser


# ---------------------------------------------------------------------------
# #UB
# ---------------------------------------------------------------------------

def test_ub_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#UB 0 1910 500.00\n")
    assert len(sie.utgående_balanser) == 1
    assert sie.utgående_balanser[0].saldo == Decimal("500.00")


def test_ub_ogiltigt_saldo_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#UB 0 1910 OGILTIGT\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#UB"]
    assert tb
    assert not sie.utgående_balanser


# ---------------------------------------------------------------------------
# #RES
# ---------------------------------------------------------------------------

def test_res_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#RES 0 3000 -50000.00\n")
    assert len(sie.resultat) == 1
    assert sie.resultat[0].saldo == Decimal("-50000.00")


def test_res_saknar_saldo_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#RES 0 3000\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#RES"]
    assert tb
    assert not sie.resultat


# ---------------------------------------------------------------------------
# #OIB
# ---------------------------------------------------------------------------

def test_oib_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OIB 0 1910 {6 P001} 500.00\n")
    assert len(sie.objekt_ingående_balanser) == 1
    sp = sie.objekt_ingående_balanser[0]
    assert isinstance(sp, Saldopost)
    assert sp.objektreferenser == {6: "P001"}
    assert sp.saldo == Decimal("500.00")


def test_oib_ogiltigt_saldo_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OIB 0 1910 {6 P001} OGILTIGT\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#OIB"]
    assert tb
    assert not sie.objekt_ingående_balanser


# ---------------------------------------------------------------------------
# #OUB
# ---------------------------------------------------------------------------

def test_oub_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OUB 0 1910 {6 P001} 200.00\n")
    assert len(sie.objekt_utgående_balanser) == 1
    assert sie.objekt_utgående_balanser[0].saldo == Decimal("200.00")


def test_oub_saknar_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OUB 0\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#OUB"]
    assert tb
    assert not sie.objekt_utgående_balanser


# ---------------------------------------------------------------------------
# #PSALDO
# ---------------------------------------------------------------------------

def test_psaldo_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#PSALDO 0 202501 1910 {} 100.00\n")
    assert len(sie.periodsaldon) == 1
    ps = sie.periodsaldon[0]
    assert isinstance(ps, Periodsaldo)
    assert ps.period == "202501"
    assert ps.kontonr == "1910"
    assert ps.saldo == Decimal("100.00")
    assert ps.objektreferenser == {}


def test_psaldo_saknar_saldo_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#PSALDO 0 202501 1910 {}\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#PSALDO"]
    assert tb
    assert not sie.periodsaldon


# ---------------------------------------------------------------------------
# #PBUDGET
# ---------------------------------------------------------------------------

def test_pbudget_lagras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#PBUDGET 0 202501 1910 {} 9000.00\n")
    assert len(sie.periodbudgetar) == 1
    ps = sie.periodbudgetar[0]
    assert isinstance(ps, Periodsaldo)
    assert ps.saldo == Decimal("9000.00")


def test_pbudget_ogiltigt_saldo_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#PBUDGET 0 202501 1910 {} OGILTIGT\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#PBUDGET"]
    assert tb
    assert not sie.periodbudgetar


# ---------------------------------------------------------------------------
# Specifika kantfall
# ---------------------------------------------------------------------------

def test_oib_utan_klammerprefix_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OIB 0 1910 INGEN_KLAMMER 500.00\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#OIB"]
    assert tb, "Objektlistefält utan {-prefix ska ge tolkningsbehov"
    assert "objektlista" in tb[0].anledning.lower()
    assert not sie.objekt_ingående_balanser


def test_psaldo_ogiltig_manad_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#PSALDO 0 202613 1910 {} 100.00\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#PSALDO"]
    assert tb, "Ogiltig månad (13) i period ska ge tolkningsbehov"
    assert "period" in tb[0].anledning.lower()
    assert not sie.periodsaldon


def test_ib_negativt_arsnr_tolkas_korrekt(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#IB -1 1910 1000.00\n")
    assert not any(t.etikett == "#IB" for t in sie.tolkningsbehov)
    assert len(sie.ingående_balanser) == 1
    assert sie.ingående_balanser[0].årsnr == -1
