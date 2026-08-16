"""Lager 1b, steg 5 — test av sökvägsvakt, maskering och .gitignore enligt
hantverksbok/BOKSLUTSPROGRAMMET.md §4.4.

En punkt per test, som specen begär."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import mcp_server.server as server_modul
from mcp_server.server import KONTOUTDRAG_KATALOG_ENV, _tillaten_kontoutdrag

from avstamning.camt053 import Utdrag, Utdragsrad
from avstamning.sekretess import maskera_utdrag

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RÅ_PII = "Anna Andersson"


# --- Sökvägsvakt -------------------------------------------------------


def test_tillaten_kontoutdrag_utan_konfiguration_ger_none(monkeypatch, tmp_path):
    monkeypatch.delenv(KONTOUTDRAG_KATALOG_ENV, raising=False)
    fil = tmp_path / "utdrag.xml"
    fil.write_text("data", encoding="utf-8")
    assert _tillaten_kontoutdrag(str(fil)) is None


def test_tillaten_kontoutdrag_tillater_fil_i_konfigurerad_katalog(monkeypatch, tmp_path):
    monkeypatch.setenv(KONTOUTDRAG_KATALOG_ENV, str(tmp_path))
    fil = tmp_path / "utdrag.xml"
    fil.write_text("data", encoding="utf-8")
    assert _tillaten_kontoutdrag(str(fil)) == fil.resolve()


def test_tillaten_kontoutdrag_avvisar_fil_utanfor_katalogen(monkeypatch, tmp_path):
    tillaten_dir = tmp_path / "tillaten"
    tillaten_dir.mkdir()
    utanfor_dir = tmp_path / "utanfor"
    utanfor_dir.mkdir()
    fil = utanfor_dir / "utdrag.xml"
    fil.write_text("data", encoding="utf-8")

    monkeypatch.setenv(KONTOUTDRAG_KATALOG_ENV, str(tillaten_dir))
    assert _tillaten_kontoutdrag(str(fil)) is None


def test_tillaten_kontoutdrag_avvisar_saknad_fil(monkeypatch, tmp_path):
    monkeypatch.setenv(KONTOUTDRAG_KATALOG_ENV, str(tmp_path))
    assert _tillaten_kontoutdrag(str(tmp_path / "finns_inte.xml")) is None


def test_tillaten_kontoutdrag_har_en_egen_miljovariabel_skild_fran_sie():
    """§4.4: en EGEN miljövariabel, inte SIE-filernas."""
    assert KONTOUTDRAG_KATALOG_ENV != server_modul.SIE_KATALOG_ENV
    assert KONTOUTDRAG_KATALOG_ENV == "SIE_MCP_KONTOUTDRAG_KATALOG"


# --- Maskering -----------------------------------------------------------


def _utdrag(rader):
    return Utdrag(
        kontonr="1930", period_start=None, period_slut=None,
        ingaende_saldo=None, utgaende_saldo=None, rader=tuple(rader),
    )


def test_maskera_utdrag_maskerar_kant_namn_i_text_och_motpart():
    utdrag = _utdrag([
        Utdragsrad(
            datum=date(2026, 6, 5), belopp=Decimal("1000"),
            text=f"Betalning från {_RÅ_PII}", motpart=_RÅ_PII,
        )
    ])
    resultat = maskera_utdrag(utdrag, referenslista={_RÅ_PII})

    rad = resultat.maskerat_utdrag.rader[0]
    assert _RÅ_PII not in rad.text
    assert _RÅ_PII not in rad.motpart
    assert "PERSON_" in rad.text
    assert "PERSON_" in rad.motpart


def test_maskera_utdrag_lamnar_belopp_datum_referens_kontonr_ororda():
    utdrag = Utdrag(
        kontonr="1930", period_start=None, period_slut=None,
        ingaende_saldo=None, utgaende_saldo=None,
        rader=(
            Utdragsrad(
                datum=date(2026, 6, 5), belopp=Decimal("1000.50"),
                text=f"Från {_RÅ_PII}", motpart=None, referens="REF-42",
            ),
        ),
    )
    resultat = maskera_utdrag(utdrag, referenslista={_RÅ_PII})
    rad = resultat.maskerat_utdrag.rader[0]

    assert rad.datum == date(2026, 6, 5)
    assert rad.belopp == Decimal("1000.50")
    assert rad.referens == "REF-42"
    assert resultat.maskerat_utdrag.kontonr == "1930"


def test_maskera_utdrag_flaggar_okant_namn_och_utesluter_raden():
    """Fail-closed: en rad med ett olöst maskeringsbehov (ett namn ingen
    referenslista känner till) ska INTE hamna i sandningsbara_rader —
    samma princip som blockerade_verifikationer i sekretesslager.py."""
    utdrag = _utdrag([
        Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"), motpart="Berit Kvist"),
        Utdragsrad(datum=date(2026, 6, 6), belopp=Decimal("500"), text="Ren rad utan namn"),
    ])
    resultat = maskera_utdrag(utdrag)  # ingen referenslista — flaggas i stället för auto-maskeras

    assert resultat.maskeringsbehov  # minst ett olöst behov
    assert len(resultat.sandningsbara_rader) == 1
    assert resultat.sandningsbara_rader[0].belopp == Decimal("500")


def test_maskera_utdrag_undantagslista_forhindrar_ny_flaggning():
    utdrag = _utdrag([
        Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"), motpart="Danske Disks"),
    ])
    resultat = maskera_utdrag(utdrag, undantagslista={"Danske Disks"})
    assert resultat.maskeringsbehov == []
    assert len(resultat.sandningsbara_rader) == 1


def test_maskera_utdrag_rad_utan_fritext_ar_alltid_sandningsbar():
    utdrag = _utdrag([Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"))])
    resultat = maskera_utdrag(utdrag)
    assert resultat.maskeringsbehov == []
    assert len(resultat.sandningsbara_rader) == 1


def test_maskera_utdrag_tomt_utdrag_ger_tomt_resultat():
    resultat = maskera_utdrag(_utdrag([]))
    assert resultat.maskerat_utdrag.rader == ()
    assert resultat.sandningsbara_rader == ()
    assert resultat.maskeringsbehov == []


def test_maskera_utdrag_platser_ar_unika_per_rad():
    utdrag = _utdrag([
        Utdragsrad(datum=date(2026, 6, 5), belopp=Decimal("1000"), motpart="Berit Kvist"),
        Utdragsrad(datum=date(2026, 6, 6), belopp=Decimal("500"), motpart="Cornelis Nilsson"),
    ])
    resultat = maskera_utdrag(utdrag)
    platser = {b.plats for b in resultat.maskeringsbehov}
    assert platser == {"kontoutdragsrad=0", "kontoutdragsrad=1"}
    assert resultat.sandningsbara_rader == ()


# --- .gitignore ------------------------------------------------------------


def test_gitignore_utokad_med_kontoutdragsformat():
    """§4.4: '.gitignore utökas med de format som kan innehålla utdrag.'
    *.csv fanns redan (bredare skydd, se filens egen kommentar); *.xml
    (camt.053) är den nya raden."""
    innehall = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    rader = {rad.strip() for rad in innehall.splitlines()}
    assert "*.csv" in rader
    assert "*.xml" in rader
