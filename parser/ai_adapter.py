"""ai_adapter — centralt fabriks-/adapterlager som bygger rätt
analys- eller chattanropare utifrån aktiv AIKonfiguration.

Enda stället i kodbasen där "vilken leverantör gör vad" avgörs för
FAKTISK analys och FAKTISKT samtal (inte modellistning — det sköter
ai_konfiguration.py). app.py, analysflode.py och samtalsflode.py ska
aldrig behöva special-hantera en specifik leverantör själva; de frågar
bara det här lagret.

Fail-closed genomgående: saknas nyckel/modell, eller stöds leverantören
inte än, kastas AnalysanropareFel respektive SamtalanropareFel med ett
tydligt, ärligt meddelande — appen låtsas aldrig stöd som inte finns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anthropic

from ai_konfiguration import AIKonfiguration
from chatt_klient import AgentSvar, skapa_agentanropare, skapa_verklig_chattanropare
from domain_model import Konto
from haiku_klient import skapa_verklig_haiku_anropare
from ollama_klient import (
    skapa_agentanropare as skapa_verklig_ollama_agentanropare,
    skapa_verklig_chattanropare as skapa_verklig_ollama_chattanropare,
)

STÖDDA_LEVERANTÖRER_FÖR_ANALYS: tuple[str, ...] = ("Anthropic",)

# Egen konstant, inte återanvänd från analysvägen — analys och samtal är
# två olika förmågor som kan komma att stödja olika leverantörer i takt
# med att fler byggs ut. Råkar vara samma lista idag, av en slump, inte
# av nödvändighet.
STÖDDA_LEVERANTÖRER_FÖR_SAMTAL: tuple[str, ...] = ("Anthropic", "Ollama")


def leverantor_har_analysstod(leverantör: str) -> bool:
    return leverantör in STÖDDA_LEVERANTÖRER_FÖR_ANALYS


def leverantor_har_samtalsstod(leverantör: str) -> bool:
    return leverantör in STÖDDA_LEVERANTÖRER_FÖR_SAMTAL


class AnalysanropareFel(Exception):
    """Fail-closed-fel när ingen riktig analysanropare kan byggas för
    aktiv konfiguration — ej stödd leverantör, eller ofullständig
    konfiguration (saknad nyckel/modell)."""


def bygg_analysanropare(
    konfiguration: AIKonfiguration, kontoplan: dict[str, Konto], logg: Any = None
) -> Callable[[list[dict], str | None], list[dict]]:
    """Bygger en riktig, körbar analysanropare för konfigurationens
    leverantör och vald_modell. Fail-closed vid varje ofullständigt
    eller ej stött läge — ingen tyst gissning.

    logg är en valfri sessionslogg som träs vidare till klienten. Adaptern är
    den enda platsen som känner alla tre leverantörsvägarna, så det är här
    loggaren kopplas på — inte i app.py, och inte i varje klient för sig."""
    if not leverantor_har_analysstod(konfiguration.leverantör):
        raise AnalysanropareFel(
            f"{konfiguration.leverantör} stöds ännu inte för faktisk analys."
        )
    if konfiguration.leverantör != "Ollama" and not konfiguration.api_nyckel:
        raise AnalysanropareFel("Ingen API-nyckel angiven.")
    if konfiguration.vald_modell is None:
        raise AnalysanropareFel("Ingen modell vald.")

    if konfiguration.leverantör == "Anthropic":
        klient = anthropic.Anthropic(api_key=konfiguration.api_nyckel)
        return skapa_verklig_haiku_anropare(
            kontoplan, klient=klient, modell=konfiguration.vald_modell, logg=logg
        )

    # Ska aldrig nås — leverantor_har_analysstod filtrerade redan bort
    # allt annat. Fail-closed ändå, ingen tyst genomsläpp om listan och
    # dispatchen här någon gång glider isär.
    raise AnalysanropareFel(f"{konfiguration.leverantör} stöds ännu inte för faktisk analys.")


class SamtalanropareFel(Exception):
    """Fail-closed-fel när ingen riktig chattanropare kan byggas för
    aktiv konfiguration — ej stödd leverantör, eller ofullständig
    konfiguration (saknad nyckel/modell)."""


def bygg_chattanropare(
    konfiguration: AIKonfiguration, logg: Any = None
) -> Callable[[str, str], str]:
    """Bygger en riktig, körbar chattanropare för konfigurationens
    leverantör och vald_modell. Fail-closed vid varje ofullständigt
    eller ej stött läge — ingen tyst gissning. logg träs vidare till
    klienten, se bygg_analysanropare."""
    if not leverantor_har_samtalsstod(konfiguration.leverantör):
        raise SamtalanropareFel(f"{konfiguration.leverantör} stöds ännu inte för samtal.")
    if konfiguration.leverantör != "Ollama" and not konfiguration.api_nyckel:
        raise SamtalanropareFel("Ingen API-nyckel angiven.")
    if konfiguration.vald_modell is None:
        raise SamtalanropareFel("Ingen modell vald.")

    if konfiguration.leverantör == "Anthropic":
        klient = anthropic.Anthropic(api_key=konfiguration.api_nyckel)
        return skapa_verklig_chattanropare(
            klient=klient, modell=konfiguration.vald_modell, logg=logg
        )
    if konfiguration.leverantör == "Ollama":
        return skapa_verklig_ollama_chattanropare(
            modell=konfiguration.vald_modell, logg=logg
        )

    # Ska aldrig nås — leverantor_har_samtalsstod filtrerade redan bort
    # allt annat. Fail-closed ändå, av samma skäl som bygg_analysanropare.
    raise SamtalanropareFel(f"{konfiguration.leverantör} stöds ännu inte för samtal.")


def bygg_agentanropare(
    konfiguration: AIKonfiguration, logg: Any = None
) -> Callable[[list[dict[str, str]], str], AgentSvar]:
    """Som bygg_chattanropare, men bygger en AGENT-anropare (Tool Calling,
    Fas 9) — samma fail-closed-kontroller (stöd/nyckel/modell), samma
    leverantörslista (STÖDDA_LEVERANTÖRER_FÖR_SAMTAL: agentläget är en form
    av samtal, inget nytt stödbehov). Fas 10: anroparen tar en FULL
    konversationshistorik (se chatt_klient.skapa_agentanropare), inte en
    enda fråga."""
    if not leverantor_har_samtalsstod(konfiguration.leverantör):
        raise SamtalanropareFel(f"{konfiguration.leverantör} stöds ännu inte för samtal.")
    if konfiguration.leverantör != "Ollama" and not konfiguration.api_nyckel:
        raise SamtalanropareFel("Ingen API-nyckel angiven.")
    if konfiguration.vald_modell is None:
        raise SamtalanropareFel("Ingen modell vald.")

    if konfiguration.leverantör == "Anthropic":
        klient = anthropic.Anthropic(api_key=konfiguration.api_nyckel)
        return skapa_agentanropare(
            klient=klient, modell=konfiguration.vald_modell, logg=logg
        )
    if konfiguration.leverantör == "Ollama":
        return skapa_verklig_ollama_agentanropare(
            modell=konfiguration.vald_modell, logg=logg
        )

    raise SamtalanropareFel(
        f"Agentläge (Tool Calling) stöds ännu inte för {konfiguration.leverantör} "
        "— vanlig chatt fungerar redan."
    )
