import re
from pathlib import Path

f = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_spiris_adapter.py")
content = f.read_text("utf-8")

# Fix hamta_en mocks
content = re.sub(r'def hamta_en\(self, path, params=None\):', r'def hamta_en(self, path, params=None, **kwargs):', content)
content = re.sub(r'def hamta_en\(self, path\):', r'def hamta_en(self, path, params=None, **kwargs):', content)

# Update test_referensdata_skickar_odata to use a valid referenstyp "valutor"
# And we expect the path to be "/currencies"
content = content.replace(
    'hamta_referensdata(klient, "kunder", filter="Namn", select=["Id"], orderby="Namn", pagesize=10)',
    'hamta_referensdata(klient, "valutor", filter="Namn", select=["Id"], orderby="Namn", pagesize=10)'
)
content = content.replace(
    'assert klient.anrop[0] == ("/customers", "Namn", ["Id"], "Namn", 10)',
    'assert klient.anrop[0] == ("/currencies", "Namn", ["Id"], "Namn", 10)'
)

f.write_text(content, "utf-8")
