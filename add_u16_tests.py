import os
from pathlib import Path

fpath = "tests/test_mcp_lasande_bredd.py"
content = Path(fpath).read_text(encoding="utf-8")

# 1. Update imports
from_import = "spiris_kvittningskandidater,"
new_imports = "spiris_kvittningskandidater,\n    spiris_prislistor, spiris_rabattavtal, spiris_etiketter,"
content = content.replace(from_import, new_imports)

# 2. Add to ALLA_SPIRISVERKTYG
old_dict = '"spiris_kvittningskandidater": lambda: spiris_kvittningskandidater("inv-1"),\n}'
new_dict = '"spiris_kvittningskandidater": lambda: spiris_kvittningskandidater("inv-1"),\n    "spiris_prislistor": lambda: spiris_prislistor(),\n    "spiris_rabattavtal": lambda: spiris_rabattavtal(),\n    "spiris_etiketter": lambda: spiris_etiketter("kund"),\n}'
content = content.replace(old_dict, new_dict)

# 3. Add to _FejkKlient mock responses
old_mock = '        if path == "/fiscalyears/openingbalances":\n            return _OPENING_BALANCES\n        raise AssertionError(f"oväntad hamta_alla: {path}")'
new_mock = '''        if path == "/fiscalyears/openingbalances":
            return _OPENING_BALANCES
        if path.startswith("/salespricelists"):
            return [{"Id": "123", "Name": "Lista"}]
        if path == "/discountagreements":
            return [{"Id": "123", "Name": "Avtal"}]
        if path in ("/customerlabels", "/articlelabels"):
            return [{"Id": "123", "Name": "Etikett"}]
        raise AssertionError(f"oväntad hamta_alla: {path}")'''
content = content.replace(old_mock, new_mock)

Path(fpath).write_text(content, encoding="utf-8")
