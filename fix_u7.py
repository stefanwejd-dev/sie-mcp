import re

with open("parser/spiris_rag.py", "r", encoding="utf-8") as f:
    text = f.read()

# Fix unmatched parentheses:
text = text.replace("offset=offset, limit=limit))", "offset=offset, limit=limit)")
text = text.replace("offset=offset, limit=limit) )", "offset=offset, limit=limit)")

with open("parser/spiris_rag.py", "w", encoding="utf-8") as f:
    f.write(text)
