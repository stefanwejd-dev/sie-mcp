"""ai_konfiguration — leverantörsoberoende AI-konfigurationsskikt (DEL B).

Detta byggsteg gör ENDAST modellhämtning — ingen AI-analys körs härifrån.
Leverantörsskillnader kapslas här så att app.py och en framtida analyslogik
inte behöver veta vilken leverantör som valts.

Adapterbeslut (flaggade, inte tysta antaganden):
- Anthropic: återanvänder redan installerade `anthropic`-SDK:ts
  `.models.list()` (deras Models API).
- OpenAI/Google: rena REST-anrop via `httpx` (redan ett beroende) i stället
  för att lägga till `openai`- och `google-generativeai`-SDK:er bara för
  modell-listning — minsta rimliga lösning.
- Googles API-nyckel skickas som header (`x-goog-api-key`), inte som
  query-param, så den aldrig hamnar synlig i en URL (loggar, exceptions).

Fail-closed genomgående: går anropet fel, blir svaret tomt, eller går det
inte att tolka som förväntat, kastas ModellhämtningsFel med ett statiskt,
generiskt meddelande — ALDRIG härlett från den råa exception-texten, som för
Google (nyckel i header) och OpenAI (nyckel i header) i teorin skulle kunna
läcka in i en underliggande felsträng. API-nyckeln loggas eller visas
aldrig.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

import anthropic
import httpx

LEVERANTÖRER: tuple[str, ...] = ("Anthropic", "OpenAI", "Google", "Ollama")

_TIMEOUT_SEKUNDER = 15.0


def leverantör_giltig(leverantör: str) -> bool:
    return leverantör in LEVERANTÖRER


class ModellhämtningsFel(Exception):
    """Fail-closed-fel vid modellhämtning. Meddelandet är alltid en
    statisk, generisk text — får ALDRIG innehålla API-nyckeln."""


@dataclass
class AIKonfiguration:
    leverantör: str
    api_nyckel: str
    vald_modell: str | None = None
    tillgängliga_modeller: list[str] = field(default_factory=list)
    status: Literal["ingen_hämtning", "modeller_hämtade", "fel"] = "ingen_hämtning"
    felmeddelande: str | None = None


def _hamta_modeller_anthropic(api_nyckel: str, *, klient: Any | None = None) -> list[str]:
    aktiv_klient = klient if klient is not None else anthropic.Anthropic(api_key=api_nyckel)
    try:
        svar = aktiv_klient.models.list()
        modeller = [modell.id for modell in svar.data]
    except Exception as e:
        raise ModellhämtningsFel(
            "Kunde inte hämta modeller från Anthropic. Kontrollera API-nyckeln."
        ) from e

    if not modeller:
        raise ModellhämtningsFel("Anthropic returnerade ingen modellista.")
    return modeller


def _hamta_modeller_openai(api_nyckel: str, *, klient: httpx.Client | None = None) -> list[str]:
    aktiv_klient = klient if klient is not None else httpx.Client(timeout=_TIMEOUT_SEKUNDER)
    try:
        try:
            svar = aktiv_klient.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_nyckel}"},
            )
            svar.raise_for_status()
            data = svar.json()
            modeller = [rad["id"] for rad in data["data"]]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ModellhämtningsFel("Ogiltig API-nyckel för OpenAI.") from e
            raise ModellhämtningsFel("OpenAI avvisade förfrågan.") from e
        except httpx.TimeoutException as e:
            raise ModellhämtningsFel("Tidsgräns överskreds vid anrop mot OpenAI.") from e
        except httpx.HTTPError as e:
            raise ModellhämtningsFel("Nätverksfel vid anrop mot OpenAI.") from e
        except Exception as e:
            raise ModellhämtningsFel("Oväntat svarsformat från OpenAI.") from e
    finally:
        if klient is None:
            aktiv_klient.close()

    if not modeller:
        raise ModellhämtningsFel("OpenAI returnerade ingen modellista.")
    return modeller


def _hamta_modeller_google(api_nyckel: str, *, klient: httpx.Client | None = None) -> list[str]:
    aktiv_klient = klient if klient is not None else httpx.Client(timeout=_TIMEOUT_SEKUNDER)
    try:
        try:
            svar = aktiv_klient.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": api_nyckel},
            )
            svar.raise_for_status()
            data = svar.json()
            modeller = [rad["name"].removeprefix("models/") for rad in data["models"]]
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise ModellhämtningsFel("Ogiltig API-nyckel för Google.") from e
            raise ModellhämtningsFel("Google avvisade förfrågan.") from e
        except httpx.TimeoutException as e:
            raise ModellhämtningsFel("Tidsgräns överskreds vid anrop mot Google.") from e
        except httpx.HTTPError as e:
            raise ModellhämtningsFel("Nätverksfel vid anrop mot Google.") from e
        except Exception as e:
            raise ModellhämtningsFel("Oväntat svarsformat från Google.") from e
    finally:
        if klient is None:
            aktiv_klient.close()

    if not modeller:
        raise ModellhämtningsFel("Google returnerade ingen modellista.")
    return modeller


def _hamta_modeller_ollama(api_nyckel: str, *, klient: httpx.Client | None = None) -> list[str]:
    """api_nyckel ignoreras medvetet — Ollama körs lokalt utan nyckel
    (beslut C1: tom nyckel giltig för denna leverantör). Signaturen matchar
    ändå övriga _hamta_modeller_*-funktioner för enhetlig dispatch."""
    aktiv_klient = klient if klient is not None else httpx.Client(timeout=_TIMEOUT_SEKUNDER)
    try:
        try:
            svar = aktiv_klient.get("http://localhost:11434/api/tags")
            svar.raise_for_status()
            data = svar.json()
            modeller = [rad["name"] for rad in data["models"]]
        except httpx.ConnectError as e:
            raise ModellhämtningsFel(
                "Kunde inte nå Ollama på http://localhost:11434. Kontrollera att servern körs."
            ) from e
        except httpx.HTTPStatusError as e:
            raise ModellhämtningsFel("Ollama avvisade förfrågan.") from e
        except httpx.TimeoutException as e:
            raise ModellhämtningsFel("Tidsgräns överskreds vid anrop mot Ollama.") from e
        except httpx.HTTPError as e:
            raise ModellhämtningsFel("Nätverksfel vid anrop mot Ollama.") from e
        except Exception as e:
            raise ModellhämtningsFel("Oväntat svarsformat från Ollama.") from e
    finally:
        if klient is None:
            aktiv_klient.close()

    if not modeller:
        raise ModellhämtningsFel("Ollama returnerade ingen modellista.")
    return modeller


def hamta_modeller_for_leverantor(
    leverantör: str,
    api_nyckel: str,
    *,
    anthropic_klient: Any | None = None,
    http_klient: httpx.Client | None = None,
) -> list[str]:
    if leverantör == "Anthropic":
        return _hamta_modeller_anthropic(api_nyckel, klient=anthropic_klient)
    if leverantör == "OpenAI":
        return _hamta_modeller_openai(api_nyckel, klient=http_klient)
    if leverantör == "Google":
        return _hamta_modeller_google(api_nyckel, klient=http_klient)
    if leverantör == "Ollama":
        return _hamta_modeller_ollama(api_nyckel, klient=http_klient)
    raise ModellhämtningsFel("Okänd leverantör.")


def uppdatera_med_hamtade_modeller(
    konfiguration: AIKonfiguration,
    *,
    anthropic_klient: Any | None = None,
    http_klient: httpx.Client | None = None,
) -> AIKonfiguration:
    try:
        modeller = hamta_modeller_for_leverantor(
            konfiguration.leverantör,
            konfiguration.api_nyckel,
            anthropic_klient=anthropic_klient,
            http_klient=http_klient,
        )
    except ModellhämtningsFel as fel:
        return replace(
            konfiguration,
            tillgängliga_modeller=[],
            vald_modell=None,
            status="fel",
            felmeddelande=str(fel),
        )

    return replace(
        konfiguration,
        tillgängliga_modeller=modeller,
        vald_modell=None,
        status="modeller_hämtade",
        felmeddelande=None,
    )
