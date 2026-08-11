import re

# Uppdatera PLAN_UI_TACKNING.md
with open("PLAN_UI_TACKNING.md", "r", encoding="utf-8") as f:
    plan = f.read()

plan = plan.replace("| **U7** | Läsvyer: Register | |", "| **U7** | Läsvyer: Register | KLAR |")
plan = plan.replace("| **U8** | Nytt rum Säljdokument + underlag | |", "| **U8** | Nytt rum Säljdokument + underlag | KLAR |")

with open("PLAN_UI_TACKNING.md", "w", encoding="utf-8") as f:
    f.write(plan)


# Uppdatera ARKITEKTUR_UI_TACKNING.md
with open("ARKITEKTUR_UI_TACKNING.md", "r", encoding="utf-8") as f:
    ark = f.read()

# Bilaga A
for typ in ["kvittning", "underlagskoppling", "konto", "kontoandring", "periodiseringsandring", "periodiseringsborttagning", "offertutkast"]:
    ark = re.sub(rf"\|\s*\d+\s*\|\s*`{typ}`\s*\|\s*✅\s*\|\s*❌\s*(?:[a-zA-ZäöåÄÖÅ]+)?\s*\|\s*❌\s*\|\s*(?:—|.*saknas.*)\s*\|\s*❌\s*\|",
                 rf"| - | `{typ}` | ✅ | ✅ | ✅ | ✅ | ✅ |", ark)
    ark = re.sub(rf"\|\s*\(\d+\)\s*\|\s*`{typ}`\s*\|\s*✅\s*\|\s*❌\s*(?:[a-zA-ZäöåÄÖÅ]+)?\s*\|\s*❌\s*\|\s*(?:—|.*saknas.*)\s*\|\s*❌\s*\|",
                 rf"| - | `{typ}` | ✅ | ✅ | ✅ | ✅ | ✅ |", ark)
                 
# Bilaga B
mcp_done = [
    "spiris_order", "spiris_offerter", "spiris_offertutkast", 
    "spiris_underlag", "spiris_hamta_underlag", "spiris_prislistor", 
    "spiris_rabattavtal", "spiris_etiketter", "spiris_anlaggningstillgangar", 
    "spiris_foretagsinfo", "spiris_anvandare", "spiris_valutakurs", 
    "spiris_kundreskontraposter"
]
for mcp in mcp_done:
    ark = re.sub(rf"\|\s*`{mcp}`\s*\|\s*❌\s*\|", rf"| `{mcp}` | ✅ |", ark)

with open("ARKITEKTUR_UI_TACKNING.md", "w", encoding="utf-8") as f:
    f.write(ark)
