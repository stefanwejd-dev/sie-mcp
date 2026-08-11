import sys
import pytest
import subprocess

# Ensure we can import without streamlit triggering
import parser.rum as rum

def test_rum_i_ratt_ordning():
    """Testar att vi har exakt de åtta rummen i rätt ordning."""
    ids = [r.id for r in rum.RUM]
    assert ids == [
        "oversikt",
        "beslut",
        "pengar-in",
        "pengar-ut",
        "bank",
        "bockerna",
        "register",
        "rapporter",
        "investering",
        "juridik",
        "foretagsdata",
        "data",
        "saljdokument",
    ]

def test_alla_rum_har_unikt_url_path():
    """Rummets id används som bas för url_path i app.py och måste vara unikt."""
    ids = [r.id for r in rum.RUM]
    assert len(ids) == len(set(ids)), "Dubletter i rum-id"

def test_alla_vyetiketter_kommer_fran_ordboken():
    """Ingen vy har fritextetikett, alla ska ha ett Begrepp."""
    for r in rum.RUM:
        for v in r.vyer:
            assert hasattr(v, "begrepp")

def test_inget_rum_namnger_ett_affarssystem():
    """Vakthund: inga affärssystem i rumsnamn (fönstrets princip)."""
    forbjudna_ord = ["spiris", "fortnox", "briljant", "visma"]
    for r in rum.RUM:
        namn_lower = r.namn.lower()
        for ord in forbjudna_ord:
            assert ord not in namn_lower, f"Rum {r.id} namnger {ord}"
        
        for v in r.vyer:
            etikett_lower = v.begrepp.namn.lower() if hasattr(v, "begrepp") else ""
            for ord in forbjudna_ord:
                assert ord not in etikett_lower, f"Vy i {r.id} namnger {ord}"

def test_rum_importerar_inte_streamlit():
    """Rum-modulerna definierar bara UI-deklarationerna och får inte ladda Streamlit."""
    cmd = ["python", "-c", "import sys; sys.path.insert(0, 'parser'); import rum; assert 'streamlit' not in sys.modules"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Streamlit laddades när rum importerades: {result.stderr}"

def test_app_py_navigering_grupper():
    """Verifierar att navigeringen i app.py är grupperad och innehåller alla 11 rum."""
    import ast
    with open("app.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    sidor_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "sidor":
                    sidor_dict = node.value
                    
    assert isinstance(sidor_dict, ast.Dict), "sidor är inte en dict i app.py"
    
    assert len(sidor_dict.keys) == 6, "Navigeringen ska ha exakt 6 grupper (Dagen, Pengar, Bokföring, Analys, AI-chattar, Data)"
    
    # Check total pages
    total_pages = 0
    url_paths = set()
    for val in sidor_dict.values:
        if isinstance(val, ast.List):
            for el in val.elts:
                    if isinstance(el, ast.Call) or isinstance(el, ast.Name):
                        total_pages += 1
                        if isinstance(el, ast.Call):
                            for kw in el.keywords:
                                if kw.arg == "url_path" and isinstance(kw.value, ast.Constant):
                                    url_paths.add(kw.value.value)
                        elif isinstance(el, ast.Name) and el.id == "data_page":
                            url_paths.add("data")
                            
    assert total_pages == 13, f"Förväntade 13 rum i navigeringen, hittade {total_pages}"
    
    # Verify all rooms exist
    ids = {r.id for r in rum.RUM}
    assert ids == url_paths, f"Skillnad i rum-ids och url_paths i app.py: {ids ^ url_paths}"
    
def test_kommandofaltet_klarar_nya_formen():
    from parser.kommandofalt import rendera_kommandofalt
    import parser.rum_render as rum_render
    from unittest.mock import MagicMock
    
    # Mocka st och sidor
    st_mock = MagicMock()
    st_mock.text_input.return_value = "faktura"
    
    sidor = {
        "Pengar": [
            MagicMock(url_path="pengar-in"),
        ]
    }
    
    # Ska inte kasta TypeError pga dict
    rendera_kommandofalt(st_mock, sidor)
    st_mock.switch_page.assert_called()
