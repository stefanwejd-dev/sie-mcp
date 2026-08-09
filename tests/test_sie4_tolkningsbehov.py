import textwrap
from pathlib import Path

import pytest

from sie4_parser import SIEFil, parse_sie4

# Minimal syntetisk SIE4-fil där #VER har ett ogiltigt verdatum.
# Radnumren nedan är 1-baserade och måste stämma med innehållet.
SYNTETISK_SIE4 = textwrap.dedent("""\
    #FLAGGA 0
    #FORMAT PC8
    #SIETYP 4
    #PROGRAM "TestParser" 1.0
    #GEN 20250101
    #FNAMN "Testbolag AB"
    #VER A 1 OGILTIGT "Kaffe"
    {
    #TRANS 1910 {} -100.00
    #TRANS 6250 {} 100.00
    }
    """)

_VER_RAD = 7   # #VER-raden i snutten ovan (1-baserat)
_TRANS_RADER = {9, 10}


def test_trasig_ver_hamnar_inte_i_verifikationer(tmp_path: Path) -> None:
    sie_fil = tmp_path / "trasig.SE"
    sie_fil.write_bytes(SYNTETISK_SIE4.encode("cp437"))

    sie: SIEFil = parse_sie4(sie_fil)

    assert sie.verifikationer == [], (
        "En #VER med ogiltigt verdatum ska aldrig läggas till i verifikationer"
    )


def test_trasig_ver_ger_minst_tre_tolkningsbehov(tmp_path: Path) -> None:
    sie_fil = tmp_path / "trasig.SE"
    sie_fil.write_bytes(SYNTETISK_SIE4.encode("cp437"))

    sie: SIEFil = parse_sie4(sie_fil)

    assert len(sie.tolkningsbehov) >= 3, (
        f"Förväntar minst 3 tolkningsbehov (#VER + 2 × #TRANS), "
        f"fick {len(sie.tolkningsbehov)}: {sie.tolkningsbehov}"
    )


# ---------------------------------------------------------------------------
# Scenario 2: #TRANS utanför ett {}-block
# ---------------------------------------------------------------------------

TRANS_UTAN_BLOCK = textwrap.dedent("""\
    #FLAGGA 0
    #FORMAT PC8
    #SIETYP 4
    #PROGRAM "TestParser" 1.0
    #GEN 20250101
    #FNAMN "Testbolag AB"
    #TRANS 1910 {} -100.00
    """)

_TRANS_UTAN_BLOCK_RAD = 7  # #TRANS-raden ovan


def test_trans_utan_block_hamnar_i_tolkningsbehov(tmp_path: Path) -> None:
    sie_fil = tmp_path / "trans_utan_block.SE"
    sie_fil.write_bytes(TRANS_UTAN_BLOCK.encode("cp437"))

    sie: SIEFil = parse_sie4(sie_fil)

    stray = [
        tb for tb in sie.tolkningsbehov
        if tb.radnummer == _TRANS_UTAN_BLOCK_RAD
    ]
    assert stray, (
        f"#TRANS på rad {_TRANS_UTAN_BLOCK_RAD} ska finnas i tolkningsbehov, "
        f"men tolkningsbehov är: {sie.tolkningsbehov}"
    )
    assert any("utanför" in tb.anledning for tb in stray), (
        f"Anledningen ska nämna att raden är utanför ett block, "
        f"fick: {[tb.anledning for tb in stray]}"
    )


# ---------------------------------------------------------------------------
# Scenario 3: VER1 aldrig stängd med } när VER2 börjar
# ---------------------------------------------------------------------------

OSTANGD_VER = textwrap.dedent("""\
    #FLAGGA 0
    #FORMAT PC8
    #SIETYP 4
    #PROGRAM "TestParser" 1.0
    #GEN 20250101
    #FNAMN "Testbolag AB"
    #VER A 1 20250101 "VER1"
    {
    #TRANS 1910 {} -100.00
    #VER A 2 20250102 "VER2"
    {
    #TRANS 1910 {} -200.00
    #TRANS 2640 {} 200.00
    }
    """)

_VER1_RAD = 7
_VER1_TRANS_RAD = 9
_VER1_TRANS_RÅTEXT = "#TRANS 1910 {} -100.00"
_VER2_VERNR = "2"


def test_ostangd_ver_hamnar_inte_i_verifikationer(tmp_path: Path) -> None:
    sie_fil = tmp_path / "ostangd.SE"
    sie_fil.write_bytes(OSTANGD_VER.encode("cp437"))
    sie: SIEFil = parse_sie4(sie_fil)

    assert len(sie.verifikationer) == 1, (
        f"Bara VER2 ska finnas i verifikationer, fick: {sie.verifikationer}"
    )
    assert sie.verifikationer[0].vernr == _VER2_VERNR


def test_ostangd_ver_header_i_tolkningsbehov(tmp_path: Path) -> None:
    sie_fil = tmp_path / "ostangd.SE"
    sie_fil.write_bytes(OSTANGD_VER.encode("cp437"))
    sie: SIEFil = parse_sie4(sie_fil)

    ver1_tb = [
        tb for tb in sie.tolkningsbehov
        if tb.radnummer == _VER1_RAD and tb.etikett == "#VER"
    ]
    assert ver1_tb, f"Ingen tolkningsbehov för VER1 på rad {_VER1_RAD}"
    anledning = ver1_tb[0].anledning.lower()
    assert "aldrig" in anledning or "avslutad" in anledning, (
        f"Anledningen ska beskriva att verifikationen aldrig stängdes: {ver1_tb[0].anledning!r}"
    )


