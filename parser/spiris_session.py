"""spiris_session — sessionshantering för MCP-serverns Spiris-verktyg.

Bygger en SpirisKlient från miljövariabler (SPIRIS_CLIENT_ID/SECRET) plus
access-/refresh-token ur en lokal, dold .spiris_session.json, och sparar
tillbaka en ev. refreshad token så den stateless MCP-servern alltid har en
giltig session. Plus JSON-säker serialisering (Decimal -> float) för värden
som ska ut till LLM:en.

Ingen hemlighet skrivs till repot: .spiris_session.json är gitignore:ad och
credentials kommer från miljön.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import saker_lagring
from spiris_klient import SpirisKlient

# Paket B1: sessionen lagras DPAPI-skyddad (per Windows-användare) i den säkra,
# icke-synkade secrets-katalogen. Formatet är en DPAPI-blob — INTE klartext-
# JSON. Konvertering av en ev. gammal .spiris_session.json sker explicit i
# B2-migreringsverktyget; B1 läser/skriver enbart det nya formatet.
SESSION_NAMN = ".spiris_session"


class SpirisSessionFel(Exception):
    """Ingen användbar Spiris-session — saknade credentials i miljön eller
    saknad/ofullständig .spiris_session.json. Fail-closed: verktyget svarar
    med ett tydligt meddelande istället för att krascha."""


def json_sakert(obj: Any) -> Any:
    """Gör ett värde JSON-serialiserbart: Decimal -> float, rekursivt genom
    dict/list. Decimal-disciplinen har hållit genom all beräkning; det här är
    bara presentationsgränsen mot LLM:en (JSON saknar Decimal-typ)."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {nyckel: json_sakert(värde) for nyckel, värde in obj.items()}
    if isinstance(obj, list):
        return [json_sakert(värde) for värde in obj]
    return obj


def bygg_klient(
    session_fil: Path | None = None,
    *,
    klient_klass: type = SpirisKlient,
    avskydda: Callable[[bytes], bytes] = saker_lagring.dpapi_avskydda,
) -> Any:
    """Bygger en SpirisKlient från miljöns credentials + DPAPI-skyddade tokens
    ur session_fil. Fail-closed: saknas credentials/session, eller går den inte
    att avskydda (t.ex. på icke-Windows utan DPAPI), kastas SpirisSessionFel med
    ett neutralt meddelande — aldrig tokeninnehåll. `avskydda` injiceras i test."""
    client_id = os.environ.get("SPIRIS_CLIENT_ID")
    client_secret = os.environ.get("SPIRIS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SpirisSessionFel(
            "SPIRIS_CLIENT_ID/SPIRIS_CLIENT_SECRET saknas i miljön."
        )

    session_fil = saker_lagring.artefakt_sokvag(
        session_fil, kategori="secret", namn=SESSION_NAMN
    )
    try:
        blob = Path(session_fil).read_bytes()
    except OSError as e:
        raise SpirisSessionFel(
            "Ingen giltig Spiris-session — logga in mot Spiris först."
        ) from e
    try:
        tokens = json.loads(avskydda(blob))
    except Exception as e:  # noqa: BLE001 — inkl. DPAPI-/plattformsfel; aldrig innehåll ut
        raise SpirisSessionFel(
            "Kunde inte läsa Spiris-sessionen (skyddat format) — logga in på nytt."
        ) from e

    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    refresh_token = tokens.get("refresh_token") if isinstance(tokens, dict) else None
    if not access_token or not refresh_token:
        raise SpirisSessionFel("Sessionen saknar access_token/refresh_token.")

    return klient_klass(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )


