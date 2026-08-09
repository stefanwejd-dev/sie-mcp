import pytest
from datetime import date
from parser.app_tillstand import bygg_rapportunderlag

class DummySessionState(dict):
    def __getattr__(self, key):
        if key in self:
            return self[key]
        raise AttributeError(f"'DummySessionState' object has no attribute '{key}'")

class DummySt:
    def __init__(self, session_state_dict):
        self.session_state = DummySessionState(session_state_dict)

def test_bygg_rapportunderlag_ingen():
    st = DummySt({"aktiv_datakälla": "Ladda upp lokal SIE4-fil"})
    underlag = bygg_rapportunderlag(st)
    assert underlag.rapporter is None
    assert underlag.kundbetalbeteende == {}
    assert underlag.likviditetsprognos is None
    assert underlag.lage == "ingen"

def test_bygg_rapportunderlag_fil(monkeypatch):
    sie_mock = type("Mock", (), {})()
    st = DummySt({
        "aktiv_datakälla": "Ladda upp lokal SIE4-fil",
        "sie": sie_mock
    })
    
    monkeypatch.setattr("parser.app_tillstand.rapporter_fran_sie", lambda x: {"mock": "fil"})
    
    underlag = bygg_rapportunderlag(st)
    assert underlag.rapporter == {"mock": "fil"}
    assert underlag.kundbetalbeteende == {}
    assert underlag.likviditetsprognos is None
    assert underlag.lage == "fil"

def test_bygg_rapportunderlag_spiris(monkeypatch):
    st = DummySt({
        "aktiv_datakälla": "Koppla till Spiris",
        "spiris_dashboarddata": {"balans": {"poster": {"kassa_och_bank": 100}}},
        "spiris_kundbetalhistorik": [],
        "spiris_reskontra": [],
        "spiris_kundreskontra": [],
        "sie": None,
    })
    
    monkeypatch.setattr("parser.app_tillstand.berakna_kundbetalbeteende", lambda x: {"beteende": True})
    monkeypatch.setattr("parser.app_tillstand.likviditetsprognos_fran_reskontra", lambda *args, **kwargs: [{"saldo": 100}])
    
    underlag = bygg_rapportunderlag(st)
    assert underlag.rapporter is not None
    assert underlag.kundbetalbeteende == {"beteende": True}
    assert underlag.likviditetsprognos == [{"saldo": 100}]
    assert underlag.lage == "spiris"
