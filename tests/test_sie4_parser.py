from decimal import Decimal
from pathlib import Path

import pytest

from sie4_parser import SIEFil, parse_sie4

SAMPLE = Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"


@pytest.fixture(scope="module")
def sie() -> SIEFil:
    return parse_sie4(SAMPLE)


def test_företagsnamn(sie: SIEFil) -> None:
    assert sie.företagsnamn == "Exempelbolaget Nordvind AB"


def test_konton_inte_tomma(sie: SIEFil) -> None:
    assert len(sie.konton) >= 1


def test_verifikationer_inte_tomma(sie: SIEFil) -> None:
    assert len(sie.verifikationer) >= 1


def test_verifikationer_balanserade(sie: SIEFil) -> None:
    for ver in sie.verifikationer:
        total = sum((t.belopp for t in ver.transaktioner), Decimal(0))
        assert total == Decimal(0), (
            f"Verifikation {ver.serie}/{ver.vernr} är inte balanserad: summa={total}"
        )


def test_svenska_tecken_avkodas_korrekt(sie: SIEFil) -> None:
    # Konto 1060 heter "Hyresrätt" i filen (CP437 byte 0x84 = ä).
    # Med fel encoding (windows-1252) hade samma byte gett „ (U+201E).
    assert sie.konton["1060"].namn == "Hyresrätt"
