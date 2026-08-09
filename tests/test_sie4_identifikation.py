"""Tests för identifikationsposters tolkning och validering."""
from datetime import date
from pathlib import Path

from sie4_parser import SIEFil, parse_sie4


def _parse(tmp_path: Path, content: str) -> SIEFil:
    f = tmp_path / "test.SE"
    f.write_bytes(content.encode("cp437"))
    return parse_sie4(f)


# ---------------------------------------------------------------------------
# #FORMAT
# ---------------------------------------------------------------------------

def test_format_giltig_ger_inga_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FORMAT PC8\n")
    assert not any(tb.etikett == "#FORMAT" for tb in sie.tolkningsbehov)


def test_format_ogiltigt_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FORMAT LATIN1\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#FORMAT"]
    assert tb, "Ogiltigt #FORMAT-värde ska ge tolkningsbehov"
    assert "encoding" in tb[0].anledning.lower() or "okänt" in tb[0].anledning.lower(), (
        f"Anledning ska nämna encoding eller okänt värde: {tb[0].anledning!r}"
    )


# ---------------------------------------------------------------------------
# #PROGRAM
# ---------------------------------------------------------------------------

def test_program_sätts_korrekt(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#PROGRAM "MinApp" 2.1\n')
    assert sie.program == "MinApp"
    assert sie.program_version == "2.1"


def test_program_utan_version_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#PROGRAM MinApp\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#PROGRAM"]
    assert tb, "Ofullständig #PROGRAM-rad (saknar version) ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #GEN
# ---------------------------------------------------------------------------

def test_gen_datum_och_sign_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#GEN 20250101 Stefan\n")
    assert sie.genererad == date(2025, 1, 1)
    assert sie.genererad_sign == "Stefan"


def test_gen_ogiltigt_datum_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#GEN OGILTIGT\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#GEN"]
    assert tb, "Ogiltigt #GEN-datum ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #SIETYP
# ---------------------------------------------------------------------------

def test_sietyp_sätts_som_int(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#SIETYP 4\n")
    assert sie.sietyp == 4


def test_sietyp_utanför_intervall_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#SIETYP 9\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#SIETYP"]
    assert tb, "#SIETYP 9 ska ge tolkningsbehov (inte i intervall 1–4)"


# ---------------------------------------------------------------------------
# #FLAGGA
# ---------------------------------------------------------------------------

def test_flagga_sätts_korrekt(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FLAGGA 1\n")
    assert sie.flagga == 1


def test_flagga_ogiltigt_värde_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FLAGGA 2\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#FLAGGA"]
    assert tb, "#FLAGGA 2 ska ge tolkningsbehov (inte 0 eller 1)"


# ---------------------------------------------------------------------------
# #FTYP, #FNR, #BKOD, #TAXAR  (enkelt textfält — om saknas: flagga)
# ---------------------------------------------------------------------------

def test_ftyp_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FTYP AB\n")
    assert sie.företagstyp == "AB"


def test_ftyp_utan_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FTYP\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#FTYP"]
    assert tb, "Saknat #FTYP-fält ska ge tolkningsbehov"


def test_fnr_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FNR 12345\n")
    assert sie.företagsid == "12345"


def test_fnr_utan_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#FNR\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#FNR"]
    assert tb, "Saknat #FNR-fält ska ge tolkningsbehov"


def test_bkod_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#BKOD 62010\n")
    assert sie.sni_kod == "62010"


def test_bkod_utan_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#BKOD\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#BKOD"]
    assert tb, "Saknat #BKOD-fält ska ge tolkningsbehov"


def test_taxar_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#TAXAR 2025\n")
    assert sie.taxeringsår == "2025"


def test_taxar_utan_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#TAXAR\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#TAXAR"]
    assert tb, "Saknat #TAXAR-fält ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #KPTYP
# ---------------------------------------------------------------------------

def test_kptyp_sätts_korrekt(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KPTYP BAS96\n")
    assert sie.kontoplanstyp == "BAS96"


def test_kptyp_ogiltigt_värde_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KPTYP OKANT\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KPTYP"]
    assert tb, "Ogiltigt #KPTYP-värde ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #VALUTA
# ---------------------------------------------------------------------------

def test_valuta_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#VALUTA EUR\n")
    assert sie.valuta == "EUR"


def test_valuta_utan_fält_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#VALUTA\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#VALUTA"]
    assert tb, "Saknat #VALUTA-fält ska ge tolkningsbehov"


# ---------------------------------------------------------------------------
# #PROSA  (fritext — ingen valideringsgren)
# ---------------------------------------------------------------------------

def test_prosa_sätts(tmp_path: Path) -> None:
    sie = _parse(tmp_path, '#PROSA "Fri text om bolaget"\n')
    assert sie.prosa == "Fri text om bolaget"
