import os
from pathlib import Path

# Update HISTORIK.md
fpath = "HISTORIK.md"
content = Path(fpath).read_text(encoding="utf-8")

new_historik = """
### 2026-08-10 (Etapp 16 - Prislistor, rabattavtal och etiketter)
*   **Status**: IMPLEMENTERAT & TESTAT.
*   **Ändringar**:
    *   **R16.1**: Implementerat `spiris_prislistor` med stöd för hämtning av alla prislistor (GET `/salespricelists`) eller priser för specifik lista (GET `/salespricelists/prices/{id}`).
    *   **R16.2**: Implementerat `spiris_rabattavtal` för läsning av rabattavtal (GET `/discountagreements`).
    *   **R16.3**: Implementerat `spiris_etiketter` som stöder typ-argumentet ("kund" eller "artikel") och anropar antingen `/customerlabels` eller `/articlelabels`.
    *   **R16.4**: Lagt till verktygen i MCP-servern (`mcp_server/server.py`) bakom `_kor_spiris_verktyg` så att de skyddas av användargodkännande.
    *   **R16.5**: Uppdaterat testsviterna (`test_mcp_lasande_bredd.py` och `test_mcp_villkorssparr.py`) och skapat separata tester i `test_etapp16_strukturer.py`.
*   **Resultat**: 206/206 tester gröna.
"""

content += new_historik
Path(fpath).write_text(content, encoding="utf-8")

# Update AI_HANDOVER.md
fpath2 = "AI_HANDOVER.md"
content2 = Path(fpath2).read_text(encoding="utf-8")

if "Etapp 16 (Prislistor, rabattavtal och etiketter)" in content2:
    pass
else:
    # Update latest status
    content2 = content2.replace("Arbetar med Etapp 16", "Etapp 16 klar, redo för Etapp 17")
    content2 += "\n- **Senaste uppdatering**: Etapp 16 (prislistor, rabattavtal och etiketter) är fullt implementerad, testad och integrerad.\n"
    Path(fpath2).write_text(content2, encoding="utf-8")
