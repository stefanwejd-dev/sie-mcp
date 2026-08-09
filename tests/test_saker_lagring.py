"""Tester för saker_lagring — den fail-closed sökvägsgrunden (Paket B1).

Bevisar att Drive-/repo-/relativa sökvägar blockeras FÖRE läsning/skrivning,
att en säker lokal temp-rot tillåts, att default-sökvägar hamnar under en
icke-synkad datarot, och att DPAPI round-trippar på Windows (skip annars) utan
osäker fallback. Inga riktiga hemligheter förekommer; syntetiska värden får
aldrig läcka i testutdata.
"""

from __future__ import annotations

import os

import pytest

import saker_lagring


class TestGuard:
    def test_blockerar_repo_roten_och_barn(self):
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.kontrollera_saker_plats(saker_lagring.REPO_ROOT)
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.kontrollera_saker_plats(saker_lagring.REPO_ROOT / "secrets" / ".env")

    def test_blockerar_relativ_sokvag(self):
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.kontrollera_saker_plats(".env")

    def test_blockerar_synk_markor(self, tmp_path):
        # Absolut, ej under repo, men med en molnsynk-markör i sökvägen.
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.kontrollera_saker_plats(tmp_path / "My Drive" / "sie" / ".env")
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.kontrollera_saker_plats(tmp_path / "OneDrive" / "state.enc")

    def test_tillater_saker_absolut_temp(self, tmp_path):
        # Ska inte höja något.
        saker_lagring.kontrollera_saker_plats(tmp_path / "sie_mcp_data" / "secrets" / ".env")

    def test_felmeddelanden_ar_statiska_utan_sokvag(self):
        try:
            saker_lagring.kontrollera_saker_plats("relativ.env")
        except saker_lagring.SakerLagringFel as e:
            assert "relativ.env" not in str(e)  # ingen sökväg/innehåll läcker


class TestDatarot:
    def test_override_maste_vara_saker(self, monkeypatch):
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(saker_lagring.REPO_ROOT))
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.app_data_root()

    def test_override_relativ_blockeras(self, monkeypatch):
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, "relativ_rot")
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.app_data_root()

    def test_saker_override_ger_underkataloger(self, monkeypatch, tmp_path):
        rot = tmp_path / "sie_mcp_data"
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(rot))
        assert saker_lagring.app_data_root() == rot.resolve()
        assert saker_lagring.secrets_dir() == (rot / "secrets").resolve()
        assert saker_lagring.state_dir() == (rot / "state").resolve()
        assert saker_lagring.logs_dir() == (rot / "logs").resolve()

    def test_initiera_skapar_katalogerna(self, monkeypatch, tmp_path):
        rot = tmp_path / "sie_mcp_data"
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(rot))
        saker_lagring.initiera_lagring()
        assert (rot / "secrets").is_dir()
        assert (rot / "state").is_dir()
        assert (rot / "logs").is_dir()


class TestArtefaktSokvag:
    def test_none_ger_default_under_kategori(self, monkeypatch, tmp_path):
        rot = tmp_path / "sie_mcp_data"
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(rot))
        assert saker_lagring.artefakt_sokvag(None, kategori="secret", namn=".env") == (
            rot / "secrets" / ".env"
        ).resolve()
        assert saker_lagring.artefakt_sokvag(None, kategori="state", namn="x.enc") == (
            rot / "state" / "x.enc"
        ).resolve()
        assert saker_lagring.artefakt_sokvag(None, kategori="log", namn="y.jsonl") == (
            rot / "logs" / "y.jsonl"
        ).resolve()

    def test_explicit_repo_sokvag_blockeras(self):
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.artefakt_sokvag(
                saker_lagring.REPO_ROOT / ".env", kategori="secret", namn=".env"
            )


def _snapshot(p):
    """Ögonblicksbild av en repo-fil (finns? + bytes) — för att bevisa att B1
    ALDRIG rör en (ev. redan befintlig, stale) artefakt i Drive/repo. B1 flyttar
    inte befintlig data; det gör B2."""
    return (p.exists(), p.read_bytes() if p.exists() else None)


class TestCentraliseradeVagar:
    """Bevisar att de refaktorerade modulerna nu (a) skriver default-data under
    den säkra dataroten, inte repo/Drive, (b) inte rör en ev. redan befintlig
    repo-artefakt, och (c) vägrar en repo-sökväg FÖRE någon läsning/skrivning."""

    def test_liggare_default_hamnar_under_datarot_och_rorinte_repo(self, monkeypatch, tmp_path):
        rot = tmp_path / "sie_mcp_data"
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(rot))
        import app_config

        repo_fil = saker_lagring.REPO_ROOT / "mask_dict.enc"
        fore = _snapshot(repo_fil)

        app_config.spara_maskeringsliggare({"X Y": "[PERSON 1]"})

        assert (rot / "state" / "mask_dict.enc").exists()
        # Endast chiffertext på disk (den syntetiska masken läcker inte).
        assert b"[PERSON 1]" not in (rot / "state" / "mask_dict.enc").read_bytes()
        # En ev. redan befintlig repo-artefakt är OFÖRÄNDRAD (B1 rör den inte).
        assert _snapshot(repo_fil) == fore

    def test_las_liggare_vagrar_repo_sokvag_fore_io(self):
        import app_config

        with pytest.raises(saker_lagring.SakerLagringFel):
            app_config.las_maskeringsliggare(mask_fil=saker_lagring.REPO_ROOT / "mask_dict.enc")

    def test_revisionslogg_default_hamnar_under_logs_och_rorinte_repo(self, monkeypatch, tmp_path):
        rot = tmp_path / "sie_mcp_data"
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(rot))
        import revisionslogg

        repo_fil = saker_lagring.REPO_ROOT / "ai_utflodeslogg.jsonl"
        fore = _snapshot(repo_fil)

        revisionslogg.logga_ai_utflode("Anthropic", "m", "analys", datakategorier=["x"])

        assert (rot / "logs" / "ai_utflodeslogg.jsonl").exists()
        assert _snapshot(repo_fil) == fore  # repo-loggen orörd


class TestDpapi:
    @pytest.mark.skipif(os.name != "nt", reason="DPAPI kräver Windows")
    def test_dpapi_round_trip_windows(self):
        hemligt = b"syntetiskt-token-abc-123"
        blob = saker_lagring.dpapi_skydda(hemligt)
        assert blob != hemligt
        assert hemligt not in blob  # skyddat, ej klartext
        assert saker_lagring.dpapi_avskydda(blob) == hemligt

    @pytest.mark.skipif(os.name == "nt", reason="testar icke-Windows fail-closed")
    def test_dpapi_failclosed_utan_windows(self):
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.dpapi_skydda(b"x")
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.dpapi_avskydda(b"x")
