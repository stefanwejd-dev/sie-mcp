from __future__ import annotations

from datetime import date
from decimal import Decimal
import pytest

from snabbvyer import (
    Vydata,
    bygg_kontoplan,
    bygg_kontosaldon,
    bygg_verifikatsokning,
    bygg_momsoversikt_vy,
    bygg_verifikatutkast,
)
from domain_model import Verifikation, Transaktion
from formatering import Formateringsval

def test_kontoplan_saknas():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_kontoplan(data)
    assert res.rubrik == "Kontoplan"
    assert "saknas" in res.sektioner[0].tomtext

def test_kontoplan_innehall():
    k1 = {"kontonr": "1930", "kontonamn": "Bank", "kontotyp": "tillgång", "aktivt": True}
    k2 = {"kontonr": "2890", "kontonamn": "Skuld", "kontotyp": None, "aktivt": False}
    data = Vydata(idag=date(2026, 8, 6), kontoplan=[k1, k2])
    res = bygg_kontoplan(data)
    
    assert int(res.nyckeltal[0].varde) == 2  # Antal
    assert int(res.nyckeltal[1].varde) == 1  # Aktiva
    assert int(res.nyckeltal[2].varde) == 1  # Utan typ
    
    tabell = res.sektioner[0].tabell
    assert tabell.rader[0] == {"kontonr": "1930", "kontonamn": "Bank", "kontotyp": "tillgång", "aktivt": "Ja"}
    assert tabell.rader[1] == {"kontonr": "2890", "kontonamn": "Skuld", "kontotyp": "—", "aktivt": "Nej"}

def test_kontoplan_utan_typ_blir_streck():
    data = Vydata(idag=date(2026, 8, 6), kontoplan=[{"kontonr": "3000", "kontotyp": None}])
    res = bygg_kontoplan(data)
    assert res.sektioner[0].tabell.rader[0]["kontotyp"] == "—"

def test_kontoplan_tom_lista():
    data = Vydata(idag=date(2026, 8, 6), kontoplan=[])
    res = bygg_kontoplan(data)
    assert int(res.nyckeltal[0].varde) == 0

def test_kontosaldon_saknas():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_kontosaldon(data)
    assert "saknas" in res.sektioner[0].tomtext

class MockSaldopost:
    def __init__(self, kontonr, saldo):
        self.kontonr = kontonr
        self.saldo = Decimal(str(saldo))

def test_kontosaldon_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        kontoplan=[{"kontonr": "1930", "kontonamn": "Bank"}, {"kontonr": "2440", "kontonamn": "LevSkuld"}],
        kontosaldon=[MockSaldopost("1930", "1500.50"), MockSaldopost("2440", "-500.00")],
        formateringsval=Formateringsval(decimaler=2)
    )
    res = bygg_kontosaldon(data)
    
    assert res.nyckeltal[0].varde == "2" # Antal
    assert "1 500,50" in res.nyckeltal[1].varde # Tillgångar
    assert "-500,00" in res.nyckeltal[2].varde # Skulder
    
    tabell = res.sektioner[0].tabell
    assert tabell.rader[0]["kontonamn"] == "Bank"
    assert tabell.rader[1]["kontonamn"] == "LevSkuld"

def test_kontosaldon_formatering():
    data = Vydata(
        idag=date(2026, 8, 6),
        kontosaldon=[MockSaldopost("1930", "1500.50")],
        formateringsval=Formateringsval(decimaler=0, tusentalsavgransare="")
    )
    res = bygg_kontosaldon(data)
    assert res.nyckeltal[1].varde == "1500 kr"
    
def test_kontosaldon_decimal_bevaras():
    s = MockSaldopost("1930", "0.33")
    data = Vydata(idag=date(2026, 8, 6), kontosaldon=[s], formateringsval=Formateringsval(decimaler=2))
    res = bygg_kontosaldon(data)
    assert "0,33" in res.nyckeltal[1].varde

