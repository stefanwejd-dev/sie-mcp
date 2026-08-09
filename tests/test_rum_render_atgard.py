import pytest
from unittest.mock import MagicMock, patch
import json
from parser.rum_render import (
    rendera_atgardsformular, rendera_pengar_in, rendera_pengar_ut, 
    rendera_bockerna, rendera_register
)
from parser.atgardsformular import FAKTURAUTSKICK

class MockStFormContextManager:
    def __init__(self, key, clear_on_submit):
        self.key = key
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

class MockSt:
    def __init__(self):
        self.text_inputs = {}
        self.errors = []
        self.successes = []
        self.submits = False
        self.session_state = MagicMock()
        self.expander_calls = []

    def subheader(self, text):
        pass

    def form(self, key, clear_on_submit=False):
        return MockStFormContextManager(key, clear_on_submit)

    def text_input(self, label, help=None, value="", **kwargs):
        return self.text_inputs.get(label, "Hej") # Fallback for encoding issues
        
    def checkbox(self, label, help=None):
        return False
        
    def selectbox(self, label, options, key=None, help=None):
        return options[0] if options else None

    def form_submit_button(self, label):
        return self.submits

    def error(self, msg):
        self.errors.append(msg)
        
    def success(self, msg):
        self.successes.append(msg)
        
    def caption(self, msg):
        pass

    def expander(self, label):
        self.expander_calls.append(label)
        return MockStFormContextManager(label, False)
        
    def header(self, msg):
        pass
        
    def markdown(self, body, unsafe_allow_html=False):
        pass

    def columns(self, n):
        return [self] * n
        
    def button(self, *args, **kwargs):
        return False

def test_rendera_atgardsformular_anropar_inte_utfor_utkast():
    st_mock = MockSt()
    st_mock.submits = True
    st_mock.text_inputs = {"Fakturanummer *": "123"}
    
    with patch('parser.rum_render.utkast.skapa') as mock_skapa, patch('parser.spiris_adapter.utfor_utkast') as mock_utfor:
        rendera_atgardsformular(st_mock, FAKTURAUTSKICK)
        
        assert not [e for e in st_mock.errors if "Ett skickat mejl" not in e], f"Errors: {st_mock.errors}"
        mock_skapa.assert_called_once()
        mock_utfor.assert_not_called()

def test_rendera_atgardsformular_obligatoriska_falt_blockerar():
    st_mock = MockSt()
    st_mock.submits = True
    st_mock.text_inputs = {"Fakturanummer *": "123"}
    # Simulera att Meddelande saknas
    original_text_input = st_mock.text_input
    st_mock.text_input = lambda lbl, **kwargs: "" if "Meddelande" in lbl else "123"
    
    with patch('parser.rum_render.utkast.skapa') as mock_skapa:
        rendera_atgardsformular(st_mock, FAKTURAUTSKICK)
        
        mock_skapa.assert_not_called()
        assert any("obligatoriska" in err for err in st_mock.errors)

def test_rendera_atgardsformular_bekraftelse_namner_beslut():
    st_mock = MockSt()
    st_mock.submits = True
    st_mock.text_inputs = {"Fakturanummer *": "123"}
    
    with patch('parser.rum_render.utkast.skapa'):
        rendera_atgardsformular(st_mock, FAKTURAUTSKICK)
        
        assert any("Beslut" in msg for msg in st_mock.successes)

def test_rendera_atgardsformular_exakt_ett_utkast():
    st_mock = MockSt()
    st_mock.submits = True
    st_mock.text_inputs = {"Fakturanummer *": "123"}
    
    with patch('parser.rum_render.utkast.skapa') as mock_skapa:
        rendera_atgardsformular(st_mock, FAKTURAUTSKICK)
        
        assert not [e for e in st_mock.errors if "obligatoriska" in e], f"Errors: {st_mock.errors}"
        assert mock_skapa.call_count == 1

def _setup_st_for_rooms(st_mock):
    sie_mock = MagicMock()
    sie_mock.verifikationer = []
    st_mock.session_state.get.side_effect = lambda k: sie_mock if k == "sie" else (None if k == "rapportunderlag" else True)
    st_mock.session_state.spiris_kundreskontra = []
    st_mock.session_state.spiris_reskontra = []

def test_rum_pengar_in_har_atgardsformular():
    st_mock = MockSt()
    _setup_st_for_rooms(st_mock)
    with patch('parser.rum_render.st', st_mock), patch('parser.snabbvy_render.rendera_snabbvyfalt'), patch('parser.snabbvy_render.injicera_snabbvy_css'), patch('parser.rum_render.rendera_atgardsformular') as mock_render_form:
        rendera_pengar_in()
        assert "➕ Ny åtgärd" in st_mock.expander_calls
        assert mock_render_form.call_count == 7 # Pengar in har 7 formulär

def test_rum_pengar_ut_har_atgardsformular():
    st_mock = MockSt()
    _setup_st_for_rooms(st_mock)
    with patch('parser.rum_render.st', st_mock), patch('parser.snabbvy_render.rendera_snabbvyfalt'), patch('parser.snabbvy_render.injicera_snabbvy_css'), patch('parser.rum_render.rendera_atgardsformular') as mock_render_form:
        rendera_pengar_ut()
        assert "➕ Ny åtgärd" in st_mock.expander_calls
        assert mock_render_form.call_count == 3 # Pengar ut har 3 formulär

def test_rum_bockerna_har_atgardsformular():
    st_mock = MockSt()
    _setup_st_for_rooms(st_mock)
    with patch('parser.app_tillstand.ladda_bockerna_data'), patch('parser.rum_render.st', st_mock), patch('parser.snabbvy_render.rendera_snabbvyfalt'), patch('parser.snabbvy_render.injicera_snabbvy_css'), patch('parser.rum_render.rendera_atgardsformular') as mock_render_form:
        rendera_bockerna()
        assert "➕ Ny åtgärd" in st_mock.expander_calls
        assert mock_render_form.call_count == 2 # Böckerna har 2 formulär

def test_rum_register_har_atgardsformular():
    st_mock = MockSt()
    _setup_st_for_rooms(st_mock)
    with patch('parser.app_tillstand.ladda_register_data'), patch('parser.rum_render.st', st_mock), patch('parser.snabbvy_render.rendera_snabbvyfalt'), patch('parser.snabbvy_render.injicera_snabbvy_css'), patch('parser.rum_render.rendera_atgardsformular') as mock_render_form:
        rendera_register()
        assert "➕ Ny åtgärd" in st_mock.expander_calls
        assert mock_render_form.call_count == 2 # Register har 2 formulär
