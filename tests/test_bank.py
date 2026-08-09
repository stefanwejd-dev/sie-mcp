from datetime import date
from decimal import Decimal
from parser.snabbvyer import (
    Vydata,
    bygg_bankkonton,
    bygg_avstamningslage,
    bygg_bankhandelser,
)

def test_bankkonton_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_bankkonton(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_bankkonton_innehall():
    data = Vydata(
        idag=date(2026, 8, 6),
        bankkonton=[
            {"id": "b1", "namn": "Företagskonto", "bas_konto": "1930", "saldo": "10000.50", "valuta": "SEK"},
            {"id": "b2", "namn": "Sparkonto", "bas_konto": "1940", "saldo": "5000", "valuta": "SEK"},
        ]
    )
    res = bygg_bankkonton(data)
    assert "15 001 kr" in res.nyckeltal[1].varde or "15 000 kr" in res.nyckeltal[1].varde
    
    # ID ska inte synas
    rader = res.sektioner[0].tabell.rader
    assert "b1" not in rader[0].values()

def test_bankkonton_id_dolt():
    data = Vydata(idag=date(2026, 8, 6), bankkonton=[{"id": "HEMLIGT_ID", "namn": "Konto", "saldo": "0"}])
    res = bygg_bankkonton(data)
    for k in res.sektioner[0].tabell.kolumner:
        assert k.nyckel != "id"
    for rad in res.sektioner[0].tabell.rader:
        assert "HEMLIGT_ID" not in rad.values()

def test_avstamningslage_tomt():
    data = Vydata(idag=date(2026, 8, 6))
    res = bygg_avstamningslage(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_avstamningslage_nivaer():
    data = Vydata(
        idag=date(2026, 8, 6),
        avstamningslage=[
            {"bankkonto": "K1", "antal_omatchade": 0, "summa_omatchade": "0"},
            {"bankkonto": "K2", "antal_omatchade": 1, "summa_omatchade": "100"},
            {"bankkonto": "K3", "antal_omatchade": 9, "summa_omatchade": "900"},
            {"bankkonto": "K4", "antal_omatchade": 10, "summa_omatchade": "1000"},
        ]
    )
    res = bygg_avstamningslage(data)
    assert res.sektioner[0].niva == "framgang" # 0
    assert res.sektioner[1].niva == "varning" # 1
    assert res.sektioner[2].niva == "varning" # 9
    assert res.sektioner[3].niva == "fara" # 10

def test_avstamningslage_aldsta_datum():
    data = Vydata(
        idag=date(2026, 8, 6),
        avstamningslage=[
            {"bankkonto": "K1", "antal_omatchade": 1, "summa_omatchade": "100", "aldsta_omatchad": "2026-08-01"},
        ]
    )
    res = bygg_avstamningslage(data)
    assert res.sektioner[0].tabell.rader[0]["aldsta"] == "2026-08-01"

def test_avstamningslage_noll_omatchade():
    data = Vydata(idag=date(2026, 8, 6), avstamningslage=[])
    res = bygg_avstamningslage(data)
    assert "Inga obokförda banktransaktioner" in res.sektioner[0].beskrivning

def test_bankhandelser_tomt():
    data = Vydata(idag=date(2026, 8, 6), bankkonto_id="valt_konto")
    res = bygg_bankhandelser(data)
    assert "saknas" in res.sektioner[0].tomtext

def test_bankhandelser_krav_konto():
    data = Vydata(idag=date(2026, 8, 6), bankkonto_id="")
    res = bygg_bankhandelser(data)
    assert "Välj ett bankkonto" in res.sektioner[0].beskrivning

def test_bankhandelser_avstamda():
    data = Vydata(
        idag=date(2026, 8, 6),
        bankkonto_id="K1",
        bankhandelser=[
            {"datum": "2026-08-01", "belopp": "100.50", "avstamd": True, "avgift": "0", "antal_konteringsrader": 2},
            {"datum": "2026-08-02", "belopp": "200", "avstamd": False, "avgift": "5.50", "antal_konteringsrader": 0},
        ]
    )
    res = bygg_bankhandelser(data)
    assert res.nyckeltal[2].varde == "1" # Antal avstämda

def test_bankhandelser_decimal():
    data = Vydata(
        idag=date(2026, 8, 6),
        bankkonto_id="K1",
        bankhandelser=[
            {"datum": "2026-08-01", "belopp": "100.25", "avstamd": True, "avgift": "0"},
            {"datum": "2026-08-02", "belopp": "200.75", "avstamd": False, "avgift": "0"},
        ]
    )
    res = bygg_bankhandelser(data)
    assert "301 kr" in res.nyckeltal[1].varde
