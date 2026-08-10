import os
from pathlib import Path

fpath = "tests/test_etapp16_strukturer.py"
content = Path(fpath).read_text(encoding="utf-8")

content = content.replace("async def hamta_alla", "def hamta_alla")

Path(fpath).write_text(content, encoding="utf-8")
