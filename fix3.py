import re
from pathlib import Path

# Fix test_kunder_skickar_odata
f1 = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_spiris_adapter.py")
c1 = f1.read_text("utf-8")
c1 = c1.replace(
    'def test_kunder_skickar_odata(self):\n        from spiris_adapter import hamta_kunder\n        klient = self._FangarKlient()\n        hamta_kunder(klient, filter="Namn", select=["Id"], orderby="Namn", pagesize=10)\n        assert klient.anrop[0] == ("/currencies", "Namn", ["Id"], "Namn", 10)',
    'def test_kunder_skickar_odata(self):\n        from spiris_adapter import hamta_kunder\n        klient = self._FangarKlient()\n        hamta_kunder(klient, filter="Namn", select=["Id"], orderby="Namn", pagesize=10)\n        assert klient.anrop[0] == ("/customers", "Namn", ["Id"], "Namn", 10)'
)
f1.write_text(c1, "utf-8")

# Fix hamta_referensdata in spiris_adapter.py
f2 = Path("G:/My Drive/Claude Cowork/sie-mcp/parser/spiris_adapter.py")
c2 = f2.read_text("utf-8")
c2 = c2.replace(
    'for rå in klient.hamta_alla(path):',
    'for rå in klient.hamta_alla(path, filter=filter, select=select, orderby=orderby, pagesize=pagesize):'
)
f2.write_text(c2, "utf-8")
