with open("parser/navigering.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "def sticky_nav_css" in line or "def flikettiketter" in line:
        break
    if "NAV_TOPP_OFFSET =" in line or "from stil import BAKGRUND_LJUS, BAKGRUND_MORK, bakgrundsfarg" in line:
        continue
    new_lines.append(line)

with open("parser/navigering.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

with open("tests/test_navigering.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
    
new_lines = []
for line in lines:
    if "class TestFlikettiketter:" in line or "class TestStickyCss:" in line:
        break
    if "FLIK_AI_ASSISTENT," in line or "FLIK_DATASTATUS," in line or "FLIK_INVESTERINGSKALKYL," in line or "FLIK_RAPPORTER," in line or "NAV_NYCKEL," in line or "bakgrundsfarg," in line or "flikettiketter," in line or "sticky_nav_css," in line:
        continue
    new_lines.append(line)
    
with open("tests/test_navigering.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
