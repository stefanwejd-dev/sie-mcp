"""Tests för A2: #RAR, #OMFATTN, #ADRESS, #ORGNR samt uppdaterad datamodell."""
from datetime import date
from pathlib import Path

from sie4_parser import Adress, Räkenskapsår, SIEFil, parse_sie4


def _parse(tmp_path: Path, content: str) -> SIEFil:
    f = tmp_path / "test.SE"
    f.write_bytes(content.encode("cp437"))
    return parse_sie4(f)


# ---------------------------------------------------------------------------
# #RAR
# ---------------------------------------------------------------------------

def test_rar_sätts_korrekt(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#RAR 0 20250101 20251231\n")
    assert 0 in sie.räkenskapsår
    rar = sie.räkenskapsår[0]
    assert isinstance(rar, Räkenskapsår)
    assert rar.årsnr == 0
    assert rar.start == date(2025, 1, 1)
    assert rar.slut == date(2025, 12, 31)


def test_rar_negativt_arsnr_fungerar(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#RAR -1 20240101 20241231\n")
    assert -1 in sie.räkenskapsår
    assert sie.räkenskapsår[-1].start == date(2024, 1, 1)


def test_rar_ogiltigt_datum_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#RAR 0 OGILTIGT 20251231\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#RAR"]
    assert tb, "Ogiltigt startdatum i #RAR ska ge tolkningsbehov"
    assert 0 not in sie.räkenskapsår, "Felaktigt #RAR ska inte lagras"


# ---------------------------------------------------------------------------
# #OMFATTN
# ---------------------------------------------------------------------------

def test_omfattn_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OMFATTN 20250601\n")
    assert sie.omfattning == date(2025, 6, 1)


def test_omfattn_ogiltigt_datum_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#OMFATTN FELDAT\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#OMFATTN"]
    assert tb, "Ogiltigt #OMFATTN-datum ska ge tolkningsbehov"
    assert sie.omfattning is None


# ---------------------------------------------------------------------------
# #ADRESS  (fyra positionella frivilliga fält, ingen valideringsgren)
# ---------------------------------------------------------------------------

def test_adress_sätts(tmp_path: Path) -> None:
    sie = _parse(
        tmp_path,
        '#ADRESS "Kalle Svensson" "Box 1" "12345 Stockholm" "08-123456"\n',
    )
    assert isinstance(sie.adress, Adress)
    assert sie.adress.kontakt == "Kalle Svensson"
    assert sie.adress.utdelningsadress == "Box 1"
    assert sie.adress.postadress == "12345 Stockholm"
    assert sie.adress.telefon == "08-123456"


# ---------------------------------------------------------------------------
# #ORGNR
# ---------------------------------------------------------------------------

def test_orgnr_alla_tre_fält(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#ORGNR 556677-1234 5 7\n")
    assert sie.orgnr == "556677-1234"
    assert sie.förvaltningsnummer == "5"
    assert sie.verksamhetsnummer == "7"
    assert not any(tb.etikett == "#ORGNR" for tb in sie.tolkningsbehov), (
        "Entydigt 3-fälts #ORGNR ska inte ge tolkningsbehov"
    )


def test_orgnr_bara_orgnr(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#ORGNR 556677-1234\n")
    assert sie.orgnr == "556677-1234"
    assert sie.förvaltningsnummer is None
    assert sie.verksamhetsnummer is None
    assert not any(tb.etikett == "#ORGNR" for tb in sie.tolkningsbehov), (
        "Enbart orgnr ska inte ge tolkningsbehov"
    )


def test_orgnr_tvetydig_tvåfält_ger_tolkningsbehov_och_gissar(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#ORGNR 556677-1234 5\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#ORGNR"]
    assert tb, "Tvetydig 2-fälts #ORGNR ska ge tolkningsbehov"
    assert tb[0].partiell_tolkning is not None
    assert "556677-1234" in tb[0].partiell_tolkning
    assert "5" in tb[0].partiell_tolkning
    # Gissningen: fält 2 tolkas som förvaltningsnummer
    assert sie.orgnr == "556677-1234"
    assert sie.förvaltningsnummer == "5"
    assert sie.verksamhetsnummer is None


def test_orgnr_utan_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#ORGNR\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#ORGNR"]
    assert tb, "Helt saknat orgnr ska ge tolkningsbehov"
    assert sie.orgnr is None


def test_orgnr_explicit_platshållare_i_fält1_är_entydigt(tmp_path: Path) -> None:
    # #ORGNR "" 02 — fält 1 är explicit "" (platshållare för orgnr),
    # fält 2 är per definition förvaltningsnummer. Ingen gissning, ingen flaggning.
    sie = _parse(tmp_path, '#ORGNR "" 02\n')
    assert sie.orgnr == ""
    assert sie.förvaltningsnummer == "02"
    assert sie.verksamhetsnummer is None
    assert not any(tb.etikett == "#ORGNR" for tb in sie.tolkningsbehov), (
        "Entydigt 2-fälts #ORGNR med platshållare i fält 1 ska inte ge tolkningsbehov"
    )
