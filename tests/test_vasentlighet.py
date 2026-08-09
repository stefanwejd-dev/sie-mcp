"""
Testfallsskelett — Modul 1: Väsentlighetsberäkning

STATUS: Röd fas (TDD). Dessa tester är avsiktligt skrivna innan
implementationen finns. `berakna_vasentlighet` och `Vasentlighetstal`
existerar ännu inte — det är nästa steg för Claude Code att bygga,
utifrån ARCHITECTURE_tillagg_vasentlighet.md.

OBS – justera innan körning:
  - Importvägen nedan (`from vasentlighet import ...`) är en platshållare.
    Sätt den till er faktiska modulplacering (t.ex. `parser.vasentlighet`
    om filen läggs i samma katalog som domain_model.py).
  - Sökvägen till exempelfilen antar `samples/SIE4_Exempelfil.SE`
    utifrån er tidigare gitkommando (`git add ... samples/`).
    Justera vid behov.

Facit är manuellt uträknat och verifierat mot filens råa #RES/#UB-rader
i konversationen — se ARCHITECTURE_tillagg_vasentlighet.md för underlaget.
"""

from decimal import Decimal
from pathlib import Path

import pytest

# --- Platshållare: byt till er faktiska modulstruktur ----------------------
from vasentlighet import berakna_vasentlighet, Vasentlighetstal
from sie4_parser import parse_sie4  # byt om er entry-point heter annat
from domain_model import SIEFil, Saldopost
# -----------------------------------------------------------------------

SAMPLE_FIL = Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"


# ---------------------------------------------------------------------------
# Golden-file-tester: facit räknat direkt ur SIE4_Exempelfil.SE (år 0, 2021)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def exempelfil() -> SIEFil:
    return parse_sie4(SAMPLE_FIL)


def test_omsattning_fran_exempelfilen(exempelfil):
    resultat = berakna_vasentlighet(exempelfil)
    assert resultat.omsattning == Decimal("2583800.00")


def test_resultat_fran_exempelfilen(exempelfil):
    resultat = berakna_vasentlighet(exempelfil)
    assert resultat.resultat == Decimal("428690.00")


def test_balansomslutning_fran_exempelfilen(exempelfil):
    resultat = berakna_vasentlighet(exempelfil)
    assert resultat.balansomslutning == Decimal("3457690.00")


def test_eget_kapital_fran_exempelfilen_alternativ_b(exempelfil):
    """
    Eget kapital = #UB (2010-2099) + samtliga #RES.
    Alternativ B, beslutat — se ARCHITECTURE_tillagg_vasentlighet.md.
    """
    resultat = berakna_vasentlighet(exempelfil)
    assert resultat.eget_kapital == Decimal("2267690.00")


def test_berakna_vasentlighet_returnerar_ratt_typ(exempelfil):
    resultat = berakna_vasentlighet(exempelfil)
    assert isinstance(resultat, Vasentlighetstal)


# ---------------------------------------------------------------------------
# Isolerade enhetstester: konstruerad minimal SIEFil, oberoende av exempelfilen
# Dessa görs snabbare/mer riktade och fångar kontogränserna exakt.
# ---------------------------------------------------------------------------

def _tom_siefil(**overrides) -> SIEFil:
    """
    Hjälpfunktion som bygger en minimal SIEFil för enhetstester.
    Justera fältnamn/konstruktoranrop om SIEFil kräver fler obligatoriska
    fält än vad som antas här.
    """
    bas = dict(resultat=[], utgående_balanser=[], tolkningsbehov=[])
    bas.update(overrides)
    return SIEFil(**bas)


def test_tomt_underlag_ger_nollor():
    tom_fil = _tom_siefil()
    resultat = berakna_vasentlighet(tom_fil)
    assert resultat.omsattning == Decimal("0")
    assert resultat.resultat == Decimal("0")
    assert resultat.balansomslutning == Decimal("0")
    assert resultat.eget_kapital == Decimal("0")


def test_omsattningsgransen_exkluderar_konto_3800_och_uppat():
    """
    Kontogränsen för omsättning är strikt 3000-3799 (beslutat).
    Konto 3900 (övriga rörelseintäkter) ska INTE räknas som omsättning,
    även om det bidrar till resultatet.
    """
    fil = _tom_siefil(
        resultat=[
            Saldopost(årsnr=0, kontonr="3500", objektreferenser={}, saldo=Decimal("-1000"), kvantitet=None),
            Saldopost(årsnr=0, kontonr="3900", objektreferenser={}, saldo=Decimal("-500"), kvantitet=None),
        ]
    )
    resultat = berakna_vasentlighet(fil)
    assert resultat.omsattning == Decimal("1000")      # bara 3500
    assert resultat.resultat == Decimal("1500")         # 3500 + 3900


def test_eget_kapital_gransen_exkluderar_obeskattade_reserver():
    """
    Konto 2100-2199 (obeskattade reserver) ska INTE räknas in i eget
    kapital, trots att de ligger i samma huvudgrupp 2.
    """
    fil = _tom_siefil(
        utgående_balanser=[
            Saldopost(årsnr=0, kontonr="2081", objektreferenser={}, saldo=Decimal("-100000"), kvantitet=None),
            Saldopost(årsnr=0, kontonr="2150", objektreferenser={}, saldo=Decimal("-50000"), kvantitet=None),
        ],
        resultat=[],
    )
    resultat = berakna_vasentlighet(fil)
    assert resultat.eget_kapital == Decimal("100000")   # bara 2081, inte 2150


def test_jamforelsear_ignoreras():
    """
    Modul 1 ska enbart räkna på årsnr 0. Poster för -1 (föregående år)
    ska inte påverka resultatet.
    """
    fil = _tom_siefil(
        resultat=[
            Saldopost(årsnr=0, kontonr="3500", objektreferenser={}, saldo=Decimal("-1000"), kvantitet=None),
            Saldopost(årsnr=-1, kontonr="3500", objektreferenser={}, saldo=Decimal("-999999"), kvantitet=None),
        ]
    )
    resultat = berakna_vasentlighet(fil)
    assert resultat.omsattning == Decimal("1000")
