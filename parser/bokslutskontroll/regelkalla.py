"""Läser regelverk/regelregister.toml — enda sanningen om regelhänvisningar och
parametrar (B-4). Skriv aldrig om den filen härifrån.

Registret läses en gång och cachas i modulen."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

from .modell import Regelhanvisning

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STANDARDSOKVAG = _REPO_ROOT / "regelverk" / "regelregister.toml"

Register = dict[str, Any]

_cache: Register | None = None
_cache_sokvag: Path | None = None


def _sfs_till_lank(sfs: str) -> tuple[str, str]:
    del_tecken = sfs.replace(":", "-")
    lank_manniska = (
        f"https://www.riksdagen.se/sv/dokument-och-lagar/dokument/_sfs-{del_tecken}/"
    )
    lank_maskin = f"https://data.riksdagen.se/dokument/sfs-{del_tecken}"
    return lank_manniska, lank_maskin


def _till_decimal(varde: Any) -> Any:
    """Konverterar beloppssträngar till Decimal, rekursivt genom dict/list.
    Aldrig float (I-7)."""
    if isinstance(varde, str):
        try:
            return Decimal(varde)
        except Exception:
            return varde
    if isinstance(varde, dict):
        return {k: _till_decimal(v) for k, v in varde.items()}
    if isinstance(varde, list):
        return [_till_decimal(v) for v in varde]
    return varde


def las_register(sokvag: Path | None = None) -> Register:
    """Läser och validerar regelregistret. Kastar ValueError med kontroll-id:t
    i meddelandet om en post saknar `rubrik`, eller saknar både `sfs` och
    `lank_manniska`."""
    global _cache, _cache_sokvag
    vald_sokvag = sokvag if sokvag is not None else _STANDARDSOKVAG

    if _cache is not None and _cache_sokvag == vald_sokvag:
        return _cache

    with open(vald_sokvag, "rb") as f:
        rådata = tomllib.load(f)

    kontroller = rådata.get("kontroll", {})
    for kontroll_id, post in kontroller.items():
        if not post.get("rubrik"):
            raise ValueError(f"Regelpost {kontroll_id} saknar 'rubrik'.")
        if not post.get("sfs") and not post.get("lank_manniska"):
            raise ValueError(
                f"Regelpost {kontroll_id} saknar både 'sfs' och 'lank_manniska'."
            )

    parametrar_rå = rådata.get("parametrar", {})
    parametrar: dict[str, Any] = {}
    for namn, varde in parametrar_rå.items():
        if namn == "periodiseringsfonster_dagar":
            parametrar[namn] = int(varde)
        else:
            parametrar[namn] = _till_decimal(varde)

    register: Register = {
        "parametrar": parametrar,
        "kontolistor": rådata.get("kontolistor", {}),
        "kontroll": kontroller,
    }

    _cache = register
    _cache_sokvag = vald_sokvag
    return register


def hamta_regel(kontroll_id: str) -> Regelhanvisning | None:
    register = las_register()
    post = register["kontroll"].get(kontroll_id)
    if post is None:
        return None

    sfs = post.get("sfs")
    if sfs:
        lank_manniska, lank_maskin = _sfs_till_lank(sfs)
        kalla = f"SFS {sfs}"
    else:
        lank_manniska = post["lank_manniska"]
        lank_maskin = None
        kalla = post.get("lag", "")

    kommentar = post.get("kommentar")
    if kommentar is None:
        kommentar = post.get("lydelse")

    return Regelhanvisning(
        kalla=kalla,
        beteckning=post.get("beteckning", ""),
        lank_manniska=lank_manniska,
        lank_maskin=lank_maskin,
        kommentar=kommentar,
    )


def hamta_parameter(namn: str, ar: int | None = None) -> Any:
    """Slår upp `namn` i [parametrar], och om det inte finns där i
    [kontolistor] — kontroller i grupp B och C hämtar kontolistor och
    marginaler genom samma funktion (§7 steg 4), så att ingen kontolista
    eller marginal ligger som literal i Python."""
    register = las_register()
    varde = register["parametrar"].get(namn)
    if varde is None:
        varde = register["kontolistor"].get(namn)
    if varde is None:
        return None
    if ar is not None:
        if not isinstance(varde, dict):
            return None
        return varde.get(str(ar))
    return varde


def kontroll_ider() -> set[str]:
    register = las_register()
    return set(register["kontroll"].keys())
