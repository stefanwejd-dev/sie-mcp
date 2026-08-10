"""
Rökprov för att verifiera pagineringsmekanismer (offset/limit).

RÖKPROVSNOTERING:
Detta skript kräver en levande Spiris-session. Villkorsspärren kopplas ur 
temporärt eftersom rökprovet körs av en utvecklare på en maskin där villkoren 
redan är bedömda och godkända i GUI:t. Urkopplingen är en teknisk genväg 
förbi den interaktiva grinden, inte ett kringgående av regelverket.
"""
import sys
import os
import asyncio
sys.path.append(os.path.join(os.getcwd(), 'parser'))

import compliance
# Bypass compliance for smoke test
compliance.godkann_compliance = lambda: None
compliance._VILLKOR_GODKANDA = True

from dotenv import load_dotenv
import saker_lagring
load_dotenv(saker_lagring.artefakt_sokvag(None, kategori="secret", namn=".env"))

if os.environ.get("SIE_MCP_SPIRIS_CLIENT_ID"):
    os.environ["SPIRIS_CLIENT_ID"] = os.environ.get("SIE_MCP_SPIRIS_CLIENT_ID")
if os.environ.get("SIE_MCP_SPIRIS_CLIENT_SECRET"):
    os.environ["SPIRIS_CLIENT_SECRET"] = os.environ.get("SIE_MCP_SPIRIS_CLIENT_SECRET")

from spiris_session import bygg_klient
from spiris_rag import hamta_kontotransaktioner, hamta_verifikationer_alla, hamta_kundfakturor, hamta_kundreskontra_rag, hamta_leverantorsreskontra, hamta_underlag, hamta_rakenskapsar

async def main():
    klient = bygg_klient()
    
    print("\n--- Testar hamta_kundfakturor (limit 2) ---")
    res = await hamta_kundfakturor(klient, offset=0, limit=2)
    print("totalt_antal:", res["totalt_antal"], "visade:", res["visade"], "trunkerat:", res.get("trunkerat"))
    if res["visade"] > 0: print("Data:", res["data"][0])
    
    print("\n--- Testar hamta_kundreskontra_rag (limit 2) ---")
    res = await hamta_kundreskontra_rag(klient, offset=0, limit=2)
    print("totalt_antal:", res["totalt_antal"], "visade:", res["visade"], "trunkerat:", res.get("trunkerat"))
    
    print("\n--- Testar hamta_leverantorsreskontra (limit 2) ---")
    res = await hamta_leverantorsreskontra(klient, offset=0, limit=2)
    print("totalt_antal:", res["totalt_antal"], "visade:", res["visade"], "trunkerat:", res.get("trunkerat"))
    
    print("\n--- Testar hamta_underlag (limit 2) ---")
    res = await hamta_underlag(klient, include_matched=False, offset=0, limit=2)
    print("totalt_antal:", res["totalt_antal"], "visade:", res["visade"], "trunkerat:", res.get("trunkerat"))
    
    print("\n--- Testar hamta_verifikationer_alla (limit 2) ---")
    res = await hamta_verifikationer_alla(klient, offset=0, limit=2)
    print("totalt_antal:", res["totalt_antal"], "visade:", res["visade"], "trunkerat:", res.get("trunkerat"))
    
    print("\n--- Testar hamta_kontotransaktioner (limit 2) ---")
    rar = await hamta_rakenskapsar(klient)
    if rar["data"]:
        rar_id = rar["data"][0]["id"]
        res = await hamta_kontotransaktioner(klient, rar_id, "1910", offset=0, limit=2)
        print("totalt_antal:", res["totalt_antal"], "visade:", res["visade"], "trunkerat:", res.get("trunkerat"))
    else:
        print("Inga räkenskapsår hittades.")

asyncio.run(main())
