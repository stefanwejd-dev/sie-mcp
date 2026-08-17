import json
import pytest
from parser.kraschlogg import registrera_krasch, hamta_senaste_krasch, hamta_alla_krascher, KRASCHLOGG_FIL


def test_registrera_krasch_skapar_loggrad(tmp_path, monkeypatch):
    test_logg = tmp_path / "kraschlogg.jsonl"
    monkeypatch.setattr("parser.kraschlogg.KRASCHLOGG_FIL", test_logg)
    monkeypatch.setattr("parser.kraschlogg.LOGG_KATALOG", tmp_path)

    try:
        raise ValueError("Test-krasch för validering")
    except Exception as e:
        rapport = registrera_krasch(e, sida="test_sida")

    assert rapport["feltyp"] == "ValueError"
    assert rapport["felmeddelande"] == "Test-krasch för validering"
    assert rapport["sida"] == "test_sida"
    assert "test_registrera_krasch" in rapport["stacktrace"]
    assert test_logg.exists()

    senaste = hamta_senaste_krasch()
    assert senaste is not None
    assert senaste["felmeddelande"] == "Test-krasch för validering"

    alla = hamta_alla_krascher()
    assert len(alla) == 1
