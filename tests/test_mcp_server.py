"""
Tester för mcp_server/server.py.

Etablerar och verifierar kontraktet för de två verktygen (se ARCHITECTURE.md,
avsnittet "MCP-brygga (Modul 1 + Modul 2)", §3) — inte en uttömmande testsvit.
"""

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import compliance
import mcp_server.server as server_modul
from mcp_server.server import (
    berakna_vasentlighet,
    granska_kontotyper,
    spiris_balansrapport,
    spiris_kontosaldon,
    spiris_kontotransaktioner,
    spiris_resultatrapport,
    spiris_sok_verifikationer,
)

SIE4_EXEMPEL = str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE")


@pytest.fixture(autouse=True)
def _tillat_test_siefiler(monkeypatch, tmp_path):
    kataloger = f"{Path(SIE4_EXEMPEL).parent.resolve()}{os.pathsep}{tmp_path.resolve()}"
    monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", kataloger)


@pytest.fixture(autouse=True)
def _godkanda_villkor():
    """Villkoren godkända i den isolerade datarot conftest sätter upp.

    Verktygen är fail-closed bakom villkorsspärren (server._villkor_godkanda).
    Testerna i den här filen prövar verktygens SAKINNEHÅLL — själva spärren har
    en egen svit i tests/test_mcp_villkorssparr.py, som medvetet INTE godkänner.
    """
    compliance.godkann_compliance()


class TestBeraknaVasentlighet:

    def test_facit_mot_exempelfilen(self):
        resultat = berakna_vasentlighet(SIE4_EXEMPEL)

        assert resultat["fel"] is None
        v = resultat["vasentlighet"]
        assert v is not None
        assert v["omsattning"] == pytest.approx(2583800.00, abs=0.01)
        assert v["resultat"] == pytest.approx(428690.00, abs=0.01)
        assert v["balansomslutning"] == pytest.approx(3457690.00, abs=0.01)
        assert v["eget_kapital"] == pytest.approx(2267690.00, abs=0.01)

    def test_saknad_fil_ger_strukturerat_fel_inte_krasch(self):
        resultat = berakna_vasentlighet("/sokvag/som/inte/finns.SE")

        assert resultat["vasentlighet"] is None
        assert resultat["fel"] is not None
        assert isinstance(resultat["fel"], str)


class TestGranskaKontotyper:

    def test_facit_flaggade_konton_mot_exempelfilen(self):
        resultat = granska_kontotyper(SIE4_EXEMPEL)

        assert resultat["fel"] is None
        flaggade_konton = {a["konto"] for a in resultat["avvikelser"]}
        assert {"2084", "2085", "2157"}.issubset(flaggade_konton)

        konto_2157 = next(a for a in resultat["avvikelser"] if a["konto"] == "2157")
        assert set(konto_2157["lager"]) == {"internmonster", "referensmonster"}
        assert konto_2157["stod"] == "4/5"
        # Facit-motiveringstexten är inte känd i förväg (genereras av
        # kontotyp_vakt.py) — testar bara att fälten är meningsfullt
        # ifyllda, inte en exakt ordalydelse.
        assert isinstance(konto_2157["kontonamn"], str) and konto_2157["kontonamn"] != ""
        assert isinstance(konto_2157["motivering"], str) and konto_2157["motivering"] != ""

    def test_stod_ar_none_for_konto_flaggat_enbart_av_referensmonster(self):
        """Kontrollfall mot 2157: 2084/2085 fångas bara av referensmönster
        (klassnivå), inte internmönster (grannjämförelse) — stod ska då
        vara None, inte en sträng."""
        resultat = granska_kontotyper(SIE4_EXEMPEL)

        konto_2084 = next(a for a in resultat["avvikelser"] if a["konto"] == "2084")
        assert konto_2084["lager"] == ["referensmonster"]
        assert konto_2084["stod"] is None

    def test_saknad_fil_ger_strukturerat_fel_inte_krasch(self):
        resultat = granska_kontotyper("/sokvag/som/inte/finns.SE")

        assert resultat["avvikelser"] is None
        assert resultat["fel"] is not None
        assert isinstance(resultat["fel"], str)


