import os

fpath = "tests/test_mcp_villkorssparr.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

new_funcs = '''    "spiris_prislistor": server_modul.spiris_prislistor,
    "spiris_rabattavtal": server_modul.spiris_rabattavtal,
    "spiris_etiketter": server_modul.spiris_etiketter,
'''

content = content.replace('"spiris_offertutkast": spiris_offertutkast,', '"spiris_offertutkast": spiris_offertutkast,\n' + new_funcs)

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)
