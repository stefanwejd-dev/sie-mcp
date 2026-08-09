import re
from pathlib import Path

f = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_spiris_adapter.py")
content = f.read_text("utf-8")
content = re.sub(r'def hamta_alla\(self, path, params=None\):', r'def hamta_alla(self, path, params=None, **kwargs):', content)
content = re.sub(r'def hamta_alla\(self, path\):', r'def hamta_alla(self, path, **kwargs):', content)
f.write_text(content, "utf-8")

f2 = Path("G:/My Drive/Claude Cowork/sie-mcp/parser/spiris_adapter.py")
content2 = f2.read_text("utf-8")
content2 = re.sub(r'def hamta_referensdata\(klient: _Spirisklient, typ: str\) -> list\[dict\]:', r'def hamta_referensdata(klient: _Spirisklient, typ: str, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:', content2)
content2 = re.sub(r'for rå in klient.hamta_alla\("/vatcodesrates"\):', r'for rå in klient.hamta_alla("/vatcodesrates", filter=filter, select=select, orderby=orderby, pagesize=pagesize):', content2)

def repl_tuple(m):
    return f'return [_mappa(r, mappning) for r in klient.hamta_alla(path, filter=filter, select=select, orderby=orderby, pagesize=pagesize)]'

content2 = re.sub(r'return \[\_mappa\(r, mappning\) for r in klient.hamta_alla\(path\)\]', repl_tuple, content2)
f2.write_text(content2, "utf-8")
