"""Tester för app_config.py — liten lokal konfigurationshanterare som
persisterar app-inställningar (Spiris client_id/secret, AI-leverantör,
API-nyckel, senast valda modell) mellan sessioner i en gitignorerad .env-fil.

Testerna använder en temporär .env — aldrig en riktig hemlighet.
"""

from __future__ import annotations

from app_config import (
    AppConfig,
    las_config,
    las_konteringsminne,
    las_maskeringsliggare,
    rensa_config,
    slå_upp_kontering,
    spara_falt,
    spara_konteringsminne,
    spara_maskeringsliggare,
    spara_om_andrad,
    tom_maskeringsliggare,
    tomt_konteringsminne,
    uppdatera_konteringsminne,
    lagg_till_undantag,
    las_undantagslista,
    normaliserade_undantag,
    spara_undantagslista,
    ta_bort_undantag,
    tom_undantagslista,
)


class TestLasOchSpara:
    def test_saknad_env_ger_tomma_falt(self, tmp_path):
        assert las_config(tmp_path / ".env") == AppConfig()

    def test_round_trip_alla_falt(self, tmp_path):
        env = tmp_path / ".env"
        spara_falt("spiris_client_id", "CID", env)
        spara_falt("spiris_client_secret", "SEC", env)
        spara_falt("ai_leverantör", "Anthropic", env)
        spara_falt("ai_api_nyckel", "hemlig-nyckel", env)
        spara_falt("ai_vald_modell", "claude-x", env)
        assert las_config(env) == AppConfig(
            spiris_client_id="CID",
            spiris_client_secret="SEC",
            ai_leverantör="Anthropic",
            ai_api_nyckel="hemlig-nyckel",
            ai_vald_modell="claude-x",
        )

    def test_spara_om_andrad_skriver_bara_nytt_varde(self, tmp_path):
        env = tmp_path / ".env"
        spara_falt("ai_api_nyckel", "gammal", env)
        config = las_config(env)  # ai_api_nyckel == "gammal"
        # Samma värde -> ingen förändring; nytt värde -> skrivs.
        spara_om_andrad("ai_api_nyckel", "gammal", config, env)
        assert las_config(env).ai_api_nyckel == "gammal"
        spara_om_andrad("ai_api_nyckel", "ny", config, env)
        assert las_config(env).ai_api_nyckel == "ny"

    def test_bevarar_andra_env_nycklar(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("ANNAT=x\n", encoding="utf-8")
        spara_falt("ai_api_nyckel", "k", env)
        from dotenv import dotenv_values

        assert dotenv_values(str(env)).get("ANNAT") == "x"
        assert las_config(env).ai_api_nyckel == "k"


class TestRensa:
    def test_rensar_alla_falt(self, tmp_path):
        env = tmp_path / ".env"
        spara_falt("spiris_client_id", "CID", env)
        spara_falt("ai_api_nyckel", "k", env)
        rensa_config(env)
        assert las_config(env) == AppConfig()


class TestKrypteradMaskeringsliggare:
    """Maskeringsliggaren (namn -> mask) lagras Fernet-krypterad i mask_dict.enc.
    Fernet-nyckeln genereras vid behov och sparas i .env. Endast chiffertext når
    disk — de riktiga namnen läcker aldrig i klartext."""

    def _filer(self, tmp_path):
        return tmp_path / ".env", tmp_path / "mask_dict.enc"

    def test_saknad_fil_ger_tom_liggare(self, tmp_path):
        env, enc = self._filer(tmp_path)
        assert las_maskeringsliggare(env, enc) == {}

    def test_round_trip_krypterat(self, tmp_path):
        env, enc = self._filer(tmp_path)
        liggare = {"Kalle Eriksson": "[PERSON 1]", "Anna Berg": "[PERSON 2]"}
        spara_maskeringsliggare(liggare, env, enc)
        assert las_maskeringsliggare(env, enc) == liggare

    def test_fernet_nyckel_sparas_i_env(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_maskeringsliggare({"X Y": "[PERSON 1]"}, env, enc)
        from dotenv import dotenv_values

        assert dotenv_values(str(env)).get("SIE_MCP_FERNET_KEY")

    def test_filen_pa_disk_ar_chiffertext_inte_klartext(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_maskeringsliggare({"Kalle Eriksson": "[PERSON 1]"}, env, enc)
        rådata = enc.read_bytes()
        assert b"Kalle Eriksson" not in rådata  # namnet får ALDRIG stå i klartext

    def test_fel_nyckel_ger_tom_liggare_inte_krasch(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_maskeringsliggare({"Kalle Eriksson": "[PERSON 1]"}, env, enc)
        # Byt ut Fernet-nyckeln -> gammal chiffertext går inte att dekryptera.
        from cryptography.fernet import Fernet
        from dotenv import set_key

        set_key(str(env), "SIE_MCP_FERNET_KEY", Fernet.generate_key().decode())
        assert las_maskeringsliggare(env, enc) == {}

    def test_tom_maskeringsliggare_raderar(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_maskeringsliggare({"Kalle Eriksson": "[PERSON 1]"}, env, enc)
        tom_maskeringsliggare(enc)
        assert las_maskeringsliggare(env, enc) == {}


class TestKrypteradUndantagslista:
    """Undantagslistan (allowlist) — strängar en människa bedömt som icke-PII.

    Krypteras med samma Fernet-nyckel som maskeringsliggaren men i EGEN fil:
    de två betyder rakt motsatta saker och får aldrig kunna blandas ihop.
    Fail-safe pekar mot MER flaggning — trasig fil ger tom lista, inte krasch."""

    def _filer(self, tmp_path):
        return tmp_path / ".env", tmp_path / "allowlist.enc"

    def test_saknad_fil_ger_tom_lista(self, tmp_path):
        env, enc = self._filer(tmp_path)
        assert las_undantagslista(env, enc) == []

    def test_round_trip_krypterat(self, tmp_path):
        env, enc = self._filer(tmp_path)
        poster = lagg_till_undantag([], ["Danske Disks"])
        spara_undantagslista(poster, env, enc)
        assert las_undantagslista(env, enc) == poster

    def test_klartext_nar_aldrig_disk(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_undantagslista(lagg_till_undantag([], ["Danske Disks"]), env, enc)
        assert b"Danske Disks" not in enc.read_bytes()

    def test_trasig_fil_ger_tom_lista_inte_krasch(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_undantagslista(lagg_till_undantag([], ["Danske Disks"]), env, enc)
        enc.write_bytes(b"inte-giltig-chiffertext")
        assert las_undantagslista(env, enc) == []

    def test_fel_nyckel_ger_tom_lista(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_undantagslista(lagg_till_undantag([], ["Danske Disks"]), env, enc)
        annan_env = tmp_path / "annan.env"
        assert las_undantagslista(annan_env, enc) == []

    def test_okand_version_ger_tom_lista(self, tmp_path):
        """Framtidssäkring: ett format vi inte förstår tolkas som INGA undantag
        (mer flaggning), aldrig som en gissning om vad posterna betyder."""
        import json
        from app_config import _hamta_eller_skapa_fernet

        env, enc = self._filer(tmp_path)
        chiffer = _hamta_eller_skapa_fernet(env).encrypt(
            json.dumps({"version": 99, "poster": [{"normaliserad": "x"}]}).encode("utf-8")
        )
        enc.write_bytes(chiffer)
        assert las_undantagslista(env, enc) == []

    def test_dubbletter_laggs_inte_till_igen(self):
        poster = lagg_till_undantag([], ["Danske Disks"])
        assert len(lagg_till_undantag(poster, ["danske  DISKS"])) == 1

    def test_personnummer_kan_aldrig_undantas(self):
        """Hängslen och livrem: lager 2 maskerar personnummer innan flaggningen,
        men en allowlist är fel ställe att lita på att en annan modul gjort sitt."""
        assert lagg_till_undantag([], ["19900102-1238"]) == []

    def test_tom_strang_ignoreras(self):
        assert lagg_till_undantag([], ["", "   "]) == []

    def test_ta_bort_undantag(self):
        poster = lagg_till_undantag([], ["Danske Disks", "Nordisk Kabel"])
        kvar = ta_bort_undantag(poster, "danske disks")
        assert [p["text"] for p in kvar] == ["Nordisk Kabel"]

    def test_lagg_till_ror_inte_indatan(self):
        poster = lagg_till_undantag([], ["Danske Disks"])
        lagg_till_undantag(poster, ["Nordisk Kabel"])
        assert len(poster) == 1  # ren funktion

    def test_normaliserade_undantag_ger_matchningsmangden(self):
        poster = lagg_till_undantag([], ["Danske Disks", "Nordisk Kabel"])
        assert normaliserade_undantag(poster) == {"danske disks", "nordisk kabel"}

    def test_tom_undantagslista_raderar_filen(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_undantagslista(lagg_till_undantag([], ["Danske Disks"]), env, enc)
        tom_undantagslista(enc)
        assert not enc.exists()
        assert las_undantagslista(env, enc) == []


class TestKrypteratKonteringsminne:
    """Tredje krypterade liggaren i samma familj som maskeringsliggaren/
    undantagslistan — kund -> godkänt konteringsmönster (Fas 7:
    skapa_kundfaktura HITL)."""

    def _filer(self, tmp_path):
        return tmp_path / ".env", tmp_path / "konteringsminne.enc"

    def test_saknad_fil_ger_tomt_minne(self, tmp_path):
        env, enc = self._filer(tmp_path)
        assert las_konteringsminne(env, enc) == {}

    def test_round_trip_krypterat(self, tmp_path):
        env, enc = self._filer(tmp_path)
        minne = uppdatera_konteringsminne(
            {}, "Anna Andersson", "fysisk_person_med_rot",
            {"arbete": "3041", "materiel": "3051"},
        )
        spara_konteringsminne(minne, env, enc)
        assert las_konteringsminne(env, enc) == minne

    def test_klartext_namn_nar_aldrig_disk(self, tmp_path):
        env, enc = self._filer(tmp_path)
        minne = uppdatera_konteringsminne(
            {}, "Anna Andersson", "juridisk_person", {"arbete": "3041"}
        )
        spara_konteringsminne(minne, env, enc)
        assert b"Anna Andersson" not in enc.read_bytes()

    def test_trasig_fil_ger_tomt_minne_inte_krasch(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_konteringsminne(
            uppdatera_konteringsminne({}, "X", "juridisk_person", {"arbete": "3041"}),
            env, enc,
        )
        enc.write_bytes(b"inte giltig chiffertext")
        assert las_konteringsminne(env, enc) == {}

    def test_fel_nyckel_ger_tomt_minne(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_konteringsminne(
            uppdatera_konteringsminne({}, "X", "juridisk_person", {"arbete": "3041"}),
            env, enc,
        )
        annan_env = tmp_path / "annan.env"
        assert las_konteringsminne(annan_env, enc) == {}

    def test_okand_version_ger_tomt_minne(self, tmp_path):
        import json
        from app_config import _hamta_eller_skapa_fernet

        env, enc = self._filer(tmp_path)
        chiffer = _hamta_eller_skapa_fernet(env).encrypt(
            json.dumps({"version": 99, "kunder": {"x": {}}}).encode("utf-8")
        )
        enc.write_bytes(chiffer)
        assert las_konteringsminne(env, enc) == {}

    def test_slå_upp_kontering_hittar_kund(self):
        minne = uppdatera_konteringsminne(
            {}, "Anna Andersson", "fysisk_person_med_rot",
            {"arbete": "3041", "materiel": "3051"},
        )
        träff = slå_upp_kontering(minne, "Anna Andersson")
        assert träff["kontering"] == {"arbete": "3041", "materiel": "3051"}
        assert träff["fakturatyp"] == "fysisk_person_med_rot"

    def test_slå_upp_kontering_ar_skiftlagesokanslig_och_whitespace_tolerant(self):
        minne = uppdatera_konteringsminne(
            {}, "Anna  Andersson", "juridisk_person", {"arbete": "3041"}
        )
        assert slå_upp_kontering(minne, "anna andersson") is not None

    def test_slå_upp_kontering_okand_kund_ger_none(self):
        assert slå_upp_kontering({}, "Okänd Kund") is None

    def test_uppdatera_konteringsminne_ror_inte_indatan(self):
        original = {}
        uppdatera_konteringsminne(original, "X", "juridisk_person", {"arbete": "3041"})
        assert original == {}  # ren funktion

    def test_uppdatera_overskriver_samma_kunds_gamla_monster(self):
        minne = uppdatera_konteringsminne(
            {}, "Anna Andersson", "juridisk_person", {"arbete": "3041", "materiel": "3051"}
        )
        minne = uppdatera_konteringsminne(
            minne, "Anna Andersson", "fysisk_person_med_rot", {"arbete": "3099"}
        )
        träff = slå_upp_kontering(minne, "Anna Andersson")
        assert träff["kontering"] == {"arbete": "3099"}
        assert träff["fakturatyp"] == "fysisk_person_med_rot"

    def test_ingen_rot_personuppgift_sparas(self):
        # Medvetet beslut: bara kontonr + fakturatyp lärs in, ALDRIG
        # personnummer/fastighetsbeteckning (de hör till den enskilda
        # fakturan, inte ett återanvändbart mönster).
        minne = uppdatera_konteringsminne(
            {}, "Anna Andersson", "fysisk_person_med_rot", {"arbete": "3041"}
        )
        träff = slå_upp_kontering(minne, "Anna Andersson")
        assert "personnummer" not in str(träff).lower()
        assert "fastighet" not in str(träff).lower()

    def test_tomt_konteringsminne_raderar_filen(self, tmp_path):
        env, enc = self._filer(tmp_path)
        spara_konteringsminne(
            uppdatera_konteringsminne({}, "X", "juridisk_person", {"arbete": "3041"}),
            env, enc,
        )
        tomt_konteringsminne(enc)
        assert not enc.exists()
        assert las_konteringsminne(env, enc) == {}
