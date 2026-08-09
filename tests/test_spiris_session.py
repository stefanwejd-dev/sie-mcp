"""Tester för spiris_session.py — sessionshanteringen bakom MCP-serverns
Spiris-verktyg: bygg klient från miljö + DPAPI-skyddad session, spara refreshad
token, och JSON-säker serialisering (Decimal -> float).

Paket B1: sessionen lagras DPAPI-skyddad. Testerna injicerar en REVERSIBEL
fejk-skyddare (aldrig riktig DPAPI, aldrig klartext-antagande) — den riktiga
DPAPI-vägen täcks av ett Windows-only integrationstest i test_saker_lagring.py.
Inga riktiga tokens/hemligheter förekommer.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

import saker_lagring
from spiris_session import (
    SpirisSessionFel,
    bygg_klient,
    json_sakert,
    spara_session,
)


def _fejk_skydda(b: bytes) -> bytes:
    return b[::-1]  # reversibel, icke-identitet: bevisar round-trip utan klartext


def _fejk_avskydda(b: bytes) -> bytes:
    return b[::-1]


class _FejkKlientKlass:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _FejkKlient:
    def __init__(self, access_token: str, refresh_token: str) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token


class TestJsonSakert:
    def test_decimal_blir_float(self):
        assert json_sakert(Decimal("500.00")) == 500.0
        assert isinstance(json_sakert(Decimal("1.5")), float)

    def test_nastlad_struktur_konverteras(self):
        ut = json_sakert({"data": [{"saldo": Decimal("-381.03")}], "n": 2})
        assert ut == {"data": [{"saldo": -381.03}], "n": 2}
        assert isinstance(ut["data"][0]["saldo"], float)

    def test_ovriga_typer_ror_inte(self):
        assert json_sakert("text") == "text"
        assert json_sakert(None) is None


class TestByggKlient:
    def _env(self, monkeypatch):
        monkeypatch.setenv("SPIRIS_CLIENT_ID", "xsandbox")
        monkeypatch.setenv("SPIRIS_CLIENT_SECRET", "hemlis")

    def _skriv_session(self, path, tokens: dict) -> None:
        spara_session_blob = _fejk_skydda(json.dumps(tokens).encode("utf-8"))
        path.write_bytes(spara_session_blob)

    def test_bygger_klient_fran_dpapi_skyddad_session(self, monkeypatch, tmp_path):
        self._env(monkeypatch)
        session = tmp_path / ".spiris_session"
        self._skriv_session(session, {"access_token": "AT", "refresh_token": "RT"})

        klient = bygg_klient(
            session_fil=session, klient_klass=_FejkKlientKlass, avskydda=_fejk_avskydda
        )

        assert klient.kwargs["access_token"] == "AT"
        assert klient.kwargs["refresh_token"] == "RT"
        assert klient.kwargs["client_id"] == "xsandbox"
        assert klient.kwargs["client_secret"] == "hemlis"

    def test_saknad_miljovariabel_ger_sessionfel(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SPIRIS_CLIENT_ID", raising=False)
        monkeypatch.delenv("SPIRIS_CLIENT_SECRET", raising=False)
        session = tmp_path / ".spiris_session"
        self._skriv_session(session, {"access_token": "AT", "refresh_token": "RT"})

        with pytest.raises(SpirisSessionFel):
            bygg_klient(session_fil=session, klient_klass=_FejkKlientKlass, avskydda=_fejk_avskydda)

    def test_saknad_sessionsfil_ger_sessionfel(self, monkeypatch, tmp_path):
        self._env(monkeypatch)
        with pytest.raises(SpirisSessionFel):
            bygg_klient(
                session_fil=tmp_path / "finns-inte", klient_klass=_FejkKlientKlass,
                avskydda=_fejk_avskydda,
            )

    def test_ofullstandig_session_ger_sessionfel(self, monkeypatch, tmp_path):
        self._env(monkeypatch)
        session = tmp_path / ".spiris_session"
        self._skriv_session(session, {"access_token": "AT"})  # saknar refresh_token
        with pytest.raises(SpirisSessionFel):
            bygg_klient(session_fil=session, klient_klass=_FejkKlientKlass, avskydda=_fejk_avskydda)

    def test_avskyddningsfel_ger_neutralt_fel_utan_innehall(self, monkeypatch, tmp_path):
        # Om avskyddningen misslyckas (t.ex. icke-Windows utan DPAPI) ska ett
        # neutralt SpirisSessionFel höjas — aldrig tokeninnehåll.
        self._env(monkeypatch)
        session = tmp_path / ".spiris_session"
        session.write_bytes(b"HEMLIGT_TOKENVARDE_ABC")

        def _trasig_avskydda(_b):
            raise saker_lagring.SakerLagringFel("DPAPI kräver Windows; ingen osäker fallback tillåts.")

        with pytest.raises(SpirisSessionFel) as ei:
            bygg_klient(session_fil=session, klient_klass=_FejkKlientKlass, avskydda=_trasig_avskydda)
        assert "HEMLIGT_TOKENVARDE_ABC" not in str(ei.value)


class TestSparaSession:
    def test_skriver_tillbaka_dpapi_skyddade_tokens(self, tmp_path):
        session = tmp_path / ".spiris_session"
        # Simulera att klienten refreshat sitt token under ett anrop.
        spara_session(
            _FejkKlient(access_token="NYTT_AT", refresh_token="NYTT_RT"),
            session_fil=session, skydda=_fejk_skydda,
        )

        # Filen på disk är den skyddade (reverserade) blobben, aldrig klartext.
        blob = session.read_bytes()
        assert b"NYTT_AT" not in blob
        återställd = json.loads(_fejk_avskydda(blob))
        assert återställd == {"access_token": "NYTT_AT", "refresh_token": "NYTT_RT"}

    def test_skyddsfel_sparar_ingen_klartext(self, tmp_path):
        # Om skyddet misslyckas (icke-Windows utan DPAPI) ska INGEN fil skrivas
        # — aldrig en klartext-token på disk (fail-closed, best-effort).
        session = tmp_path / ".spiris_session"

        def _trasig_skydda(_b):
            raise saker_lagring.SakerLagringFel("DPAPI kräver Windows; ingen osäker fallback tillåts.")

        spara_session(
            _FejkKlient(access_token="AT", refresh_token="RT"),
            session_fil=session, skydda=_trasig_skydda,
        )
        assert not session.exists()


# ===========================================================================
# B2.4-B: explicit, verifierbar DPAPI-persistens + radering (syntetiska värden)
# ===========================================================================

_AT = "SYNTETISK_AT_123"
_RT = "SYNTETISK_RT_456"


class _FakeTokens:
    """Duck-typar SpirisTokens (.access_token/.refresh_token)."""

    def __init__(self, at: str, rt: str) -> None:
        self.access_token = at
        self.refresh_token = rt


def _rev_skydda(b: bytes) -> bytes:
    return b[::-1]  # reversibel fake-DPAPI: bevisar skydd utan klartext-antagande


def _rev_avskydda(b: bytes) -> bytes:
    return b[::-1]


def _fel_skydda(_b: bytes) -> bytes:
    raise saker_lagring.SakerLagringFel("DPAPI kräver Windows; ingen osäker fallback tillåts.")


class TestPersistSession:
    def test_persist_skapar_dpapi_blob_utan_tokenlitteraler(self, tmp_path):
        from spiris_session import persist_session
        fil = tmp_path / "secrets" / ".spiris_session"
        r = persist_session(_FakeTokens(_AT, _RT), session_fil=fil, skydda=_rev_skydda)
        assert r.sparad is True
        assert fil.exists()
        blob = fil.read_bytes()
        assert _AT.encode() not in blob and _RT.encode() not in blob

    def test_lyckad_persist_ger_tokenfri_framgangsstatus(self, tmp_path):
        from spiris_session import persist_session
        fil = tmp_path / "secrets" / ".spiris_session"
        r = persist_session(_FakeTokens(_AT, _RT), session_fil=fil, skydda=_rev_skydda)
        assert r.sparad is True and r.felkod is None
        assert _AT not in str(r) and _RT not in str(r)

    def test_dpapi_fel_ger_tokenfri_felstatus_ingen_klartextfil(self, tmp_path):
        from spiris_session import persist_session
        fil = tmp_path / "secrets" / ".spiris_session"
        r = persist_session(_FakeTokens(_AT, _RT), session_fil=fil, skydda=_fel_skydda)
        assert r.sparad is False and r.felkod is not None
        assert not fil.exists()
        assert _AT not in str(r) and _RT not in str(r)

    def test_persist_vagrar_ofullstandiga_tokens(self, tmp_path):
        from spiris_session import persist_session
        fil = tmp_path / "secrets" / ".spiris_session"
        r = persist_session(_FakeTokens(_AT, ""), session_fil=fil, skydda=_rev_skydda)
        assert r.sparad is False
        assert not fil.exists()

    def test_round_trip_persist_sedan_bygg_klient(self, tmp_path, monkeypatch):
        from spiris_session import persist_session
        monkeypatch.setenv("SPIRIS_CLIENT_ID", "cid")
        monkeypatch.setenv("SPIRIS_CLIENT_SECRET", "csec")
        fil = tmp_path / "secrets" / ".spiris_session"
        assert persist_session(_FakeTokens(_AT, _RT), session_fil=fil, skydda=_rev_skydda).sparad
        klient = bygg_klient(session_fil=fil, klient_klass=_FejkKlientKlass, avskydda=_rev_avskydda)
        assert klient.kwargs["access_token"] == _AT
        assert klient.kwargs["refresh_token"] == _RT

    def test_persist_blockeras_for_osakra_sokvagar(self, tmp_path):
        from spiris_session import persist_session
        osakra = [
            saker_lagring.REPO_ROOT / ".spiris_session",           # repo
            tmp_path / "My Drive" / ".spiris_session",             # synk-markör
            "relativ_session",                                     # relativ
        ]
        for bad in osakra:
            r = persist_session(_FakeTokens(_AT, _RT), session_fil=bad, skydda=_rev_skydda)
            assert r.sparad is False and r.felkod == "GUARD"

    def test_persist_skriver_inget_till_stdout(self, tmp_path, capsys):
        from spiris_session import persist_session
        fil = tmp_path / "secrets" / ".spiris_session"
        persist_session(_FakeTokens(_AT, _RT), session_fil=fil, skydda=_rev_skydda)
        ut = capsys.readouterr()
        assert _AT not in ut.out and _RT not in ut.out
        assert _AT not in ut.err and _RT not in ut.err


class TestRaderaSession:
    def test_radera_tar_bort_befintlig(self, tmp_path):
        from spiris_session import persist_session, radera_session
        fil = tmp_path / "secrets" / ".spiris_session"
        persist_session(_FakeTokens(_AT, _RT), session_fil=fil, skydda=_rev_skydda)
        assert fil.exists()
        r = radera_session(session_fil=fil)
        assert r.sparad is True
        assert not fil.exists()

    def test_radera_saknad_fil_neutral_noop(self, tmp_path):
        from spiris_session import radera_session
        fil = tmp_path / "secrets" / ".spiris_session"
        r = radera_session(session_fil=fil)
        assert r.sparad is True and r.felkod is None
        assert not fil.exists()

    def test_radera_blockeras_for_osakra_sokvagar(self, tmp_path):
        from spiris_session import radera_session
        for bad in [saker_lagring.REPO_ROOT / ".spiris_session",
                    tmp_path / "OneDrive" / ".spiris_session", "relativ_session"]:
            r = radera_session(session_fil=bad)
            assert r.sparad is False and r.felkod == "GUARD"
