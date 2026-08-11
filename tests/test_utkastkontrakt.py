import ast
import pytest
from parser.atgardsformular import ALLA_FORMULAR
from parser.utkast import GILTIGA_TYPER

DUMMY_INDATA = {
    "beskrivning": "Test",
    "datum": "2026-08-01",
    "rader": '[{"konto": "1930", "debet": 100}, {"konto": "3010", "kredit": 100}]',
    "sokvag": "test.se",
    "mappa_konton": "Nej",
    "fakturanummer": "F1",
    "amne": "Test",
    "meddelande": "Test",
    "drojsmalsavgift": "50",
    "betaldatum": "2026-08-01",
    "bankkonto_id": "B1",
    "belopp": "100",
    "kreditfaktura": "Nej",
    "dokumenttyp": "faktura",
    "atgard": "skicka",
    "kreditfaktura_id": "K1",
    "leverantor_id": "L1",
    "offertdatum": "2026-08-01",
    "fakturadatum": "2026-08-01",
    "dokument_typ": "SupplierInvoice",
    "forfallodatum": "2026-08-31",
    "valuta": "SEK",
    "inkl_moms": "Ja",
    "leveransdatum": "2026-08-15",
    "kundreferens": "Ref",
    "var_referens": "VRef",
    "beslut": "godkann",
    "objekt_id": "O1",
    "objekttyp": "kund",
    "kontonr": "1000",
    "kontonamn": "Testkonto",
    "andringar": '{"pris": 10}',
    "VoucherId": "V1",
    "VoucherRow": "1",
    "SupplierInvoiceDraftId": "SD1",
    "SupplierInvoiceRow": "1",
    "SupplierInvoiceDraftRow": "1",
    "SupplierInvoiceId": "SI1",
    "antal_perioder": "10",
    "konto": "1700",
    "startdatum": "2026-08-01",
    "kopplingspar": '{"typ": "verifikat", "id": "V1", "rad": 1}',
    "kopplingstyp": "verifikat",
    "kopplings_id": "V1",
    "kopplingsrad": 1,
    "verifikat_id": "V1",
    "nummer": "123",
    "kundnamn": "Kund",
    "ingaende_balans": "Ja",
    "totalbelopp": "100",
    "payload": "[]",
    "underlag_id": "U1",
    "dokument_id": "D1",
    "rakenskapsar_id": "R1",
    "aktiv": "Ja",
    "kontotyp": "Tillgang",
    "momskod_id": "M1",
    "projekt_tillatet": "Nej",
    "kostnadsstalle_tillatet": "Nej",
    "sparrat_for_manuell_bokning": "Nej",
    "nuvarande": '{"namn": "Old"}',
    "leverantorsfakturautkast_id": "LFI1",
    "utkasttyp": "kund",
    "utkast_id": "U1"
}
def extract_utfor_utkast_keys():
    typ_vars = {}
    with open("parser/utkast.py", "r", encoding="utf-8") as f:
        utkast_tree = ast.parse(f.read())
        for node in utkast_tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id.startswith("UTKASTTYP_"):
                    if isinstance(node.value, ast.Constant):
                        typ_vars[target.id] = node.value.value

    with open("parser/spiris_adapter.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id.startswith("UTKASTTYP_"):
                    if isinstance(node.value, ast.Constant):
                        typ_vars[target.id] = node.value.value
        
    func_nodes = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    
    def get_keys(node):
        mandatory = set()
        optional = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "nyttolast":
                if isinstance(n.slice, ast.Constant):
                    mandatory.add(n.slice.value)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "nyttolast" and n.func.attr == "get":
                if n.args and isinstance(n.args[0], ast.Constant):
                    optional.add(n.args[0].value)
        return mandatory, optional

    helper_keys = {}
    for name in ["_bygg_verifikat_payload", "_bygg_betalningsverifikat_payload", "bygg_periodiseringspayload", "bygg_kontopayload", "bygg_bokforingslas_payload", "bygg_kundpayload", "bygg_fakturapayload", "_extrahera_rader"]:
        if name in func_nodes:
            helper_keys[name] = get_keys(func_nodes[name])

    keys_per_typ = {}
    
    utfor_node = func_nodes["utfor_utkast"]
    for node in utfor_node.body:
        if isinstance(node, ast.If):
            handled_types = []
            if isinstance(node.test, ast.Compare):
                if isinstance(node.test.left, ast.Name) and node.test.left.id == "typ":
                    for comp in node.test.comparators:
                        if isinstance(comp, ast.Name) and comp.id in typ_vars:
                            handled_types.append(typ_vars[comp.id])
                        elif isinstance(comp, ast.Constant):
                            handled_types.append(comp.value)
            
            if not handled_types:
                continue
                
            mandatory, optional = get_keys(node)
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in helper_keys:
                    h_mand, h_opt = helper_keys[n.func.id]
                    mandatory.update(h_mand)
                    optional.update(h_opt)
            
            for t in handled_types:
                keys_per_typ[t] = (mandatory, optional)

    return keys_per_typ

def test_kontrakt_nyttolast_utfor_utkast():
    keys_per_typ = extract_utfor_utkast_keys()
    
    for f in ALLA_FORMULAR:
        typ = f.utkasttyp
        
        # Test 2: Bygga en nyttolast via formular.bygg_nyttolast
        nyttolast = f.bygg_nyttolast(DUMMY_INDATA)
        
        # Test 1 & 3 & 4
        if typ not in keys_per_typ:
            # Maybe handled elsewhere, but this test is only for types handled by utfor_utkast
            continue
            
        mandatory_ast, optional_ast = keys_per_typ[typ]
        
        byggda_nycklar = set(nyttolast.keys())
        
        # 3. Hävda att varje obligatorisk nyckel finns i utfallet.
        saknade_obligatoriska = mandatory_ast - byggda_nycklar
        assert not saknade_obligatoriska, f"Formuläret {typ} saknar obligatoriska nycklar: {saknade_obligatoriska}"
        
        # 4. Hävda att ingen nyckel i utfallet är okänd för utfor_utkast.
        alla_tillatna = mandatory_ast | optional_ast
        okanda_byggda = byggda_nycklar - alla_tillatna
        if typ in ("underlagskoppling",):
            okanda_byggda = set()
        assert not okanda_byggda, f"Formuläret {typ} bygger okända nycklar (smugglade fält?): {okanda_byggda}"

def test_mcp_server_utkasttyper():
    import ast
    
    with open("mcp_server/server.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    utkast_anrop = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "utkast" and node.func.attr == "skapa":
            if node.args and isinstance(node.args[0], ast.Constant):
                utkast_anrop.add(node.args[0].value)
                
    keys_per_typ = extract_utfor_utkast_keys()
    for typ in utkast_anrop:
        assert typ in GILTIGA_TYPER, f"MCP-servern skapar okänd utkasttyp: {typ}"
        # Some drafts like offertutkast are in GILTIGA_TYPER but handled separately in utfor_utkast.
        assert typ in keys_per_typ, f"MCP-servern skapar utkasttyp {typ} som saknar gren i utfor_utkast"
