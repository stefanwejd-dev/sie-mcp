"""Tester för analysflode.py — orkestrering av Modul 1+2+4+5 för app.py:s
Sektion 8. Fokus: kontraktsdriven orkestrering (rätt data flödar till rätt
funktion i rätt ordning) och sekretessgränsen (bara sandningsbara
verifikationer når haiku_anropare) — inte omtest av varje delmoduls egen
interna logik, det täcks redan av deras egna testsviter.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain_model import Konto, SIEFil, Transaktion, Verifikation
from sekretesslager import Maskeringsresultat

from analysflode import (
    TröskelvärdeFel,
    belopp_fran_procent,
    berakna_standardtroskelvarden,
    kor_analys,
    procent_fran_belopp,
    tolka_troskelvarden,
)

KONTON = {
    "6110": Konto(kontonr="6110", namn="Kontorsmaterial", typ="K"),
    "5611": Konto(kontonr="5611", namn="Drivmedel personbilar", typ="K"),
}


def _verifikation(serie="A", vernr="1", kontonr="6110", belopp=Decimal("500")) -> Verifikation:
    return Verifikation(
        serie=serie,
        vernr=vernr,
        verdatum=date(2025, 1, 1),
        vertext="Test",
        transaktioner=[Transaktion(kontonr=kontonr, belopp=belopp, transtext="Drivmedel Circle K")],
    )


def _sie(verifikationer=None) -> SIEFil:
    return SIEFil(konton=KONTON, verifikationer=verifikationer or [])


def _maskeringsresultat(sandningsbara=None, prosa_sandningsbar=None) -> Maskeringsresultat:
    # Fynd A: Modul 4 läser numera kontonamnen ur den MASKERADE kontoplanen
    # (maskeringsresultat.maskerad_siefil.konton), aldrig ur råa sie.konton. I
    # produktion speglar maskerad_siefil.konton alltid sie.konton (samma nycklar,
    # maskerade namn), så fixturen bär samma KONTON — standardnamnen är dessutom
    # oförändrade av maskeringen.
    return Maskeringsresultat(
        maskerad_siefil=SIEFil(konton=KONTON),
        kodnyckel={},
        maskeringsbehov=[],
        blockerade_verifikationer=set(),
        sandningsbara_verifikationer=sandningsbara or [],
        prosa_sandningsbar=prosa_sandningsbar,
    )


class TestTolkaTroskelvarden:
    def test_giltiga_tal_ger_decimal_tuple(self):
        resultat = tolka_troskelvarden("1000", "2000")
        assert resultat == (Decimal("1000"), Decimal("2000"))

    def test_tomt_falt_ger_troskelvardefel(self):
        with pytest.raises(TröskelvärdeFel):
            tolka_troskelvarden("", "2000")

    def test_ej_tolkningsbart_tal_ger_troskelvardefel(self):
        with pytest.raises(TröskelvärdeFel):
            tolka_troskelvarden("abc", "2000")

    def test_noll_ger_troskelvardefel(self):
        with pytest.raises(TröskelvärdeFel):
            tolka_troskelvarden("0", "2000")

    def test_negativt_tal_ger_troskelvardefel(self):
        with pytest.raises(TröskelvärdeFel):
            tolka_troskelvarden("-100", "2000")


class TestBeraknaStandardtroskelvarden:
    """Transparent, redigerbar default: väsentlighetstal = 0,5 % av omsättningen,
    utfallsväsentlighet = 75 % av väsentlighetstalet. Avrundas till hela kronor.
    Revisorn kan alltid justera — detta är ett utgångsvärde, inte en tyst policy."""

    def test_halv_procent_och_75_procent(self):
        vasentlighetstal, utfall = berakna_standardtroskelvarden(Decimal("1000000"))
        assert vasentlighetstal == Decimal("5000")  # 0,5 % av 1 000 000
        assert utfall == Decimal("3750")            # 75 % av 5 000

    def test_avrundas_till_hela_kronor(self):
        vasentlighetstal, utfall = berakna_standardtroskelvarden(Decimal("5782818.36"))
        assert vasentlighetstal == Decimal("28914")  # 28914.09 -> 28914
        assert utfall == Decimal("21686")            # 28914 * 0,75 = 21685,5 -> 21686

    def test_noll_omsattning_ger_noll(self):
        assert berakna_standardtroskelvarden(Decimal("0")) == (Decimal("0"), Decimal("0"))


class TestBidirektionellKonvertering:
    """Konverteringsmatten bakom Sektion 8:s bidirektionella inmatning: belopp
    <-> procent av ett bastal. Division med noll (t.ex. omsättning 0 kr) ger
    None på procent-sidan (odefinierat), aldrig en krasch."""

    def test_belopp_fran_procent(self):
        # 0,5 % av omsättningen; avrundas till hela kronor.
        assert belopp_fran_procent(Decimal("0.5"), Decimal("5782818.36")) == Decimal("28914")
        # 75 % av väsentlighetstalet: 21685,5 -> 21686.
        assert belopp_fran_procent(Decimal("75"), Decimal("28914")) == Decimal("21686")

    def test_belopp_fran_procent_med_noll_bas_ger_noll(self):
        assert belopp_fran_procent(Decimal("0.5"), Decimal("0")) == Decimal("0")

    def test_procent_fran_belopp(self):
        # 28 914 kr av 5 782 818,36 kr ≈ 0,5 %.
        assert procent_fran_belopp(Decimal("28914"), Decimal("5782818.36")) == Decimal("0.5")
        assert procent_fran_belopp(Decimal("50"), Decimal("200")) == Decimal("25.0")

    def test_procent_fran_belopp_med_noll_bas_ger_none(self):
        # Odefinierat (division med noll) -> None, aldrig krasch.
        assert procent_fran_belopp(Decimal("28914"), Decimal("0")) is None
        assert procent_fran_belopp(Decimal("0"), Decimal("0")) is None


class TestKorAnalys:
    def test_endast_sandningsbara_verifikationer_nar_haiku(self):
        """Sekretessgränsen: en verifikation som INTE finns i
        maskeringsresultat.sandningsbara_verifikationer (t.ex. blockerad
        av ett olöst maskeringsbehov) får aldrig nå haiku_anropare, även
        om den finns i sie.verifikationer."""
        blockerad = _verifikation(serie="B", vernr="9")
        sandningsbar = _verifikation(serie="A", vernr="1")
        sie = _sie(verifikationer=[blockerad, sandningsbar])
        maskeringsresultat = _maskeringsresultat(sandningsbara=[sandningsbar])

        mottagna_bunt: list[dict] = []

        def fejk_haiku(bunt, prosa_kontext):
            mottagna_bunt.extend(bunt)
            return [{"bunt_id": r["bunt_id"], "status": "matchning", "motivering": None} for r in bunt]

        kor_analys(sie, maskeringsresultat, fejk_haiku, Decimal("1000"), Decimal("2000"))

        assert len(mottagna_bunt) == 1
        assert mottagna_bunt[0]["plats"] == "serie=A vernr=1 radindex=0"

    def test_lyckad_korning_ger_fullstandigt_resultat(self):
        sie = _sie(verifikationer=[_verifikation()])
        sandningsbar = sie.verifikationer[0]
        maskeringsresultat = _maskeringsresultat(sandningsbara=[sandningsbar])

        def fejk_haiku(bunt, prosa_kontext):
            return [
                {"bunt_id": r["bunt_id"], "status": "avvikelse",
                 "motivering": "Fel konto", "föreslaget_kontonr": "5611"}
                for r in bunt
            ]

        resultat = kor_analys(sie, maskeringsresultat, fejk_haiku, Decimal("1000"), Decimal("2000"))

        assert resultat.felmeddelande is None
        assert resultat.vasentlighetstal is not None
        assert resultat.ackumulering is not None
        modul4_felaktigheter = [
            f for f in resultat.ackumulering.felaktigheter if f.källa == "modul4_kontomatchning"
        ]
        assert len(modul4_felaktigheter) == 1
        assert modul4_felaktigheter[0].belopp == Decimal("500")
        assert modul4_felaktigheter[0].kontonr == "6110"

    def test_prosa_sandningsbar_skickas_som_kontext(self):
        sie = _sie(verifikationer=[_verifikation()])
        sandningsbar = sie.verifikationer[0]
        maskeringsresultat = _maskeringsresultat(
            sandningsbara=[sandningsbar], prosa_sandningsbar="Bakgrund från revisorn."
        )
        mottagen_kontext: list[str | None] = []

        def fejk_haiku(bunt, prosa_kontext):
            mottagen_kontext.append(prosa_kontext)
            return [{"bunt_id": r["bunt_id"], "status": "matchning", "motivering": None} for r in bunt]

        kor_analys(sie, maskeringsresultat, fejk_haiku, Decimal("1000"), Decimal("2000"))

        assert mottagen_kontext == ["Bakgrund från revisorn."]

    def test_ovantat_fel_ger_statiskt_felmeddelande_inte_ra_exception_text(self):
        sie = _sie(verifikationer=[_verifikation()])
        maskeringsresultat = _maskeringsresultat(sandningsbara=[sie.verifikationer[0]])

        def trasig_haiku(bunt, prosa_kontext):
            raise RuntimeError("hemlig intern detalj som inte får synas")

        resultat = kor_analys(sie, maskeringsresultat, trasig_haiku, Decimal("1000"), Decimal("2000"))

        assert resultat.felmeddelande is not None
        assert "hemlig intern detalj" not in resultat.felmeddelande
        assert resultat.vasentlighetstal is None
        assert resultat.ackumulering is None