# --- Kontraktstest: felschemat är symmetriskt mellan verktygen -------------

class TestGemensamtFelkontrakt:

    def test_bada_verktygen_foljer_samma_felschema(self):
        v_resultat = berakna_vasentlighet("/finns/inte.SE")
        k_resultat = granska_kontotyper("/finns/inte.SE")

        assert set(v_resultat.keys()) == {"vasentlighet", "tolkningsbehov_antal", "fel"}
        assert set(k_resultat.keys()) == {"avvikelser", "tolkningsbehov_antal", "fel"}


class _FejkSpirisKlient:
    def __init__(self) -> None:
        self.access_token = "AT"
        self.refresh_token = "RT"

    def hamta_en(self, path, params=None):
        return {"Name": "X Sandbox", "CorporateIdentityNumber": "556677-8899"}

    def hamta_alla(self, path, params=None):
        if path.startswith("/accounts/"):
            return [{"Number": "1910", "Name": "Kassa", "Type": 9}]
        if path.startswith("/accountbalances/"):
            return [{"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("500.00")}]
        raise AssertionError(f"oväntad path: {path}")


class TestSpirisRagOmslag:
    def test_ingen_session_ger_failclosed_info_inte_krasch(self, monkeypatch):
        monkeypatch.delenv("SPIRIS_CLIENT_ID", raising=False)
        monkeypatch.delenv("SPIRIS_CLIENT_SECRET", raising=False)

        resultat = asyncio.run(spiris_kontosaldon("fy-2026", "2026-12-31"))

        assert resultat["data"] == []
        assert "session" in resultat["info"].lower()

    def test_decimal_serialiseras_till_float(self, monkeypatch):
        fejk = _FejkSpirisKlient()
        monkeypatch.setattr(server_modul, "bygg_klient", lambda: fejk)
        monkeypatch.setattr(server_modul, "spara_session", lambda k: None)

        resultat = asyncio.run(spiris_kontosaldon("fy-2026", "2026-12-31"))

        assert resultat["data"], "borde ha minst ett konto"
        assert all(isinstance(rad["saldo"], float) for rad in resultat["data"])

    def test_persisterar_token_efter_anrop(self, monkeypatch):
        fejk = _FejkSpirisKlient()
        sparade = []
        monkeypatch.setattr(server_modul, "bygg_klient", lambda: fejk)
        monkeypatch.setattr(server_modul, "spara_session", lambda k: sparade.append(k))

        asyncio.run(spiris_kontosaldon("fy-2026", "2026-12-31"))

        assert sparade == [fejk]  # token skrevs tillbaka (finally) efter anropet


# ===========================================================================
# Säkerhetspaket K1/H1/H2 — MCP-servern får aldrig läcka rå PII
# ===========================================================================

# Ett känt referenslistnamn ("Anna Andersson" finns i namnreferens.STANDARDNAMN)
# planteras i FÖRETAGSNAMN, KONTONAMN, VERIFIKATIONSTEXT och TRANSAKTIONSTEXT.
# Efter maskering (Lager 1 strukturellt + Lager 3a) får det ALDRIG förekomma i
# något serialiserat MCP-svar.
_RÅ_PII = "Anna Andersson"

_PII_COMPANY = {"Name": f"{_RÅ_PII} AB", "CorporateIdentityNumber": "556677-8899"}
_PII_ACCOUNTS = [
    {"Number": "1910", "Name": "Kassa", "Type": 9},
    {"Number": "1510", "Name": "Kundfordringar", "Type": 5},
    {"Number": "3041", "Name": _RÅ_PII, "Type": 20},
]
_PII_BALANCES = [
    {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("500.00")},
    {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("1000.00")},
    {"AccountNumber": 3041, "AccountName": _RÅ_PII, "Balance": Decimal("-1500.00")},
]
_PII_VOUCHERS = [
    {
        "NumberAndNumberSeries": "A1", "NumberSeries": "A", "VoucherDate": "2026-01-05",
        "VoucherText": f"Kundfaktura till {_RÅ_PII}", "CreatedUtc": "2026-01-05T00:00:00Z",
        "Rows": [
            {"AccountNumber": 1510, "DebitAmount": Decimal("1000.00"),
             "CreditAmount": Decimal("0"), "TransactionText": f"Faktura {_RÅ_PII}"},
            {"AccountNumber": 3041, "DebitAmount": Decimal("0"),
             "CreditAmount": Decimal("1000.00"), "TransactionText": f"Faktura {_RÅ_PII}"},
        ],
    },
]


class _FejkSpirisKlientMedPii:
    """Serverar huvudboksdata där ett känt personnamn förekommer i varje
    fritextfält — för att bevisa att ingen MCP-väg släpper ut det omaskerat."""

    def __init__(self) -> None:
        self.access_token = "AT"
        self.refresh_token = "RT"

    def hamta_en(self, path, params=None):
        if path == "/companysettings":
            return _PII_COMPANY
        raise AssertionError(f"oväntad hamta_en: {path}")

    def hamta_alla(self, path, params=None):
        if path.startswith("/accounts/"):
            return _PII_ACCOUNTS
        if path.startswith("/accountbalances/"):
            return _PII_BALANCES
        if path.startswith("/vouchers/"):
            return _PII_VOUCHERS
        raise AssertionError(f"oväntad hamta_alla: {path}")


class TestK1IngaHitlVerktygIRegistret:
    """K1: den läckande MCP-HITL-vägen (som skickade rå misstänkt_text till
    AI-klienten) är helt borttagen. Verktygsregistret får inte ens antyda att
    rå maskeringsgranskning kan göras via MCP."""

    def _registrerade_verktyg(self) -> set[str]:
        return {t.name for t in asyncio.run(server_modul.mcp.list_tools())}

    def test_borttagna_hitl_verktyg_finns_inte(self):
        namn = self._registrerade_verktyg()
        assert "spiris_lista_maskeringsbehov" not in namn
        assert "spiris_besluta_maskering" not in namn

    def test_forvantade_verktyg_finns_kvar(self):
        namn = self._registrerade_verktyg()
        assert {
            "berakna_vasentlighet", "granska_kontotyper", "spiris_kontosaldon",
            "spiris_kontotransaktioner", "spiris_sok_verifikationer",
            "spiris_resultatrapport", "spiris_balansrapport",
        }.issubset(namn)

    def test_modulen_exporterar_inte_langre_hitl_funktioner(self):
        # Ingen död publik funktion kvar som antyder MCP-maskeringsgranskning.
        assert not hasattr(server_modul, "spiris_lista_maskeringsbehov")
        assert not hasattr(server_modul, "spiris_besluta_maskering")


class TestK1IngenRaPiiIMcpUtflode:
    """K1-regressionstest: kör VARJE PII-hanterande MCP-verktyg mot data där
    'Anna Andersson' är planterat i alla fritextfält, och bevisa att namnet
    aldrig förekommer i det serialiserade svaret."""

    def _kor_alla_spiris_verktyg(self, monkeypatch, tmp_path) -> list[dict]:
        monkeypatch.chdir(tmp_path)  # isolera revisionslogg/namnreferens från roten
        fejk = _FejkSpirisKlientMedPii()
        monkeypatch.setattr(server_modul, "bygg_klient", lambda: fejk)
        monkeypatch.setattr(server_modul, "spara_session", lambda k: None)
        return [
            asyncio.run(spiris_kontosaldon("fy-2026", "2026-12-31")),
            asyncio.run(spiris_kontotransaktioner("fy-2026", "3041")),
            asyncio.run(spiris_sok_verifikationer("fy-2026", "faktura")),
            asyncio.run(spiris_resultatrapport("2026-01-01", "2026-12-31")),
            asyncio.run(spiris_balansrapport("2026-12-31")),
        ]

    def test_ra_pii_forekommer_aldrig_i_nagot_spiris_svar(self, monkeypatch, tmp_path):
        svar = self._kor_alla_spiris_verktyg(monkeypatch, tmp_path)
        serialiserat = json.dumps(svar, ensure_ascii=False, default=str)
        assert _RÅ_PII not in serialiserat

    def test_verktygen_returnerar_faktiskt_data_att_granska(self, monkeypatch, tmp_path):
        # Vaktar mot ett falskt godkänt test där tomma svar trivialt "saknar" PII.
        svar = self._kor_alla_spiris_verktyg(monkeypatch, tmp_path)
        assert any(s.get("data") for s in svar[:3])


class TestH1MaskeratKontonamnIGranskaKontotyper:
    """H1: det filbaserade verktyget granska_kontotyper maskerade förr aldrig
    kontonamnet. Ett kontonamn är osäker fritext (Visma: '7010 Lön Anna
    Andersson'), så det måste maskeras innan det lämnar processen — men
    kontonr, kontotyp, stöd och motivering ska bevaras."""

    def _kor_med_pii_kontonamn(self, monkeypatch, tmp_path) -> dict:
        monkeypatch.chdir(tmp_path)
        dummy = tmp_path / "dummy.se"
        dummy.write_text("#FLAGGA 0\n", encoding="utf-8")
        monkeypatch.setattr(
            server_modul, "parse_sie4", lambda _s: SimpleNamespace(tolkningsbehov=[])
        )
        avvikelse = SimpleNamespace(
            kontonr="7010", kontonamn=f"Lön {_RÅ_PII}", forvantad_typ="K",
            angiven_typ="T", lager=["referensmonster"], stod_internmonster=None,
            motivering="Klass 7 väntas normalt vara en kostnad (K).",
        )
        monkeypatch.setattr(server_modul, "analysera_kontotyper", lambda _s: [avvikelse])
        return granska_kontotyper(str(dummy))

    def test_kontonamn_maskeras_men_ovriga_falt_bevaras(self, monkeypatch, tmp_path):
        resultat = self._kor_med_pii_kontonamn(monkeypatch, tmp_path)
        assert resultat["fel"] is None
        rad = resultat["avvikelser"][0]
        assert _RÅ_PII not in rad["kontonamn"]
        assert "PERSON_" in rad["kontonamn"]
        # Bokföringsdata bevaras oförändrat.
        assert rad["konto"] == "7010"
        assert rad["forvantad_typ"] == "K"
        assert rad["faktisk_typ"] == "T"
        assert rad["motivering"] == "Klass 7 väntas normalt vara en kostnad (K)."

    def test_hela_serialiserade_svaret_ar_pii_fritt(self, monkeypatch, tmp_path):
        resultat = self._kor_med_pii_kontonamn(monkeypatch, tmp_path)
        assert _RÅ_PII not in json.dumps(resultat, ensure_ascii=False)


class TestH2StatiskaFelmeddelanden:
    """H2: felmeddelanden som RETURNERAS till MCP-klienten är statiska och
    generiska — aldrig den råa exception-texten, som kan bära en filrad med
    PII. Detaljen loggas bara lokalt (och då bara typnamn, M2)."""

    _HEMLIG = "Lön Berit Kvist 850615-1234"

    def test_parsefel_lacker_inte_rå_exceptiontext(self, monkeypatch, tmp_path):
        dummy = tmp_path / "x.se"
        dummy.write_text("#FLAGGA 0\n", encoding="utf-8")

        def _kasta(_s):
            raise ValueError(self._HEMLIG)

        monkeypatch.setattr(server_modul, "parse_sie4", _kasta)
        resultat = berakna_vasentlighet(str(dummy))

        assert resultat["fel"] == "Internt fel vid inläsning av filen."
        assert self._HEMLIG not in resultat["fel"]
        assert "850615-1234" not in resultat["fel"]

    def test_berakningsfel_lacker_inte_rå_exceptiontext(self, monkeypatch, tmp_path):
        dummy = tmp_path / "x.se"
        dummy.write_text("#FLAGGA 0\n", encoding="utf-8")
        monkeypatch.setattr(
            server_modul, "parse_sie4", lambda _s: SimpleNamespace(tolkningsbehov=[])
        )

        def _kasta(_s):
            raise ValueError(self._HEMLIG)

        monkeypatch.setattr(server_modul, "_berakna_vasentlighet", _kasta)
        resultat = berakna_vasentlighet(str(dummy))

        assert resultat["fel"] == "Internt fel vid beräkning."
        assert self._HEMLIG not in json.dumps(resultat, ensure_ascii=False)

    def test_kontotypfel_lacker_inte_rå_exceptiontext(self, monkeypatch, tmp_path):
        dummy = tmp_path / "x.se"
        dummy.write_text("#FLAGGA 0\n", encoding="utf-8")
        monkeypatch.setattr(
            server_modul, "parse_sie4", lambda _s: SimpleNamespace(tolkningsbehov=[])
        )

        def _kasta(_s):
            raise ValueError(self._HEMLIG)

        monkeypatch.setattr(server_modul, "analysera_kontotyper", _kasta)
        resultat = granska_kontotyper(str(dummy))

        assert resultat["fel"] == "Internt fel vid analys."
        assert self._HEMLIG not in json.dumps(resultat, ensure_ascii=False)

    def test_filnotfound_ger_statiskt_meddelande(self, monkeypatch):
        def _kasta(_s):
            raise FileNotFoundError(self._HEMLIG)

        monkeypatch.setattr(server_modul, "parse_sie4", _kasta)
        resultat = granska_kontotyper("/x.SE")

        assert resultat["fel"] == (
            "Kunde inte läsa filen (kontrollera att sökvägen finns och är läsbar)."
        )
        assert self._HEMLIG not in resultat["fel"]


class TestSokvagsvakt:
    """Paket C2: Sökvägsvakt för de filbaserade MCP-verktygen."""

    def test_filbaserat_verktyg_avvisar_sokvag_utanfor_allowlist(self, monkeypatch, tmp_path):
        tillaten_dir = tmp_path / "tillaten"
        otillaten_dir = tmp_path / "otillaten"
        tillaten_dir.mkdir()
        otillaten_dir.mkdir()

        fil_utanfor = otillaten_dir / "test.se"
        fil_utanfor.write_text("#FLAGGA 0\n", encoding="utf-8")

        monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tillaten_dir))

        res_v = berakna_vasentlighet(str(fil_utanfor))
        assert res_v["vasentlighet"] is None
        assert res_v["fel"] == "Kunde inte läsa filen (kontrollera att sökvägen finns och är läsbar)."

        res_g = granska_kontotyper(str(fil_utanfor))
        assert res_g["avvikelser"] is None
        assert res_g["fel"] == "Kunde inte läsa filen (kontrollera att sökvägen finns och är läsbar)."

    def test_avvisad_sokvag_ger_samma_fel_som_saknad_fil(self, monkeypatch, tmp_path):
        tillaten_dir = tmp_path / "tillaten"
        otillaten_dir = tmp_path / "otillaten"
        tillaten_dir.mkdir()
        otillaten_dir.mkdir()

        fil_utanfor = otillaten_dir / "test.se"
        fil_utanfor.write_text("#FLAGGA 0\n", encoding="utf-8")

        fil_saknad_inom = tillaten_dir / "saknad.se"

        monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tillaten_dir))

        res_utanfor = granska_kontotyper(str(fil_utanfor))
        res_saknad = granska_kontotyper(str(fil_saknad_inom))

        assert res_utanfor["fel"] == res_saknad["fel"]
        assert res_utanfor["fel"] == "Kunde inte läsa filen (kontrollera att sökvägen finns och är läsbar)."


