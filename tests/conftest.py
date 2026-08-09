"""Delad testkonfiguration.

Isolerar all lokal säkerhetsdata till en per-test temp-katalog: sätter
SIE_MCP_DATA_ROOT så att default-sökvägar (secrets/state/logs) via
saker_lagring aldrig hamnar i den riktiga %LOCALAPPDATA% eller i repo-/
Drive-mappen under en testkörning. Tester som uttryckligen vill pröva
default- eller env-beteendet kan själva monkeypatcha över detta.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolerad_saker_datarot(tmp_path, monkeypatch):
    monkeypatch.setenv("SIE_MCP_DATA_ROOT", str(tmp_path / "sie_mcp_data"))
    yield
