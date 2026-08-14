"""Datamodell för bokslutskontrollerna — se hantverksbok/BOKSLUTSKONTROLLER.md §4.

Rena dataklasser. Inga beroenden utom domain_model och standardbiblioteket."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Literal

from domain_model import SIEFil

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


Kontroll = Callable[[Kontext], list[Fynd]]
