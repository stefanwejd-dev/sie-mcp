"""Tests för completeness-kontroll: obligatoriska poster som saknas helt i filen."""
import textwrap
from pathlib import Path

from sie4_parser import SIEFil, parse_sie4


def _parse(tmp_path: Path, content: str) -> SIEFil:
    f = tmp_path / "test.SE"
    f.write_bytes(content.encode("cp437"))
    return parse_sie4(f)


# Komplett fil utom #FNAMN
UTAN_FNAMN = textwrap.dedent("""\
    #FLAGGA 0
    #FORMAT PC8
    #GEN 20250101
    #PROGRAM "TestParser" 1.0
    """)

# Komplett fil utom #FORMAT och #GEN
UTAN_FORMAT_OCH_GEN = textwrap.dedent("""\
    #FLAGGA 0
    #FNAMN "Testbolag AB"
    #PROGRAM "TestParser" 1.0
    """)

# Alla fem obligatoriska etiketter förekommer, men #GEN har ogiltigt datum
TRASIG_GEN_MEN_FOREKOM = textwrap.dedent("""\
    #FLAGGA 0
    #FORMAT PC8
    #GEN OGILTIGT
    #PROGRAM "TestParser" 1.0
    #FNAMN "Testbolag AB"
    """)


def test_saknad_fnamn_ger_filnivå_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, UTAN_FNAMN)

    fnamn_tb = [
        tb for tb in sie.tolkningsbehov
        if tb.etikett == "#FNAMN" and tb.radnummer == 0
    ]
    assert len(fnamn_tb) == 1, (
        f"Saknad #FNAMN ska ge exakt 1 filnivå-tolkningsbehov (radnummer=0), "
        f"fick: {[tb for tb in sie.tolkningsbehov if tb.etikett == '#FNAMN']}"
    )
    assert "saknas" in fnamn_tb[0].anledning.lower(), (
        f"Anledning ska beskriva att posten saknas: {fnamn_tb[0].anledning!r}"
    )


def test_saknade_format_och_gen_ger_två_filnivå_tolkningsbehov(tmp_path: Path) -> None:
    sie = _parse(tmp_path, UTAN_FORMAT_OCH_GEN)

    filnivå_tb = [tb for tb in sie.tolkningsbehov if tb.radnummer == 0]
    saknade_etiketter = {tb.etikett for tb in filnivå_tb}

    assert "#FORMAT" in saknade_etiketter, (
        f"Saknad #FORMAT ska ge filnivå-tolkningsbehov. Filnivåposter: {filnivå_tb}"
    )
    assert "#GEN" in saknade_etiketter, (
        f"Saknad #GEN ska ge filnivå-tolkningsbehov. Filnivåposter: {filnivå_tb}"
    )


def test_trasig_gen_men_förekom_ger_ett_tolkningsbehov_inte_två(tmp_path: Path) -> None:
    sie = _parse(tmp_path, TRASIG_GEN_MEN_FOREKOM)

    gen_tb = [tb for tb in sie.tolkningsbehov if tb.etikett == "#GEN"]
    assert len(gen_tb) == 1, (
        f"Trasig men förekommande #GEN ska ge exakt 1 tolkningsbehov (radfel), "
        f"inte 2 (radfel + filnivå). Fick {len(gen_tb)}: {gen_tb}"
    )
    assert gen_tb[0].radnummer != 0, (
        f"Tolkningsbehovet ska vara ett radfel (radnummer > 0), "
        f"inte ett filnivåfel (radnummer=0). Fick radnummer={gen_tb[0].radnummer}"
    )
