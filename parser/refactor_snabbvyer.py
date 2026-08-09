import sys
import re

with open('parser/snabbvyer.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('from svarskontrakt import KolumnDef, TabellBlock', 'from svarskontrakt import KolumnDef, TabellBlock\nfrom vy_modell import Vyresultat\nfrom stil import HARKOMST_LOKAL')

# Remove Snabbvyresultat definition
text = re.sub(r'@dataclass\nclass Snabbvyresultat:.*?fotnot: str \| None = None\n', '', text, flags=re.DOTALL)

# Replace all occurrences of Snabbvyresultat with Vyresultat
text = text.replace('Snabbvyresultat', 'Vyresultat')

# Fix instantiation of Vyresultat to include harkomst=HARKOMST_LOKAL and tuple conversions
# Examples of current instantiation:
# Vyresultat(rubrik="...")
# Vyresultat(rubrik="...", nyckeltal=[...], sektioner=[...], fotnot="...")

def fix_vyresultat(match):
    inner = match.group(1)
    
    # We need to add harkomst=HARKOMST_LOKAL
    if 'harkomst=' not in inner:
        if inner.strip():
            inner = 'harkomst=HARKOMST_LOKAL, ' + inner
        else:
            inner = 'harkomst=HARKOMST_LOKAL'
            
    # Replace list comprehensions or brackets in nyckeltal= and sektioner=
    # For simplicity, we can just let Python handle lists implicitly if Vyresultat can accept them, 
    # but Vyresultat requires tuples. Actually, Vyresultat uses tuple[Nyckeltal, ...] = ()
    # Dataclasses don't strictly enforce types at runtime, but we should pass tuples.
    # We'll just replace `nyckeltal=[` with `nyckeltal=tuple([` and `sektioner=[` with `sektioner=tuple([`
    inner = re.sub(r'nyckeltal=(\[[^\]]*\])', r'nyckeltal=tuple(\1)', inner, flags=re.DOTALL)
    inner = re.sub(r'sektioner=(\[[^\]]*\])', r'sektioner=tuple(\1)', inner, flags=re.DOTALL)
    
    # Also handle the cases where they are variables, e.g. nyckeltal=nyckeltal
    inner = re.sub(r'nyckeltal=([a-zA-Z_]\w*)', r'nyckeltal=tuple(\1)', inner)
    inner = re.sub(r'sektioner=([a-zA-Z_]\w*)', r'sektioner=tuple(\1)', inner)

    return 'Vyresultat(' + inner + ')'

text = re.sub(r'Vyresultat\((.*?)\)', fix_vyresultat, text, flags=re.DOTALL)

with open('parser/snabbvyer.py', 'w', encoding='utf-8') as f:
    f.write(text)