def spara_session(
    klient: Any,
    session_fil: Path | None = None,
    *,
    skydda: Callable[[bytes], bytes] = saker_lagring.dpapi_skydda,
) -> None:
    """Skriver tillbaka klientens aktuella tokens DPAPI-skyddade så nästa
    MCP-anrop plockar upp en giltig session. Best-effort — ett skriv- eller
    skyddsfel (t.ex. icke-Windows utan DPAPI) får aldrig fälla verktyget och
    lämnar ALDRIG en klartext-token på disk (fail-closed). `skydda` injiceras
    i test."""
    session_fil = saker_lagring.artefakt_sokvag(
        session_fil, kategori="secret", namn=SESSION_NAMN
    )
    try:
        blob = skydda(
            json.dumps(
                {"access_token": klient.access_token, "refresh_token": klient.refresh_token}
            ).encode("utf-8")
        )
        saker_lagring.sakerstall_katalog(session_fil)
        Path(session_fil).write_bytes(blob)
    except (OSError, saker_lagring.SakerLagringFel):
        pass


# --- B2.4-B: explicit, verifierbar persistens + radering --------------------
# Skild från spara_session (best-effort under MCP-serverns finally). Detta är en
# UTTRYCKLIG användaråtgärd: vid guard-/DPAPI-/skrivfel returneras ett tydligt,
# tokenfritt misslyckande — aldrig en falsk framgångsstatus, aldrig klartext.

@dataclass
class SessionPersistResult:
    """Tokenfri metadata om en explicit persist-/raderingsåtgärd. Innehåller
    ALDRIG tokens, sökvägar med användaridentitet eller råa undantagstexter —
    bara en boolesk utfallsflagga, en neutral statuskod och en valfri felkod."""

    sparad: bool
    statuskod: str
    felkod: str | None = None


def persist_session(
    tokens: Any,
    *,
    session_fil: Path | None = None,
    skydda: Callable[[bytes], bytes] = saker_lagring.dpapi_skydda,
) -> SessionPersistResult:
    """Skyddar (DPAPI) och skriver EXPLICIT den inloggade sessionens access-/
    refresh-token till den guardade secrets-sökvägen. Endast dessa två fält
    persisteras — client_id/secret lagras aldrig i filen. Vid ofullständiga
    tokens, osäker sökväg, DPAPI-fel eller skrivfel returneras ett tokenfritt
    MISSLYCKANDE och INGEN klartextfil skrivs. `skydda` injiceras i test."""
    at = getattr(tokens, "access_token", None)
    rt = getattr(tokens, "refresh_token", None)
    if not at or not rt:
        return SessionPersistResult(False, "ogiltiga_tokens", "TOKENS_SAKNAS")

    try:
        fil = saker_lagring.artefakt_sokvag(session_fil, kategori="secret", namn=SESSION_NAMN)
    except saker_lagring.SakerLagringFel:
        return SessionPersistResult(False, "osaker_sokvag", "GUARD")

    try:
        blob = skydda(json.dumps({"access_token": at, "refresh_token": rt}).encode("utf-8"))
        saker_lagring.sakerstall_katalog(fil)
        Path(fil).write_bytes(blob)
    except saker_lagring.SakerLagringFel:
        return SessionPersistResult(False, "dpapi_ej_tillgangligt", "DPAPI")
    except OSError:
        return SessionPersistResult(False, "skrivfel", "IO")

    if not Path(fil).exists():
        return SessionPersistResult(False, "verifiering_misslyckades", "VERIFIERING")
    return SessionPersistResult(True, "sparad", None)


def radera_session(*, session_fil: Path | None = None) -> SessionPersistResult:
    """Raderar den lokala DPAPI-sessionen (utloggning). Guardad sökväg; en
    saknad fil är en neutral no-op; guard-/raderingsfel ger tydlig, tokenfri
    felstatus. Ingen server-side token-revoke sker här (senare paket)."""
    try:
        fil = saker_lagring.artefakt_sokvag(session_fil, kategori="secret", namn=SESSION_NAMN)
    except saker_lagring.SakerLagringFel:
        return SessionPersistResult(False, "osaker_sokvag", "GUARD")

    p = Path(fil)
    if not p.exists():
        return SessionPersistResult(True, "ingen_session", None)
    try:
        p.unlink()
    except OSError:
        return SessionPersistResult(False, "raderingsfel", "IO")
    return SessionPersistResult(True, "raderad", None)
