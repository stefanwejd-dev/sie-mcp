import re
import os

# 1. FIX server.py
server_path = os.path.join("mcp_server", "server.py")
with open(server_path, "r", encoding="utf-8") as f:
    server_code = f.read()

server_code = re.sub(
    r'@mcp\.tool\(\)\nasync def forbered_underlagskoppling.*?KATEGORI_UTKAST\)',
    '''@mcp.tool()
async def forbered_underlagskoppling(underlag_id: str, dokument_id: str, dokument_typ: str = "SupplierInvoice") -> str:
    """Skapar ett utkast för att koppla ett befintligt underlag till ett befintligt dokument.
    dokument_typ är oftast 'SupplierInvoice' (Leverantörsfaktura) eller 'Voucher' (Verifikat)."""
    import parser.utkast as utkast
    from parser.spiris_adapter import UTKASTTYP_UNDERLAGSKOPPLING
    payload = {
        "DocumentId": dokument_id,
        "AttachmentIds": [underlag_id],
        "DocumentType": dokument_typ
    }
    u = utkast.skapa(
        UTKASTTYP_UNDERLAGSKOPPLING,
        payload,
        f"Koppla bilaga till {dokument_id} ({dokument_typ})"
    )
    import json
    return json.dumps({"utkast_id": u.id, "info": f"Utkast {u.id} skapat."})''',
    server_code,
    flags=re.DOTALL
)

with open(server_path, "w", encoding="utf-8") as f:
    f.write(server_code)


# 2. FIX test_etapp4_underlag.py
test_path = os.path.join("tests", "test_etapp4_underlag.py")
with open(test_path, "r", encoding="utf-8") as f:
    test_code = f.read()

test_code = re.sub(
    r'def test_forbered_underlagskoppling_skapar_utkast\(\):.*?assert res\.get\("utkast_id"\) is not None\n',
    '''def test_forbered_underlagskoppling_skapar_utkast(monkeypatch):
    from parser import utkast
    class DummyUtkast:
        def __init__(self):
            self.id = "mock-id-123"
    monkeypatch.setattr(utkast, "skapa", lambda a,b,c: DummyUtkast())
    res = asyncio.run(forbered_underlagskoppling("att1", "doc1", "Voucher"))
    import json
    res = json.loads(res)
    assert res.get("utkast_id") == "mock-id-123"

def test_forbered_underlagskoppling_default_type(monkeypatch):
    from parser import utkast
    class DummyUtkast:
        def __init__(self):
            self.id = "mock-id-123"
    monkeypatch.setattr(utkast, "skapa", lambda a,b,c: DummyUtkast())
    res = asyncio.run(forbered_underlagskoppling("att1", "doc1"))
    import json
    res = json.loads(res)
    assert res.get("utkast_id") == "mock-id-123"
''',
    test_code,
    flags=re.DOTALL
)

with open(test_path, "w", encoding="utf-8") as f:
    f.write(test_code)
