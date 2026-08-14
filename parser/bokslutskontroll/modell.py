"""Datamodell för bokslutskontrollerna — se hantverksbok/BOKSLUTSKONTROLLER.md §4.

Rena dataklasser. Inga beroenden utom domain_model och standardbiblioteket."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Literal

from domain_model import SIEFil

if TYPE_CHECKING:
    # Bara för typannotering (från __future__ import annotations gör alla
    # annotationer till strängar — ingen körtidsimport sker). bokslutskontroll
    # importerar ALDRIG avstamning på riktigt: det vore ett cirkulärt
    # paketberoende, eftersom avstamning/kontroller.py importerar
    # bokslutskontroll (registrera, Fynd, Kontext). Beroendet går bara åt
    # ena hållet — se hantverksbok/BOKSLUTSPROGRAMMET.md §4.5 steg 4.
    from avstamning.camt053 import Utdrag

Allvarlighet = Literal["avvikelse", "observation", "upplysning"]


@dataclass(frozen=True)
class Konteringsrad:
    kontonr: str
    debet: Decimal = Decimal("0")
    kredit: Decimal = Decimal("0")
    text: str | None = None


@dataclass(frozen=True)
class Rattelseforslag:
    """Ett förslag i text och konteringsrader. Utförs aldrig av lager 1 (I-2)."""

    beskrivning: str
    rader: tuple[Konteringsrad, ...] = ()
    forbehall: str | None = None  # t.ex. "kräver att underlaget kontrolleras"


@dataclass(frozen=True)
class Regelhanvisning:
    """Speglar quiet_chatts Faktapost-disciplin: en hänvisning utan både en
    läsbar och en maskinell länk är ingen hänvisning."""

    kalla: str  # "SFS 1999:1078", "BFNAR 2016:10", "Skatteverket"
    beteckning: str  # "5 kap. 6 §"
    lank_manniska: str
    lank_maskin: str | None = None
    kommentar: str | None = None


@dataclass(frozen=True)
class Fynd:
    kontroll_id: str  # "K-01"
    rubrik: str  # kort, en rad
    allvarlighet: Allvarlighet
    motivering: str  # varför detta är ett fynd, med tal
    konton: tuple[str, ...] = ()
    verifikationer: tuple[str, ...] = ()  # "A/12" — serie/vernr
    belopp: Decimal | None = None
    vasentlig: bool | None = None  # None = väsentlighet ej beräknbar
    regel: Regelhanvisning | None = None
    forslag: Rattelseforslag | None = None


@dataclass(frozen=True)
class Kontext:
    """Allt en kontroll behöver. En kontroll får aldrig läsa klockan eller
    filsystemet själv (B-2) — allt kommer härifrån."""

    sie: SIEFil
    idag: date
    arsnr: int = 0  # 0 = innevarande räkenskapsår
    vasentlighetstal: Decimal | None = None
    utfallsvasentlighet: Decimal | None = None
    parametrar: dict[str, object] = field(default_factory=dict)  # ur registret
    tolerans: Decimal = Decimal("1.00")  # kronor; ur registret
    # Lager 1b (avstämning, se BOKSLUTSPROGRAMMET.md §4). Båda None som
    # standard — lager 1:s K-*-kontroller och alla befintliga anrop är helt
    # opåverkade. A-*-kontrollerna kör bara när båda är satta: det finns
    # ingen väg att stämma av ett konto utan att användaren tillhandahåller
    # utdraget OCH pekar ut vilket bokfört konto det gäller (utdragets egen
    # kontoidentifierare, t.ex. ett IBAN, är inte samma sträng som ett
    # BAS-kontonummer — mappningen görs av anroparen, inte gissas här).
    utdrag: "Utdrag | None" = None
    avstamningskonto: str | None = None


Kontroll = Callable[[Kontext], list[Fynd]]