def test_ostangd_ver_trans_i_tolkningsbehov_med_kontext_och_partiell(tmp_path: Path) -> None:
    sie_fil = tmp_path / "ostangd.SE"
    sie_fil.write_bytes(OSTANGD_VER.encode("cp437"))
    sie: SIEFil = parse_sie4(sie_fil)

    trans_tb = [tb for tb in sie.tolkningsbehov if tb.radnummer == _VER1_TRANS_RAD]
    assert trans_tb, f"Ingen tolkningsbehov för TRANS på rad {_VER1_TRANS_RAD}"
    tb = trans_tb[0]

    assert str(_VER1_RAD) in (tb.kontext or ""), (
        f"kontext ska referera till VER1:s radnummer ({_VER1_RAD}): {tb.kontext!r}"
    )
    assert tb.råtext == _VER1_TRANS_RÅTEXT, (
        f"råtext ska vara den omodifierade originalraden: {tb.råtext!r}"
    )
    assert tb.partiell_tolkning is not None, "partiell_tolkning ska vara satt"
    assert "1910" in tb.partiell_tolkning, (
        f"partiell_tolkning ska nämna kontonr: {tb.partiell_tolkning!r}"
    )
    assert "-100.00" in tb.partiell_tolkning, (
        f"partiell_tolkning ska nämna belopp: {tb.partiell_tolkning!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 4: filen tar slut (EOF) utan avslutande } — ingen ny #VER efteråt
# ---------------------------------------------------------------------------

EOF_VER = textwrap.dedent("""\
    #FLAGGA 0
    #FORMAT PC8
    #SIETYP 4
    #PROGRAM "TestParser" 1.0
    #GEN 20250101
    #FNAMN "Testbolag AB"
    #VER A 1 20250101 "VER1"
    {
    #TRANS 1910 {} -100.00
    """)

_EOF_VER_RAD = 7
_EOF_TRANS_RAD = 9


def test_eof_ver_hamnar_inte_i_verifikationer(tmp_path: Path) -> None:
    sie_fil = tmp_path / "eof_ver.SE"
    sie_fil.write_bytes(EOF_VER.encode("cp437"))
    sie: SIEFil = parse_sie4(sie_fil)

    assert sie.verifikationer == [], (
        f"Oavslutad verifikation vid EOF ska inte finnas i verifikationer, fick: {sie.verifikationer}"
    )


def test_eof_ver_header_i_tolkningsbehov(tmp_path: Path) -> None:
    sie_fil = tmp_path / "eof_ver.SE"
    sie_fil.write_bytes(EOF_VER.encode("cp437"))
    sie: SIEFil = parse_sie4(sie_fil)

    ver_tb = [
        tb for tb in sie.tolkningsbehov
        if tb.radnummer == _EOF_VER_RAD and tb.etikett == "#VER"
    ]
    assert ver_tb, f"Ingen tolkningsbehov för #VER-headern på rad {_EOF_VER_RAD}"
    anledning = ver_tb[0].anledning.lower()
    assert "ny #ver" not in anledning, (
        f"Anledningen ska inte nämna 'ny #VER' vid EOF: {ver_tb[0].anledning!r}"
    )
    assert "fil" in anledning or "slut" in anledning or "eof" in anledning, (
        f"Anledningen ska beskriva att filen tog slut: {ver_tb[0].anledning!r}"
    )


def test_eof_ver_trans_i_tolkningsbehov(tmp_path: Path) -> None:
    sie_fil = tmp_path / "eof_ver.SE"
    sie_fil.write_bytes(EOF_VER.encode("cp437"))
    sie: SIEFil = parse_sie4(sie_fil)

    trans_tb = [tb for tb in sie.tolkningsbehov if tb.radnummer == _EOF_TRANS_RAD]
    assert trans_tb, (
        f"Ingen tolkningsbehov för #TRANS på rad {_EOF_TRANS_RAD}, "
        f"tolkningsbehov: {sie.tolkningsbehov}"
    )


# ---------------------------------------------------------------------------


def test_trans_i_brutet_block_har_kontext_med_ver_radnummer(tmp_path: Path) -> None:
    sie_fil = tmp_path / "trasig.SE"
    sie_fil.write_bytes(SYNTETISK_SIE4.encode("cp437"))

    sie: SIEFil = parse_sie4(sie_fil)

    trans_med_kontext = [
        tb for tb in sie.tolkningsbehov
        if tb.etikett in ("#TRANS", "#RTRANS", "#BTRANS")
        and str(_VER_RAD) in (tb.kontext or "")
    ]
    assert trans_med_kontext, (
        f"Minst en #TRANS i tolkningsbehov ska ha kontext som nämner "
        f"#VER-radens radnummer ({_VER_RAD}). "
        f"Tolkningsbehov: {sie.tolkningsbehov}"
    )