# --- Lager 3b v2: okänt namn i STRÄNGSTART får aldrig läcka via MCP ---------

_STARTNAMN = "Xerxes Qoolio"  # okänt (ej i referenslistan), står först i fälten

_START_COMPANY = {"Name": "X Sandbox", "CorporateIdentityNumber": "556677-8899"}
_START_ACCOUNTS = [
    {"Number": "1910", "Name": "Kassa", "Type": 9},
    {"Number": "2393", "Name": _STARTNAMN, "Type": 15},  # bart namn i strängstart
]
_START_BALANCES = [
    {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("500.00")},
    {"AccountNumber": 2393, "AccountName": _STARTNAMN, "Balance": Decimal("-500.00")},
]
_START_VOUCHERS = [
    {
        "NumberAndNumberSeries": "A1", "NumberSeries": "A", "VoucherDate": "2026-01-05",
        "VoucherText": f"{_STARTNAMN} ny kund", "CreatedUtc": "2026-01-05T00:00:00Z",
        "Rows": [
            {"AccountNumber": 1510, "DebitAmount": Decimal("500.00"),
             "CreditAmount": Decimal("0"), "TransactionText": f"{_STARTNAMN} betalning"},
        ],
    },
]


class _FejkKlientStartnamn:
    def __init__(self) -> None:
        self.access_token = "AT"
        self.refresh_token = "RT"

    def hamta_en(self, path, params=None):
        if path == "/companysettings":
            return _START_COMPANY
        raise AssertionError(f"oväntad hamta_en: {path}")

    def hamta_alla(self, path, params=None):
        if path.startswith("/accounts/"):
            return _START_ACCOUNTS
        if path.startswith("/accountbalances/"):
            return _START_BALANCES
        if path.startswith("/vouchers/"):
            return _START_VOUCHERS
        raise AssertionError(f"oväntad hamta_alla: {path}")


