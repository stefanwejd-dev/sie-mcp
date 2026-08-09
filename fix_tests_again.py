import os
import re

# 1. Fix test_etapp5.py (add compliance godkannande)
with open("tests/test_etapp5.py", "r", encoding="utf-8") as f:
    code = f.read()

if "import compliance" not in code:
    code = code.replace("from mcp_server import server", "from mcp_server import server\nimport compliance")

code = code.replace(
    'def test_forbered_betalningsverifikat_ok():',
    'def test_forbered_betalningsverifikat_ok():\n    compliance.godkann_compliance()'
)

code = code.replace(
    'def test_forbered_betalningsverifikat_balans():',
    'def test_forbered_betalningsverifikat_balans():\n    compliance.godkann_compliance()'
)

with open("tests/test_etapp5.py", "w", encoding="utf-8") as f:
    f.write(code)

# 2. Fix parser/spiris_rag.py (maskerare is a function, not an object with a .maskera method)
with open("parser/spiris_rag.py", "r", encoding="utf-8") as f:
    code = f.read()

code = code.replace(
    'maskerare.maskera(k.get("SupplierName") or "")',
    'maskerare(k.get("SupplierName") or "")'
)

with open("parser/spiris_rag.py", "w", encoding="utf-8") as f:
    f.write(code)
