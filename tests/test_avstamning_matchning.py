"""Lager 1b, steg 3 — test av avstamning.matchning.

Se hantverksbok/BOKSLUTSPROGRAMMET.md §4.3/§4.3.1/§4.5 steg 3.
test_varje_registrerad_kontroll_finns_i_registret_och_tvartom förblir röd
till och med steg 4 — rörs inte här."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from avstamning.camt053 import Utdragsrad
from avstamning.matchning import Match, Parkoppling, matcha
from domain_model import Transaktion

# Små, "neutrala" trösklar för pass 3 i de test som inte handlar om
# parkoppling — små nog att inte råka fånga upp de olika-belopp-fallen som
# testar att INGET av något slag matchas.
_KRONOR = Decimal("5.00")
_ANDEL = Decimal("0.01")


def _matcha(bokforda, utdrag, *, matchningsfonster_dagar=5, kronor=_KRONOR, andel=_ANDEL):
    return matcha(
        bokforda,
        utdrag,
        matchningsfonster_dagar=matchningsfonster_dagar,
        avstamning_beloppsdiff_kronor=kronor,
        avstamning_beloppsdiff_andel=andel,
    )


def _post(datum: str, belopp: str) -> Transaktion:
    return Transaktion(kontonr="1930", belopp=Decimal(belopp), transdat=date.fromisoformat(datum))


def _rad(datum: str, belopp: str) -> Utdragsrad:
    return Utdragsrad(datum=date.fromisoformat(datum), belopp=Decimal(belopp))


# --- Pass 1 — exakt ----------------------------------------------------


def test_exakt_match_samma_datum_och_belopp():
    resultat = _matcha([_post("2026-06-05", "1000.00")], [_rad("2026-06-05", "1000.00")])
    assert len(resultat.matchningar) == 1
    match = resultat.matchningar[0]
    assert match == Match(bokford_index=0, utdrag_index=0, sakerhet="exakt")
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == ()
    assert resultat.omatchade_utdragsrader == ()


# --- Pass 2 — nära i tid -------------------------------------------------


def test_nara_match_inom_fonstret():
    resultat = _matcha([_post("2026-06-05", "1000.00")], [_rad("2026-06-08", "1000.00")])
    assert len(resultat.matchningar) == 1
    assert resultat.matchningar[0].sakerhet == "nara"


def test_fonstrets_grans_ar_inklusiv():
    """± matchningsfonster_dagar — exakt N dagar ska matcha, N+1 inte."""
    inom_gransen = _matcha([_post("2026-06-01", "1000.00")], [_rad("2026-06-06", "1000.00")])
    assert len(inom_gransen.matchningar) == 1

    utanfor_gransen = _matcha([_post("2026-06-01", "1000.00")], [_rad("2026-06-07", "1000.00")])
    assert utanfor_gransen.matchningar == ()


def test_tva_bokforda_poster_en_utdragsrad_ger_en_match_och_en_rest():
    """§4.3:s explicita exempel: ett belopp matchas mot exakt EN motpart."""
    resultat = _matcha(
        [_post("2026-06-05", "1000.00"), _post("2026-06-05", "1000.00")],
        [_rad("2026-06-05", "1000.00")],
    )
    assert len(resultat.matchningar) == 1
    assert len(resultat.omatchade_bokforda) == 1
    assert resultat.omatchade_utdragsrader == ()


def test_en_bokford_post_tva_utdragsrader_ger_en_match_och_en_rest():
    """Samma regel åt andra hållet."""
    resultat = _matcha(
        [_post("2026-06-05", "1000.00")],
        [_rad("2026-06-05", "1000.00"), _rad("2026-06-05", "1000.00")],
    )
    assert len(resultat.matchningar) == 1
    assert resultat.omatchade_bokforda == ()
    assert len(resultat.omatchade_utdragsrader) == 1


def test_pass_2_valjer_narmaste_datum_bland_flera_kandidater():
    resultat = _matcha(
        [_post("2026-06-05", "1000.00")],
        [_rad("2026-06-09", "1000.00"), _rad("2026-06-07", "1000.00")],
    )
    assert len(resultat.matchningar) == 1
    # Index 1 (2026-06-07) ligger närmare 2026-06-05 än index 0 (2026-06-09).
    assert resultat.matchningar[0].utdrag_index == 1
    assert resultat.omatchade_utdragsrader == (0,)


def test_exakt_match_prioriteras_over_nara():
    """En post med både en exakt och en nära kandidat ska ta den exakta —
    pass 1 körs, och konsumerar kandidaten, innan pass 2 ens börjar."""
    resultat = _matcha(
        [_post("2026-06-05", "1000.00")],
        [_rad("2026-06-07", "1000.00"), _rad("2026-06-05", "1000.00")],
    )
    assert len(resultat.matchningar) == 1
    match = resultat.matchningar[0]
    assert match.sakerhet == "exakt"
    assert match.utdrag_index == 1
    assert resultat.omatchade_utdragsrader == (0,)


def test_post_utan_transdat_matchas_aldrig():
    post_utan_datum = Transaktion(kontonr="1930", belopp=Decimal("1000.00"), transdat=None)
    resultat = _matcha([post_utan_datum], [_rad("2026-06-05", "1000.00")])
    assert resultat.matchningar == ()
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == (0,)
    assert resultat.omatchade_utdragsrader == (0,)


def test_tomma_listor_ger_tomt_resultat_utan_att_kasta():
    resultat = _matcha([], [])
    assert resultat.matchningar == ()
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == ()
    assert resultat.omatchade_utdragsrader == ()


def test_flera_ovannedade_par_matchas_alla_exakt():
    resultat = _matcha(
        [_post("2026-06-01", "100.00"), _post("2026-06-02", "200.00")],
        [_rad("2026-06-01", "100.00"), _rad("2026-06-02", "200.00")],
    )
    assert len(resultat.matchningar) == 2
    assert {m.sakerhet for m in resultat.matchningar} == {"exakt"}
    assert resultat.omatchade_bokforda == ()
    assert resultat.omatchade_utdragsrader == ()


def test_matchningsfonster_dagar_maste_anges_explicit():
    """B-4: inga standardvärden i koden — anroparen tvingas hämta talen ur
    registret."""
    with pytest.raises(TypeError):
        matcha([], [])  # type: ignore[call-arg]


# --- Pass 3 — parkoppling (§4.3.1), ger A-03-kandidater ---------------------


def test_par_helt_utanfor_alla_troskar_ger_ingen_matchning_alls():
    """Ett par som varken har lika belopp eller ligger inom
    beloppsdiff-gränsen ska inte matchas av NÅGOT pass."""
    resultat = _matcha([_post("2026-06-05", "1000.00")], [_rad("2026-06-05", "500.00")])
    assert resultat.matchningar == ()
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == (0,)
    assert resultat.omatchade_utdragsrader == (0,)


def test_parkoppling_inom_kronorgransen():
    resultat = _matcha(
        [_post("2026-06-05", "1000.00")], [_rad("2026-06-05", "990.00")], kronor=Decimal("50")
    )
    assert resultat.matchningar == ()
    assert resultat.parkopplingar == (Parkoppling(bokford_index=0, utdrag_index=0),)
    assert resultat.omatchade_bokforda == ()
    assert resultat.omatchade_utdragsrader == ()


def test_parkoppling_utanfor_kronorgransen_men_ingen_andel_ger_inget():
    resultat = _matcha(
        [_post("2026-06-05", "1000.00")], [_rad("2026-06-05", "900.00")],
        kronor=Decimal("50"), andel=Decimal("0"),
    )
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == (0,)


def test_andelsgransen_vinner_nar_den_ar_generosare():
    """Diff 100 kr på ett belopp om 10 000 kr är 1 % — över kronorgränsen
    (50 kr) men innanför andelsgränsen (2 %). Den generösare gränsen vinner
    (§4.3.1: max(...))."""
    resultat = _matcha(
        [_post("2026-06-05", "10000.00")], [_rad("2026-06-05", "9900.00")],
        kronor=Decimal("50"), andel=Decimal("0.02"),
    )
    assert len(resultat.parkopplingar) == 1


def test_olika_tecken_parkopplas_aldrig():
    """En insättning och ett uttag av liknande storlek är inte samma
    händelse, oavsett hur nära beloppen ligger varandra."""
    resultat = _matcha(
        [_post("2026-06-05", "1000.00")], [_rad("2026-06-05", "-990.00")], kronor=Decimal("50")
    )
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == (0,)
    assert resultat.omatchade_utdragsrader == (0,)


def test_parkoppling_kraver_datum_inom_fonstret():
    resultat = _matcha(
        [_post("2026-06-01", "1000.00")], [_rad("2026-06-10", "990.00")],
        matchningsfonster_dagar=5, kronor=Decimal("50"),
    )
    assert resultat.parkopplingar == ()
    assert resultat.omatchade_bokforda == (0,)


def test_parkoppling_bara_pa_rester_efter_pass_1_och_2():
    """Ett par som redan matchats exakt (lika belopp) ska inte omprövas av
    pass 3 — det finns inget kvar att para."""
    resultat = _matcha([_post("2026-06-05", "1000.00")], [_rad("2026-06-05", "1000.00")])
    assert resultat.parkopplingar == ()
    assert len(resultat.matchningar) == 1


def test_parkoppling_ett_belopp_mot_exakt_en_motpart():
    """§4.3:s 1:1-regel gäller genom alla fyra passen: två bokförda poster
    som båda skulle kunna parkopplas mot samma utdragsrad ger EN
    parkoppling och en kvarvarande rest."""
    resultat = _matcha(
        [_post("2026-06-05", "1000.00"), _post("2026-06-05", "1001.00")],
        [_rad("2026-06-05", "990.00")],
        kronor=Decimal("50"),
    )
    assert len(resultat.parkopplingar) == 1
    assert len(resultat.omatchade_bokforda) == 1


def test_greedy_valjer_minsta_relativa_skillnad_forst():
    """Två bokförda poster kan båda parkopplas mot samma utdragsrad — den
    med minst relativ skillnad mot posten (inte kronor) ska vinna."""
    resultat = _matcha(
        [_post("2026-06-05", "1000.00"), _post("2026-06-05", "1030.00")],
        [_rad("2026-06-05", "990.00")],
        kronor=Decimal("50"),
    )
    # Post 0: diff 10, relativ 1 %. Post 1: diff 40, relativ ~3,9 %. Post 0
    # vinner — post 1 blir kvar utan någon utdragsrad att paras mot.
    assert resultat.parkopplingar == (Parkoppling(bokford_index=0, utdrag_index=0),)
    assert resultat.omatchade_bokforda == (1,)


def test_greedy_prioritet_mellan_tva_konkurrerande_parkopplingar():
    resultat = _matcha(
        [_post("2026-06-05", "1000.00"), _post("2026-06-05", "2000.00")],
        [_rad("2026-06-05", "980.00"), _rad("2026-06-05", "1970.00")],
        kronor=Decimal("50"),
    )
    # 1000 mot 980: diff 20, relativ 2 %. 1000 mot 1970: diff 970, för stort.
    # 2000 mot 1970: diff 30, relativ 1.5 %. 2000 mot 980: för stort.
    # Bästa globala parning: (1000,980) och (2000,1970) — inga korsvisa
    # alternativ är ens under kronorgränsen (50) samtidigt som andelen.
    par = {(p.bokford_index, p.utdrag_index) for p in resultat.parkopplingar}
    assert par == {(0, 0), (1, 1)}
