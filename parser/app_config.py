"""app_config — liten lokal konfigurationshanterare. Persisterar app-inställningar
mellan sessioner i en gitignorerad .env-fil (python-dotenv): Spiris-uppgifter
(client_id/secret), AI-leverantör, API-nyckel och senast valda modell.

.env är gitignorerad — hemligheter committas ALDRIG, loggas aldrig, ekas aldrig.
Ren I/O-glue; testbar med en temporär .env. Best-effort: I/O-fel sväljs så att
UI:t aldrig kraschar av att en config-fil inte gick att läsa/skriva.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values, set_key, unset_key

import saker_lagring

# Undantagslistans matchningsregler ägs av sekretesslagret — normaliseringen
# får aldrig dupliceras här och glida isär från den som faktiskt filtrerar.
from sekretesslager import normalisera_undantag, är_giltigt_personnummer

# Artefaktnamn (Paket B1): sökvägen löses centralt via saker_lagring till en
# säker, icke-synkad lokal katalog. .env med Fernet-nyckeln är 'secret'; de
# krypterade liggarna är 'state'. Ingen sökväg defaultar längre till den
# (potentiellt Drive-synkade) projektmappen.
ENV_NAMN = ".env"
MASK_DICT_NAMN = "mask_dict.enc"
_FERNET_NYCKEL = "SIE_MCP_FERNET_KEY"


def _env_sokvag(explicit) -> Path:
    return saker_lagring.artefakt_sokvag(explicit, kategori="secret", namn=ENV_NAMN)


def _state_sokvag(explicit, namn: str) -> Path:
    return saker_lagring.artefakt_sokvag(explicit, kategori="state", namn=namn)

# Fältnamn -> .env-nyckel. AI-nycklarna behåller sina namn från tidigare ai_env
# så att en redan sparad .env fortsätter att laddas.
_NYCKLAR: dict[str, str] = {
    "spiris_client_id": "SIE_MCP_SPIRIS_CLIENT_ID",
    "spiris_client_secret": "SIE_MCP_SPIRIS_CLIENT_SECRET",
    "ai_leverantör": "SIE_MCP_AI_LEVERANTOR",
    "ai_api_nyckel": "SIE_MCP_AI_API_NYCKEL",
    "ai_vald_modell": "SIE_MCP_AI_VALD_MODELL",
}


@dataclass
class AppConfig:
    spiris_client_id: str = ""
    spiris_client_secret: str = ""
    ai_leverantör: str = ""
    ai_api_nyckel: str = ""
    ai_vald_modell: str = ""


def las_config(env_fil: Path | None = None) -> AppConfig:
    """Läser persisterade fält ur .env eller miljövariabler (för webbdrift)."""
    import os
    värden = dotenv_values(str(_env_sokvag(env_fil)))
    res = {}
    for fält, nyckel in _NYCKLAR.items():
        val = värden.get(nyckel) or ("" if env_fil is not None else os.environ.get(nyckel, ""))
        if not val and env_fil is None and fält == "ai_api_nyckel":
            val = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        if not val and env_fil is None and fält == "ai_leverantör" and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SIE_MCP_AI_API_NYCKEL")):
            val = "Anthropic"
        res[fält] = val
    return AppConfig(**res)


def spara_falt(fält: str, värde: str, env_fil: Path | None = None) -> None:
    """Sparar ETT fält till .env utan att röra övriga (skapar filen vid behov).
    Best-effort — I/O-fel sväljs."""
    nyckel = _NYCKLAR[fält]
    env_fil = _env_sokvag(env_fil)
    try:
        saker_lagring.sakerstall_katalog(env_fil)
        env_fil.touch(exist_ok=True)
        set_key(str(env_fil), nyckel, värde or "")
    except OSError:
        pass


def spara_om_andrad(fält: str, värde: str, config: AppConfig, env_fil: Path | None = None) -> None:
    """Sparar bara om värdet skiljer sig från det redan lästa (config) — undviker
    onödig disk-skrivning vid varje Streamlit-rerun."""
    if (värde or "") != getattr(config, fält):
        spara_falt(fält, värde, env_fil)


def rensa_config(env_fil: Path | None = None) -> None:
    """Tar bort alla persisterade fält ur .env (övriga nycklar bevaras).
    Best-effort."""
    env_fil = _env_sokvag(env_fil)
    if not env_fil.exists():
        return
    for nyckel in _NYCKLAR.values():
        try:
            unset_key(str(env_fil), nyckel)
        except (OSError, KeyError):
            pass


# --- Krypterad maskeringsliggare (namn -> mask) ------------------------------
# "Security by design": liggaren innehåller riktiga namn (PII) och lagras därför
# Fernet-krypterad i mask_dict.enc — endast chiffertext når disk (och därmed en
# ev. molnsynk av mappen). Den symmetriska nyckeln ligger i den gitignorerade
# .env-filen. Liggaren skickas ALDRIG till någon AI; den används bara lokalt för
# pre-pass-maskeringen.

def _hamta_eller_skapa_fernet(env_fil: Path | None = None) -> Fernet:
    """Läser Fernet-nyckeln ur .env (säker, icke-synkad plats); genererar och
    sparar en ny om den saknas."""
    env_fil = _env_sokvag(env_fil)
    nyckel = dotenv_values(str(env_fil)).get(_FERNET_NYCKEL)
    if not nyckel:
        nyckel = Fernet.generate_key().decode()
        try:
            saker_lagring.sakerstall_katalog(env_fil)
            env_fil.touch(exist_ok=True)
            set_key(str(env_fil), _FERNET_NYCKEL, nyckel)
        except OSError:
            pass
    return Fernet(nyckel.encode())


def las_maskeringsliggare(
    env_fil: Path | None = None, mask_fil: Path | None = None
) -> dict[str, str]:
    """Läser och dekrypterar maskeringsliggaren. Saknad/trasig fil eller fel
    nyckel -> tom liggare (fail-safe: hellre tom än krascha)."""
    mask_fil = _state_sokvag(mask_fil, MASK_DICT_NAMN)
    if not mask_fil.exists():
        return {}
    try:
        klartext = _hamta_eller_skapa_fernet(env_fil).decrypt(mask_fil.read_bytes())
        liggare = json.loads(klartext.decode("utf-8"))
    except (OSError, InvalidToken, ValueError, json.JSONDecodeError):
        return {}
    return liggare if isinstance(liggare, dict) else {}


def spara_maskeringsliggare(
    liggare: dict[str, str], env_fil: Path | None = None, mask_fil: Path | None = None
) -> None:
    """Krypterar (Fernet) och skriver maskeringsliggaren till disk. Best-effort."""
    mask_fil = _state_sokvag(mask_fil, MASK_DICT_NAMN)
    chiffer = _hamta_eller_skapa_fernet(env_fil).encrypt(
        json.dumps(liggare, ensure_ascii=False).encode("utf-8")
    )
    try:
        saker_lagring.sakerstall_katalog(mask_fil)
        mask_fil.write_bytes(chiffer)
    except OSError:
        pass


def tom_maskeringsliggare(mask_fil: Path | None = None) -> None:
    """Raderar den krypterade liggaren från disk (börja om från noll)."""
    try:
        _state_sokvag(mask_fil, MASK_DICT_NAMN).unlink(missing_ok=True)
    except OSError:
        pass


# --- Krypterad undantagslista / allowlist ------------------------------------
# Motsatsen till maskeringsliggaren: strängar som en människa uttryckligen
# bedömt som ICKE-PII ("Danske Disks" är en leverantör, inte en person) och som
# sekretesslagret därför ska sluta flagga i nya filer och sessioner.
#
# Egen fil, inte inbakad i mask_dict.enc: de två liggarna betyder rakt motsatta
# saker (maskera alltid vs. maskera aldrig) och en sammanblandning vid en
# framtida migrering hade blivit tyst och allvarlig. Samma Fernet-nyckel och
# samma fail-safe-mönster återanvänds däremot rakt av.
#
# Krypteringen är inte överdrift: posterna är strängar som lagret klassat som
# MISSTÄNKT PII, och en felklick lägger annars ett riktigt personnamn i
# klartext på disk (projektmappen kan vara molnsynkad). Trasig fil eller fel
# nyckel ger tom lista — degraderingen går alltså mot MER flaggning, vilket är
# rätt håll för en mekanism som per definition är fail-open.

ALLOWLIST_NAMN = "allowlist.enc"
UNDANTAGSLISTA_VERSION = 1


def las_undantagslista(
    env_fil: Path | None = None, allowlist_fil: Path | None = None
) -> list[dict[str, str]]:
    """Läser och dekrypterar undantagslistan. Saknad/trasig fil, fel nyckel
    eller okänd version -> tom lista (fail-safe mot mer flaggning)."""
    allowlist_fil = _state_sokvag(allowlist_fil, ALLOWLIST_NAMN)
    if not allowlist_fil.exists():
        return []
    try:
        klartext = _hamta_eller_skapa_fernet(env_fil).decrypt(allowlist_fil.read_bytes())
        data = json.loads(klartext.decode("utf-8"))
    except (OSError, InvalidToken, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or data.get("version") != UNDANTAGSLISTA_VERSION:
        return []
    poster = data.get("poster")
    if not isinstance(poster, list):
        return []
    return [post for post in poster if isinstance(post, dict) and post.get("normaliserad")]


def spara_undantagslista(
    poster: list[dict[str, str]],
    env_fil: Path | None = None,
    allowlist_fil: Path | None = None,
) -> None:
    """Krypterar (Fernet) och skriver undantagslistan till disk. Best-effort."""
    allowlist_fil = _state_sokvag(allowlist_fil, ALLOWLIST_NAMN)
    chiffer = _hamta_eller_skapa_fernet(env_fil).encrypt(
        json.dumps(
            {"version": UNDANTAGSLISTA_VERSION, "poster": poster}, ensure_ascii=False
        ).encode("utf-8")
    )
    try:
        saker_lagring.sakerstall_katalog(allowlist_fil)
        allowlist_fil.write_bytes(chiffer)
    except OSError:
        pass


def lagg_till_undantag(
    poster: list[dict[str, str]], texter: Iterable[str]
) -> list[dict[str, str]]:
    """Lägger till nya undantag och returnerar en NY lista (ren funktion — I/O
    sker separat via spara_undantagslista). Dubbletter hoppas över.

    Personnummer kan ALDRIG undantas, oavsett vad anroparen skickar. Lager 2
    maskerar dem redan innan flaggningen så vägen hit ska inte finnas — men en
    allowlist är fel ställe att lita på att en annan modul gjort sitt jobb."""
    uppdaterad = list(poster)
    redan = {post["normaliserad"] for post in uppdaterad}
    for text in texter:
        text = (text or "").strip()
        if not text or är_giltigt_personnummer(text):
            continue
        normaliserad = normalisera_undantag(text)
        if normaliserad in redan:
            continue
        redan.add(normaliserad)
        uppdaterad.append(
            {
                "text": text,
                "normaliserad": normaliserad,
                "tillagd": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return uppdaterad


def ta_bort_undantag(
    poster: list[dict[str, str]], normaliserad: str
) -> list[dict[str, str]]:
    """Tar bort ETT undantag (ångra en felklickad 'Ingen maskering').
    Ren funktion — returnerar en ny lista."""
    return [post for post in poster if post.get("normaliserad") != normaliserad]


def normaliserade_undantag(poster: list[dict[str, str]]) -> set[str]:
    """Matchningsmängden som skickas till sekretesslager.maskera_siefil."""
    return {post["normaliserad"] for post in poster if post.get("normaliserad")}


def tom_undantagslista(allowlist_fil: Path | None = None) -> None:
    """Raderar undantagslistan från disk (börja om från noll)."""
    try:
        _state_sokvag(allowlist_fil, ALLOWLIST_NAMN).unlink(missing_ok=True)
    except OSError:
        pass


# --- Krypterat konteringsminne (Fas 7: skapa_kundfaktura HITL) ---------------
#
# Tredje medlemmen i samma familj som maskeringsliggaren/undantagslistan: en
# krypterad, lokal, per-entitet-inlärd JSON. Här: vilken BAS-kontering en
# människa VALDE (efter att ev. ha rättat AI:ts förslag) för en viss kund,
# så nästa fakturautkast åt samma kund kan förifyllas i stället för att gissa
# på nytt varje gång.
#
# Sparar ENDAST kontonr per kategori + fakturatyp — ALDRIG ROT-specifika
# personuppgifter (personnummer, fastighetsbeteckning). Det är ett medvetet
# beslut, inte bara "vad som råkade specificeras": en kontering ("arbete på
# 3041") är ett återanvändbart MÖNSTER, men en fastighetsbeteckning/ett
# personnummer hör till DEN ENSKILDA fakturan och kan variera fakturor emellan
# även för samma kund. Att auto-återanvända dem hade varit att tyst lita på
# gammal känslig data i stället för att låta människan bekräfta den varje
# gång — se app_vy.bygg_fakturautkast, som alltid kräver ROT-uppgifterna som
# egna, oberoende parametrar.

KONTERINGSMINNE_NAMN = "konteringsminne.enc"
KONTERINGSMINNE_VERSION = 1


def _normalisera_kundnamn(namn: str) -> str:
    """Matchningsnyckel för konteringsminnet: skiftlägesokänslig och med
    kollapsad whitespace, så att 'Anna  Andersson' och 'anna andersson' slår
    upp samma kund. Egen, syftesspecifik funktion — inte sekretesslager.
    normalisera_undantag, som är dokumenterad för undantagslistans matchning
    specifikt, inte generell strängnormalisering."""
    return " ".join(namn.split()).casefold()


def las_konteringsminne(
    env_fil: Path | None = None, konteringsminne_fil: Path | None = None
) -> dict[str, dict]:
    """Läser och dekrypterar konteringsminnet. Saknad/trasig fil, fel nyckel
    eller okänd version -> tomt minne (fail-safe: hellre fråga om kontering
    på nytt än krascha eller lita på skräpdata)."""
    konteringsminne_fil = _state_sokvag(konteringsminne_fil, KONTERINGSMINNE_NAMN)
    if not konteringsminne_fil.exists():
        return {}
    try:
        klartext = _hamta_eller_skapa_fernet(env_fil).decrypt(konteringsminne_fil.read_bytes())
        data = json.loads(klartext.decode("utf-8"))
    except (OSError, InvalidToken, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != KONTERINGSMINNE_VERSION:
        return {}
    kunder = data.get("kunder")
    return kunder if isinstance(kunder, dict) else {}


def spara_konteringsminne(
    kunder: dict[str, dict],
    env_fil: Path | None = None,
    konteringsminne_fil: Path | None = None,
) -> None:
    """Krypterar (Fernet) och skriver konteringsminnet till disk. Best-effort."""
    konteringsminne_fil = _state_sokvag(konteringsminne_fil, KONTERINGSMINNE_NAMN)
    chiffer = _hamta_eller_skapa_fernet(env_fil).encrypt(
        json.dumps(
            {"version": KONTERINGSMINNE_VERSION, "kunder": kunder}, ensure_ascii=False
        ).encode("utf-8")
    )
    try:
        saker_lagring.sakerstall_katalog(konteringsminne_fil)
        konteringsminne_fil.write_bytes(chiffer)
    except OSError:
        pass


def uppdatera_konteringsminne(
    kunder: dict[str, dict], kundnamn: str, fakturatyp: str, kontering: dict[str, str]
) -> dict[str, dict]:
    """Lär in (eller uppdaterar) ETT kundmönster efter ett mänskligt
    godkännande. Ren funktion — I/O sker separat via spara_konteringsminne.
    kontering är {kategori: kontonr}, t.ex. {"arbete": "3041", "materiel":
    "3051"} — den FAKTISKT godkända konteringen, inte AI:ts råa förslag (om
    användaren rättade den, är det den rättade versionen som lärs in)."""
    uppdaterad = dict(kunder)
    uppdaterad[_normalisera_kundnamn(kundnamn)] = {
        "visningsnamn": kundnamn,
        "fakturatyp": fakturatyp,
        "kontering": dict(kontering),
        "senast_uppdaterad": datetime.now().isoformat(timespec="seconds"),
    }
    return uppdaterad


def slå_upp_kontering(kunder: dict[str, dict], kundnamn: str) -> dict | None:
    """Slår upp ett tidigare inlärt konteringsmönster för en kund. None om
    ingen historik finns — anroparen faller då tillbaka till konteringsmotorns
    (spiris_adapter.foreslå_konto) rena regelbaserade förslag."""
    return kunder.get(_normalisera_kundnamn(kundnamn))


def tomt_konteringsminne(konteringsminne_fil: Path | None = None) -> None:
    """Raderar konteringsminnet från disk (börja om från noll)."""
    try:
        _state_sokvag(konteringsminne_fil, KONTERINGSMINNE_NAMN).unlink(missing_ok=True)
    except OSError:
        pass
