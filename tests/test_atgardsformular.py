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
    
def test_metatest_varje_utkasttyp_finns_i_giltiga():
    formular_typer = {f.utkasttyp for f in ALLA_FORMULAR}
    for t in formular_typer:
        assert t in GILTIGA_TYPER, f"{t} finns inte i GILTIGA_TYPER"

@pytest.mark.xfail(strict=True, reason="Stängs i U9 (saknar formulär för rotrut/bokforingslas m.fl)")
def test_metatest_varje_giltig_typ_har_ett_formular():
    formular_typer = {f.utkasttyp for f in ALLA_FORMULAR}
    for t in GILTIGA_TYPER:
        assert t in formular_typer, f"Giltig typ {t} saknar formulär"

@pytest.mark.xfail(strict=True, reason="Stängs i U9 (inte alla formulär är inkopplade)")
def test_metatest_varje_formular_importeras_av_rum_render():
    import ast
    
    with open("parser/rum_render.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    importerade_namn = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "atgardsformular" or node.module == "parser.atgardsformular":
                for alias in node.names:
                    importerade_namn.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # If imported as `import parser.atgardsformular`, we'd check usage, but forms are imported explicitly usually.
                pass
                
    for f_obj in ALLA_FORMULAR:
        # We need to find the variable name in ALLA_FORMULAR
        # But ALLA_FORMULAR is a list of objects. How to know their variable name?
        pass

    # A better way to check if it's imported is to check if the specific variable name (e.g., VERIFIKAT_FORMULAR) is imported.
    # We can get the variable name by looking at the globals in atgardsformular.py
    import parser.atgardsformular as af
    for var_name, var_val in vars(af).items():
        if getattr(var_val, "__class__", None) is not None and var_val.__class__.__name__ == "Atgardsformular":
            if var_val in ALLA_FORMULAR:
                assert var_name in importerade_namn, f"Formuläret {var_name} importeras inte av rum_render.py"

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
    assert res == {"fakturanummer": "1"}
    
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
