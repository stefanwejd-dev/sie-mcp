import os

# 1. test_mcp_lasande_bredd.py (NameError: spiris_underlag)
fpath1 = os.path.join("tests", "test_mcp_lasande_bredd.py")
with open(fpath1, "r", encoding="utf-8") as f:
    text1 = f.read()
    
# Find the import block and add them if they are missing
if "from mcp_server.server import (" in text1 and "spiris_underlag" not in text1[:1000]:
    text1 = text1.replace("spiris_sie4export,\n)", "spiris_sie4export,\n    spiris_underlag,\n    spiris_hamta_underlag,\n)")

with open(fpath1, "w", encoding="utf-8") as f:
    f.write(text1)


# 2. test_mcp_villkorssparr.py (AssertionError forbered_underlagskoppling)
fpath2 = os.path.join("tests", "test_mcp_villkorssparr.py")
with open(fpath2, "r", encoding="utf-8") as f:
    text2 = f.read()

# Add to tackta
if '"forbered_underlagskoppling"' not in text2:
    text2 = text2.replace('{"forbered_periodisering"}', '{"forbered_periodisering", "forbered_underlagskoppling"}')
    # Let's also check if forbered_underlagskoppling needs to be imported somewhere else, probably not.

with open(fpath2, "w", encoding="utf-8") as f:
    f.write(text2)


# 3. test_sie4_utbyte.py (AttributeError: skicka_fil)
fpath3 = os.path.join("tests", "test_sie4_utbyte.py")
with open(fpath3, "r", encoding="utf-8") as f:
    text3 = f.read()

if "def skicka_fil(self" not in text3:
    # Add skicka_fil to _Fangare
    text3 = text3.replace('def skicka(self, path, data):\n                self.skickat.append((path, data))\n                return {}', 'def skicka(self, path, data):\n                self.skickat.append((path, data))\n                return {}\n            def skicka_fil(self, path, query, payload, filename):\n                self.skickat.append((path, query, filename))\n                return {}')

with open(fpath3, "w", encoding="utf-8") as f:
    f.write(text3)
