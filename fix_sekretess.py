import os

path = "parser/sekretesslager.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

if "def skapa_motpartsmaskerare" not in text:
    funcs = """
def skapa_motpartsmaskerare(referenslista: set[str] | None = None):
    pseudonym_for: dict[str, str] = {}
    
    def maskera(namn: str) -> str:
        if not namn:
            return namn
        if namn not in pseudonym_for:
            nummer = len(pseudonym_for) + 1
            pseudonym_for[namn] = f"Fiktiv Motpart {nummer} 🛑"
        return pseudonym_for[namn]
        
    maskera.kodnyckel = lambda: pseudonym_for
    return maskera
"""
    text += "\n" + funcs
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
