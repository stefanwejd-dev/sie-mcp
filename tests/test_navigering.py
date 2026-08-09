"""Tester för navigering.py — dashboardlayoutens flikstruktur och åtgärdsbadge.

Kärnkrav:
- Badgen är röd så snart NÅGOT väntar på ett mänskligt beslut, grön bara när
  båda åtgärdskällorna (maskeringsbehov + verifikationsavvikelser) är tomma.
- "Ohanterade" maskeringsbehov betyder status == "väntar_granskning", inte
  "finns i listan": sekretesslagret bär med sig även redan granskade behov.
- Flikordningen är stabil och bara Åtgärder bär badge — de andra fyra
  etiketterna får aldrig ändras mellan omkörningar (Streamlits flikidentitet).
- Sticky-CSS:en träffar toppnavigeringen men återställer nästlade flikrader.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from navigering import (
    BADGE_ATGARD_KRAVS,
    BADGE_INGET_ATT_GORA,
    Verifikationsavvikelse,
    bygg_atgardsstatus,
    hitta_verifikationsavvikelser,
    ohanterade_maskeringsbehov,
)


@dataclass
class _FalsktBehov:
    status: str


@dataclass
class _FalsktMaskeringsresultat:
    maskeringsbehov: list


def _avvikelse(plats: str = "serie=A vernr=1") -> Verifikationsavvikelse:
    return Verifikationsavvikelse(plats=plats, beskrivning="Obalanserat verifikat")


class TestOhanteradeMaskeringsbehov:
    """Bara behov som faktiskt väntar på ett beslut ska räknas."""

    def test_ingen_data_ger_noll(self):
        assert ohanterade_maskeringsbehov(None) == 0

    def test_tom_lista_ger_noll(self):
        assert ohanterade_maskeringsbehov(_FalsktMaskeringsresultat([])) == 0

    def test_raknar_bara_vantar_granskning(self):
        resultat = _FalsktMaskeringsresultat(
            [
                _FalsktBehov("väntar_granskning"),
                _FalsktBehov("bekräftad_pii"),
                _FalsktBehov("godkänd_ej_pii"),
                _FalsktBehov("väntar_granskning"),
            ]
        )

        assert ohanterade_maskeringsbehov(resultat) == 2

    def test_enbart_granskade_behov_ger_noll(self):
        # Efter en fullständig granskning ska badgen kunna bli grön igen.
        resultat = _FalsktMaskeringsresultat(
            [_FalsktBehov("bekräftad_pii"), _FalsktBehov("godkänd_ej_pii")]
        )

        assert ohanterade_maskeringsbehov(resultat) == 0


class TestVerifikationsavvikelserSeam:
    """Platshållaren ska vara tom — men aldrig kasta, och aldrig kräva data."""

    def test_returnerar_tom_lista(self):
        assert hitta_verifikationsavvikelser(None, None) == []

    def test_kastar_inte_utan_data(self):
        assert hitta_verifikationsavvikelser(None, _FalsktMaskeringsresultat([])) == []


class TestBadge:
    def test_ingen_atgard_ger_gron_badge(self):
        status = bygg_atgardsstatus(0, [])

        assert status.badge == BADGE_INGET_ATT_GORA
        assert status.kräver_åtgärd is False
        assert status.antal_totalt == 0

    def test_maskeringsbehov_ger_rod_badge(self):
        status = bygg_atgardsstatus(3, [])

        assert status.badge == BADGE_ATGARD_KRAVS
        assert status.kräver_åtgärd is True
        assert status.antal_totalt == 3

    def test_bara_avvikelser_ger_rod_badge(self):
        # Maskeringen kan vara helt genomgången och badgen ändå röd.
        status = bygg_atgardsstatus(0, [_avvikelse()])

        assert status.badge == BADGE_ATGARD_KRAVS
        assert status.antal_verifikationsavvikelser == 1
        assert status.antal_totalt == 1

    def test_bada_kallorna_summeras(self):
        status = bygg_atgardsstatus(2, [_avvikelse("A/1"), _avvikelse("A/2")])

        assert status.antal_maskeringsbehov == 2
        assert status.antal_verifikationsavvikelser == 2
        assert status.antal_totalt == 4

    def test_etikett_visar_antal_nar_atgard_kravs(self):
        assert bygg_atgardsstatus(3, []).etikett == f"{BADGE_ATGARD_KRAVS} Åtgärder (3)"

    def test_etikett_utan_antal_nar_allt_ar_klart(self):
        assert bygg_atgardsstatus(0, []).etikett == f"{BADGE_INGET_ATT_GORA} Åtgärder"


