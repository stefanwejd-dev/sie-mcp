"""test_rotera_hemligheter.py — R-01-rotationen.

Det som prövas är inte att verktyget fungerar utan att det inte kan FÖRSTÖRA
något. `app_config.las_maskeringsliggare` är fail-safe: fel nyckel ger en TOM
liggare, inte ett fel. En felaktig rotation skulle därför tyst radera
maskeringsliggaren, undantagslistan och konteringsminnet — utan felmeddelande,
och utan att någon märker det förrän pseudonymerna plötsligt är andra.

Fyra egenskaper bär hela verktyget:

1. **Dry-run ändrar ingenting.** Varken nyckel eller liggare rörs.
2. **Innehållet överlever rotationen** — läsbart med den NYA nyckeln efteråt.
3. **En liggare som inte kan dekrypteras avbryter HELA rotationen**, i stället
   för att göras permanent oläsbar.
4. **Inga hemligheter i utskriften.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import app_config
import rotera_hemligheter as rot
import saker_lagring


@pytest.fixture
def uppsatt():
    """En .env med Fernet-nyckel och tre ifyllda liggare."""
    saker_lagring.initiera_lagring()
    env = saker_lagring.secrets_dir() / app_config.ENV_NAMN
    env.touch()
    set_key(str(env), rot.FERNET_NYCKEL, Fernet.generate_key().decode())

    app_config.spara_maskeringsliggare({"Anna Andersson": "PERSON_1"})
    app_config.spara_undantagslista(
        app_config.lagg_till_undantag([], ["Scandinavian Photo"])
    )
    app_config.spara_konteringsminne(
        app_config.uppdatera_konteringsminne(
            {}, "Kundbolaget AB", "tjänst", {"arbete": "3041"}
        )
    )
    return env


def _nyckel() -> str:
    return dotenv_values(str(saker_lagring.secrets_dir() / app_config.ENV_NAMN))[
        rot.FERNET_NYCKEL
    ]


# --- 1. Dry-run -------------------------------------------------------------


def test_dryrun_andrar_varken_nyckel_eller_liggare(uppsatt):
    fore_nyckel = _nyckel()
    fore_chiffer = (saker_lagring.state_dir() / app_config.MASK_DICT_NAMN).read_bytes()

    resultat = rot.rotera_fernet(utfor=False)

    assert resultat["utfort"] is False
    assert _nyckel() == fore_nyckel
    assert (saker_lagring.state_dir() / app_config.MASK_DICT_NAMN).read_bytes() == fore_chiffer


def test_dryrun_redovisar_vad_som_skulle_kryptteras_om(uppsatt):
    resultat = rot.rotera_fernet(utfor=False)
    assert set(resultat["omkrypterade"]) == set(rot.LIGGARE)
    assert resultat["hoppade_over"] == []


# --- 2. Innehållet överlever ------------------------------------------------


def test_rotation_byter_nyckel(uppsatt):
    fore = _nyckel()
    rot.rotera_fernet(utfor=True)
    assert _nyckel() != fore


def test_liggarna_ar_lasbara_efter_rotation(uppsatt):
    """Kärntestet. Utan omkryptering hade allt detta tyst blivit tomt."""
    rot.rotera_fernet(utfor=True)

    assert app_config.las_maskeringsliggare() == {"Anna Andersson": "PERSON_1"}
    assert app_config.normaliserade_undantag(app_config.las_undantagslista())
    assert app_config.las_konteringsminne()


def test_backup_av_gamla_chiffer_skapas(uppsatt):
    resultat = rot.rotera_fernet(utfor=True)
    backup = Path(resultat["backup"])
    assert backup.is_dir()
    assert {f.name for f in backup.iterdir()} == set(rot.LIGGARE)


def test_backupen_ligger_utanfor_repot(uppsatt):
    backup = Path(rot.rotera_fernet(utfor=True)["backup"])
    assert saker_lagring.REPO_ROOT not in backup.parents


def test_saknad_liggare_hoppas_over_utan_fel(uppsatt):
    (saker_lagring.state_dir() / app_config.ALLOWLIST_NAMN).unlink()
    resultat = rot.rotera_fernet(utfor=True)
    assert app_config.ALLOWLIST_NAMN in resultat["hoppade_over"]
    assert app_config.las_maskeringsliggare() == {"Anna Andersson": "PERSON_1"}


# --- 3. Fail-closed ---------------------------------------------------------


def test_odekrypterbar_liggare_avbryter_hela_rotationen(uppsatt):
    """En fil som inte går att dekryptera hade blivit PERMANENT oläsbar om
    rotationen fortsatte. Avbryt, rör ingenting."""
    trasig = saker_lagring.state_dir() / app_config.ALLOWLIST_NAMN
    trasig.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"annan nyckel"))
    fore_nyckel = _nyckel()
    fore_mask = (saker_lagring.state_dir() / app_config.MASK_DICT_NAMN).read_bytes()

    with pytest.raises(rot.RotationsFel, match="avbryts"):
        rot.rotera_fernet(utfor=True)

    assert _nyckel() == fore_nyckel
    assert (saker_lagring.state_dir() / app_config.MASK_DICT_NAMN).read_bytes() == fore_mask


def test_saknad_nyckel_ger_tydligt_fel():
    saker_lagring.initiera_lagring()
    (saker_lagring.secrets_dir() / app_config.ENV_NAMN).write_text("", encoding="utf-8")
    with pytest.raises(rot.RotationsFel, match="saknas"):
        rot.rotera_fernet(utfor=True)


# --- 4. Spiris-sessionen ----------------------------------------------------


def test_session_raderas_bara_med_utfor():
    saker_lagring.initiera_lagring()
    session = saker_lagring.secrets_dir() / rot.SESSION_NAMN
    session.write_bytes(b"dpapi-blob")

    assert rot.rotera_spiris_session(utfor=False)["utfort"] is False
    assert session.exists()

    assert rot.rotera_spiris_session(utfor=True)["utfort"] is True
    assert not session.exists()


def test_saknad_session_ar_inget_fel():
    saker_lagring.initiera_lagring()
    assert rot.rotera_spiris_session(utfor=True) == {"fanns": False, "utfort": False}


# --- 5. CLI och tystnadsplikt ----------------------------------------------


def test_utfor_utan_bekrafta_andrar_ingenting(uppsatt, capsys):
    fore = _nyckel()
    assert rot.main(["--fernet", "--utfor"]) == 1
    assert "bekrafta" in capsys.readouterr().out
    assert _nyckel() == fore


def test_status_visar_aldrig_ett_hemligt_varde(uppsatt, capsys):
    """Verktyget körs i en terminal som kan loggas eller delas."""
    rot.main([])
    utskrift = capsys.readouterr().out

    assert _nyckel() not in utskrift
    assert "Anna Andersson" not in utskrift
    assert "satt" in utskrift  # men att den ÄR satt redovisas


def test_status_listar_de_externa_som_maste_roteras_hos_leverantoren(uppsatt, capsys):
    set_key(str(uppsatt), "SIE_MCP_AI_API_NYCKEL", "sk-hemlig-nyckel-1234567890")
    rot.main([])
    utskrift = capsys.readouterr().out

    assert "SIE_MCP_AI_API_NYCKEL" in utskrift
    assert "behöver roteras" in utskrift
    assert "sk-hemlig" not in utskrift


def test_checklistan_har_ratt_ordning(capsys):
    """Återkalla hos leverantören FÖRE lokal radering — en läckt refresh token
    fungerar tills den återkallas, oavsett vad som finns på disk."""
    assert rot.main(["--checklista"]) == 0
    text = capsys.readouterr().out
    assert text.index("Återkalla integrationens behörighet") < text.index("--spiris-session")
    assert "Gör INTE detta för hand" in text
