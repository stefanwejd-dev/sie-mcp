"""Tester för tools/migrera_lagring.py (Paket B2.1).

Endast SYNTETISKA temp-filer och en isolerad temp-rot — aldrig riktiga
artefakter, aldrig riktiga %LOCALAPPDATA%, aldrig verkligt innehåll. Bevisar
dry-run-säkerhet, bekräftelsekrav, klassavgränsning, korsvolyms-säker flytt,
felväg (källa bevaras), guard-blockering, neutral hantering av saknade
artefakter/session, och att inga (syntetiska) hemligheter läcker i utdata.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import saker_lagring
import migrera_lagring as m

STATE_FILER = {
    "mask_dict.enc": b"chiffer-1",
    "allowlist.enc": b"chiffer-2",
    "konteringsminne.enc": b"chiffer-3xx",
    "masking_memory.json": b"[]",
}


def _skapa_kalla(kalla_root: Path, filer: dict[str, bytes]) -> None:
    kalla_root.mkdir(parents=True, exist_ok=True)
    for namn, data in filer.items():
        (kalla_root / namn).write_bytes(data)


class TestDryRun:
    def test_dry_run_lamnar_kalla_och_mal_orort(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, STATE_FILER)

        kod = m.kor(["--state", "--kalla-root", str(kalla), "--data-root", str(mal)])

        assert kod == m.EXIT_OK
        for namn in STATE_FILER:
            assert (kalla / namn).exists()
            assert not (mal / "state" / namn).exists()

    def test_utan_klassval_ar_dry_run_over_allt(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, STATE_FILER)

        kod = m.kor(["--kalla-root", str(kalla), "--data-root", str(mal)])

        assert kod == m.EXIT_OK
        for namn in STATE_FILER:
            assert (kalla / namn).exists()  # inget flyttat


class TestBekraftelse:
    def test_utfor_utan_bekrafta_avvisas(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, STATE_FILER)

        kod = m.kor(["--state", "--utfor", "--kalla-root", str(kalla), "--data-root", str(mal)])

        assert kod == m.EXIT_ANVANDNING
        for namn in STATE_FILER:
            assert (kalla / namn).exists()
        assert not (mal / "state").exists()


class TestFlytt:
    def test_normal_flytt_mal_verifieras_kalla_tas_bort(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, STATE_FILER)

        kod = m.kor(
            ["--state", "--utfor", "--bekrafta", "--kalla-root", str(kalla), "--data-root", str(mal)]
        )

        assert kod == m.EXIT_OK
        for namn, data in STATE_FILER.items():
            assert (mal / "state" / namn).read_bytes() == data  # verifierat på mål
            assert not (kalla / namn).exists()  # källa borttagen sist
            # ingen tempfil kvarlämnad
            assert not (mal / "state" / (namn + ".migrering-tmp")).exists()

    def test_env_gar_till_secrets_aldrig_state(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, {".env": b"SIE_MCP_FERNET_KEY=xxx\n"})

        m.kor(["--secrets", "--utfor", "--bekrafta", "--kalla-root", str(kalla), "--data-root", str(mal)])

        assert (mal / "secrets" / ".env").exists()
        assert not (mal / "state" / ".env").exists()

    def test_klassavgransning_state_ror_ej_secret_eller_log(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, {**STATE_FILER, ".env": b"X=1", "ai_utflodeslogg.jsonl": b"{}\n"})

        m.kor(["--state", "--utfor", "--bekrafta", "--kalla-root", str(kalla), "--data-root", str(mal)])

        # secret + log orörda i källan, inget mål skapat för dem
        assert (kalla / ".env").exists()
        assert (kalla / "ai_utflodeslogg.jsonl").exists()
        assert not (mal / "secrets" / ".env").exists()
        assert not (mal / "logs" / "ai_utflodeslogg.jsonl").exists()
        # state flyttat
        assert (mal / "state" / "mask_dict.enc").exists()

    def test_backup_tas_och_kalla_flyttas(self, tmp_path):
        kalla, mal, backup = tmp_path / "repo", tmp_path / "data", tmp_path / "backup"
        _skapa_kalla(kalla, {"mask_dict.enc": b"chiffer-1"})

        kod = m.kor([
            "--state", "--utfor", "--bekrafta", "--backup-dir", str(backup),
            "--kalla-root", str(kalla), "--data-root", str(mal),
        ])

        assert kod == m.EXIT_OK
        assert (backup / "mask_dict.enc").read_bytes() == b"chiffer-1"
        assert (mal / "state" / "mask_dict.enc").exists()
        assert not (kalla / "mask_dict.enc").exists()


class TestFelvag:
    def test_storleksmiss_bevarar_kalla_och_publicerar_inte_mal(self, tmp_path, monkeypatch):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, {"mask_dict.enc": b"chiffer-langt-original"})

        def _trunkerad_kopiera(_k, dest):
            Path(dest).write_bytes(b"kort")  # fel storlek -> verifiering ska fälla

        monkeypatch.setattr(m, "_kopiera", _trunkerad_kopiera)

        kod = m.kor(
            ["--state", "--utfor", "--bekrafta", "--kalla-root", str(kalla), "--data-root", str(mal)]
        )

        assert kod == m.EXIT_MIGRERINGSFEL
        assert (kalla / "mask_dict.enc").read_bytes() == b"chiffer-langt-original"  # källa kvar
        assert not (mal / "state" / "mask_dict.enc").exists()  # mål ej publicerat
        assert not (mal / "state" / "mask_dict.enc.migrering-tmp").exists()  # temp städad


class TestGuard:
    def test_backup_under_repo_blockeras(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, {"mask_dict.enc": b"c"})
        dalig_backup = saker_lagring.REPO_ROOT / "b2_backup_temp"

        kod = m.kor([
            "--state", "--utfor", "--bekrafta", "--backup-dir", str(dalig_backup),
            "--kalla-root", str(kalla), "--data-root", str(mal),
        ])

        assert kod == m.EXIT_GUARD
        assert (kalla / "mask_dict.enc").exists()  # inget flyttat
        assert not dalig_backup.exists()

    def test_data_root_under_repo_blockeras(self, tmp_path):
        kalla = tmp_path / "repo"
        _skapa_kalla(kalla, {"mask_dict.enc": b"c"})

        kod = m.kor([
            "--state", "--kalla-root", str(kalla),
            "--data-root", str(saker_lagring.REPO_ROOT / "x"),
        ])

        assert kod == m.EXIT_GUARD

    def test_relativ_data_root_blockeras(self, tmp_path):
        kalla = tmp_path / "repo"
        _skapa_kalla(kalla, {"mask_dict.enc": b"c"})
        kod = m.kor(["--state", "--kalla-root", str(kalla), "--data-root", "relativ_rot"])
        assert kod == m.EXIT_GUARD


class TestSaknadOchSession:
    def test_saknad_artefakt_ar_neutral_noop(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        kalla.mkdir()  # inga state-filer

        kod = m.kor(
            ["--state", "--utfor", "--bekrafta", "--kalla-root", str(kalla), "--data-root", str(mal)]
        )

        assert kod == m.EXIT_OK  # saknade = neutralt, inte fel
        assert not (mal / "state").exists()  # inget nyproducerat

    def test_session_dpapi_noop_om_saknas(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        kalla.mkdir()

        kod = m.kor([
            "--session", "--dpapi", "--utfor", "--bekrafta",
            "--kalla-root", str(kalla), "--data-root", str(mal),
        ])

        assert kod == m.EXIT_OK
        assert not (mal / "secrets" / ".spiris_session").exists()  # ingen sessionfil skapad
        assert not (kalla / ".spiris_session.json").exists()

    def test_session_present_uppskjuten_ingen_flytt(self, tmp_path):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, {".spiris_session.json": b"gammalt-plaintext"})

        kod = m.kor([
            "--session", "--utfor", "--bekrafta",
            "--kalla-root", str(kalla), "--data-root", str(mal),
        ])

        assert kod == m.EXIT_OK
        assert (kalla / ".spiris_session.json").exists()  # ingen flytt/konvertering i B2.1
        assert not (mal / "secrets" / ".spiris_session").exists()


class TestSekretess:
    def test_ingen_syntetisk_hemlighet_i_utdata(self, tmp_path, capsys):
        kalla, mal = tmp_path / "repo", tmp_path / "data"
        _skapa_kalla(kalla, {
            ".env": b"SIE_MCP_AI_API_NYCKEL=hemligt-varde-XYZ\n",
            "mask_dict.enc": b"chiffer",
        })

        m.kor(["--secrets", "--state", "--kalla-root", str(kalla), "--data-root", str(mal)])
        m.kor([
            "--secrets", "--state", "--utfor", "--bekrafta",
            "--kalla-root", str(kalla), "--data-root", str(mal),
        ])

        ut = capsys.readouterr()
        assert "hemligt-varde-XYZ" not in ut.out
        assert "hemligt-varde-XYZ" not in ut.err