class TestLager3bStrangstartMcp:
    """Okänt namn allra först i kontonamn/vertext/transtext får aldrig
    förekomma i ett serialiserat MCP-svar (kontonamn maskeras, verifikat med
    olöst namn blockeras)."""

    def _svar(self, monkeypatch, tmp_path) -> list[dict]:
        monkeypatch.chdir(tmp_path)
        fejk = _FejkKlientStartnamn()
        monkeypatch.setattr(server_modul, "bygg_klient", lambda: fejk)
        monkeypatch.setattr(server_modul, "spara_session", lambda k: None)
        return [
            asyncio.run(spiris_kontosaldon("fy-2026", "2026-12-31")),
            asyncio.run(spiris_kontotransaktioner("fy-2026", "1510")),
            asyncio.run(spiris_sok_verifikationer("fy-2026", "kund")),
            asyncio.run(spiris_balansrapport("2026-12-31")),
        ]

    def test_startnamn_forekommer_aldrig_i_serialiserat_svar(self, monkeypatch, tmp_path):
        svar = self._svar(monkeypatch, tmp_path)
        serialiserat = json.dumps(svar, ensure_ascii=False, default=str)
        assert _STARTNAMN not in serialiserat

    def test_kontonamn_i_strangstart_maskeras_till_token(self, monkeypatch, tmp_path):
        saldon = self._svar(monkeypatch, tmp_path)[0]
        rad = next(r for r in saldon["data"] if r["kontonr"] == "2393")
        assert _STARTNAMN not in rad["kontonamn"]
        assert "PERSON_" in rad["kontonamn"]

    def test_verifikat_med_okant_namn_i_strangstart_blockeras(self, monkeypatch, tmp_path):
        transaktioner = self._svar(monkeypatch, tmp_path)[1]
        assert transaktioner["antal_exkluderade"] >= 1
        assert transaktioner["data"] == []
