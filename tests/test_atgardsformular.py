import pytest
from parser.atgardsformular import (
    Falt, Atgardsformular, ALLA_FORMULAR,
    VERIFIKAT, SIE4IMPORT, FAKTURAUTSKICK, BETALNINGSPAMINNELSE,
    BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK,
    SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD, LEVERANTORSFAKTURAUTKAST,
    LEVERANTORSBETALNING, ATTEST, MASTERDATAANDRING, MASTERDATABORTTAGNING
)
from parser.utkast import GILTIGA_TYPER
from parser.spiris_adapter import _BORTTAGBARA

def test_dataclasses():
    f = Falt("test", "Test", "text")
    assert f.nyckel == "test"
    assert f.obligatoriskt is True
    
def test_metatest_at_bada_hallen():
    formular_typer = {f.utkasttyp for f in ALLA_FORMULAR}
    
    # Alla formulärtyper måste finnas i GILTIGA_TYPER
    for t in formular_typer:
        assert t in GILTIGA_TYPER, f"{t} finns inte i GILTIGA_TYPER"
        
    # Alla giltiga typer (utom kund, kundfaktura) måste ha ett formulär
    undantagna = {"kund", "kundfaktura", "underlagskoppling"}
    for t in GILTIGA_TYPER:
        if t not in undantagna:
            assert t in formular_typer, f"Giltig typ {t} saknar formulär"

def test_bygg_nyttolast_ren_funktion():
    varden = {"beskrivning": "test", "rader": '[{"debet": 100}, {"kredit": 100}]'}
    varden_copy = varden.copy()
    res1 = VERIFIKAT.bygg_nyttolast(varden)
    res2 = VERIFIKAT.bygg_nyttolast(varden)
    assert res1 == res2
    assert varden == varden_copy # Inga sidoeffekter på indata

def test_verifikat_nyttolast():
    res = VERIFIKAT.bygg_nyttolast({"beskrivning": "A", "datum": "2026-01-01", "rader": '[{"debet": 100}, {"kredit": 100}]'})
    assert "beskrivning" in res
    assert "transaktionsdatum" in res
    assert "rader" in res
    
def test_verifikat_balanskontroll():
    with pytest.raises(ValueError, match="balanserar inte"):
        VERIFIKAT.bygg_nyttolast({
            "beskrivning": "A", 
            "datum": "2026-01-01", 
            "rader": '[{"debet": 100, "kredit": 90}]'
        })
        
def test_sie4import_nyttolast():
    res = SIE4IMPORT.bygg_nyttolast({"sokvag": "x.se"})
    assert "sokvag" in res
    assert "skriv_over_saldon" in res

def test_fakturautskick_nyttolast():
    res = FAKTURAUTSKICK.bygg_nyttolast({"fakturanummer": "1"})
    assert "fakturanummer" in res
    
def test_betalningspaminnelse_nyttolast():
    res = BETALNINGSPAMINNELSE.bygg_nyttolast({"fakturanummer": "1", "drojsmalsavgift": ""})
    assert res["drojsmalsavgift"] is None
    
    res2 = BETALNINGSPAMINNELSE.bygg_nyttolast({"fakturanummer": "1", "drojsmalsavgift": "50"})
    assert res2["drojsmalsavgift"] == 50.0

def test_betalningsregistrering_nyttolast():
    res = BETALNINGSREGISTRERING.bygg_nyttolast({"fakturanummer": "1", "belopp": "100"})
    assert res["belopp"] == 100.0
    
def test_makulering_nyttolast():
    res = MAKULERING.bygg_nyttolast({"fakturanummer": "1", "motivering": "Fel"})
    assert "motivering" in res
    
def test_efakturautskick_nyttolast():
    res = EFAKTURAUTSKICK.bygg_nyttolast({"fakturanummer": "1"})
    assert "fakturanummer" in res
    
def test_saljdokumentutskick_nyttolast():
    res = SALJDOKUMENTUTSKICK.bygg_nyttolast({"dokumenttyp": "offert"})
    assert "dokumenttyp" in res
    
def test_saljdokumentatgard_nyttolast():
    res = SALJDOKUMENTATGARD.bygg_nyttolast({"atgard": "skapa_order"})
    assert "atgard" in res
    
def test_leverantorsfakturautkast_nyttolast():
    with pytest.raises(ValueError, match="Totalbelopp är obligatoriskt"):
        LEVERANTORSFAKTURAUTKAST.bygg_nyttolast({"fakturanummer": "1"})
        
    res = LEVERANTORSFAKTURAUTKAST.bygg_nyttolast({"totalbelopp": "100"})
    assert res["totalbelopp"] == 100.0
    
def test_leverantorsbetalning_nyttolast():
    res = LEVERANTORSBETALNING.bygg_nyttolast({"faktura": "1", "belopp": "100"})
    assert "faktura" in res
    
def test_attest_nyttolast():
    res = ATTEST.bygg_nyttolast({"beslut": "godkann"})
    assert "beslut" in res

def test_masterdataandring_nyttolast():
    res = MASTERDATAANDRING.bygg_nyttolast({
        "objekttyp": "kund",
        "objekt_id": "1",
        "namn": "Nytt namn",
        "ogiltig": "x"
    })
    assert "andringar" in res
    assert "namn" in res["andringar"]
    assert "ogiltig" not in res["andringar"]
    
def test_masterdataborttagning_nyttolast():
    with pytest.raises(ValueError, match="går inte att ta bort"):
        MASTERDATABORTTAGNING.bygg_nyttolast({"objekttyp": "artikel"})
        
    res = MASTERDATABORTTAGNING.bygg_nyttolast({"objekttyp": "kund", "objekt_id": "1"})
    assert res["objekttyp"] == "kund"
