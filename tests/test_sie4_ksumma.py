"""Tests för #KSUMMA — registrering och trunkeringsdetektering (Alternativ C)."""
from pathlib import Path

from sie4_parser import SIEFil, parse_sie4


def _parse(tmp_path: Path, content: str) -> SIEFil:
    f = tmp_path / "test.SE"
    f.write_bytes(content.encode("cp437"))
    return parse_sie4(f)


def test_ksumma_normalt_par_registreras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KSUMMA\n#KSUMMA 123456\n")
    assert sie.ksumma == 123456
    assert not any(t.etikett == "#KSUMMA" for t in sie.tolkningsbehov)


def test_ksumma_oppen_utan_avslut_ger_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KSUMMA\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KSUMMA"]
    assert tb, "Öppning utan avslutande post ska ge tolkningsbehov vid EOF"
    assert "trunkerad" in tb[0].anledning.lower()
    assert sie.ksumma is None


def test_ksumma_dubbel_oeppning_flaggar_foersta(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KSUMMA\n#KSUMMA\n#KSUMMA 99999\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KSUMMA"]
    assert len(tb) == 1, f"Exakt en flagga ska ges (för den första öppningen), fick: {tb}"
    assert sie.ksumma == 99999


def test_ksumma_avslut_utan_foergaende_oeppning_flaggas_men_registreras(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KSUMMA 999\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KSUMMA"]
    assert tb, "Avslutande post utan föregående öppning ska flaggas"
    assert "tvåpost" in tb[0].anledning.lower() or "signal" in tb[0].anledning.lower()
    assert sie.ksumma == 999


def test_ksumma_ogiltigt_vaerde_flaggas(tmp_path: Path) -> None:
    sie = _parse(tmp_path, "#KSUMMA\n#KSUMMA abc\n")
    tb = [t for t in sie.tolkningsbehov if t.etikett == "#KSUMMA"]
    assert tb, "Ogiltigt kontrollsummevärde ska ge tolkningsbehov"
    assert "abc" in tb[0].anledning
    assert sie.ksumma is None
