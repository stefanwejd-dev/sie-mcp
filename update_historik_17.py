import os
from pathlib import Path

# Update HISTORIK.md
fpath = "HISTORIK.md"
content = Path(fpath).read_text(encoding="utf-8")

new_historik = """
### 2026-08-10 (Etapp 17 - Småplock)
*   **Status**: IMPLEMENTERAT & REDO FÖR GRIND 17.
*   **Ändringar**:
    *   **U17.1**: Implementerat `spiris_verifikation` som hämtar en specifik verifikation (`GET /vouchers/{fy}/{id}`) och maskerar fritexten (KATEGORI_HUVUDBOK).
    *   **U17.2**: Implementerat `spiris_bankhandelse` som hämtar en specifik bankhändelse (`GET /banktransactions/{account}/{id}`).
    *   **RAG**: Båda verktygen ligger bakom `_kor_spiris_verktyg` i servern och skyddas av Villkorsspärren.
*   **Resultat**: 2244/2244 tester gröna.
"""

content += new_historik
Path(fpath).write_text(content, encoding="utf-8")

# Update AI_HANDOVER.md
fpath2 = "AI_HANDOVER.md"
content2 = Path(fpath2).read_text(encoding="utf-8")

if "Etapp 17" in content2:
    pass
else:
    # Update latest status
    content2 = content2.replace("Etapp 16 klar, redo för Etapp 17", "Etapp 17 klar, redo för GRIND 17")
    content2 += "\n- **Senaste uppdatering**: Etapp 17 (Småplock: Enstaka verifikat och bankhändelser) är implementerad och inväntar GRIND 17.\n"
    Path(fpath2).write_text(content2, encoding="utf-8")
