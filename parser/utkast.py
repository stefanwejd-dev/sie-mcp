"""utkast.py — lokal kö för föreslagna men EJ UTFÖRDA skrivningar mot Spiris.

Det här är grinden i Steg 2. Läs den här innan du rör något som skriver mot ett
affärssystem.

**Konstruktionen.** En MCP-klient (alltså en AI) kan *föreslå* en skrivning
genom att lägga ett utkast här. Den kan aldrig utföra det. Utförandet sker i
Streamlit-appen, där en människa ser de VERKLIGA värdena och trycker "Godkänn
och skicka". MCP-servern får därmed noll skrivförmåga mot Spiris — invarianten
"HITL sker aldrig över MCP" (ARCHITECTURE.md, DATASKYDD §8.1) överlever
oförändrad i stället för att urholkas.

**Varför inte MCP:ns elicitation som grind.** SDK:t har `Context.elicit`, och
det var förstahandsförslaget när Steg 2 skissades. Men specen säger uttryckligen
att en agentklient får besvara en elicitation *automatiskt* i stället för att
fråga användaren. En grind som kan passeras av samma modell som föreslog
åtgärden är ingen grind.

Elicitation används därför enbart som en TIDIG SAMMANFATTNING
(`server._visa_tidig_sammanfattning`, S2-D), med en avsiktligt asymmetrisk
verkan: ett avböjande stoppar utkastet, men ett accepterande godkänner
ingenting — det skapar bara utkastet, som fortfarande måste godkännas lokalt i
appen. Saknar klienten stöd fortsätter flödet oförändrat (fail-OPEN), eftersom
detta inte är ett säkerhetssteg och det därmed inte finns något att fail-closa.

**Hashbindningen.** Utkastet lagras på disk mellan förslag och godkännande.
`nyttolast_hash` är SHA-256 över den kanoniserade nyttolasten, och räknas om vid
godkännandet. Det gör att det människan såg är exakt det som skickas — en
ändrad utkastfil (av vad som helst: en bugg, en annan process, en angripare med
lokal åtkomst) leder till vägran, inte till en tyst avvikelse.

**Livslängd.** 24 timmar. Ett dygn gammalt utkast som godkänns av misstag är en
verklig risk: underlaget kan ha ändrats i Spiris under tiden.

**Innehållet är omaskerat.** Nyttolasten bär verkliga namn, belopp och
eventuella personnummer — det MÅSTE den, eftersom det är exakt den payload som
ska POSTas och eftersom människan ska kunna granska den. Filerna ligger därför
under `saker_lagring.state_dir()` med samma ACL-härdning som hemligheterna, och
gallras. Det är en egen personuppgiftsbehandling; se DATASKYDD §2.3.1.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import saker_lagring

KATALOG = "utkast"

# Ett dygn. Kort med flit: underlaget i Spiris kan ha ändrats.
STANDARD_LIVSLANGD_TIMMAR = 24

# Statusvärden. "vantar" är det enda läge ur vilket en sändning får ske.
VANTAR = "vantar"
SKICKAT = "skickat"
AVVISAT = "avvisat"
MISSLYCKAT = "misslyckat"

# Steg 5 lade till kundfakturans livscykelåtgärder. De två första är
# UTÅTRIKTADE — de skickar något till en tredje man (kunden) och kan inte
# kallas tillbaka. Vilka typer som är utåtriktade avgörs INTE här utan i
# spiris_adapter.UTATRIKTADE_TYPER: kön är en generisk lagringsmekanism och
# ska inte bära domänkunskap om vad en typ innebär.
GILTIGA_TYPER = (
    "kund",
    "kundfaktura",
    "verifikat",
    "betalningsverifikat",
    "fakturautskick",
    "betalningspaminnelse",
    "betalningsregistrering",
    "makulering",
    # Steg 5b: offert- och orderkedjan.
    "saljdokumentutskick",
    "efakturautskick",
    "saljdokumentatgard",
    # Steg 6: inköp och attest.
    "leverantorsfakturautkast",
    "attest",
    "leverantorsbetalning",
    "kvittning",
    # Steg 7: masterdata.
    "masterdataandring",
    "masterdataborttagning",
    "sie4import",
    "underlagskoppling",
    # Steg 4: utkastvägen.
    "utkastandring",
    "utkastborttagning",
    "utkastbokforing",
    "periodisering",
    "konto",
    "kontoandring",
    "periodiseringsandring",
    "periodiseringsborttagning",
    "bokforingslas",
    "rotrut",
)


class UtkastFel(Exception):
    """Utkastet får inte skickas. Alltid fail-closed: hellre ett vägrat
    godkännande än en skrivning på fel underlag."""


@dataclass(frozen=True)
class Utkast:
    utkast_id: str
    typ: str
    skapad: str
    status: str
    nyttolast: dict[str, Any]
    nyttolast_hash: str
    # (etikett, värde)-par som visas för människan. Byggs av den som skapar
    # utkastet, eftersom bara den vet vad som är begripligt för just den typen.
    sammanfattning: list[list[str]] = field(default_factory=list)
    resultat: dict[str, Any] | None = None

    @property
    def ar_utgangen(self) -> bool:
        return _alder_timmar(self.skapad) > STANDARD_LIVSLANGD_TIMMAR


def _katalog() -> Path:
    d = saker_lagring.state_dir() / KATALOG
    d.mkdir(parents=True, exist_ok=True)
    saker_lagring._begransa_behorighet(d)
    return d


def _sokvag(utkast_id: str) -> Path:
    # Bara vårt eget id-format får bli ett filnamn — ett utkast_id kommer från
    # en MCP-klient, alltså från en AI. Utan den här kontrollen vore
    # kontrollera_utkast("../../secrets/.env") en filläsningsprimitiv.
    if not _giltigt_id(utkast_id):
        raise UtkastFel("Ogiltigt utkast-id.")
    return _katalog() / f"{utkast_id}.json"


def _giltigt_id(utkast_id: str) -> bool:
    return (
        isinstance(utkast_id, str)
        and 8 <= len(utkast_id) <= 40
        and all(t in "0123456789abcdef-" for t in utkast_id)
    )


def _kanonisera(nyttolast: dict[str, Any]) -> str:
    """Stabil strängform av nyttolasten. sort_keys gör att en omordnad men
    identisk dict ger samma hash; default=str hanterar Decimal och date utan
    att förlora värdet."""
    return json.dumps(nyttolast, sort_keys=True, ensure_ascii=False, default=str)


def berakna_hash(nyttolast: dict[str, Any]) -> str:
    return hashlib.sha256(_kanonisera(nyttolast).encode("utf-8")).hexdigest()


def _alder_timmar(skapad_iso: str) -> float:
    try:
        skapad = datetime.fromisoformat(skapad_iso)
    except (TypeError, ValueError):
        return float("inf")  # otolkbart datum -> behandla som utgånget
    return (datetime.now() - skapad).total_seconds() / 3600


def _till_dict(u: Utkast) -> dict[str, Any]:
    return {
        "utkast_id": u.utkast_id,
        "typ": u.typ,
        "skapad": u.skapad,
        "status": u.status,
        "nyttolast": json.loads(_kanonisera(u.nyttolast)),
        "nyttolast_hash": u.nyttolast_hash,
        "sammanfattning": u.sammanfattning,
        "resultat": u.resultat,
    }


def _fran_dict(data: dict[str, Any]) -> Utkast:
    return Utkast(
        utkast_id=str(data["utkast_id"]),
        typ=str(data["typ"]),
        skapad=str(data["skapad"]),
        status=str(data["status"]),
        nyttolast=data["nyttolast"],
        nyttolast_hash=str(data["nyttolast_hash"]),
        sammanfattning=[list(par) for par in data.get("sammanfattning", [])],
        resultat=data.get("resultat"),
    )


def _skriv(u: Utkast) -> None:
    """Atomisk helskrivning: temporärfil + os.replace. Samma skäl som
    sessionslogg — en avbruten skrivning får aldrig lämna ett halvt utkast som
    någon sedan godkänner."""
    mal = _sokvag(u.utkast_id)
    tmp = mal.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(_till_dict(u), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, mal)


def skapa(
    typ: str, nyttolast: dict[str, Any], sammanfattning: list[list[str]]
) -> Utkast:
    """Lägger ett förslag i kön. Utför INGENTING."""
    if typ not in GILTIGA_TYPER:
        raise UtkastFel(f"Okänd utkasttyp: {typ!r}.")
    if not isinstance(nyttolast, dict) or not nyttolast:
        raise UtkastFel("Nyttolasten saknas.")

    u = Utkast(
        utkast_id=uuid.uuid4().hex[:16],
        typ=typ,
        skapad=datetime.now().isoformat(timespec="seconds"),
        status=VANTAR,
        nyttolast=nyttolast,
        nyttolast_hash=berakna_hash(nyttolast),
        sammanfattning=sammanfattning,
    )
    _skriv(u)
    return u


def las(utkast_id: str) -> Utkast | None:
    try:
        fil = _sokvag(utkast_id)
        if not fil.exists():
            return None
        return _fran_dict(json.loads(fil.read_text(encoding="utf-8")))
    except (UtkastFel, saker_lagring.SakerLagringFel, OSError, ValueError, KeyError):
        return None


def lista(status: str | None = None) -> list[Utkast]:
    """Alla utkast, nyast först. Trasiga filer hoppas över tyst — ett skadat
    utkast ska inte kunna fälla granskningsvyn och därmed blockera de andra."""
    try:
        katalog = _katalog()
    except saker_lagring.SakerLagringFel:
        return []
    poster: list[Utkast] = []
    for fil in katalog.glob("*.json"):
        try:
            u = _fran_dict(json.loads(fil.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError):
            continue
        if status is None or u.status == status:
            poster.append(u)
    return sorted(poster, key=lambda u: u.skapad, reverse=True)


def bekrafta_for_sandning(utkast_id: str) -> dict[str, Any]:
    """Grinden. Returnerar nyttolasten att POSTa — eller höjer UtkastFel.

    Fyra kontroller, alla fail-closed. Anropas av appen omedelbart före POST,
    aldrig av MCP-servern.
    """
    u = las(utkast_id)
    if u is None:
        raise UtkastFel("Utkastet finns inte.")
    if u.status != VANTAR:
        raise UtkastFel(f"Utkastet är redan {u.status}.")
    if u.ar_utgangen:
        raise UtkastFel(
            f"Utkastet är äldre än {STANDARD_LIVSLANGD_TIMMAR} timmar och kan "
            "inte längre skickas. Underlaget kan ha ändrats — skapa ett nytt."
        )
    if berakna_hash(u.nyttolast) != u.nyttolast_hash:
        raise UtkastFel(
            "Utkastet har ändrats sedan det skapades och skickas inte. "
            "Skapa ett nytt utkast."
        )
    return u.nyttolast


def markera_skickat(utkast_id: str, resultat: dict[str, Any] | None = None) -> None:
    _byt_status(utkast_id, SKICKAT, resultat)


def markera_misslyckat(utkast_id: str, orsak: str) -> None:
    # Bara en kort, egen orsakstext — aldrig en rå exception, som kan bära hela
    # förfrågan eller ett API-svar.
    _byt_status(utkast_id, MISSLYCKAT, {"orsak": orsak})


def avvisa(utkast_id: str) -> None:
    _byt_status(utkast_id, AVVISAT, None)


def _byt_status(utkast_id: str, status: str, resultat: dict[str, Any] | None) -> None:
    u = las(utkast_id)
    if u is None:
        raise UtkastFel("Utkastet finns inte.")
    from dataclasses import replace

    _skriv(replace(u, status=status, resultat=resultat))


def rensa_gamla(timmar: int = STANDARD_LIVSLANGD_TIMMAR) -> int:
    """Raderar utkast äldre än `timmar`. Körs vid appstart, som sessionsloggen.

    Gallringen omfattar ALLA statusar: även ett skickat utkast bär omaskerade
    personuppgifter och ska inte ligga kvar. Fail-safe — fel sväljs, och bara
    filer som ser ut som våra egna rörs."""
    if timmar <= 0:
        return 0
    try:
        katalog = _katalog()
    except saker_lagring.SakerLagringFel:
        return 0
    gransen = time.time() - timmar * 3600
    raderade = 0
    for fil in list(katalog.glob("*.json")):
        try:
            if fil.stat().st_mtime < gransen:
                fil.unlink()
                raderade += 1
        except OSError:
            continue
    return raderade
