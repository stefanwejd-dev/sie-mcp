import re

def update_file(path, replacements):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"WARNING: Could not find snippet in {path}:\n{old}")
        content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# 1. Update _envelope in spiris_rag.py
old_env = """def _envelope(data: list[dict], antal_exkluderade: int) -> dict[str, Any]:
    \"\"\"Standardiserat returobjekt med fail-closed-transparens: räknare + text
    som talar om för LLM:en att blockerad data undanhållits.\"\"\"
    if antal_exkluderade:
        info = f"{antal_exkluderade} poster exkluderades pga olösta maskeringsbehov"
    else:
        info = "Inga poster exkluderades"
    return {
        "data": data,
        "antal_exkluderade": antal_exkluderade,
        "info": info,
        "sakerhetsnot": SAKERHETSNOT,
    }"""

new_env = """def _envelope(data: list[dict], antal_exkluderade: int, offset: int = 0, limit: int = 0) -> dict[str, Any]:
    \"\"\"Standardiserat returobjekt med sidbrytning och fail-closed-transparens.\"\"\"
    totalt = len(data)
    if limit > 0:
        visad_data = data[offset : offset + limit]
        trunkerat = (offset + limit) < totalt
    else:
        visad_data = data[offset:] if offset > 0 else data
        trunkerat = False
        
    visade = len(visad_data)
    if antal_exkluderade:
        info = f"{antal_exkluderade} poster exkluderades pga olösta maskeringsbehov"
    else:
        info = "Inga poster exkluderades"
        
    if trunkerat:
        nasta = offset + limit
        info += f" | TRUNKERAT: Visar {visade} av {totalt}. Hämta resten genom att ange offset={nasta} och limit={limit}."
        
    return {
        "data": visad_data,
        "antal_exkluderade": antal_exkluderade,
        "totalt_antal": totalt,
        "visade": visade,
        "trunkerat": trunkerat,
        "info": info,
        "sakerhetsnot": SAKERHETSNOT,
    }"""

# Replacements in spiris_rag.py
rag_replacements = [
    (old_env, new_env),
    ("def hamta_kontotransaktioner(\n    klient: _Spirisklient, rakenskapsar_id: str, kontonr: str\n) -> dict[str, Any]:", 
     "def hamta_kontotransaktioner(\n    klient: _Spirisklient, rakenskapsar_id: str, kontonr: str, offset: int = 0, limit: int = 0\n) -> dict[str, Any]:"),
    ("return _envelope(mappade, antal_exkluderade=exkluderade)", "return _envelope(mappade, antal_exkluderade=exkluderade, offset=offset, limit=limit)"),
    
    ("def hamta_verifikationer_alla(\n    klient: _Spirisklient, fran_datum: str | None = None, till_datum: str | None = None\n) -> dict[str, Any]:", 
     "def hamta_verifikationer_alla(\n    klient: _Spirisklient, fran_datum: str | None = None, till_datum: str | None = None, offset: int = 0, limit: int = 0\n) -> dict[str, Any]:"),
    
    ("def hamta_kundfakturor(klient: _Spirisklient) -> dict[str, Any]:", "def hamta_kundfakturor(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:"),
    ("return _envelope(tvattad, antal_exkluderade=0)", "return _envelope(tvattad, antal_exkluderade=0, offset=offset, limit=limit)"),
    
    ("def hamta_kundreskontra(klient: _Spirisklient) -> dict[str, Any]:", "def hamta_kundreskontra(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:"),
    ("return _envelope([_kundpost_till_dict(p) for p in poster], antal_exkluderade=0)", "return _envelope([_kundpost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit)"),
    
    ("def hamta_leverantorsreskontra(klient: _Spirisklient) -> dict[str, Any]:", "def hamta_leverantorsreskontra(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:"),
    ("return _envelope([_leverantorspost_till_dict(p) for p in poster], antal_exkluderade=0)", "return _envelope([_leverantorspost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit)"),
    
    ("def hamta_underlag(klient, include_matched: bool) -> dict:", "def hamta_underlag(klient, include_matched: bool, offset: int = 0, limit: int = 0) -> dict:"),
]

# Note: hamta_underlag has multiple _envelope calls or just one? Let's check:
# "return _envelope(tvattad, antal_exkluderade=0)" is common. The script might replace multiple instances, which is fine!
# But wait, we only want to add offset and limit to the functions requested. We must be careful!
# Instead of a global replace, I'll use regex for each specific function's return in spiris_rag.py.

with open("parser/spiris_rag.py", "r", encoding="utf-8") as f:
    rag_content = f.read()

rag_content = rag_content.replace(old_env, new_env)

