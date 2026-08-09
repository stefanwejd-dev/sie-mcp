"""
Testfallsskelett — Modul 2: Kontotyp-vakten

STATUS: Röd fas (TDD). `kontotyp_vakt.py` existerar ännu inte.

OBS – justera innan körning:
  - Importvägen nedan (`from kontotyp_vakt import ...`) är en platshållare,
    samma mönster som i test_vasentlighet.py. Justera till er faktiska
    modulplacering.
  - Sökvägen till exempelfilen antar `samples/SIE4_Exempelfil.SE`.

Facit är manuellt/empiriskt uträknat mot filens råa #KONTO/#KTYP-rader —
se ARCHITECTURE_tillagg_kontotyp_vakt.md för fullständigt underlag och
motivering, inklusive varför konto 8270 medvetet INTE fångas i v1.
"""

from decimal import Decimal
from pathlib import Path

import pytest

# --- Platshållare: byt till er faktiska modulstruktur ----------------------
from kontotyp_vakt import (
    Kontotypavvikelse,
    analysera_kontotyper,
    hitta_internmonster_avvikelser,
    hitta_referensmonster_avvikelser,
)
from sie4_parser import parse_sie4  # byt om er entry-point heter annat
from domain_model import SIEFil, Konto
# -----------------------------------------------------------------------

SAMPLE_FIL = Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"


def _bygg_siefil(**overrides) -> SIEFil:
    """Hjälpfunktion: minimal SIEFil för isolerade enhetstester."""
    bas = dict(konton={}, resultat=[], utgående_balanser=[], tolkningsbehov=[])
    bas.update(overrides)
    return SIEFil(**bas)


def _konto(kontonr: str, typ: str, namn: str = "") -> Konto:
    return Konto(kontonr=kontonr, namn=namn or kontonr, typ=typ, enhet=None, sru_koder=[])


# ---------------------------------------------------------------------------
# Golden-file-tester: facit mot SIE4_Exempelfil.SE
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def exempelfil() -> SIEFil:
    return parse_sie4(SAMPLE_FIL)


def test_internmonster_facit_exempelfilen(exempelfil):
    avvikelser = hitta_internmonster_avvikelser(exempelfil)
    kontonummer = {a.kontonr for a in avvikelser}
    assert kontonummer == {"2157"}


def test_internmonster_stod_ar_korrekt(exempelfil):
    avvikelser = hitta_internmonster_avvikelser(exempelfil)
    (avvikelse,) = avvikelser
    assert avvikelse.angiven_typ == "T"
    assert avvikelse.forvantad_typ == "S"
    assert avvikelse.stod_internmonster == "4/5"


def test_referensmonster_facit_exempelfilen(exempelfil):
    avvikelser = hitta_referensmonster_avvikelser(exempelfil)
    kontonummer = {a.kontonr for a in avvikelser}
    assert kontonummer == {"2084", "2085", "2157"}


def test_referensmonster_klass_8_ar_helt_exkluderad(exempelfil):
    """
    Kontrollerar det medvetna blind spot-beslutet: konto 8270 ska INTE
    flaggas i v1, trots att det (namn: nedskrivning) ser ut som en
    kandidat. Se ARCHITECTURE_tillagg_kontotyp_vakt.md för motivering.
    """
    avvikelser = hitta_referensmonster_avvikelser(exempelfil)
    kontonummer = {a.kontonr for a in avvikelser}
    assert "8270" not in kontonummer


def test_kombinerad_analys_dedupar_och_slar_ihop_lager(exempelfil):
    avvikelser = analysera_kontotyper(exempelfil)
    per_konto = {a.kontonr: a for a in avvikelser}

    assert set(per_konto.keys()) == {"2084", "2085", "2157"}

    # 2157 ska bekräftas av båda lagren oberoende av varandra
    assert set(per_konto["2157"].lager) == {"internmonster", "referensmonster"}

    # 2084 och 2085 fångas bara av referensmönster
    assert per_konto["2084"].lager == ["referensmonster"]
    assert per_konto["2085"].lager == ["referensmonster"]


def test_kontotypavvikelse_bar_kontots_faktiska_saldo(exempelfil):
    """Gap 1: Kontotypavvikelse ska
    bära kontots faktiska saldo, inte None eller ett saknat fält —
    Modul 5 kan annars inte ackumulera belopp som inte finns.

    Medvetet gränsfall, inte en bugg: konto 2157 saknar helt #UB/#IB i
    exempelfilen (bara #KONTO/#KTYP/#SRU förekommer för det kontot,
    verifierat mot rådata) — saldo förväntas då vara Decimal("0"),
    inte ett påhittat värde."""
    avvikelser = analysera_kontotyper(exempelfil)
    konto_2157 = next(a for a in avvikelser if a.kontonr == "2157")
    assert konto_2157.saldo == Decimal("0")


