"""test_sie4_utbyte.py — Steg 8: SIE4 in och ut.

Två åtgärder med helt olika riskprofil.

EXPORT är läsande men bär den STÖRSTA läckrisken i systemet: en SIE4-fil
innehåller hela bokföringen i klartext — varje motpartsnamn, varje
verifikationstext, möjligen personnummer — och ingenting av det passerar
maskeringen. Filens innehåll får därför aldrig nå ett MCP-verktyg, och inte
heller Spiris `TemporaryUrl`, som är en bärarnyckel till samma innehåll.

IMPORT är den mest ingripande skrivningen i hela API:t. Den har ingen
utkastmotsvarighet i Spiris, så grinden är att AI:n aldrig kan LEVERERA en fil
— bara peka ut en sökväg under en katalog användaren själv konfigurerat — och
att sammanfattningen räknas fram ur filen med projektets egen SIE4-läsare.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

_DOKUMENT = {
    "Id": "dok-1",
    "Name": "bokforing_2026.se",
    "ContentType": "application/octet-stream",
    "Size": 4242,
    "TemporaryUrl": "https://filer.example.com/hemlig-nyckel-abc123",
}

# En SIE4-fil bär allt i klartext. Fixturen innehåller därför sådant som
# ALDRIG får dyka upp i ett verktygssvar.
_SIE_INNEHALL = (
    "#FLAGGA 0\n"
    "#FNAMN \"Kundbolaget AB\"\n"
    "#KONTO 1930 \"Företagskonto\"\n"
    "#VER A 1 20260101 \"Betalning Anna Andersson 900102-1238\"\n"
    "{\n"
    "#TRANS 1930 {} 1000.00\n"
    "}\n"
).encode("cp437")


_SENASTE: dict = {}


class _FejkUtkast:
    """Fångar det utkast som skulle skapats, så sammanfattningen går att
    granska utan att skriva till disk."""

    def __init__(self, typ, nyttolast, sammanfattning) -> None:
        _SENASTE.clear()
        _SENASTE.update(
            typ=typ, nyttolast=nyttolast, sammanfattning=sammanfattning
        )
        self.utkast_id = "fejk-1"
        self.typ = typ
        self.skapad = "2026-08-06T00:00:00"
        self.status = "vantar"
        self.nyttolast = nyttolast
        self.sammanfattning = sammanfattning
        self.ar_utgangen = False


class _ExportKlient:
    def __init__(self, dokument: dict | None = None) -> None:
        self.hamtade: list[str] = []
        self._dokument = dict(dokument or _DOKUMENT)

    def hamta_en(self, path: str, params: dict | None = None) -> dict:
        self.hamtade.append(path)
        return dict(self._dokument)


class TestExportLackerInte:
    """Den viktigaste egenskapen i hela steget."""

    def _kor(self, tmp_path, monkeypatch, dokument=None):
        import saker_lagring
        from spiris_adapter import ladda_ner_sie4export

        monkeypatch.setattr(saker_lagring, "state_dir", lambda: tmp_path)
        klient = _ExportKlient(dokument)
        return ladda_ner_sie4export(
            klient, "2026-01-01", "2026-12-31",
            hamtare=lambda _url: _SIE_INNEHALL,
        )

    def test_metadata_bar_inte_filens_innehall(self, tmp_path, monkeypatch):
        metadata = self._kor(tmp_path, monkeypatch)
        serialiserat = json.dumps(metadata, default=str)

        assert "Anna Andersson" not in serialiserat
        assert "900102-1238" not in serialiserat
        assert "Kundbolaget AB" not in serialiserat

    def test_metadata_bar_inte_den_temporara_urlen(self, tmp_path, monkeypatch):
        """TemporaryUrl är en bärarnyckel till exakt samma innehåll."""
        metadata = self._kor(tmp_path, monkeypatch)

        assert "hemlig-nyckel-abc123" not in json.dumps(metadata, default=str)
        assert set(metadata) == {
            "filnamn", "sokvag", "storlek_byte", "period_fran", "period_till",
        }

    def test_filen_sparas_lokalt(self, tmp_path, monkeypatch):
        from pathlib import Path

        metadata = self._kor(tmp_path, monkeypatch)
        sparad = Path(metadata["sokvag"])

        assert sparad.exists()
        assert sparad.read_bytes() == _SIE_INNEHALL
        assert metadata["storlek_byte"] == len(_SIE_INNEHALL)

    def test_filnamn_ur_svaret_kan_inte_vara_en_sokvag(self, tmp_path, monkeypatch):
        """Namnet kommer från ett externt svar. Bara filnamnsdelen används —
        annars vore en Spiris-respons en skrivprimitiv i filsystemet."""
        from pathlib import Path

        elakt = dict(_DOKUMENT, Name="../../../etc/passwd")
        metadata = self._kor(tmp_path, monkeypatch, dokument=elakt)

        assert metadata["filnamn"] == "passwd"
        assert Path(metadata["sokvag"]).parent == tmp_path / "sie4export"

    def test_saknad_lank_hojer_fel(self, tmp_path, monkeypatch):
        import saker_lagring
        from spiris_adapter import SpirisKlientFel, ladda_ner_sie4export

        monkeypatch.setattr(saker_lagring, "state_dir", lambda: tmp_path)
        klient = _ExportKlient(dict(_DOKUMENT, TemporaryUrl=""))
        with pytest.raises(SpirisKlientFel):
            ladda_ner_sie4export(
                klient, "2026-01-01", "2026-12-31", hamtare=lambda _u: b""
            )

    def test_rag_omslaget_lacker_inte_heller(self, tmp_path, monkeypatch):
        """Egressgränsen: det är spiris_rag-svaret som når MCP-klienten."""
        import saker_lagring
        import spiris_rag

        monkeypatch.setattr(saker_lagring, "state_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "spiris_adapter.ladda_ner_sie4export",
            lambda klient, f, t: {
                "filnamn": "x.se", "sokvag": str(tmp_path / "x.se"),
                "storlek_byte": 10, "period_fran": f, "period_till": t,
            },
        )
        svar = asyncio.run(
            spiris_rag.exportera_sie4(_ExportKlient(), "2026-01-01", "2026-12-31")
        )

        assert "sakerhetsnot" in svar
        assert "TemporaryUrl" not in json.dumps(svar, default=str)


class TestImportpayload:
    def test_innehallet_base64_kodas(self):
        from spiris_adapter import bygg_sie4import_payload

        payload = bygg_sie4import_payload(_SIE_INNEHALL)

        assert base64.b64decode(payload["SieData"]) == _SIE_INNEHALL

    def test_alla_flaggor_ar_avstangda_som_standard(self):
        """Var och en av dem ändrar bokföringen på ett sätt användaren kanske
        inte avsåg. EndYearAdjustment utför ett ÅRSAVSLUT."""
        from spiris_adapter import bygg_sie4import_payload

        payload = bygg_sie4import_payload(_SIE_INNEHALL)

        for falt in ("MapLedgerAccount", "ImportOpeningBalance",
                     "EndYearAdjustment", "ImportAccountNames"):
            assert payload[falt] is False, falt

    def test_flaggor_gar_att_sla_pa_uttryckligen(self):
        from spiris_adapter import bygg_sie4import_payload

        payload = bygg_sie4import_payload(
            _SIE_INNEHALL, importera_ingaende_balans=True, arsavslut=True
        )

        assert payload["ImportOpeningBalance"] is True
        assert payload["EndYearAdjustment"] is True
        assert payload["ImportAccountNames"] is False

    def test_encoding_ar_sie_standardens(self):
        from spiris_adapter import SIE4_ENCODING_STANDARD, bygg_sie4import_payload

        payload = bygg_sie4import_payload(_SIE_INNEHALL)
        assert payload["Encoding"] == SIE4_ENCODING_STANDARD

    def test_tom_fil_hojer_fel(self):
        from spiris_adapter import bygg_sie4import_payload

        with pytest.raises(ValueError):
            bygg_sie4import_payload(b"")


class TestImportvagen:
    def test_filen_lases_vid_utforandet_inte_ur_utkastet(self, tmp_path):
        """Utkastet bär bara SÖKVÄGEN och de granskade flaggorna. Innehållet
        har aldrig passerat en AI, och hashen binder användarens beslut
        (vilken fil, vilka flaggor) — inte filens bytes."""
        from spiris_adapter import utfor_utkast

        fil = tmp_path / "bok.se"
        fil.write_bytes(_SIE_INNEHALL)

        class _Fangare:
            def __init__(self):
                self.skickat = []

            def skicka(self, path, data):
                self.skickat.append((path, data))
                return {"Id": "import-1"}

        klient = _Fangare()
        utfor_utkast(klient, "sie4import", {"sokvag": str(fil)})

        path, payload = klient.skickat[0]
        assert path == "/sie4import"
        assert base64.b64decode(payload["SieData"]) == _SIE_INNEHALL

    def test_oläsbar_fil_ger_begripligt_fel_och_skickar_inget(self, tmp_path):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        class _Fangare:
            def __init__(self):
                self.skickat = []

            def skicka(self, path, data):
                self.skickat.append((path, data))
                return {}
            def skicka_fil(self, path, query, payload, filename):
                self.skickat.append((path, query, filename))
                return {}

        klient = _Fangare()
        with pytest.raises(SpirisKlientFel) as fel:
            utfor_utkast(
                klient, "sie4import", {"sokvag": str(tmp_path / "finns-inte.se")}
            )

        assert klient.skickat == []
        assert "importerats" in str(fel.value)

    def test_flaggorna_i_utkastet_foljer_med(self, tmp_path):
        from spiris_adapter import utfor_utkast

        fil = tmp_path / "bok.se"
        fil.write_bytes(_SIE_INNEHALL)

        class _Fangare:
            def __init__(self):
                self.skickat = []

            def skicka(self, path, data):
                self.skickat.append((path, data))
                return {}
            def skicka_fil(self, path, query, payload, filename):
                self.skickat.append((path, query, filename))
                return {}

        klient = _Fangare()
        utfor_utkast(klient, "sie4import", {
            "sokvag": str(fil), "ingaende_balans": True, "arsavslut": True,
        })

        payload = klient.skickat[0][1]
        assert payload["ImportOpeningBalance"] is True
        assert payload["EndYearAdjustment"] is True


class TestSokvagsvakten:
    def test_import_utanfor_tillaten_katalog_vagras(self, tmp_path, monkeypatch):
        """AI:n kan peka ut en sökväg men inte välja vilka kataloger som får
        läsas — samma vakt som filverktygen redan använder."""
        import mcp_server.server as server_modul

        monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))
        monkeypatch.setattr(server_modul, "_villkor_godkanda", lambda: True)

        utanfor = tmp_path.parent / "utanfor.se"
        utanfor.write_bytes(_SIE_INNEHALL)

        svar = asyncio.run(server_modul.forbered_sie4import(str(utanfor)))

        assert svar["utkast_id"] is None
        assert "tillåten" in svar["info"]

    def test_lyckad_vag_ger_ett_utkast_med_sammanfattning_ur_filen(
        self, tmp_path, monkeypatch
    ):
        """Det test som SAKNADES. Utan det passerade en bugg — `parse_sie4`
        tar en sökväg, inte bytes, och den första versionen skickade
        `fil.read_bytes()`. Den föll alltid med TypeError, men except-satsen
        förvandlade felet till ett trovärdigt "filen gick inte att läsa".
        Bara felfallen var testade, så sviten var grön.

        Sammanfattningen ska komma ur FILEN, inte ur AI:ns beskrivning."""
        import mcp_server.server as server_modul

        monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))
        monkeypatch.setattr(server_modul, "_villkor_godkanda", lambda: True)
        monkeypatch.setattr(
            server_modul.utkast, "skapa",
            lambda typ, nyttolast, sammanfattning: _FejkUtkast(
                typ, nyttolast, sammanfattning
            ),
        )

        fil = tmp_path / "bok.se"
        fil.write_bytes(_SIE_INNEHALL)

        svar = asyncio.run(server_modul.forbered_sie4import(str(fil)))

        assert svar["utkast_id"] == "fejk-1"
        etiketter = dict(_SENASTE["sammanfattning"])
        assert etiketter["Bolag i filen"] == "Kundbolaget AB"
        assert etiketter["Antal verifikationer"] == "1"
        assert etiketter["Ingående balanser"] == "nej"
        assert _SENASTE["nyttolast"]["sokvag"] == str(fil)

    def test_otolkbar_fil_blir_inget_utkast(self, tmp_path, monkeypatch):
        """`parse_sie4` VALIDERAR INTE att filen är SIE4 — den letar efter
        #-direktiv och ger en tom SIEFil om inga finns. En binär skräpfil
        passerade alltså utan undantag och blev ett riktigt utkast.

        Fångat i sandbox-provet, inte av den ursprungliga versionen av det här
        testet: det förutsatte att parsern skulle KASTA, och var grönt av fel
        skäl så länge en annan bugg råkade göra det. Spärren är nu explicit —
        varken verifikationer eller konton betyder att det inte är bokföring."""
        import mcp_server.server as server_modul

        monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))
        monkeypatch.setattr(server_modul, "_villkor_godkanda", lambda: True)

        skrap = tmp_path / "skrap.se"
        skrap.write_bytes(b"\x00\x01\x02 inte en SIE-fil")

        svar = asyncio.run(server_modul.forbered_sie4import(str(skrap)))

        assert svar["utkast_id"] is None
