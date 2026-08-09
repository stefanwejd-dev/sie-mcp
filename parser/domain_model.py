"""Domain model for SIE4 data — dataclasses only, no parsing logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass
class Tolkningsbehov:
    radnummer: int
    råtext: str
    etikett: str | None
    anledning: str
    kontext: str | None = None
    partiell_tolkning: str | None = None


@dataclass
class Räkenskapsår:
    årsnr: int
    start: date
    slut: date


@dataclass
class Adress:
    kontakt: str | None = None
    utdelningsadress: str | None = None
    postadress: str | None = None
    telefon: str | None = None


@dataclass
class Dimension:
    dimensionsnr: int
    namn: str
    superdimension: int | None = None


@dataclass
class Objekt:
    dimensionsnr: int
    objektnr: str
    namn: str


@dataclass
class Konto:
    kontonr: str
    namn: str
    typ: Literal["T", "S", "K", "I"] | None = None
    enhet: str | None = None
    sru_koder: list[str] = field(default_factory=list)


@dataclass
class Saldopost:
    årsnr: int
    kontonr: str
    objektreferenser: dict[int, str]
    saldo: Decimal
    kvantitet: Decimal | None = None


@dataclass
class Periodsaldo:
    årsnr: int
    period: str
    kontonr: str
    objektreferenser: dict[int, str]
    saldo: Decimal
    kvantitet: Decimal | None = None


@dataclass
class Transaktion:
    kontonr: str
    belopp: Decimal
    objektreferenser: dict[int, str] = field(default_factory=dict)
    transdat: date | None = None
    transtext: str | None = None
    kvantitet: Decimal | None = None
    sign: str | None = None
    radtyp: Literal["TRANS", "RTRANS", "BTRANS"] = "TRANS"


@dataclass
class Verifikation:
    serie: str | None
    vernr: str | None
    verdatum: date
    vertext: str | None = None
    regdatum: date | None = None
    sign: str | None = None
    transaktioner: list[Transaktion] = field(default_factory=list)


@dataclass
class SIEFil:
    sietyp: int | None = None
    program: str | None = None
    program_version: str | None = None
    genererad: date | None = None
    genererad_sign: str | None = None
    företagsnamn: str = ""
    orgnr: str | None = None
    förvaltningsnummer: str | None = None
    verksamhetsnummer: str | None = None
    företagsid: str | None = None
    företagstyp: str | None = None
    sni_kod: str | None = None
    taxeringsår: str | None = None
    kontoplanstyp: Literal["BAS95", "BAS96", "EUBAS97", "NE2007"] | None = None
    räkenskapsår: dict[int, Räkenskapsår] = field(default_factory=dict)
    valuta: str = "SEK"
    omfattning: date | None = None
    konton: dict[str, Konto] = field(default_factory=dict)
    dimensioner: dict[int, Dimension] = field(default_factory=dict)
    objektregister: dict[tuple[int, str], Objekt] = field(default_factory=dict)
    ingående_balanser: list[Saldopost] = field(default_factory=list)
    utgående_balanser: list[Saldopost] = field(default_factory=list)
    objekt_ingående_balanser: list[Saldopost] = field(default_factory=list)
    objekt_utgående_balanser: list[Saldopost] = field(default_factory=list)
    resultat: list[Saldopost] = field(default_factory=list)
    periodsaldon: list[Periodsaldo] = field(default_factory=list)
    periodbudgetar: list[Periodsaldo] = field(default_factory=list)
    verifikationer: list[Verifikation] = field(default_factory=list)
    flagga: int = 0
    prosa: str | None = None
    adress: Adress | None = None
    ksumma: int | None = None
    tolkningsbehov: list[Tolkningsbehov] = field(default_factory=list)