# ---------------------------------------------------------------------------
# Isolerade enhetstester — Lager 1 (internmönster)
# ---------------------------------------------------------------------------

def test_internmonster_kraver_minst_tre_konton_i_serien():
    """En serie med bara 2 konton ska aldrig ge en röstning/flaggning."""
    fil = _bygg_siefil(konton={
        "2150": _konto("2150", "S"),
        "2157": _konto("2157", "T"),
    })
    avvikelser = hitta_internmonster_avvikelser(fil)
    assert avvikelser == []


def test_internmonster_oavgjort_ger_ingen_flaggning():
    """2 mot 2 i en serie = oavgjort, ingen typ vinner, ingen flaggning."""
    fil = _bygg_siefil(konton={
        "2150": _konto("2150", "S"),
        "2151": _konto("2151", "S"),
        "2152": _konto("2152", "T"),
        "2153": _konto("2153", "T"),
    })
    avvikelser = hitta_internmonster_avvikelser(fil)
    assert avvikelser == []


def test_internmonster_konto_utan_ktyp_ignoreras():
    """Konto utan satt typ ska varken rösta eller kunna flaggas."""
    fil = _bygg_siefil(konton={
        "2150": _konto("2150", "S"),
        "2151": _konto("2151", "S"),
        "2152": _konto("2152", "S"),
        "2153": _konto("2153", None),  # ingen #KTYP i filen
    })
    avvikelser = hitta_internmonster_avvikelser(fil)
    assert avvikelser == []


def test_internmonster_flaggar_tydlig_minoritet():
    fil = _bygg_siefil(konton={
        "3010": _konto("3010", "I"),
        "3011": _konto("3011", "I"),
        "3012": _konto("3012", "I"),
        "3013": _konto("3013", "K"),  # avviker
    })
    avvikelser = hitta_internmonster_avvikelser(fil)
    assert len(avvikelser) == 1
    assert avvikelser[0].kontonr == "3013"
    assert avvikelser[0].stod_internmonster == "3/4"


# ---------------------------------------------------------------------------
# Isolerade enhetstester — Lager 2 (referensmönster, Version A)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kontonr,angiven,forvantad",
    [
        ("1220", "S", "T"),   # klass 1 -> T
        ("2500", "T", "S"),   # klass 2 -> S
        ("3900", "K", "I"),   # klass 3 -> I
        ("5010", "I", "K"),   # klass 4-7 -> K
    ],
)
def test_referensmonster_klassregel(kontonr, angiven, forvantad):
    fil = _bygg_siefil(konton={kontonr: _konto(kontonr, angiven)})
    avvikelser = hitta_referensmonster_avvikelser(fil)
    assert len(avvikelser) == 1
    assert avvikelser[0].forvantad_typ == forvantad


def test_referensmonster_klass_8_flaggar_aldrig():
    """Hela klass 8 är exkluderad i v1 - oavsett hur 'fel' typen ser ut."""
    fil = _bygg_siefil(konton={
        "8300": _konto("8300", "K"),  # ränteintäkter kodat som K - "fel", men ej vår sak i v1
        "8400": _konto("8400", "I"),  # räntekostnader kodat som I - "fel", men ej vår sak i v1
    })
    avvikelser = hitta_referensmonster_avvikelser(fil)
    assert avvikelser == []


def test_referensmonster_undantag_atterforing_av_nedskrivning():
    """
    Serie 776-778 ska förväntas vara I, inte K, trots att den ligger i
    kostnadsklassen. Se motivering i ARCHITECTURE_tillagg_kontotyp_vakt.md.
    """
    fil = _bygg_siefil(konton={
        "7760": _konto("7760", "K"),  # felaktigt kodad enligt undantagsregeln -> ska flaggas
        "7770": _konto("7770", "I"),  # korrekt kodad enligt undantagsregeln -> ska INTE flaggas
    })
    avvikelser = hitta_referensmonster_avvikelser(fil)
    kontonummer = {a.kontonr for a in avvikelser}
    assert kontonummer == {"7760"}
    assert avvikelser[0].forvantad_typ == "I"


def test_referensmonster_konto_utan_ktyp_ignoreras():
    fil = _bygg_siefil(konton={"2500": _konto("2500", None)})
    avvikelser = hitta_referensmonster_avvikelser(fil)
    assert avvikelser == []
