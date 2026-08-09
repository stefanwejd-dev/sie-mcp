"""Tests för Fas B: #KTYP, #ENHET, #SRU, #DIM, #UNDERDIM, #OBJEKT och uppdaterad datamodell."""
from pathlib import Path

from sie4_parser import Dimension, Objekt, SIEFil, parse_sie4


def _parse(tmp_path: Path, content: str) -> SIEFil:
    f = tmp_path / "test.SE"
    f.write_bytes(content.encode("cp437"))
    return parse_sie4(f)


# ---------------------------------------------------------------------------
# #KTYP
# ---------------------------------------------------------------------------

def test_ktyp_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#KONTO 1910 "Kassa"\n#KTYP 1910 T\n')
    assert sie.konton["1910"].typ == "T"


def test_ktyp_ogiltig_typ_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#KONTO 1910 "Kassa"\n#KTYP 1910 X\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KTYP"]
    assert tb, "Ogiltig typ ska ge tolkningsbehov"
    assert sie.konton["1910"].typ is None, "Felaktig typ ska inte lagras"


def test_ktyp_okänt_konto_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KTYP 9999 T\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KTYP"]
    assert tb, "Okänt kontonummer ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #ENHET
# ---------------------------------------------------------------------------

def test_enhet_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#KONTO 1910 "Kassa"\n#ENHET 1910 kr\n')
    assert sie.konton["1910"].enhet == "kr"


def test_enhet_saknar_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#KONTO 1910 "Kassa"\n#ENHET 1910\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#ENHET"]
    assert tb, "Saknat enhet-fält ska ge tolkningsbehov"
    assert sie.konton["1910"].enhet is None


def test_enhet_okänt_konto_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#ENHET 9999 kr\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#ENHET"]
    assert tb, "Okänt kontonummer ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #SRU
# ---------------------------------------------------------------------------

def test_sru_läggs_till(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#KONTO 1910 "Kassa"\n#SRU 1910 7214\n')
    assert "7214" in sie.konton["1910"].sru_koder


def test_sru_saknar_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#KONTO 1910 "Kassa"\n#SRU 1910\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#SRU"]
    assert tb, "Saknad SRU-kod ska ge tolkningsbehov"
    assert sie.konton["1910"].sru_koder == []


def test_sru_okänt_konto_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#SRU 9999 7214\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#SRU"]
    assert tb, "Okänt kontonummer ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #DIM
# ---------------------------------------------------------------------------

def test_dim_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#DIM 6 "Projekt"\n')
    assert 6 in sie.dimensioner
    dim = sie.dimensioner[6]
    assert isinstance(dim, Dimension)
    assert dim.namn == "Projekt"
    assert dim.superdimension is None


def test_dim_ogiltigt_dimensionsnr_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#DIM X "Projekt"\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#DIM"]
    assert tb, "Ogiltigt dimensionsnr ska ge tolkningsbehov"
    assert not sie.dimensioner


# ---------------------------------------------------------------------------
# #UNDERDIM
# ---------------------------------------------------------------------------

def test_underdim_sätts_med_superdimension(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#UNDERDIM 2 "Kostnadsbärare" 1\n')
    assert 2 in sie.dimensioner
    dim = sie.dimensioner[2]
    assert isinstance(dim, Dimension)
    assert dim.namn == "Kostnadsbärare"
    assert dim.superdimension == 1


def test_underdim_ogiltigt_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#UNDERDIM X "Kostnadsbärare" 1\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#UNDERDIM"]
    assert tb, "Ogiltigt dimensionsnr ska ge tolkningsbehov"
    assert not sie.dimensioner


# ---------------------------------------------------------------------------
# #OBJEKT
# ---------------------------------------------------------------------------

def test_objekt_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#OBJEKT 6 P001 "Projekt A"\n')
    assert (6, "P001") in sie.objektregister
    obj = sie.objektregister[(6, "P001")]
    assert isinstance(obj, Objekt)
    assert obj.dimensionsnr == 6
    assert obj.objektnr == "P001"
    assert obj.namn == "Projekt A"


def test_objekt_ogiltigt_dimensionsnr_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#OBJEKT X P001 "Projekt A"\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#OBJEKT"]
    assert tb, "Ogiltigt dimensionsnr ska ge tolkningsbehov"
    assert not sie.objektregister


# ---------------------------------------------------------------------------
# Rättelser Fas B
# ---------------------------------------------------------------------------

def test_underdim_ogiltigt_superdimensionsnr_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#UNDERDIM 6 "Avdelning" XYZ\n')
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#UNDERDIM"]
    assert tb, "Ogiltigt superdimensionsnr ska ge tolkningsbehov"
    assert "XYZ" in tb[0].anledning, "Anledningen ska nämna det ogiltiga värdet"
    assert not sie.dimensioner, "Ingen Dimension ska skapas vid ogiltigt superdimensionsnr"


def test_konto_utan_namn_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KONTO 1910\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KONTO"]
    assert tb, "Saknat kontonamn ska ge tolkningsbehov"
    assert "1910" not in sie.konton, "Ofullständigt konto ska inte lagras"
