"""Steg 1 — test av bokslutskontroll.regelkalla.

Se hantverksbok/BOKSLUTSKONTROLLER.md §5 (steg 1, acceptans)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from bokslutskontroll.regelkalla import (
    hamta_parameter,
    hamta_regel,
    kontroll_ider,
    las_register,
)

_REGISTER_SOKVAG = Path(__file__).resolve().parents[1] / "regelverk" / "regelregister.toml"


def test_giltigt_register_lases():
    register = las_register(_REGISTER_SOKVAG)
    assert "kontroll" in register
    assert "K-01" in register["kontroll"]
    assert register["parametrar"]["tolerans_kronor"] == Decimal("1.00")


def test_post_utan_lank_manniska_kastar_med_kontroll_id(tmp_path):
    trasig = tmp_path / "trasigt_register.toml"
    trasig.write_text(
        """
[kontroll.K-99]
rubrik = "Test utan grund"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="K-99"):
        las_register(trasig)


def test_post_utan_rubrik_kastar_med_kontroll_id(tmp_path):
    trasig = tmp_path / "trasigt_register2.toml"
    trasig.write_text(
        """
[kontroll.K-98]
sfs = "1999:1078"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="K-98"):
        las_register(trasig)


def test_okant_kontroll_id_ger_none_inte_keyerror():
    assert hamta_regel("K-XYZ") is None


def test_hamta_regel_for_kand_kontroll():
    regel = hamta_regel("K-01")
    assert regel is not None
    assert regel.beteckning == "5 kap. 1 §"
    assert "1999-1078" in regel.lank_manniska
    assert regel.lank_maskin is not None
    assert "1999-1078" in regel.lank_maskin


def test_k00_har_ingen_maskinlank_men_kastar_inte():
    regel = hamta_regel("K-00")
    assert regel is not None
    assert regel.lank_maskin is None


def test_hamta_parameter_skalar():
    assert hamta_parameter("tolerans_kronor") == Decimal("1.00")
    assert hamta_parameter("periodiseringsfonster_dagar") == 30


def test_hamta_parameter_ar_beroende():
    assert hamta_parameter("arbetsgivaravgift_procent", ar=2026) == Decimal("0.3142")
    assert hamta_parameter("arbetsgivaravgift_procent", ar=1999) is None


def test_kontroll_ider_innehaller_kanda_id():
    ider = kontroll_ider()
    assert "K-01" in ider
    assert "K-14" in ider
    assert "K-00" in ider
