import re
from pathlib import Path

# 1. Fix SPIRIS_ARGUMENT in test_mcp_villkorssparr.py
test_file = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_mcp_villkorssparr.py")
c = test_file.read_text("utf-8")
c = re.sub(
    r'("spiris_sie4export": \("2026-01-01", "2026-12-31"\),\n)\}',
    r'\1    "spiris_hamta_ett": ("kund", "123"),\n    "spiris_ingaende_balans": (),\n    "spiris_kontoplan_alla": (),\n    "spiris_kundfakturor": (),\n    "spiris_verifikationer_alla": (),\n    "spiris_valutakurs": ("2026-01-01", "SEK", "EUR"),\n    "spiris_anlaggningstillgangar": (),\n    "spiris_kundreskontraposter": (),\n    "spiris_anvandare": (),\n}',
    c
)
test_file.write_text(c, "utf-8")
