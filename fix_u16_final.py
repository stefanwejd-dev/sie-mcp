import os
from pathlib import Path

# 1. Fix parser/spiris_rag.py
fpath = "parser/spiris_rag.py"
content = Path(fpath).read_text(encoding="utf-8")

content = content.replace("k.hamta_alla(k, ", "k.hamta_alla(")
Path(fpath).write_text(content, encoding="utf-8")


# 2. Fix tests/test_mcp_lasande_bredd.py
fpath2 = "tests/test_mcp_lasande_bredd.py"
content2 = Path(fpath2).read_text(encoding="utf-8")

old_dict_end = '''    "spiris_bokforingslas": lambda: spiris_bokforingslas(),
}'''

new_dict_end = '''    "spiris_bokforingslas": lambda: spiris_bokforingslas(),
    "spiris_prislistor": lambda: spiris_prislistor(),
    "spiris_rabattavtal": lambda: spiris_rabattavtal(),
    "spiris_etiketter": lambda: spiris_etiketter("kund"),
}'''

content2 = content2.replace(old_dict_end, new_dict_end)
Path(fpath2).write_text(content2, encoding="utf-8")
