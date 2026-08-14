"""Steg 1 — test av bokslutskontroll.motor.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5 (steg 1, acceptans)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bokslutskontroll.modell import Fynd, Kontext
from bokslutskontroll import motor
from bokslutskontroll.motor import kor_kontroller, registrera
from domain_model import SIEFil


@pytest.fixture(autouse=True)
def _tomt_register():
    """Varje test får ett eget, tomt KONTROLLER-register så att testerna inte
    stör varandra eller de riktiga kontrollerna (som ännu inte finns)."""
    sparat = dict(motor.KONTROLLER)
    motor.KONTROLLER.clear()
    yield
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
