with open('parser/rum_render.py', 'r', encoding='utf-8') as f:
    text = f.read()

import re
# Replace with tomt_lage
text = re.sub(r'st\.info\("[^"]*Ladda in data i sidomenyn[^"]*"\)', 'tomt_lage(st, hamta("rakenskapsar"), "Data")', text)

with open('parser/rum_render.py', 'w', encoding='utf-8') as f:
    f.write(text)
