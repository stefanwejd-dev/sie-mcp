import os
import json

# Läs server.py
with open("mcp_server/server.py", "r", encoding="utf-8") as f:
    text = f.read()

# Lägg till resurser och prompter i slutet av server.py
# Kontrollera om de redan finns
if "@mcp.resource" not in text:
    tillägg = """
# ============================================================================
# RESURSER
# ============================================================================

@mcp.resource("spiris://foretag")
async def res_foretag() -> str:
    svar = await spiris_foretagsinfo()
    return json.dumps(svar, ensure_ascii=False, indent=2)

@mcp.resource("spiris://rakenskapsar")
async def res_rakenskapsar() -> str:
    svar = await spiris_rakenskapsar()
    return json.dumps(svar, ensure_ascii=False, indent=2)

@mcp.resource("spiris://kontoplan/{rakenskapsar_id}")
async def res_kontoplan(rakenskapsar_id: str) -> str:
    svar = await spiris_kontoplan(rakenskapsar_id)
    return json.dumps(svar, ensure_ascii=False, indent=2)

@mcp.resource("spiris://villkor")
def res_villkor() -> str:
    svar = visa_anvandarvillkor()
    return json.dumps(svar, ensure_ascii=False, indent=2)

# ============================================================================
# PROMPTER
# ============================================================================

_PROMPT_VARNING = "\\n\\nInget skrivs förrän en människa godkänt i Streamlit-appen."

@mcp.prompt()
def stam_av_banken() -> str:
    return "Hämta bankkonton, granska omatchade bankhändelser och visa därefter avstämningsläge." + _PROMPT_VARNING

@mcp.prompt()
def granska_momsperioden() -> str:
    return "Kontrollera momsöversikt, hämta relevanta momskoder och visa sedan momsrapporter." + _PROMPT_VARNING

@mcp.prompt()
def manadsavstamning() -> str:
    return "Hämta resultatrapport och balansrapport, granska specifika kontosaldon och utför till sist väsentlighet." + _PROMPT_VARNING

@mcp.prompt()
def granska_kundfordringar() -> str:
    return "Analysera kundreskontra, undersök kundbetalbeteende och visa slutligen likviditetsprognos." + _PROMPT_VARNING

@mcp.prompt()
def forbered_bokslutsposter() -> str:
    return "Läs ingående balans, granska periodiseringar och kontrollera anläggningstillgångar." + _PROMPT_VARNING
"""
    with open("mcp_server/server.py", "w", encoding="utf-8") as f:
        f.write(text + tillägg)
    print("Resurser och prompter tillagda i server.py")
else:
    print("Resurser och prompter finns redan i server.py")
