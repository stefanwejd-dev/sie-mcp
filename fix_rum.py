import re

with open('parser/rum_render.py', 'r', encoding='utf-8') as f:
    content = f.read()

# In rum_render.py, we need to remove the imports and usages.
content = content.replace(", KONTO_FORMULAR, KONTOANDRING_FORMULAR", "")
content = content.replace(", KONTO_FORMULAR, KONTOANDRING_FORMULAR]", "]")
content = content.replace(", KVITTNING_FORMULAR", "")
content = content.replace(", KVITTNING_FORMULAR]", "]")
content = content.replace(", PERIODISERINGSANDRING_FORMULAR, PERIODISERINGSBORTTAGNING_FORMULAR, UNDERLAGSKOPPLING_FORMULAR", "")
content = content.replace(", PERIODISERINGSANDRING_FORMULAR, PERIODISERINGSBORTTAGNING_FORMULAR, UNDERLAGSKOPPLING_FORMULAR]", "]")

# Also OFFERTUTKAST_FORMULAR maybe?
content = content.replace(", OFFERTUTKAST_FORMULAR", "")
content = content.replace(", OFFERTUTKAST_FORMULAR]", "]")

with open('parser/rum_render.py', 'w', encoding='utf-8') as f:
    f.write(content)

with open('tests/test_rum_render_atgard.py', 'r', encoding='utf-8') as f:
    tcontent = f.read()
    
# Update the numbers in tests/test_rum_render_atgard.py
# If they assert on 4, we might need to revert them to original.
# Let's print the assertions first.
for line in tcontent.splitlines():
    if "assert len(" in line and "formular" in line:
        print(line)

