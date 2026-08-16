"""avstamning.camt053 — parser för camt.053 (ISO 20022 BkToCstmrStmt).

Lager 1b, se hantverksbok/BOKSLUTSPROGRAMMET.md §4, steg 1. Bygger den
neutrala `Utdrag`/`Utdragsrad`-modellen som `csvprofil.py`, `matchning.py`
och `kontroller.py` arbetar mot — samma roll som `sie4_parser.py` fyller för
`SIEFil` i lager 1.

Namnrymden i camt.053 skiljer sig mellan versioner (.001.02 … .001.08), men
elementnamnen är stabila. Parsern matchar därför på LOKALT elementnamn (utan
namnrymdsprefix) i stället för att låsa till en specifik version — samma
princip som gör `sie4_parser.py` tolerant mot variation i källan.

Fail-closed: en fil som inte går att tolka som camt.053 ger `Camt053Fel`,
aldrig ett tomt eller gissat `Utdrag` som ser ut att stämma."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class Utdragsrad:
    """En rad på kontoutdraget — neutral oavsett källformat (camt.053 eller
    CSV, se `csvprofil.py`). `belopp` är tecknat: insättning positiv, uttag
    negativ — samma konvention som `Transaktion.belopp` i `domain_model.py`."""

    datum: date
    belopp: Decimal
    text: str | None = None
    motpart: str | None = None
    referens: str | None = None


@dataclass(frozen=True)
class Utdrag:
    """Ett helt kontoutdrag: konto, period, saldon och raderna."""

    kontonr: str | None
    period_start: date | None
    period_slut: date | None
    ingaende_saldo: Decimal | None
    utgaende_saldo: Decimal | None
    rader: tuple[Utdragsrad, ...] = ()


class Camt053Fel(Exception):
    """Filen kunde inte tolkas som ett camt.053-kontoutdrag."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hitta(el: ET.Element, *vag: str) -> ET.Element | None:
    """Följer en kedja av lokala elementnamn nedåt från `el`. `None` om något
    steg saknas — anroparen avgör om det är ett fel eller bara frånvarande
    (valfritt) fält."""
    aktuell = el
    for namn in vag:
        nasta = None
        for barn in aktuell:
            if _local(barn.tag) == namn:
                nasta = barn
                break
        if nasta is None:
            return None
        aktuell = nasta
    return aktuell


def _text(el: ET.Element, *vag: str) -> str | None:
    funnen = _hitta(el, *vag)
    if funnen is None or funnen.text is None:
        return None
    text = funnen.text.strip()
    return text or None


def _decimal(varde: str | None) -> Decimal | None:
    if varde is None:
        return None
    try:
        return Decimal(varde)
    except InvalidOperation:
        return None


def _datum(varde: str | None) -> date | None:
    if varde is None:
        return None
    try:
        return date.fromisoformat(varde[:10])
    except ValueError:
        return None


def _tecknat_belopp(entry_el: ET.Element) -> Decimal | None:
    belopp = _decimal(_text(entry_el, "Amt"))
    if belopp is None:
        return None
    return -belopp if _text(entry_el, "CdtDbtInd") == "DBIT" else belopp


def _entry_datum(entry_el: ET.Element) -> date | None:
    # BookgDt föredras, ValDt som reserv — samma prioritetsordning bankerna
    # själva exponerar i camt.053.
    for gren in ("BookgDt", "ValDt"):
        for taggnamn in ("Dt", "DtTm"):
            funnet = _datum(_text(entry_el, gren, taggnamn))
            if funnet is not None:
                return funnet
    return None


def _entry_text(entry_el: ET.Element) -> str | None:
    # RmtInf/Ustrd ligger normalt under NtryDtls/TxDtls, men vissa banker
    # lägger den direkt under Ntry. AddtlNtryInf som sista reserv.
    for vag in (
        ("NtryDtls", "TxDtls", "RmtInf", "Ustrd"),
        ("RmtInf", "Ustrd"),
        ("AddtlNtryInf",),
    ):
        text = _text(entry_el, *vag)
        if text:
            return text
    return None


def _entry_motpart(entry_el: ET.Element) -> str | None:
    for part in ("Dbtr", "Cdtr"):
        for vag in (
            ("NtryDtls", "TxDtls", "RltdPties", part, "Nm"),
            ("RltdPties", part, "Nm"),
        ):
            namn = _text(entry_el, *vag)
            if namn:
                return namn
    return None


def _entry_referens(entry_el: ET.Element) -> str | None:
    for vag in (
        ("NtryRef",),
        ("AcctSvcrRef",),
        ("NtryDtls", "TxDtls", "Refs", "AcctSvcrRef"),
        ("NtryDtls", "TxDtls", "Refs", "EndToEndId"),
    ):
        ref = _text(entry_el, *vag)
        if ref:
            return ref
    return None


def _saldo(stmt_el: ET.Element, kod: str) -> Decimal | None:
    for bal_el in stmt_el:
        if _local(bal_el.tag) != "Bal":
            continue
        if _text(bal_el, "Tp", "CdOrPrtry", "Cd") != kod:
            continue
        belopp = _decimal(_text(bal_el, "Amt"))
        if belopp is None:
            continue
        return -belopp if _text(bal_el, "CdtDbtInd") == "DBIT" else belopp
    return None


def parse_camt053(sokvag: str | Path) -> Utdrag:
    """Läser en camt.053-fil och bygger ett neutralt `Utdrag`.

    Kastar `Camt053Fel` om filen inte går att tolka — aldrig ett tomt eller
    gissat resultat. En enskild `Ntry`-rad utan belopp eller datum hoppas
    över (går inte att stämma av), men fäller inte hela inläsningen."""
    try:
        träd = ET.parse(str(sokvag))
    except ET.ParseError as e:
        raise Camt053Fel(f"Filen är inte giltig XML: {e}") from e
    except OSError as e:
        raise Camt053Fel(f"Kunde inte läsa filen: {e}") from e

    rot = träd.getroot()
    stmt = _hitta(rot, "BkToCstmrStmt", "Stmt")
    if stmt is None:
        raise Camt053Fel(
            "Filen innehåller ingen BkToCstmrStmt/Stmt — inte ett camt.053-kontoutdrag."
        )

    kontonr = _text(stmt, "Acct", "Id", "IBAN") or _text(stmt, "Acct", "Id", "Othr", "Id")
    period_start = _datum(_text(stmt, "FrToDt", "FrDtTm"))
    period_slut = _datum(_text(stmt, "FrToDt", "ToDtTm"))
    ingaende = _saldo(stmt, "OPBD")
    utgaende = _saldo(stmt, "CLBD")

    rader: list[Utdragsrad] = []
    for entry_el in stmt:
        if _local(entry_el.tag) != "Ntry":
            continue
        belopp = _tecknat_belopp(entry_el)
        datum = _entry_datum(entry_el)
        if belopp is None or datum is None:
            continue
        rader.append(
            Utdragsrad(
                datum=datum,
                belopp=belopp,
                text=_entry_text(entry_el),
                motpart=_entry_motpart(entry_el),
                referens=_entry_referens(entry_el),
            )
        )

    return Utdrag(
        kontonr=kontonr,
        period_start=period_start,
        period_slut=period_slut,
        ingaende_saldo=ingaende,
        utgaende_saldo=utgaende,
        rader=tuple(rader),
    )
