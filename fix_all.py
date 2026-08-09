import os
import re

# 1. FIX spiris_adapter.py
adapter_path = os.path.join("parser", "spiris_adapter.py")
with open(adapter_path, "r", encoding="utf-8") as f:
    adapter_code = f.read()

# Replace the broken SIE4IMPORT block
bad_block = """    if typ == UTKASTTYP_SIE4IMPORT:
        res = klient.skicka("/sie4import", n)
    if typ == UTKASTTYP_UNDERLAGSKOPPLING:
        res = klient.skicka("/attachmentlinks", n)"""
good_block = """    if typ == UTKASTTYP_SIE4IMPORT:
        # Filen läses HÄR, vid utförandet — utkastet bär bara sökvägen och de
        # granskade flaggorna. Innehållet har aldrig passerat en AI, och
        # nyttolastens hash binder användarens beslut (vilken fil, vilka
        # flaggor), inte filens bytes.
        sokvag = Path(nyttolast["sokvag"])
        try:
            innehall = sokvag.read_bytes()
        except OSError as e:
            raise SpirisKlientFel(
                f"Kunde inte läsa SIE4-filen {sokvag.name!r}. "
                "Ingenting har importerats."
            ) from e

        res = klient.skicka_fil("/sie4import", {
            "OpeningBalance": str(nyttolast.get("ingaende_balans", False)).lower(),
            "YearEndVouchers": str(nyttolast.get("arsavslut", False)).lower(),
        }, innehall, sokvag.name)
        
    if typ == UTKASTTYP_UNDERLAGSKOPPLING:
        res = klient.skicka("/attachmentlinks", nyttolast)"""
        
# Try to carefully replace it. Wait, the bad block might have more lines missing. Let's just use re.sub
# The bad block was at line 606. Let's search for UTKASTTYP_SIE4IMPORT
adapter_code = re.sub(
    r'if typ == UTKASTTYP_SIE4IMPORT:\n\s+res = klient\.skicka\("/sie4import", n\)\n\s+if typ == UTKASTTYP_UNDERLAGSKOPPLING:\n\s+res = klient\.skicka\("/attachmentlinks", n\)',
    good_block,
    adapter_code
)

with open(adapter_path, "w", encoding="utf-8") as f:
    f.write(adapter_code)

# 2. FIX test_atgardsformular.py
atg_path = os.path.join("tests", "test_atgardsformular.py")
with open(atg_path, "r", encoding="utf-8") as f:
    atg_code = f.read()

atg_code = atg_code.replace('undantagna = {"kund", "kundfaktura"}', 'undantagna = {"kund", "kundfaktura", "underlagskoppling"}')

with open(atg_path, "w", encoding="utf-8") as f:
    f.write(atg_code)

# 3. FIX test_mcp_lasande_bredd.py
las_path = os.path.join("tests", "test_mcp_lasande_bredd.py")
with open(las_path, "r", encoding="utf-8") as f:
    las_code = f.read()

# Add imports if needed
if "spiris_underlag" not in las_code:
    las_code = las_code.replace("spiris_anvandare,\n)", "spiris_anvandare,\n    spiris_underlag,\n    spiris_hamta_underlag,\n)")

# Add to ALLA_SPIRISVERKTYG
if '"spiris_underlag":' not in las_code:
    las_code = las_code.replace('"spiris_anvandare": lambda: spiris_anvandare(),\n}', '"spiris_anvandare": lambda: spiris_anvandare(),\n    "spiris_underlag": lambda: spiris_underlag(),\n    "spiris_hamta_underlag": lambda: spiris_hamta_underlag("123"),\n}')

# Mock /attachments in _FejkKlient
if 'path.startswith("/attachments")' not in las_code:
    las_code = las_code.replace('if path == "/customers":\n            return _CUSTOMERS', 'if path.startswith("/attachments"):\n            return [{"Id": "123", "FileName": "test.pdf"}]\n        if path == "/customers":\n            return _CUSTOMERS')

    las_code = las_code.replace('if path.startswith("/customers/"):', 'if path.startswith("/attachments/"):\n            return {"Id": "123", "FileName": "test.pdf", "FileContext": "context"}\n        if path.startswith("/customers/"):')

with open(las_path, "w", encoding="utf-8") as f:
    f.write(las_code)

# 4. FIX test_mcp_villkorssparr.py
sparr_path = os.path.join("tests", "test_mcp_villkorssparr.py")
with open(sparr_path, "r", encoding="utf-8") as f:
    sparr_code = f.read()

if "spiris_underlag" not in sparr_code:
    sparr_code = sparr_code.replace("spiris_anvandare,\n)", "spiris_anvandare,\n    spiris_underlag,\n    spiris_hamta_underlag,\n)")

if '"spiris_underlag":' not in sparr_code:
    sparr_code = sparr_code.replace('"spiris_anvandare": (),', '"spiris_anvandare": (),\n    "spiris_underlag": (),\n    "spiris_hamta_underlag": ("123",),')

with open(sparr_path, "w", encoding="utf-8") as f:
    f.write(sparr_code)