# hamta_kontotransaktioner
rag_content = re.sub(
    r'def hamta_kontotransaktioner\(\n    klient: _Spirisklient, rakenskapsar_id: str, kontonr: str\n\) -> dict\[str, Any\]:',
    r'def hamta_kontotransaktioner(\n    klient: _Spirisklient, rakenskapsar_id: str, kontonr: str, offset: int = 0, limit: int = 0\n) -> dict[str, Any]:',
    rag_content
)
rag_content = re.sub(
    r'def hamta_verifikationer_alla\(\n    klient: _Spirisklient, fran_datum: str \| None = None, till_datum: str \| None = None\n\) -> dict\[str, Any\]:',
    r'def hamta_verifikationer_alla(\n    klient: _Spirisklient, fran_datum: str | None = None, till_datum: str | None = None, offset: int = 0, limit: int = 0\n) -> dict[str, Any]:',
    rag_content
)
rag_content = re.sub(
    r'def hamta_kundfakturor\(klient: _Spirisklient\) -> dict\[str, Any\]:',
    r'def hamta_kundfakturor(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:',
    rag_content
)
rag_content = re.sub(
    r'def hamta_kundreskontra\(klient: _Spirisklient\) -> dict\[str, Any\]:',
    r'def hamta_kundreskontra(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:',
    rag_content
)
rag_content = re.sub(
    r'def hamta_leverantorsreskontra\(klient: _Spirisklient\) -> dict\[str, Any\]:',
    r'def hamta_leverantorsreskontra(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:',
    rag_content
)
rag_content = re.sub(
    r'async def hamta_underlag\(klient, include_matched: bool\) -> dict:',
    r'async def hamta_underlag(klient, include_matched: bool, offset: int = 0, limit: int = 0) -> dict:',
    rag_content
)

# Replace returns carefully.
def replace_return(func_name, code, new_return):
    # finds the function, then the first return _envelope inside it
    start_idx = code.find(f"def {func_name}(")
    if start_idx == -1: return code
    ret_idx = code.find("return _envelope(", start_idx)
    if ret_idx == -1: return code
    end_idx = code.find(")", ret_idx) + 1
    return code[:ret_idx] + new_return + code[end_idx:]

rag_content = replace_return("hamta_kontotransaktioner", rag_content, "return _envelope(mappade, antal_exkluderade=exkluderade, offset=offset, limit=limit)")
rag_content = replace_return("hamta_verifikationer_alla", rag_content, "return _envelope(mappade, antal_exkluderade=exkluderade, offset=offset, limit=limit)")
rag_content = replace_return("hamta_kundfakturor", rag_content, "return _envelope(tvattad, antal_exkluderade=0, offset=offset, limit=limit)")
rag_content = replace_return("hamta_kundreskontra", rag_content, "return _envelope([_kundpost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit)")
rag_content = replace_return("hamta_leverantorsreskontra", rag_content, "return _envelope([_leverantorspost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit)")
rag_content = replace_return("hamta_underlag", rag_content, "return _envelope(tvattad, antal_exkluderade=0, offset=offset, limit=limit)")

with open("parser/spiris_rag.py", "w", encoding="utf-8") as f:
    f.write(rag_content)

print("Updated spiris_rag.py")

# 2. Update server.py
with open("mcp_server/server.py", "r", encoding="utf-8") as f:
    server_content = f.read()

server_content = server_content.replace(
    "async def spiris_kontotransaktioner(rakenskapsar_id: str, kontonr: str) -> dict:",
    "async def spiris_kontotransaktioner(rakenskapsar_id: str, kontonr: str, offset: int = 0, limit: int = 0) -> dict:"
).replace(
    "lambda k: spiris_rag.hamta_kontotransaktioner(k, rakenskapsar_id, kontonr)",
    "lambda k: spiris_rag.hamta_kontotransaktioner(k, rakenskapsar_id, kontonr, offset, limit)"
)

server_content = server_content.replace(
    "async def spiris_verifikationer_alla(fran_datum: str | None = None, till_datum: str | None = None) -> dict:",
    "async def spiris_verifikationer_alla(fran_datum: str | None = None, till_datum: str | None = None, offset: int = 0, limit: int = 0) -> dict:"
).replace(
    "lambda k: spiris_rag.hamta_verifikationer_alla(k, fran_datum, till_datum)",
    "lambda k: spiris_rag.hamta_verifikationer_alla(k, fran_datum, till_datum, offset, limit)"
)

server_content = server_content.replace(
    "async def spiris_kundfakturor() -> dict:",
    "async def spiris_kundfakturor(offset: int = 0, limit: int = 0) -> dict:"
).replace(
    "lambda k: spiris_rag.hamta_kundfakturor(k)",
    "lambda k: spiris_rag.hamta_kundfakturor(k, offset, limit)"
)

server_content = server_content.replace(
    "async def spiris_kundreskontra() -> dict:",
    "async def spiris_kundreskontra(offset: int = 0, limit: int = 0) -> dict:"
).replace(
    "lambda k: spiris_rag.hamta_kundreskontra(k)",
    "lambda k: spiris_rag.hamta_kundreskontra(k, offset, limit)"
)

server_content = server_content.replace(
    "async def spiris_leverantorsreskontra() -> dict:",
    "async def spiris_leverantorsreskontra(offset: int = 0, limit: int = 0) -> dict:"
).replace(
    "lambda k: spiris_rag.hamta_leverantorsreskontra(k)",
    "lambda k: spiris_rag.hamta_leverantorsreskontra(k, offset, limit)"
)

server_content = server_content.replace(
    "async def spiris_underlag(include_matched: bool = False) -> str:",
    "async def spiris_underlag(include_matched: bool = False, offset: int = 0, limit: int = 0) -> str:"
).replace(
    "lambda k: spiris_rag.hamta_underlag(k, include_matched)",
    "lambda k: spiris_rag.hamta_underlag(k, include_matched, offset, limit)"
)

with open("mcp_server/server.py", "w", encoding="utf-8") as f:
    f.write(server_content)
    
print("Updated server.py")

