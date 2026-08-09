import re
import pytest
from ordbok import hamta, alla

def test_hamta_okant_begrepp_kastar():
    with pytest.raises(KeyError):
        hamta("finns_inte")

def test_begrepps_id_ar_ascii_snake_case():
    for begrepp in alla():
        assert re.match(r'^[a-z0-9_]+$', begrepp.id)

def test_inga_kallsynonymer_i_namn_eller_forklaring():
    forbid = ["Spiris", "Fortnox", "Briljant", "Visma"]
    for begrepp in alla():
        for f in forbid:
            assert f not in begrepp.namn
            assert f not in begrepp.forklaring

def test_ordbok_importerar_inte_streamlit():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-c", "import ordbok, sys; print('streamlit' in sys.modules)"], 
        capture_output=True, text=True, cwd="parser"
    )
    assert "False" in result.stdout
