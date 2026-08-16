"""Steg 7 — test av MCP-verktygen bokslutskontroll/spiris_bokslutskontroll.

Se hantverksbok/BOKSLUTSKONTROLLER.md §7 steg 7 (acceptans). Villkorsspärren
för BÅDA verktygen (blockerat läge) och Spiris-varianten som helhet täcks
redan generiskt av tests/test_mcp_villkorssparr.py respektive
tests/test_mcp_lasande_bredd.py — den här filen prövar sakinnehållet: I-3
(maskerad data på MCP-vägen) och sökvägsvakten, i samma stil som
tests/test_mcp_server.py gör för granska_kontotyper (H1)."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import compliance
import mcp_server.server as server_modul
from bokslutskontroll.modell import Fynd
from domain_model import Konto, SIEFil
from mcp_server.server import bokslutskontroll

SIE4_EXEMPEL = str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE")
_RÅ_PII = "Anna Andersson"


@pytest.fixture(autouse=True)
def _tillat_test_siefiler(monkeypatch, tmp_path):
    kataloger = f"{Path(SIE4_EXEMPEL).parent.resolve()}{os.pathsep}{tmp_path.resolve()}"
    monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", kataloger)


class TestVillkorsspärrenLäserAldrigFilen:
    """Spärrat läge ska stoppa INNAN filen ens läses — inte bara innan
    resultatet lämnas ut. Kompletterar test_mcp_villkorssparr.py, som bara
    prövar svarsformen."""

    def test_ingen_fil_las_nar_villkor_ej_godkanda(self, monkeypatch, tmp_path):
        fil = tmp_path / "bok.se"
        fil.write_text("#FLAGGA 0\n", encoding="utf-8")

        def _far_inte_anropas(_s):
            raise AssertionError("parse_sie4 anropades trots spärrat läge")

        monkeypatch.setattr(server_modul, "parse_sie4", _far_inte_anropas)

        svar = bokslutskontroll(str(fil))

        assert svar["fel"] == compliance.SPARRTEXT_KORT
        assert svar["fynd"] is None
        assert svar["sammanfattning"] is None


class TestSökvägsvakten:

    def test_avvisar_fil_utanfor_sie_katalog(self, monkeypatch, tmp_path):
        compliance.godkann_compliance()
        utanfor = tmp_path.parent / "utanfor_allowlist.se"
        utanfor.write_text("#FLAGGA 0\n", encoding="utf-8")
        # Bara tmp_path (inte dess förälder) är tillåten av fixturen ovan.
        monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))

        svar = bokslutskontroll(str(utanfor))

        assert svar["fynd"] is None
        assert svar["sammanfattning"] is None
        assert svar["fel"] is not None


class TestI3MaskeradDataPåMCPVägen:
    """I-3: MCP-vägen ska ALLTID köra motorn mot den maskerade SIEFil:en.
    Testet bygger en riktig SIEFil med ett personnamn i ett kontonamn, och
    en fejkad kontroll vars fynd ekar precis det namn motorn faktiskt fick
    se. Nådde det råa namnet fram är maskeringen förbikopplad."""

    def _kor_med_pii_kontonamn(self, monkeypatch, tmp_path) -> dict:
        compliance.godkann_compliance()
        fil = tmp_path / "bok.se"
        fil.write_text("#FLAGGA 0\n", encoding="utf-8")

        sie = SIEFil(
            företagsnamn="Testbolaget AB",
            konton={"3041": Konto(kontonr="3041", namn=f"Försäljning till {_RÅ_PII}")},
        )
        monkeypatch.setattr(server_modul, "parse_sie4", lambda _s: sie)

        def _fejkad_kor_kontroller(maskerad_sie, *, idag, arsnr=0, endast=None):
            # Ekar tillbaka precis det kontonamn motorn faktiskt tog emot —
            # om det är maskerat visar fyndets motivering en token, annars
            # det råa namnet.
            return [
                Fynd(
                    kontroll_id="K-01",
                    rubrik="Testfynd",
                    allvarlighet="upplysning",
                    motivering=maskerad_sie.konton["3041"].namn,
                )
            ]

        monkeypatch.setattr(
            server_modul, "_kor_bokslutskontroller", _fejkad_kor_kontroller
        )
        return bokslutskontroll(str(fil))

    def test_ratt_namn_maskeras_bort(self, monkeypatch, tmp_path):
        resultat = self._kor_med_pii_kontonamn(monkeypatch, tmp_path)
        assert resultat["fel"] is None
        motivering = resultat["fynd"][0]["motivering"]
        assert _RÅ_PII not in motivering
        assert "PERSON_" in motivering

    def test_hela_serialiserade_svaret_ar_pii_fritt(self, monkeypatch, tmp_path):
        resultat = self._kor_med_pii_kontonamn(monkeypatch, tmp_path)
        assert _RÅ_PII not in json.dumps(resultat, ensure_ascii=False)


class TestFacitMotExempelfilen:

    def test_giltig_fil_ger_strukturerat_svar(self):
        compliance.godkann_compliance()
        resultat = bokslutskontroll(SIE4_EXEMPEL)

        assert resultat["fel"] is None
        assert isinstance(resultat["fynd"], list)
        assert set(resultat["sammanfattning"]) == {"avvikelse", "observation", "upplysning"}
        for fynd in resultat["fynd"]:
            assert fynd["kontroll_id"]
            assert fynd["allvarlighet"] in ("avvikelse", "observation", "upplysning")
            if fynd["belopp"] is not None:
                assert isinstance(fynd["belopp"], float)

    def test_saknad_fil_ger_strukturerat_fel_inte_krasch(self):
        compliance.godkann_compliance()
        resultat = bokslutskontroll("/sokvag/som/inte/finns.SE")

        assert resultat["fynd"] is None
        assert resultat["fel"] is not None
        assert isinstance(resultat["fel"], str)
