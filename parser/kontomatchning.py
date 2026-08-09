"""Kontomatchning — se ARCHITECTURE_tillagg_modul4.md, "Modul 4: Semantisk kontomatchning".

Bedömer om en transaktions text rimligen matchar det konto den är bokad
på. Flaggar bara — föreslår aldrig ett alternativt konto, ändrar aldrig
data. Litar blint på sin indata (privacygränsen i §2 är anroparens
ansvar, inte denna moduls — se test_endast_sandningsbara_verifikationer_nar_haiku).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from domain_model import Konto, Verifikation

_GILTIGA_STATUS = {"matchning", "avvikelse", "osäker"}

# §4, skyddslager 2: mönster för kontonummer-kandidater i motiveringstext.
# En kandidat räknas som "avvikande kontonummer" bara om den finns i den
# faktiska kontoplanen (§9-frågan, avgjord 2026-07-02) — annars nedgraderas
# legitima avvikelse-motiveringar som råkar nämna ett fyrsiffrigt belopp
# ("Beloppet 2340 kr är ovanligt högt") till osäker i onödan. Utan
# kontoplan (konton=None) gäller det strikta beteendet: varje fyrsiffrigt
# tal triggar — fail-closed när belopp inte kan skiljas från konto.
_KONTONUMMER_I_TEXT = re.compile(r"\b\d{4}\b")


@dataclass
class Kontobedömning:
    plats: str
    kontonr: str
    text_analyserad: str
    status: Literal["matchning", "avvikelse", "osäker"]
    belopp: Decimal
    motivering: str | None = None
    föreslaget_kontonr: str | None = None


def bygg_bunt(
    verifikationer: list[Verifikation],
    konton: dict[str, Konto],
    max_storlek: int = 40,
) -> list[list[dict]]:
    """Bygger buntar av transaktionsunderlag. Varje underlag: bunt_id,
    kontonr, kontonamn, transtext, vertext, plats, text_analyserad,
    belopp."""
    underlag: list[dict] = []
    for verifikation in verifikationer:
        for radindex, transaktion in enumerate(verifikation.transaktioner):
            text = transaktion.transtext or verifikation.vertext
            konto = konton.get(transaktion.kontonr)
            underlag.append(
                {
                    "kontonr": transaktion.kontonr,
                    "kontonamn": konto.namn if konto is not None else None,
                    "transtext": text,
                    "vertext": verifikation.vertext,
                    "plats": f"serie={verifikation.serie} vernr={verifikation.vernr} radindex={radindex}",
                    "text_analyserad": text,
                    "belopp": transaktion.belopp,
                }
            )

    buntar: list[list[dict]] = []
    for start in range(0, len(underlag), max_storlek):
        del_ = underlag[start : start + max_storlek]
        # Lokalt bunt-id: börjar om på T1 i varje bunt. Varje bunt blir ett
        # eget, fristående Haiku-anrop, och tolka_haiku_svar matchar alltid
        # en bunt mot enbart dess egna svar — global unikhet fyller ingen
        # funktion och gör inget enklare.
        for i, rad in enumerate(del_):
            rad["bunt_id"] = f"T{i + 1}"
        buntar.append(del_)

    return buntar


def _kontonr_finns_i_kontoplan(kontonr: str, giltiga_konton: set[str] | None) -> bool:
    """Delad primitiv för Skyddslager 2 — återanvänd av både
    motivering-skanningen och föreslaget_kontonr-valideringen (Gap 3),
    inte omimplementerad parallellt."""
    return giltiga_konton is not None and kontonr in giltiga_konton


def _har_avvikande_kontonummer(
    motivering: str, kontonr: str, giltiga_konton: set[str] | None
) -> bool:
    return any(
        tal != kontonr and (giltiga_konton is None or _kontonr_finns_i_kontoplan(tal, giltiga_konton))
        for tal in _KONTONUMMER_I_TEXT.findall(motivering)
    )


def _tolka_en_rad(
    underlag: dict, svar: dict | None, giltiga_konton: set[str] | None
) -> Kontobedömning:
    plats = underlag["plats"]
    kontonr = underlag["kontonr"]
    text_analyserad = underlag["text_analyserad"]
    # .get med default: bygg_bunt fyller alltid i belopp, men tolka_haiku_svar
    # tar emot vilken list[dict] som helst — samma undantag som redan gäller
    # för svar.get("motivering") nedan.
    belopp = underlag.get("belopp", Decimal("0"))

    if svar is None:
        return Kontobedömning(
            plats=plats,
            kontonr=kontonr,
            text_analyserad=text_analyserad,
            status="osäker",
            belopp=belopp,
            motivering="Inget svar från Haiku för detta bunt-id.",
        )

    try:
        status = svar["status"]
        motivering = svar.get("motivering")
        föreslaget_kontonr = svar.get("föreslaget_kontonr")
    except (KeyError, TypeError, AttributeError):
        return Kontobedömning(
            plats=plats,
            kontonr=kontonr,
            text_analyserad=text_analyserad,
            status="osäker",
            belopp=belopp,
            motivering="Strukturellt ogiltigt svar från Haiku.",
        )

    if status not in _GILTIGA_STATUS:
        return Kontobedömning(
            plats=plats,
            kontonr=kontonr,
            text_analyserad=text_analyserad,
            status="osäker",
            belopp=belopp,
            motivering="Strukturellt ogiltigt svar från Haiku.",
        )

    if motivering and _har_avvikande_kontonummer(motivering, kontonr, giltiga_konton):
        return Kontobedömning(
            plats=plats,
            kontonr=kontonr,
            text_analyserad=text_analyserad,
            status="osäker",
            belopp=belopp,
            motivering=motivering,
        )

    # Gap 3, samma fail-closed-princip som Skyddslager 2 ovan (och samma
    # delade primitiv, _kontonr_finns_i_kontoplan): ett föreslaget_kontonr
    # som inte finns i kontoplanen är lika misstänkt som ett avvikande tal
    # i motivering — hela svaret nedgraderas till osäker, inte bara fältet.
    if status == "avvikelse" and föreslaget_kontonr and not _kontonr_finns_i_kontoplan(
        föreslaget_kontonr, giltiga_konton
    ):
        return Kontobedömning(
            plats=plats,
            kontonr=kontonr,
            text_analyserad=text_analyserad,
            status="osäker",
            belopp=belopp,
            motivering=motivering,
        )

    return Kontobedömning(
        plats=plats,
        kontonr=kontonr,
        text_analyserad=text_analyserad,
        status=status,
        föreslaget_kontonr=föreslaget_kontonr if status == "avvikelse" else None,
        belopp=belopp,
        motivering=motivering,
    )


def tolka_haiku_svar(
    bunt: list[dict],
    haiku_svar: list[dict],
    konton: dict[str, Konto] | None = None,
) -> list[Kontobedömning]:
    """Matchar Haikus svar mot bunten via bunt_id. Saknat/trasigt/
    misstänkt svar -> 'osäker', aldrig tyst 'matchning'. Med konton
    reagerar skyddslager 2 bara på tal som finns i kontoplanen; utan
    triggar varje fyrsiffrigt tal (fail-closed)."""
    svar_för_bunt_id: dict[str, dict] = {}
    for post in haiku_svar:
        try:
            svar_för_bunt_id[post["bunt_id"]] = post
        except (KeyError, TypeError):
            continue  # strukturellt ogiltig post — ignoreras, motsvarande underlag blir "osäker"

    giltiga_konton = set(konton) if konton is not None else None
    return [
        _tolka_en_rad(underlag, svar_för_bunt_id.get(underlag["bunt_id"]), giltiga_konton)
        for underlag in bunt
    ]


def bedöm_transaktioner(
    sandningsbara_verifikationer: list[Verifikation],
    konton: dict[str, Konto],
    haiku_anropare: Callable[[list[dict], str | None], list[dict]],
    max_bunt_storlek: int = 40,
    prosa_kontext: str | None = None,
) -> list[Kontobedömning]:
    """Orkestrerar hela flödet. haiku_anropare injiceras för testbarhet.
    Validerar INTE att indatan faktiskt är sandningsbara_verifikationer
    — den gränsen (§2) är anroparens ansvar, inte denna funktions.

    prosa_kontext är delad bakgrundskontext för hela batchen (t.ex. en
    revisors kommentar), inte något som analyseras per transaktion (§2,
    §5) — skickas oförändrad som andra argument till haiku_anropare vid
    varje bunt-anrop, None om den inte är satt."""
    buntar = bygg_bunt(sandningsbara_verifikationer, konton, max_storlek=max_bunt_storlek)

    resultat: list[Kontobedömning] = []
    for bunt in buntar:
        haiku_svar = haiku_anropare(bunt, prosa_kontext)
        resultat.extend(tolka_haiku_svar(bunt, haiku_svar, konton=konton))
    return resultat
