import re
from pathlib import Path

# 1. Fix SPIRIS_ARGUMENT in tests/test_mcp_villkorssparr.py
test_file = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_mcp_villkorssparr.py")
c_test = test_file.read_text("utf-8")
c_test = c_test.replace(
    'SPIRIS_ARGUMENT = [',
    'SPIRIS_ARGUMENT = [\n    "spiris_hamta_ett", "spiris_ingaende_balans", "spiris_kontoplan_alla", "spiris_kundfakturor", "spiris_verifikationer_alla", "spiris_valutakurs", "spiris_anlaggningstillgangar", "spiris_kundreskontraposter", "spiris_anvandare",'
)
test_file.write_text(c_test, "utf-8")

# 2. Re-add OData parameters to spiris_adapter.py
adapter = Path("G:/My Drive/Claude Cowork/sie-mcp/parser/spiris_adapter.py")
c_adapter = adapter.read_text("utf-8")

c_adapter = c_adapter.replace(
    'def hamta_kunder(klient: _Spirisklient) -> list[dict]:',
    'def hamta_kunder(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:'
).replace(
    'for rå in klient.hamta_alla("/customers"):',
    'for rå in klient.hamta_alla("/customers", filter=filter, select=select, orderby=orderby, pagesize=pagesize):'
)

c_adapter = c_adapter.replace(
    'def hamta_leverantorer(klient: _Spirisklient) -> list[dict]:',
    'def hamta_leverantorer(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:'
).replace(
    'for rå in klient.hamta_alla("/suppliers"):',
    'for rå in klient.hamta_alla("/suppliers", filter=filter, select=select, orderby=orderby, pagesize=pagesize):'
)

c_adapter = c_adapter.replace(
    'def hamta_projekt(klient: _Spirisklient) -> list[dict]:',
    'def hamta_projekt(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:'
).replace(
    'for rå in klient.hamta_alla("/projects"):',
    'for rå in klient.hamta_alla("/projects", filter=filter, select=select, orderby=orderby, pagesize=pagesize):'
)

c_adapter = c_adapter.replace(
    'def hamta_kostnadsstallen(klient: _Spirisklient) -> list[dict]:',
    'def hamta_kostnadsstallen(klient: _Spirisklient, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:'
).replace(
    'for rå in klient.hamta_alla("/costcenters"):',
    'for rå in klient.hamta_alla("/costcenters", filter=filter, select=select, orderby=orderby, pagesize=pagesize):'
)

c_adapter = c_adapter.replace(
    'def hamta_kontosaldo(klient, kontonr: str, per_datum: str) -> dict:',
    'def hamta_kontosaldo(klient: _Spirisklient, kontonr: str, per_datum: str, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> dict:'
).replace(
    'rå = klient.hamta_en(f"/accountbalances/{kontonr}/{per_datum}")',
    'params = {}\n    if filter: params["$filter"] = filter\n    if select: params["$select"] = ",".join(select)\n    if orderby: params["$orderby"] = orderby\n    if pagesize: params["$pagesize"] = str(pagesize)\n    rå = klient.hamta_en(f"/accountbalances/{kontonr}/{per_datum}", params=params or None)'
)

c_adapter = c_adapter.replace(
    'def hamta_referensdata(klient: _Spirisklient, typ: str) -> list[dict]:',
    'def hamta_referensdata(klient: _Spirisklient, typ: str, *, filter: str | None = None, select: list[str] | None = None, orderby: str | None = None, pagesize: int | None = None) -> list[dict]:'
).replace(
    'return klient.hamta_alla(giltiga[typ])',
    'return klient.hamta_alla(giltiga[typ], filter=filter, select=select, orderby=orderby, pagesize=pagesize)'
)

adapter.write_text(c_adapter, "utf-8")