def test_verifikatsokning_saknas():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_verifikatsokning(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_verifikatsokning_tom_soktext_ger_senaste():
    v1 = Verifikation(serie="A", vernr="1", verdatum=date(2026, 1, 1), vertext="Gammal")
    v2 = Verifikation(serie="A", vernr="2", verdatum=date(2026, 2, 1), vertext="Ny")
    data = Vydata(idag=date(2026, 8, 6), verifikationer=[v1, v2], soktext="")
    res = bygg_verifikatsokning(data)
    assert res.nyckeltal[0].varde == "2"
    assert "Visar de 20 senaste" in res.sektioner[0].beskrivning
    assert res.sektioner[0].tabell.rader[0]["vertext"] == "Ny"

def test_verifikatsokning_traff_i_vertext():
    v1 = Verifikation(serie="A", vernr="1", verdatum=date(2026, 1, 1), vertext="Inköp papper")
    v2 = Verifikation(serie="A", vernr="2", verdatum=date(2026, 1, 2), vertext="Något annat")
    data = Vydata(idag=date(2026, 8, 6), verifikationer=[v1, v2], soktext="Papper")
    res = bygg_verifikatsokning(data)
    assert res.nyckeltal[0].varde == "1"
    assert res.sektioner[0].tabell.rader[0]["vertext"] == "Inköp papper"

def test_verifikatsokning_traff_i_transtext():
    v1 = Verifikation(serie="A", vernr="1", verdatum=date(2026, 1, 1), vertext="Test")
    v1.transaktioner.append(Transaktion(kontonr="1930", belopp=Decimal("100"), transtext="Kaffe"))
    v2 = Verifikation(serie="A", vernr="2", verdatum=date(2026, 1, 2), vertext="Test 2")
    data = Vydata(idag=date(2026, 8, 6), verifikationer=[v1, v2], soktext="kaffe")
    res = bygg_verifikatsokning(data)
    assert res.nyckeltal[0].varde == "1"

def test_verifikatsokning_ingen_traff():
    v1 = Verifikation(serie="A", vernr="1", verdatum=date(2026, 1, 1), vertext="Test")
    data = Vydata(idag=date(2026, 8, 6), verifikationer=[v1], soktext="FinnsInte")
    res = bygg_verifikatsokning(data)
    assert res.nyckeltal[0].varde == "0"
    assert res.sektioner[0].tabell is None
    assert "Hittade inga verifikationer" in res.sektioner[0].tomtext

def test_momsoversikt_saknas():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_momsoversikt_vy(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_momsoversikt_rubrik_innehaller_beraknad():
    data = Vydata(idag=date(2026, 8, 6), momsoversikt={"poster": {}, "konton": []})
    res = bygg_momsoversikt_vy(data)
    assert "beräknad" in res.rubrik.lower()

def test_momsoversikt_fotnot_finns():
    data = Vydata(idag=date(2026, 8, 6), momsoversikt={"poster": {}, "konton": []})
    res = bygg_momsoversikt_vy(data)
    assert "inte en momsdeklaration" in (res.fotnot or "").lower()

def test_momsoversikt_nettoberakning():
    mo = {
        "poster": {
            "utgaende_moms": Decimal("1000"),
            "ingaende_moms": Decimal("400"),
            "att_betala": Decimal("600")
        },
        "konton": [
            {"kontonr": "2611", "kontonamn": "Utg moms", "saldo": Decimal("-1000")},
            {"kontonr": "2641", "kontonamn": "Ing moms", "saldo": Decimal("400")}
        ]
    }
    data = Vydata(idag=date(2026, 8, 6), momsoversikt=mo, formateringsval=Formateringsval(decimaler=2))
    res = bygg_momsoversikt_vy(data)
    assert "1 000,00" in res.nyckeltal[0].varde
    assert "400,00" in res.nyckeltal[1].varde
    assert "600,00" in res.nyckeltal[2].varde
    assert res.sektioner[0].tabell.rader[0]["kontonr"] == "2611"

def test_verifikatutkast_saknas():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_verifikatutkast(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_verifikatutkast_summering():
    u = {
        "verdatum": "2026-08-01",
        "serie": "A",
        "vertext": "Utkast",
        "rader": [
            {"belopp": 100},
            {"belopp": -100}
        ]
    }
    data = Vydata(idag=date(2026, 8, 6), verifikatutkast=[u], formateringsval=Formateringsval(decimaler=2))
    res = bygg_verifikatutkast(data)
    assert res.nyckeltal[0].varde == "1"
    assert "100,00" in res.nyckeltal[1].varde
    assert res.sektioner[0].tabell.rader[0]["summa"] == "100,00 kr"
    assert res.sektioner[0].tabell.rader[0]["rader"] == "2" # Antal rader

def test_verifikatutkast_beskrivning_finns():
    data = Vydata(idag=date(2026, 8, 6), verifikatutkast=[])
    res = bygg_verifikatutkast(data)
    assert "påverkar inte räkenskaperna" in res.sektioner[0].beskrivning

