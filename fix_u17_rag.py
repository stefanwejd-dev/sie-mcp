import os
from pathlib import Path

fpath = "parser/spiris_rag.py"
content = Path(fpath).read_text(encoding="utf-8")

old_code = '''def hamta_en_verifikation(k, rakenskapsar_id: str, verifikation_id: str) -> dict:
    """U17.1 — spiris_verifikation"""
    if not rakenskapsar_id or not verifikation_id:
        raise ValueError("Både rakenskapsar_id och verifikation_id måste anges")
    
    rå = k.hamta_en(f"/vouchers/{rakenskapsar_id}/{verifikation_id}")
    return mappa_verifikation(rå)'''

new_code = '''def hamta_en_verifikation(k, rakenskapsar_id: str, verifikation_id: str) -> dict:
    """U17.1 — spiris_verifikation"""
    if not rakenskapsar_id or not verifikation_id:
        raise ValueError("Både rakenskapsar_id och verifikation_id måste anges")
    
    rå = k.hamta_en(f"/vouchers/{rakenskapsar_id}/{verifikation_id}")
    ver = mappa_verifikation(rå)
    
    företag = k.hamta_en("/companysettings")
    sie = SIEFil(
        företagsnamn=företag.get("Name", ""),
        orgnr=företag.get("CorporateIdentityNumber"),
        verifikationer=[ver],
    )
    resultat = maskera_siefil(sie, referenslista=las_namnreferens())
    
    if not resultat.sandningsbara_verifikationer:
        return {"maskerad": True, "vertext": "[DOLD: Säkerhetsskäl - helt blockerad]"}

    v = resultat.sandningsbara_verifikationer[0]
    return {
        "serie": v.serie,
        "vernr": v.vernr,
        "verdatum": str(v.verdatum),
        "vertext": v.vertext,
        "rader": [{"kontonr": r.kontonr, "belopp": str(r.belopp), "transtext": r.transtext} for r in v.transaktioner]
    }'''

content = content.replace(old_code, new_code)
Path(fpath).write_text(content, encoding="utf-8")
