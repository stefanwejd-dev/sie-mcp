"""avstamning.csvprofil — kolumnprofil för CSV-kontoutdrag, sparad per konto.

Lager 1b, se hantverksbok/BOKSLUTSPROGRAMMET.md §4.2 och §4.5 steg 2. Varje
bank har sitt eget CSV-format; en människa anger EN gång vilken kolumn som
är datum, belopp, text och (valfritt) saldo, och profilen sparas per konto
så att nästa avstämning av samma konto inte kräver samma fråga igen.

**Kolumnerna gissas ALDRIG automatiskt** (§4.2). En felgissad beloppskolumn
producerar en avstämning som ser ut att stämma och inte gör det, vilket är
värre än ingen avstämning alls — så en rad som inte går att tolka med den
angivna profilen kastar hellre ett fel än att tyst hoppas över eller gissas.

Profilen i sig (kolumnindex, avgränsare, datumformat) är strukturell
metadata, inte PII — den behöver alltså inte samma sekretessbehandling som
själva kontoutdraget (se §4.4, hanteras i steg 5)."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import saker_lagring

from .camt053 import Utdrag, Utdragsrad

CSVPROFILER_NAMN = "csvprofiler.json"


class CsvprofilFel(Exception):
    """Filen kunde inte läsas med den angivna profilen — eller profilen är
    ogiltig. Aldrig ett tyst, delvis eller gissat resultat."""


@dataclass(frozen=True)
class Kolumnprofil:
    """Vilken kolumn (0-indexerad) som är vad, för ETT kontos CSV-export.

    Alla kolumner anges explicit av en människa. `text_kolumn` och
    `saldo_kolumn` är valfria — saknas `saldo_kolumn` blir
    `Utdrag.ingaende_saldo`/`utgaende_saldo` `None`, inte ett gissat tal."""

    kontonr: str
    datum_kolumn: int
    belopp_kolumn: int
    text_kolumn: int | None = None
    saldo_kolumn: int | None = None
    avgransare: str = ";"
    har_rubrikrad: bool = True
    datumformat: str = "%Y-%m-%d"
    kodning: str = "utf-8"
    # Svenska bankexporter använder ofta ',' som decimaltecken och ibland '.'
    # som tusentalsavgränsare (t.ex. "1.234,56"). Explicit flagga i stället
    # för att gissa på vilket tecken som förekommer flest gånger.
    decimalkomma: bool = False


def _profilsokvag(explicit: str | Path | None = None) -> Path:
    return saker_lagring.artefakt_sokvag(explicit, kategori="state", namn=CSVPROFILER_NAMN)


def _las_alla_profiler(sokvag: Path) -> dict[str, dict]:
    try:
        data = json.loads(sokvag.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def spara_profil(profil: Kolumnprofil, sokvag: str | Path | None = None) -> None:
    """Sparar (eller ersätter) profilen för `profil.kontonr`. Best-effort på
    skrivfel — precis som `masking_memory`, samma resonemang: en profil som
    inte kunde sparas ska inte krascha appen, bara tvinga fram frågan igen
    nästa gång."""
    fil = _profilsokvag(sokvag)
    profiler = _las_alla_profiler(fil)
    profiler[profil.kontonr] = asdict(profil)
    try:
        saker_lagring.sakerstall_katalog(fil)
        fil.write_text(json.dumps(profiler, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def las_profil(kontonr: str, sokvag: str | Path | None = None) -> Kolumnprofil | None:
    """Den sparade profilen för ett konto, eller `None` om ingen finns."""
    profiler = _las_alla_profiler(_profilsokvag(sokvag))
    data = profiler.get(kontonr)
    if data is None:
        return None
    try:
        return Kolumnprofil(**data)
    except TypeError:
        # En profil sparad av en äldre/annan version av Kolumnprofil (fält
        # som lagts till eller tagits bort) — fail-closed: behandla som
        # ingen profil i stället för att gissa på vad som gäller.
        return None


def ta_bort_profil(kontonr: str, sokvag: str | Path | None = None) -> None:
    fil = _profilsokvag(sokvag)
    profiler = _las_alla_profiler(fil)
    if kontonr not in profiler:
        return
    del profiler[kontonr]
    try:
        saker_lagring.sakerstall_katalog(fil)
        fil.write_text(json.dumps(profiler, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _till_decimal(text: str, decimalkomma: bool) -> Decimal | None:
    text = text.strip().replace("\xa0", "").replace(" ", "")
    if not text:
        return None
    if decimalkomma:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _till_datum(text: str, datumformat: str):
    try:
        return datetime.strptime(text.strip(), datumformat).date()
    except ValueError:
        return None


def parse_csv(sokvag: str | Path, profil: Kolumnprofil) -> Utdrag:
    """Läser en CSV-fil enligt en explicit `Kolumnprofil`.

    Kastar `CsvprofilFel` om filen inte går att läsa, eller om en rad som
    inte är tom har färre kolumner än profilen kräver eller inte går att
    tolka i datum-/beloppkolumnen — hellre ett tydligt fel än en tyst
    felaktig avstämning.

    Saldo (om `saldo_kolumn` är satt) tolkas som det löpande saldot EFTER
    varje rads transaktion — vanligt i svenska bankexporter. Ingående saldo
    härleds som den kronologiskt första radens saldo minus dess eget belopp;
    utgående saldo är den kronologiskt sista radens saldo. Raderna sorteras
    efter datum (stabil sortering — ursprunglig ordning bevaras vid lika
    datum) enbart för den härledningen; `Utdrag.rader` behåller filens
    egen ordning."""
    try:
        with open(sokvag, "r", encoding=profil.kodning, newline="") as f:
            alla_rader = list(csv.reader(f, delimiter=profil.avgransare))
    except OSError as e:
        raise CsvprofilFel(f"Kunde inte läsa filen: {e}") from e
    except (LookupError, UnicodeDecodeError) as e:
        raise CsvprofilFel(f"Filen kunde inte avkodas som {profil.kodning!r}: {e}") from e

    if profil.har_rubrikrad and alla_rader:
        alla_rader = alla_rader[1:]

    kolumner = [profil.datum_kolumn, profil.belopp_kolumn, profil.text_kolumn, profil.saldo_kolumn]
    max_kolumn = max(k for k in kolumner if k is not None)

    # Saldot (om kolumnen finns) hör bara till härledningen av Utdrag.ingaende_
    # /utgaende_saldo — Utdragsrad har inget saldofält (§4.5 steg 1: bara
    # datum, belopp, text, motpart, referens), så det hålls i en separat lista
    # i stället för att tacka på klassen.
    rader: list[Utdragsrad] = []
    rad_saldon: list[Decimal | None] = []
    for radnr, rad in enumerate(alla_rader, start=1):
        if not rad or all(not falt.strip() for falt in rad):
            continue  # tom rad, t.ex. sist i filen
        if len(rad) <= max_kolumn:
            raise CsvprofilFel(
                f"Rad {radnr} har {len(rad)} kolumner, profilen kräver minst "
                f"{max_kolumn + 1} — profilen stämmer sannolikt inte mot filen."
            )

        datum = _till_datum(rad[profil.datum_kolumn], profil.datumformat)
        belopp = _till_decimal(rad[profil.belopp_kolumn], profil.decimalkomma)
        if datum is None or belopp is None:
            raise CsvprofilFel(
                f"Rad {radnr}: kunde inte tolka datum och/eller belopp med den "
                "angivna profilen (fel kolumn eller fel format?)."
            )

        text = None
        if profil.text_kolumn is not None:
            text = rad[profil.text_kolumn].strip() or None

        saldo = None
        if profil.saldo_kolumn is not None:
            saldo = _till_decimal(rad[profil.saldo_kolumn], profil.decimalkomma)

        rader.append(Utdragsrad(datum=datum, belopp=belopp, text=text))
        rad_saldon.append(saldo)

    period_start = min((r.datum for r in rader), default=None)
    period_slut = max((r.datum for r in rader), default=None)

    ingaende_saldo = None
    utgaende_saldo = None
    if profil.saldo_kolumn is not None and rader:
        i_datumordning = sorted(range(len(rader)), key=lambda i: rader[i].datum)
        forsta_index = next((i for i in i_datumordning if rad_saldon[i] is not None), None)
        sista_index = next(
            (i for i in reversed(i_datumordning) if rad_saldon[i] is not None), None
        )
        if forsta_index is not None:
            ingaende_saldo = rad_saldon[forsta_index] - rader[forsta_index].belopp
        if sista_index is not None:
            utgaende_saldo = rad_saldon[sista_index]

    return Utdrag(
        kontonr=profil.kontonr,
        period_start=period_start,
        period_slut=period_slut,
        ingaende_saldo=ingaende_saldo,
        utgaende_saldo=utgaende_saldo,
        rader=tuple(rader),
    )
