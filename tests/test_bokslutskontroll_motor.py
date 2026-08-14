"""Steg 1 och 6 — test av bokslutskontroll.motor.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5 (steg 1, acceptans) och §7 steg 6
(väsentlighet och regelhänvisningar, centralt i motorn)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from _sie_fixtures import bygg_sie

from bokslutskontroll.modell import Fynd, Kontext, Regelhanvisning
from bokslutskontroll import motor
from bokslutskontroll.motor import kor_kontroller, registrera
from bokslutskontroll.regelkalla import kontroll_ider
from domain_model import SIEFil


@pytest.fixture(autouse=True)
def _tomt_register():
    """Varje test får ett eget, tomt KONTROLLER-register så att testerna inte
    stör varandra eller de riktiga kontrollerna. Fixturen ger tillbaka den
    riktiga, sparade registerinnehållet — så att ett test som vill pröva mot
    det (t.ex. I-4-testet) kan be om det via fixturens returvärde."""
    sparat = dict(motor.KONTROLLER)
    motor.KONTROLLER.clear()
    yield sparat
    motor.KONTROLLER.clear()
    motor.KONTROLLER.update(sparat)


def test_dubbelregistrering_kastar():
    @registrera("K-TEST")
    def _kontroll(kontext: Kontext) -> list[Fynd]:
        return []

    with pytest.raises(ValueError, match="K-TEST"):

        @registrera("K-TEST")
        def _kontroll2(kontext: Kontext) -> list[Fynd]:
            return []


def test_kontroll_som_kastar_ger_ett_k00_fynd_och_stoppar_inte_ovriga():
    @registrera("K-01")
    def _trasig(kontext: Kontext) -> list[Fynd]:
        raise RuntimeError("något gick sönder")

    @registrera("K-02")
    def _fungerande(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-02",
                rubrik="Testfynd",
                allvarlighet="observation",
                motivering="test",
            )
        ]

    fynd = kor_kontroller(SIEFil(), idag=date(2026, 8, 14))

    k00_fynd = [f for f in fynd if f.kontroll_id == "K-00"]
    assert len(k00_fynd) == 1
    assert "K-01" in k00_fynd[0].motivering

    k02_fynd = [f for f in fynd if f.kontroll_id == "K-02"]
    assert len(k02_fynd) == 1


def test_endast_begransar_korningen():
    @registrera("K-01")
    def _k1(kontext: Kontext) -> list[Fynd]:
        return [Fynd(kontroll_id="K-01", rubrik="A", allvarlighet="observation", motivering="a")]

    @registrera("K-02")
    def _k2(kontext: Kontext) -> list[Fynd]:
        return [Fynd(kontroll_id="K-02", rubrik="B", allvarlighet="observation", motivering="b")]

    fynd = kor_kontroller(SIEFil(), idag=date(2026, 8, 14), endast={"K-01"})

    ider = {f.kontroll_id for f in fynd}
    assert ider == {"K-01"}


def test_sortering_foljer_specen():
    @registrera("K-02")
    def _k2(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-02",
                rubrik="Verifikation i obalans",
                allvarlighet="avvikelse",
                motivering="x",
                belopp=Decimal("10"),
            ),
            Fynd(
                kontroll_id="K-02",
                rubrik="Verifikation i obalans",
                allvarlighet="avvikelse",
                motivering="y",
                belopp=Decimal("500"),
            ),
        ]

    @registrera("K-08")
    def _k8(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-08",
                rubrik="Avräkningskonto har kvarvarande saldo",
                allvarlighet="observation",
                motivering="z",
                belopp=Decimal("9999"),
            )
        ]

    @registrera("K-11")
    def _k11(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-11",
                rubrik="Kostnad nära årsskiftet",
                allvarlighet="upplysning",
                motivering="w",
            )
        ]

    fynd = kor_kontroller(SIEFil(), idag=date(2026, 8, 14))

    # Allvarligast (avvikelse) först, störst belopp inom nivån först,
    # sedan observation, sedan upplysning.
    assert [f.kontroll_id for f in fynd] == ["K-02", "K-02", "K-08", "K-11"]
    assert fynd[0].belopp == Decimal("500")
    assert fynd[1].belopp == Decimal("10")


def test_tomt_kontrollregister_ger_tom_lista_utan_att_kasta():
    fynd = kor_kontroller(SIEFil(), idag=date(2026, 8, 14))
    assert fynd == []


def test_regel_och_vasentlighet_berikas_centralt():
    @registrera("K-01")
    def _k1(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-01",
                rubrik="Balansräkningen går inte ihop",
                allvarlighet="avvikelse",
                motivering="x",
                belopp=Decimal("100"),
            )
        ]

    fynd = kor_kontroller(SIEFil(), idag=date(2026, 8, 14))
    assert len(fynd) == 1
    assert fynd[0].regel is not None
    assert fynd[0].regel.beteckning == "5 kap. 1 §"


# --- Steg 6 — väsentlighet och regelhänvisningar --------------------------


def test_kontroll_som_satter_egen_regel_behaller_den():
    """Motorn skriver bara över `regel` när den är None. Den mekanismen finns
    för att en kontroll (t.ex. en framtida variant av K-14, vars hänvisning
    kan skilja sig från de övrigas) ska kunna ge ett fynd en egen,
    mer specifik hänvisning än den generiska som ligger i registret."""
    egen_regel = Regelhanvisning(
        kalla="Egen källa",
        beteckning="särskild motivering",
        lank_manniska="https://example.invalid/egen",
    )

    @registrera("K-01")
    def _k1(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-01",
                rubrik="Balansräkningen går inte ihop",
                allvarlighet="avvikelse",
                motivering="x",
                belopp=Decimal("100"),
                regel=egen_regel,
            )
        ]

    fynd = kor_kontroller(SIEFil(), idag=date(2026, 8, 14))
    assert len(fynd) == 1
    assert fynd[0].regel is egen_regel


def test_vasentlig_ar_none_inte_false_utan_berakningsbart_vasentlighetstal():
    """Tom bokföring (ingen omsättning) → väsentlighetstalet går inte att
    beräkna → vasentlig ska förbli None, aldrig False."""

    @registrera("K-01")
    def _k1(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-01",
                rubrik="Balansräkningen går inte ihop",
                allvarlighet="avvikelse",
                motivering="x",
                belopp=Decimal("100"),
            )
        ]

    fynd = kor_kontroller(bygg_sie(), idag=date(2026, 8, 14))
    assert len(fynd) == 1
    assert fynd[0].vasentlig is None


def test_vasentlig_satts_ratt_nar_vasentlighetstal_gar_att_berakna():
    """Med en omsättning på 1 000 000 kr blir utfallsväsentligheten (75 % av
    0,5 % av omsättningen) 3 750 kr — se analysflode.berakna_standardtroskelvarden.
    Ett fynd över tröskeln ska bli vasentlig=True, ett under ska bli False."""
    sie = bygg_sie(res={"3010": "-1000000"})

    @registrera("K-01")
    def _over(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-01",
                rubrik="Över tröskeln",
                allvarlighet="avvikelse",
                motivering="x",
                belopp=Decimal("4000"),
            )
        ]

    @registrera("K-02")
    def _under(kontext: Kontext) -> list[Fynd]:
        return [
            Fynd(
                kontroll_id="K-02",
                rubrik="Under tröskeln",
                allvarlighet="avvikelse",
                motivering="y",
                belopp=Decimal("1000"),
            )
        ]

    fynd = kor_kontroller(sie, idag=date(2026, 8, 14))
    per_id = {f.kontroll_id: f for f in fynd}
    assert per_id["K-01"].vasentlig is True
    assert per_id["K-02"].vasentlig is False


def test_varje_registrerad_kontroll_finns_i_registret_och_tvartom(_tomt_register):
    """I-4, båda hållen: varje id som faktiskt är registrerat i koden ska
    finnas i regelregistret (K-00 undantaget — det är motorns eget,
    regelfria fynd, se §5 K-00)."""
    ider_i_koden = set(_tomt_register)
    ider_i_registret = kontroll_ider() - {"K-00"}
    assert ider_i_koden == ider_i_registret
