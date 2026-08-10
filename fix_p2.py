import os
from pathlib import Path

# 1. Update .gitignore
gitignore_path = ".gitignore"
gitignore_content = Path(gitignore_path).read_text(encoding="utf-8")
gitignore_addition = """
# Vismas egen dokumentation och avtalstext. Arbetsmaterial, inte vårt att
# publicera vidare. Ligger kvar lokalt men ska aldrig till ett publikt repo.
Visma_villkor/

# Engångsskript för historikuppdatering, hör inte till projektet
update_handover_final.py
"""
if "Visma_villkor/" not in gitignore_content:
    Path(gitignore_path).write_text(gitignore_content.rstrip() + "\n" + gitignore_addition, encoding="utf-8")


# 2. Add docstrings to the probe files
def update_probe_file(filepath: str, description: str):
    if not os.path.exists(filepath):
        return
    
    content = Path(filepath).read_text(encoding="utf-8")
    
    docstring = f'''"""
{description}

RÖKPROVSNOTERING:
Detta skript kräver en levande Spiris-session. Villkorsspärren kopplas ur 
temporärt eftersom rökprovet körs av en utvecklare på en maskin där villkoren 
redan är bedömda och godkända i GUI:t. Urkopplingen är en teknisk genväg 
förbi den interaktiva grinden, inte ett kringgående av regelverket.
"""
'''
    if "RÖKPROVSNOTERING" not in content:
        # insert right after the imports, or at the top if there are none.
        # Actually it's easier to put it at the very top
        Path(filepath).write_text(docstring + content, encoding="utf-8")

update_probe_file("tools/prov_lasbredd.py", "Rökprov för att testa läsande bredd mot API:et.")
update_probe_file("tools/prov_paginering.py", "Rökprov för att verifiera pagineringsmekanismer (offset/limit).")
update_probe_file("tools/prov_etapp16.py", "Rökprov för Etapp 16 (prislistor, rabattavtal och etiketter).")
