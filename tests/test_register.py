from datetime import date
from decimal import Decimal
from parser.snabbvyer import (
    Vydata,
    bygg_kunder,
    bygg_leverantorer,
    bygg_artiklar,
    bygg_projekt,
    bygg_kostnadsstallen,
    bygg_referensdata,
)

def test_kunder_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_kunder(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_kunder_maskerad_markor():
    data = Vydata(
        idag=date(2026, 8, 6),
        kunder=[
            {"kundnummer": "1", "namn": "Fiktiv", "maskerad": True},
            {"kundnummer": "2", "namn": "Verklig", "maskerad": False},
        ]
    )
    res = bygg_kunder(data)
    rader = res.sektioner[0].tabell.rader
    assert "🔒" in rader[0]["namn"]
    assert "🔒" not in rader[1]["namn"]

def test_kunder_summering_och_kolumner():
    data = Vydata(
        idag=date(2026, 8, 6),
        kunder=[
            {"kundnummer": "1", "namn": "K1", "obetalt_belopp": "100.50"},
            {"kundnummer": "2", "namn": "K2", "obetalt_belopp": "200.25"},
        ]
    )
    res = bygg_kunder(data)
    assert "301 kr" in res.nyckeltal[2].varde or "300 kr" in res.nyckeltal[2].varde
    
    kolumner = [k.nyckel for k in res.sektioner[0].tabell.kolumner]
    assert "epost" not in kolumner
    assert "telefon" not in kolumner

def test_leverantorer_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_leverantorer(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_leverantorer_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        leverantorer=[
            {"leverantorsnummer": "1", "namn": "Lev1", "maskerad": True, "obetalt_belopp": "500"},
        ]
    )
    res = bygg_leverantorer(data)
    rader = res.sektioner[0].tabell.rader
    assert "🔒" in rader[0]["namn"]
    assert "500 kr" in res.nyckeltal[2].varde

def test_artiklar_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_artiklar(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_artiklar_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        artiklar=[
            {"artikelnr": "A1", "namn": "Bord", "pris": "1500", "enhet": "st", "konto": "3001", "aktiv": True},
        ]
    )
    res = bygg_artiklar(data)
    assert res.nyckeltal[0].varde == "1"

def test_projekt_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_projekt(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_projekt_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        projekt=[
            {"nummer": "P1", "namn": "Bygge", "kund": "K1", "maskerad": True},
        ]
    )
    res = bygg_projekt(data)
    assert "🔒" in res.sektioner[0].tabell.rader[0]["kund"]
    assert "🔒" not in res.sektioner[0].tabell.rader[0]["namn"]

def test_kostnadsstallen_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_kostnadsstallen(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_kostnadsstallen_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        kostnadsstallen=[
            {"nummer": "10", "namn": "VD", "aktiv": True},
        ]
    )
    res = bygg_kostnadsstallen(data)
    assert res.nyckeltal[0].varde == "1"

def test_referensdata_tomt():
    data = Vydata(idag=date(2026, 8, 6), vald_referenstyp="enheter")
    res = bygg_referensdata(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_referensdata_krav_val():
    data = Vydata(idag=date(2026, 8, 6), vald_referenstyp="")
    res = bygg_referensdata(data)
    assert "Välj en referenstyp" in res.sektioner[0].beskrivning

def test_referensdata_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        vald_referenstyp="enheter",
        referensdata=[
            {"kod": "st", "namn": "Styck"},
            {"kod": "tim", "namn": "Timmar"},
        ]
    )
    res = bygg_referensdata(data)
    assert res.nyckeltal[0].varde == "2"
    assert res.sektioner[0].tabell.kolumner[0].nyckel == "kod"
    assert res.sektioner[0].tabell.kolumner[1].nyckel == "namn"
    assert "maskeras medvetet inte" in res.sektioner[0].beskrivning

def test_referensdata_okand_typ_tom_lista():
    data = Vydata(
        idag=date(2026, 8, 6),
        vald_referenstyp="okand",
        referensdata=[]
    )
    res = bygg_referensdata(data)
    assert "Listan är tom" in res.sektioner[0].tomtext
