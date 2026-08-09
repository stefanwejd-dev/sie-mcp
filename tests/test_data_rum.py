import pytest
from unittest.mock import patch, MagicMock
import unittest.mock
from parser.rum_render import rendera_data
import parser.rum_render
from parser.rum.data import RUM_DATA

class MockSt:
    def __init__(self):
        self.headers = []
        self.subheaders = []
        self.captions = []
        self.infos = []
        self.successes = []
        self.writes = []
        self.errors = []
        
    def header(self, t): self.headers.append(t)
    def subheader(self, t): self.subheaders.append(t)
    def caption(self, t): self.captions.append(t)
    def info(self, t): self.infos.append(t)
    def success(self, t): self.successes.append(t)
    def write(self, t): self.writes.append(t)
    def error(self, t): self.errors.append(t)
    def divider(self): pass
    def spinner(self, t): return MagicMock()
    
    def form(self, key):
        return MagicMock()
        
    def columns(self, n):
        return [self] * n
        
    def date_input(self, label, key=None):
        import datetime
        return datetime.date(2023, 1, 1)
        
    def form_submit_button(self, label):
        return True # Simulate click
        
    def download_button(self, label, data, file_name=None, mime=None):
        self.writes.append(f"DOWNLOAD_BUTTON: {file_name}")

def test_data_rummet_finns():
    assert RUM_DATA.id == "data"
    assert RUM_DATA.namn == "Data in/ut"

def test_spiris_auth_vy_inte_andrats():
    # Verify that the core functions are still there
    import parser.spiris_auth_vy as auth
    assert hasattr(auth, 'bygg_auktoriserings_url')
    assert hasattr(auth, 'extrahera_kod')
    assert hasattr(auth, 'vaxla_kod_mot_token')

@patch('parser.rum_render.st')
@patch('parser.rum_render._bygg_spiris_klient_fran_session')
@patch('parser.rum_render.app_config.las_config')
@patch('parser.spiris_adapter.ladda_ner_sie4export')
@patch('parser.kalla_vy.rendera_anslutning')
def test_data_export_ktyp_varning(mock_anslutning, mock_export, mock_ladda, mock_bygg, st_mock):
    st_mock.columns.return_value = [st_mock, st_mock]
    mock_export.return_value = ("fil.se", "fake_path", 1234, "2023-01-01", "2023-01-31")
    
    with patch('builtins.open', unittest.mock.mock_open(read_data=b"HEMLIGT_INNEHALL")):
        rendera_data()
    
    # Check #KTYP warning
    found_warning = False
    for args, kwargs in st_mock.caption.call_args_list:
        if args and "#KTYP" in args[0]:
            found_warning = True
            break
    assert found_warning, "Missed #KTYP warning"

@patch('parser.rum_render.st')
@patch('parser.rum_render._bygg_spiris_klient_fran_session')
@patch('parser.rum_render.app_config.las_config')
@patch('parser.spiris_adapter.ladda_ner_sie4export')
@patch('parser.kalla_vy.rendera_anslutning')
@patch('parser.rum_render.utfor_utkast')
def test_data_export_anropar_inte_utfor_utkast(mock_utfor, mock_anslutning, mock_export, mock_ladda, mock_bygg, st_mock):
    st_mock.columns.return_value = [st_mock, st_mock]
    mock_export.return_value = ("fil.se", "fake_path", 1234, "2023-01-01", "2023-01-31")
    
    with patch('builtins.open', unittest.mock.mock_open(read_data=b"HEMLIGT_INNEHALL")):
        rendera_data()
        
    mock_utfor.assert_not_called()

@patch('parser.rum_render.st')
@patch('parser.rum_render._bygg_spiris_klient_fran_session')
@patch('parser.rum_render.app_config.las_config')
@patch('parser.spiris_adapter.ladda_ner_sie4export')
@patch('parser.kalla_vy.rendera_anslutning')
def test_data_export_visar_inte_innehall(mock_anslutning, mock_export, mock_ladda, mock_bygg, st_mock):
    st_mock.columns.return_value = [st_mock, st_mock]
    mock_export.return_value = ("fil.se", "fake_path", 1234, "2023-01-01", "2023-01-31")
    
    with patch('builtins.open', unittest.mock.mock_open(read_data=b"HEMLIGT_INNEHALL")):
        rendera_data()
        
    for args, kwargs in st_mock.write.call_args_list:
        if args:
            assert "HEMLIGT_INNEHALL" not in str(args[0])
    for args, kwargs in st_mock.caption.call_args_list:
        if args:
            assert "HEMLIGT_INNEHALL" not in str(args[0])
    for args, kwargs in st_mock.info.call_args_list:
        if args:
            assert "HEMLIGT_INNEHALL" not in str(args[0])
