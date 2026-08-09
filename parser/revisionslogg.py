"""revisionslogg — lokal behandlingslogg över AI-utflöde (granskningens
svaghet 3 / GDPR Art. 30 + 5(2)).

Bakgrund: förr fanns ingen logg över VAD som faktiskt skickades till VILKEN
AI-leverantör NÄR, och breda `except Exception` svalde allt tyst. För
ansvarsskyldighet (Art. 5(2)), register över behandling (Art. 30) och
incidentutredning behövs åtminstone: anropstidpunkt, mottagare (leverantör +
modell), vilken förmåga som anropades, vilka datakategorier som ingick, och
maskeringsstatistik.

Vad som loggas är METADATA — aldrig själva nyttolasten, aldrig fritext, aldrig
kodnyckeln eller ett enda personnummer/namn. Loggen är i sig inte en känslig
PII-artefakt; den beskriver att en behandling skedde, inte innehållet.

Format: JSON Lines (en post per rad) i en lokal, gitignorerad fil. Best-effort
och fail-safe genomgående — loggen får ALDRIG krascha appen eller blockera ett
AI-anrop. En trasig eller oläsbar fil ger en tom lista vid läsning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import saker_lagring

# Paket B1: behandlingsloggen (metadata, ingen PII/nyttolast) lagras i den
# säkra, icke-synkade logs-katalogen. Sökvägen löses centralt.
REVISIONSLOGG_NAMN = "ai_utflodeslogg.jsonl"


def _logg_sokvag(explicit) -> Path:
    return saker_lagring.artefakt_sokvag(explicit, kategori="log", namn=REVISIONSLOGG_NAMN)


@dataclass
class Utfloedespost:
    """En rad i behandlingsloggen. Enbart metadata — se modulens docstring."""

    tidpunkt: str
    leverantör: str
    modell: str
    förmåga: str                       # "analys" | "samtal" | "agent" | "mcp_rag"
    datakategorier: list[str] = field(default_factory=list)
    maskeringsstatistik: dict[str, Any] = field(default_factory=dict)

    def som_rad(self) -> dict[str, Any]:
        return {
            "tidpunkt": self.tidpunkt,
            "leverantör": self.leverantör,
            "modell": self.modell,
            "förmåga": self.förmåga,
            "datakategorier": list(self.datakategorier),
            "maskeringsstatistik": dict(self.maskeringsstatistik),
        }


def maskeringsstatistik_fran_resultat(maskeringsresultat: Any) -> dict[str, int]:
    """Plockar ut de icke-känsliga RÄKNARNA ur ett Maskeringsresultat — aldrig
    kodnyckelns värden, bara hur många. Duck-typat och defensivt (getattr) så en
    ofullständig/testdubbel aldrig kraschar loggningen."""
    kodnyckel = getattr(maskeringsresultat, "kodnyckel", {}) or {}
    return {
        "antal_kodnyckel_poster": len(kodnyckel),
        "antal_maskeringsbehov": len(getattr(maskeringsresultat, "maskeringsbehov", []) or []),
        "antal_blockerade_verifikationer": len(
            getattr(maskeringsresultat, "blockerade_verifikationer", []) or []
        ),
        "antal_sandningsbara_verifikationer": len(
            getattr(maskeringsresultat, "sandningsbara_verifikationer", []) or []
        ),
    }


def logga_ai_utflode(
    leverantör: str,
    modell: str,
    förmåga: str,
    datakategorier: list[str] | None = None,
    maskeringsstatistik: dict[str, Any] | None = None,
    logg_fil: Path | None = None,
) -> None:
    """Lägger till EN metadatapost i behandlingsloggen (best-effort). Tidpunkten
    sätts här (lokal ISO-8601 med sekundprecision). I/O-fel sväljs — loggningen
    får aldrig störa själva AI-anropet."""
    post = Utfloedespost(
        tidpunkt=datetime.now().isoformat(timespec="seconds"),
        leverantör=leverantör or "",
        modell=modell or "",
        förmåga=förmåga or "",
        datakategorier=datakategorier or [],
        maskeringsstatistik=maskeringsstatistik or {},
    )
    fil = _logg_sokvag(logg_fil)
    try:
        saker_lagring.sakerstall_katalog(fil)
        with fil.open("a", encoding="utf-8") as f:
            f.write(json.dumps(post.som_rad(), ensure_ascii=False) + "\n")
    except OSError:
        pass


def las_revisionslogg(logg_fil: Path | None = None) -> list[dict[str, Any]]:
    """Läser hela behandlingsloggen (för granskning/UI/test). Saknad eller trasig
    fil -> tom lista (fail-safe). Enskilda oläsbara rader hoppas över i stället
    för att fälla hela läsningen."""
    try:
        rader = _logg_sokvag(logg_fil).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    poster: list[dict[str, Any]] = []
    for rad in rader:
        rad = rad.strip()
        if not rad:
            continue
        try:
            poster.append(json.loads(rad))
        except json.JSONDecodeError:
            continue
    return poster
