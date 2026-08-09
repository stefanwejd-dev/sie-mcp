"""masking_memory — enkelt, lokalt minne över redan granskade/maskerade
verifikationer, sparat som en JSON-lista i masking_memory.json.

Syfte: när huvudboken hämtas på nytt från Spiris ska verifikat som redan
hanterats (maskerats och blivit sändningsbara) inte dyka upp igen. Endast
verifikations-ID (serie#vernr) lagras — ingen kontodata, inga belopp, ingen PII.

Fail-safe: en saknad eller trasig fil ger en tom mängd (hellre visa ett
verifikat en extra gång än att tappa det tyst). Anm.: nyckeln serie#vernr är
unik inom ETT bolag; minnet används därför i Spiris-flödet där en session rör
ett bolag.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import saker_lagring

# Paket B1 / skärpning B: masking_memory behandlas som state med skyddsvärde och
# får aldrig läsas från eller skrivas till den (potentiellt Drive-synkade)
# projektmappen. Sökvägen löses centralt via saker_lagring.
MASKERINGSMINNE_NAMN = "masking_memory.json"


def _sokvag(explicit) -> Path:
    return saker_lagring.artefakt_sokvag(explicit, kategori="state", namn=MASKERINGSMINNE_NAMN)


def _innehallsfingeravtryck(verifikation: Any) -> str:
    """Kort hash av verifikatets FAKTISKA innehåll (svaghet 5). Utan den räckte
    serie#vernr som nyckel — men om ett verifikat ändras i Spiris EFTER
    godkännandet (t.ex. ny transaktionstext med ett personnamn) skulle den nya
    versionen ärva det gamla godkännandet och aldrig granskas om.

    Fingeravtrycket täcker både fritexten (vertext/sign/transtext/trans-sign) och
    de strukturella fälten (kontonr, belopp, datum, radtyp) — så en ändring av
    antingen text ELLER substans ger en ny nyckel och tvingar fram en ny
    granskning. Defensivt getattr: fungerar även för minimala test-dubletter."""
    delar: list[str] = [
        str(getattr(verifikation, "vertext", "") or ""),
        str(getattr(verifikation, "sign", "") or ""),
        str(getattr(verifikation, "verdatum", "") or ""),
        str(getattr(verifikation, "regdatum", "") or ""),
    ]
    for t in getattr(verifikation, "transaktioner", None) or []:
        delar.append("|".join(str(getattr(t, f, "") or "") for f in (
            "kontonr", "belopp", "transdat", "transtext", "sign", "kvantitet", "radtyp",
        )))
    rå = "␟".join(delar)
    return hashlib.sha256(rå.encode("utf-8")).hexdigest()[:12]


def verifikation_id(verifikation: Any) -> str:
    """Stabil nyckel för en verifikation inom ett bolag: serie + vernr + ett
    innehållsfingeravtryck. Fingeravtrycket gör nyckeln känslig för ändringar av
    verifikatet (svaghet 5) — ett ändrat verifikat får en NY nyckel och granskas
    om i stället för att tyst ärva ett gammalt godkännande."""
    return f"{verifikation.serie}#{verifikation.vernr}#{_innehallsfingeravtryck(verifikation)}"


def las_maskeringsminne(sokvag: Path | None = None) -> set[str]:
    """Läser sparade verifikations-ID. Saknad/trasig fil -> tom mängd (fail-safe)."""
    try:
        data = json.loads(_sokvag(sokvag).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {str(post) for post in data}


def lagg_till_maskeringsminne(
    nya_id: Iterable[str], sokvag: Path | None = None
) -> set[str]:
    """Lägger till verifikations-ID i minnet (union med befintliga) och skriver
    tillbaka sorterat. Returnerar hela den uppdaterade mängden. Skrivfel sväljs
    (best-effort) — minnet får aldrig krascha appen."""
    fil = _sokvag(sokvag)
    uppdaterad = las_maskeringsminne(fil) | {str(post) for post in nya_id}
    try:
        saker_lagring.sakerstall_katalog(fil)
        fil.write_text(
            json.dumps(sorted(uppdaterad), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return uppdaterad


def filtrera_bort_sedda(verifikationer: Iterable[Any], sedda_id: set[str]) -> list:
    """Returnerar bara de verifikationer vars ID INTE redan finns i minnet."""
    return [v for v in verifikationer if verifikation_id(v) not in sedda_id]
