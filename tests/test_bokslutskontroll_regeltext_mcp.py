"""Steg 9a — test av MCP-verktyget hamta_regeltext.

Se hantverksbok/BOKSLUTSKONTROLLER.md §8.3. Villkorsspärren (blockerat läge)
täcks av tests/test_mcp_villkorssparr.py::test_hamta_regeltext_sparras_utan_godkannande
— den här filen prövar sakinnehållet."""

from __future__ import annotations

import asyncio

import compliance
import mcp_server.server as server_modul
from mcp_server.server import hamta_regeltext


def _kor(kontroll_id: str) -> dict:
    return asyncio.run(hamta_regeltext(kontroll_id))


def test_okant_kontroll_id_ger_strukturerat_fel():
    compliance.godkann_compliance()
    svar = _kor("K-999")
    assert svar["lydelse"] is None
    assert svar["fel"] is not None
    assert "K-999" in svar["fel"]


def test_k00_saknar_sfs_grundad_hanvisning():
    """K-00 har medvetet ingen rättslig grund (motorns eget felfynd) — ska
    ge ett tydligt fel, inte försöka slå upp något."""
    compliance.godkann_compliance()
    svar = _kor("K-00")
    assert svar["lydelse"] is None
    assert svar["fel"] is not None
    assert svar["beteckning"] is None or svar["beteckning"] == ""


def test_kalla_som_inte_hittar_nagot_ger_strukturerat_fel_inte_krasch(monkeypatch):
    compliance.godkann_compliance()

    class _TomKalla:
        def hamta(self, sfs, beteckning):
            return None

    import bokslutskontroll.regeltext as regeltext_modul

    monkeypatch.setattr(regeltext_modul, "valj_regeltextkalla", lambda: _TomKalla())

    svar = _kor("K-01")
    assert svar["lydelse"] is None
    assert svar["fel"] is not None
    assert svar["beteckning"] == "5 kap. 1 §"


def test_kalla_som_hittar_lydelsen(monkeypatch):
    compliance.godkann_compliance()

    class _FullKalla:
        def hamta(self, sfs, beteckning):
            return "Bokföring skall ske på ett sådant sätt att ..."

    import bokslutskontroll.regeltext as regeltext_modul

    monkeypatch.setattr(regeltext_modul, "valj_regeltextkalla", lambda: _FullKalla())

    svar = _kor("K-01")
    assert svar["fel"] is None
    assert svar["lydelse"] == "Bokföring skall ske på ett sådant sätt att ..."
    assert svar["beteckning"] == "5 kap. 1 §"


def test_ovantat_fel_i_kallan_lacker_inte_ra_exceptiontext(monkeypatch):
    compliance.godkann_compliance()

    class _Kraschar:
        def hamta(self, sfs, beteckning):
            raise RuntimeError("Lön Berit Kvist 850615-1234")

    import bokslutskontroll.regeltext as regeltext_modul

    monkeypatch.setattr(regeltext_modul, "valj_regeltextkalla", lambda: _Kraschar())

    svar = _kor("K-01")
    assert svar["lydelse"] is None
    assert "Berit" not in str(svar)
    assert "850615" not in str(svar)
