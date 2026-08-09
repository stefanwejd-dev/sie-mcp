"""SIE4 file parser — #FNAMN, #KONTO, #VER, #TRANS, with tolkningsbehov."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from domain_model import (
    Adress,
    Dimension,
    Konto,
    Objekt,
    Periodsaldo,
    Räkenskapsår,
    Saldopost,
    SIEFil,
    Tolkningsbehov,
    Transaktion,
    Verifikation,
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(line: str) -> list[str]:
    """Split a SIE line into tokens.

    Handles unquoted words, "quoted strings" with backslash-escaped quotes,
    and {object lists} as single opaque tokens.
    """
    tokens: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        while i < n and line[i] in " \t":
            i += 1
        if i >= n:
            break

        ch = line[i]
        if ch == '"':
            i += 1
            chars: list[str] = []
            while i < n and line[i] != '"':
                if line[i] == '\\' and i + 1 < n and line[i + 1] == '"':
                    chars.append('"')
                    i += 2
                else:
                    chars.append(line[i])
                    i += 1
            if i < n:
                i += 1  # skip closing "
            tokens.append("".join(chars))
        elif ch == '{':
            depth = 0
            start = i
            while i < n:
                if line[i] == '{':
                    depth += 1
                elif line[i] == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            tokens.append(line[start:i])
        else:
            start = i
            while i < n and line[i] not in " \t":
                i += 1
            tokens.append(line[start:i])
    return tokens


def _parse_objlista(s: str) -> dict[int, str]:
    """Parse '{dimnr objnr dimnr objnr ...}' into dict[int, str]."""
    inner = s[1:-1].strip()
    if not inner:
        return {}
    parts = _tokenize(inner)
    result: dict[int, str] = {}
    for j in range(0, len(parts) - 1, 2):
        try:
            result[int(parts[j])] = parts[j + 1]
        except (ValueError, IndexError):
            pass
    return result


def _parse_date(s: str) -> date | None:
    """Parse ÅÅÅÅMMDD, return None if blank or malformed."""
    s = s.strip()
    if not s or len(s) != 8:
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _giltig_period(s: str) -> bool:
    """True om s är exakt 6 siffror och månadsdelen (de två sista) är 01–12."""
    return len(s) == 6 and s.isdigit() and 1 <= int(s[4:6]) <= 12


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_TRANS_LABELS = frozenset({"#TRANS", "#RTRANS", "#BTRANS"})
_KPTYP_VÄRDEN = frozenset({"BAS95", "BAS96", "EUBAS97", "NE2007"})
_KTYP_TYP_VÄRDEN = frozenset({"T", "S", "K", "I"})
_ALLTID_OBLIGATORISKA_ETIKETTER = frozenset({"#FLAGGA", "#PROGRAM", "#FORMAT", "#GEN", "#FNAMN"})


def _flush_abandoned_ver(
    sie: SIEFil,
    ver: Verifikation,
    ver_lineno: int,
    ver_raw: str,
    trans_list: list[tuple[int, str, Transaktion]],
    avbrottsorsak: str,
) -> None:
    """Generate tolkningsbehov for a VER block that was never closed with }."""
    sie.tolkningsbehov.append(Tolkningsbehov(
        radnummer=ver_lineno,
        råtext=ver_raw,
        etikett="#VER",
        anledning=f"verifikation aldrig avslutad med }} — {avbrottsorsak}",
        partiell_tolkning=f"serie={ver.serie}, vernr={ver.vernr}, verdatum={ver.verdatum}",
    ))
    for t_lineno, t_raw, trans in trans_list:
        sie.tolkningsbehov.append(Tolkningsbehov(
            radnummer=t_lineno,
            råtext=t_raw,
            etikett=f"#{trans.radtyp}",
            anledning="underpost till aldrig avslutad #VER, hoppas över i kaskad",
            kontext=f"underpost till #VER på rad {ver_lineno}",
            partiell_tolkning=f"kontonr={trans.kontonr}, belopp={trans.belopp}",
        ))


def parse_sie4(filepath: str | Path) -> SIEFil:
    """Read and parse a SIE4 file. Returns a populated SIEFil.

    Encoding: cp437 per spec §5.8, with windows-1252 fallback for files
    produced by non-compliant software.
    """
    data = Path(filepath).read_bytes()
    try:
        text = data.decode("cp437")
    except UnicodeDecodeError:
        text = data.decode("windows-1252")

    sie = SIEFil()
    current_ver: Verifikation | None = None
    current_ver_lineno: int | None = None       # rad där aktuell #VER påbörjades
    current_ver_raw: str | None = None          # råtext för aktuell #VER-rad
    current_ver_trans: list[tuple[int, str, Transaktion]] = []  # (lineno, raw, trans)
    in_ver_block = False
    broken_ver_rad: int | None = None           # radnummer för senaste ogiltiga #VER
    sedda_etiketter: set[str] = set()           # varje etikett som förekommit, oavsett om raden var giltig
    ksumma_oppen: bool = False
    ksumma_oppen_lineno: int | None = None
    ksumma_oppen_raw: str | None = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line == "{":
            in_ver_block = True
            continue

        if line == "}":
            if current_ver is not None:
                sie.verifikationer.append(current_ver)
            current_ver = None
            current_ver_lineno = None
            current_ver_raw = None
            current_ver_trans = []
            in_ver_block = False
            broken_ver_rad = None
            continue

        tokens = _tokenize(line)
        if not tokens:
            continue
        label = tokens[0]
        fields = tokens[1:]
        sedda_etiketter.add(label)

        # --- flaggpost ---
        if label == "#FLAGGA":
            flagga_val: int | None = None
            if fields:
                try:
                    flagga_val = int(fields[0])
                except ValueError:
                    pass
            if flagga_val in (0, 1):
                sie.flagga = flagga_val  # type: ignore[assignment]
            else:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#FLAGGA",
                    anledning="värde saknas eller är inte 0 eller 1",
                ))

        # --- identifikationsposter ---
        elif label == "#FORMAT":
            if not fields or fields[0] != "PC8":
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#FORMAT",
                    anledning="okänt #FORMAT-värde, encoding-antagandet kan vara fel",
                ))

        elif label == "#PROGRAM":
            if len(fields) < 2:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#PROGRAM",
                    anledning="saknar programnamn eller version",
                ))
            else:
                sie.program = fields[0]
                sie.program_version = fields[1]

        elif label == "#GEN":
            gen_datum = _parse_date(fields[0]) if fields else None
            if gen_datum is None:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#GEN",
                    anledning="datum saknas eller är ogiltigt",
                ))
            else:
                sie.genererad = gen_datum
                sie.genererad_sign = fields[1] if len(fields) > 1 else None

        elif label == "#FNAMN":
            sie.företagsnamn = fields[0] if fields else ""

        elif label == "#SIETYP":
            sietyp_val: int | None = None
            if fields:
                try:
                    sietyp_val = int(fields[0])
                except ValueError:
                    pass
            if sietyp_val is not None and sietyp_val in (1, 2, 3, 4):
                sie.sietyp = sietyp_val
            else:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#SIETYP",
                    anledning="typnr saknas eller är inte ett heltal 1–4",
                ))

        elif label == "#FTYP":
            if not fields:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#FTYP",
                    anledning="företagstyp saknas",
                ))
            else:
                sie.företagstyp = fields[0]

        elif label == "#FNR":
            if not fields:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#FNR",
                    anledning="företags-id saknas",
                ))
            else:
                sie.företagsid = fields[0]

        elif label == "#BKOD":
            if not fields:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#BKOD",
                    anledning="SNI-kod saknas",
                ))
            else:
                sie.sni_kod = fields[0]

        elif label == "#TAXAR":
            if not fields:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#TAXAR",
                    anledning="taxeringsår saknas",
                ))
            else:
                sie.taxeringsår = fields[0]

        elif label == "#KPTYP":
            if not fields or fields[0] not in _KPTYP_VÄRDEN:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#KPTYP",
                    anledning=f"okänd kontoplanstyp — tillåtna värden: {', '.join(sorted(_KPTYP_VÄRDEN))}",
                ))
            else:
                sie.kontoplanstyp = fields[0]  # type: ignore[assignment]

        elif label == "#VALUTA":
            if not fields:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#VALUTA",
                    anledning="valutakod saknas",
                ))
            else:
                sie.valuta = fields[0]

        elif label == "#PROSA":
            sie.prosa = fields[0] if fields else None

        elif label == "#RAR":
            if len(fields) < 3:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#RAR",
                    anledning="saknar ett eller flera obligatoriska fält (årsnr start slut)",
                ))
            else:
                arsnr_val: int | None = None
                try:
                    arsnr_val = int(fields[0])
                except ValueError:
                    pass
                start_val = _parse_date(fields[1])
                slut_val = _parse_date(fields[2])
                if arsnr_val is None or start_val is None or slut_val is None:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno,
                        råtext=raw_line,
                        etikett="#RAR",
                        anledning="ogiltigt värde i ett eller flera fält (årsnr, startdatum, slutdatum)",
                    ))
                else:
                    sie.räkenskapsår[arsnr_val] = Räkenskapsår(
                        årsnr=arsnr_val, start=start_val, slut=slut_val
                    )

        elif label == "#OMFATTN":
            omfattn_datum = _parse_date(fields[0]) if fields else None
            if omfattn_datum is None:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#OMFATTN",
                    anledning="datum saknas eller är ogiltigt",
                ))
            else:
                sie.omfattning = omfattn_datum

        elif label == "#ADRESS":
            sie.adress = Adress(
                kontakt=fields[0] if len(fields) > 0 else None,
                utdelningsadress=fields[1] if len(fields) > 1 else None,
                postadress=fields[2] if len(fields) > 2 else None,
                telefon=fields[3] if len(fields) > 3 else None,
            )

        elif label == "#ORGNR":
            if not fields:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#ORGNR",
                    anledning="organisationsnummer saknas",
                ))
            elif len(fields) == 2 and fields[0] != "" and fields[1] != "":
                # Tvetydig: 2 fält utan explicit platshållare — oklart om fält 2 är förvnr eller verknr
                sie.orgnr = fields[0]
                sie.förvaltningsnummer = fields[1]
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#ORGNR",
                    anledning="tvetydig #ORGNR-rad: 2 fält utan platshållare, "
                              "oklart om fält 2 är förvaltningsnummer eller verksamhetsnummer",
                    partiell_tolkning=f"orgnr={fields[0]}, gissade förvaltningsnummer={fields[1]}",
                ))
            else:
                sie.orgnr = fields[0]
                sie.förvaltningsnummer = fields[1] if len(fields) > 1 else None
                sie.verksamhetsnummer = fields[2] if len(fields) > 2 else None

        # --- kontoplan ---
        elif label == "#KONTO":
            if len(fields) < 2:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#KONTO",
                    anledning="saknar kontonr eller kontonamn",
                ))
            else:
                kontonr, namn = fields[0], fields[1]
                sie.konton[kontonr] = Konto(kontonr=kontonr, namn=namn)

        elif label == "#KTYP":
            if len(fields) < 2:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#KTYP",
                    anledning="saknar kontonr eller typ",
                ))
            elif fields[0] not in sie.konton:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#KTYP",
                    anledning=f"kontonr {fields[0]} finns inte i kontoplanen",
                ))
            elif fields[1] not in _KTYP_TYP_VÄRDEN:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#KTYP",
                    anledning=f"ogiltigt kontotypvärde {fields[1]!r} — tillåtna: T S K I",
                ))
            else:
                sie.konton[fields[0]].typ = fields[1]  # type: ignore[assignment]

        elif label == "#ENHET":
            if len(fields) < 2:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#ENHET",
                    anledning="saknar kontonr eller enhet",
                ))
            elif fields[0] not in sie.konton:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#ENHET",
                    anledning=f"kontonr {fields[0]} finns inte i kontoplanen",
                ))
            else:
                sie.konton[fields[0]].enhet = fields[1]

        elif label == "#SRU":
            if len(fields) < 2:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#SRU",
                    anledning="saknar kontonr eller SRU-kod",
                ))
            elif fields[0] not in sie.konton:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#SRU",
                    anledning=f"kontonr {fields[0]} finns inte i kontoplanen",
                ))
            else:
                sie.konton[fields[0]].sru_koder.append(fields[1])

        # --- dimensioner och objekt ---
        elif label == "#DIM":
            if len(fields) < 2:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#DIM",
                    anledning="saknar dimensionsnr eller namn",
                ))
            else:
                try:
                    dimnr = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno, råtext=raw_line, etikett="#DIM",
                        anledning=f"dimensionsnr {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    sie.dimensioner[dimnr] = Dimension(dimensionsnr=dimnr, namn=fields[1])

        elif label == "#UNDERDIM":
            if len(fields) < 3:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#UNDERDIM",
                    anledning="saknar dimensionsnr, namn eller superdimensionsnr",
                ))
            else:
                try:
                    dimnr = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno, råtext=raw_line, etikett="#UNDERDIM",
                        anledning=f"dimensionsnr {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    try:
                        supernr = int(fields[2])
                    except ValueError:
                        sie.tolkningsbehov.append(Tolkningsbehov(
                            radnummer=lineno, råtext=raw_line, etikett="#UNDERDIM",
                            anledning=f"superdimensionsnr {fields[2]!r} är inte ett heltal",
                        ))
                    else:
                        sie.dimensioner[dimnr] = Dimension(
                            dimensionsnr=dimnr, namn=fields[1], superdimension=supernr
                        )

        elif label == "#OBJEKT":
            if len(fields) < 3:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett="#OBJEKT",
                    anledning="saknar dimensionsnr, objektnr eller namn",
                ))
            else:
                try:
                    dimnr = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno, råtext=raw_line, etikett="#OBJEKT",
                        anledning=f"dimensionsnr {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    sie.objektregister[(dimnr, fields[1])] = Objekt(
                        dimensionsnr=dimnr, objektnr=fields[1], namn=fields[2]
                    )

        # --- saldoposter ---
        # Designbeslut 1: ingen kontoexistenskontroll — saldoposter kan förekomma
        # före motsvarande #KONTO-rad (single-pass), och spec kräver inte att konton
        # deklareras innan de refereras i saldoposter.
        # Designbeslut 2: {-prefixkontroll för objektlistor — vi kontrollerar att
        # fältet faktiskt börjar med "{" innan _parse_objlista anropas, för att
        # fånga förskjutna fält utan att råka tolka fri text som en tom lista.

        elif label in ("#IB", "#UB", "#RES"):
            _saldolista = {
                "#IB": sie.ingående_balanser,
                "#UB": sie.utgående_balanser,
                "#RES": sie.resultat,
            }[label]
            if len(fields) < 3:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett=label,
                    anledning="saknar ett eller flera obligatoriska fält (årsnr konto saldo)",
                ))
            else:
                try:
                    arsnr = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno, råtext=raw_line, etikett=label,
                        anledning=f"årsnr {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    try:
                        saldo = Decimal(fields[2])
                    except InvalidOperation:
                        sie.tolkningsbehov.append(Tolkningsbehov(
                            radnummer=lineno, råtext=raw_line, etikett=label,
                            anledning=f"saldo {fields[2]!r} är inte ett giltigt decimaltal",
                        ))
                    else:
                        kvant_str = fields[3] if len(fields) > 3 else ""
                        try:
                            kvantitet: Decimal | None = Decimal(kvant_str) if kvant_str else None
                        except InvalidOperation:
                            kvantitet = None
                        _saldolista.append(Saldopost(
                            årsnr=arsnr, kontonr=fields[1],
                            objektreferenser={}, saldo=saldo, kvantitet=kvantitet,
                        ))

        elif label in ("#OIB", "#OUB"):
            _objsaldolista = {
                "#OIB": sie.objekt_ingående_balanser,
                "#OUB": sie.objekt_utgående_balanser,
            }[label]
            if len(fields) < 4:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett=label,
                    anledning="saknar ett eller flera obligatoriska fält (årsnr konto {objlista} saldo)",
                ))
            elif not fields[2].startswith("{"):
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett=label,
                    anledning="objektlista saknas eller är felformaterad",
                ))
            else:
                try:
                    arsnr = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno, råtext=raw_line, etikett=label,
                        anledning=f"årsnr {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    try:
                        saldo = Decimal(fields[3])
                    except InvalidOperation:
                        sie.tolkningsbehov.append(Tolkningsbehov(
                            radnummer=lineno, råtext=raw_line, etikett=label,
                            anledning=f"saldo {fields[3]!r} är inte ett giltigt decimaltal",
                        ))
                    else:
                        kvant_str = fields[4] if len(fields) > 4 else ""
                        try:
                            kvantitet = Decimal(kvant_str) if kvant_str else None
                        except InvalidOperation:
                            kvantitet = None
                        _objsaldolista.append(Saldopost(
                            årsnr=arsnr, kontonr=fields[1],
                            objektreferenser=_parse_objlista(fields[2]),
                            saldo=saldo, kvantitet=kvantitet,
                        ))

        elif label in ("#PSALDO", "#PBUDGET"):
            _perslista = {
                "#PSALDO": sie.periodsaldon,
                "#PBUDGET": sie.periodbudgetar,
            }[label]
            if len(fields) < 5:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno, råtext=raw_line, etikett=label,
                    anledning="saknar ett eller flera obligatoriska fält (årsnr period konto {objlista} saldo)",
                ))
            else:
                try:
                    arsnr = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno, råtext=raw_line, etikett=label,
                        anledning=f"årsnr {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    if not _giltig_period(fields[1]):
                        sie.tolkningsbehov.append(Tolkningsbehov(
                            radnummer=lineno, råtext=raw_line, etikett=label,
                            anledning="period är inte ett giltigt ÅÅÅÅMM-värde",
                        ))
                    elif not fields[3].startswith("{"):
                        sie.tolkningsbehov.append(Tolkningsbehov(
                            radnummer=lineno, råtext=raw_line, etikett=label,
                            anledning="objektlista saknas eller är felformaterad",
                        ))
                    else:
                        try:
                            saldo = Decimal(fields[4])
                        except InvalidOperation:
                            sie.tolkningsbehov.append(Tolkningsbehov(
                                radnummer=lineno, råtext=raw_line, etikett=label,
                                anledning=f"saldo {fields[4]!r} är inte ett giltigt decimaltal",
                            ))
                        else:
                            kvant_str = fields[5] if len(fields) > 5 else ""
                            try:
                                kvantitet = Decimal(kvant_str) if kvant_str else None
                            except InvalidOperation:
                                kvantitet = None
                            _perslista.append(Periodsaldo(
                                årsnr=arsnr, period=fields[1], kontonr=fields[2],
                                objektreferenser=_parse_objlista(fields[3]),
                                saldo=saldo, kvantitet=kvantitet,
                            ))

        # --- #KSUMMA (Alternativ C: registrering + trunkeringsdetektering, ingen CRC-beräkning) ---
        elif label == "#KSUMMA":
            if not fields:
                # Öppnande signal
                if ksumma_oppen:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=ksumma_oppen_lineno,  # type: ignore[arg-type]
                        råtext=ksumma_oppen_raw or "",
                        etikett="#KSUMMA",
                        anledning="kontrollsummering påbörjades men avslutades aldrig innan en ny #KSUMMA-signal — filen kan vara trunkerad",
                    ))
                ksumma_oppen = True
                ksumma_oppen_lineno = lineno
                ksumma_oppen_raw = raw_line
            else:
                # Avslutande post med värde
                try:
                    ksumma_val = int(fields[0])
                except ValueError:
                    sie.tolkningsbehov.append(Tolkningsbehov(
                        radnummer=lineno,
                        råtext=raw_line,
                        etikett="#KSUMMA",
                        anledning=f"kontrollsummevärde {fields[0]!r} är inte ett heltal",
                    ))
                else:
                    if not ksumma_oppen:
                        sie.tolkningsbehov.append(Tolkningsbehov(
                            radnummer=lineno,
                            råtext=raw_line,
                            etikett="#KSUMMA",
                            anledning="#KSUMMA med värde utan föregående tom #KSUMMA-signal — avviker från specens tvåpost-mönster",
                        ))
                    else:
                        ksumma_oppen = False
                    sie.ksumma = ksumma_val

        # --- verifikation header ---
        elif label == "#VER":
            # En pågående verifikation utan avslutande } — flusha den
            if current_ver is not None:
                _flush_abandoned_ver(
                    sie, current_ver,
                    current_ver_lineno, current_ver_raw,  # type: ignore[arg-type]
                    current_ver_trans,
                    avbrottsorsak=f"ny #VER påbörjades på rad {lineno}",
                )
                current_ver = None
                current_ver_lineno = None
                current_ver_raw = None
                current_ver_trans = []
                in_ver_block = False

            verdatum = _parse_date(fields[2]) if len(fields) > 2 else None
            if verdatum is None:
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett="#VER",
                    anledning="verdatum saknas eller är ogiltigt",
                ))
                broken_ver_rad = lineno
            else:
                serie = fields[0] if len(fields) > 0 else None
                vernr = fields[1] if len(fields) > 1 else None
                vertext = fields[3] if len(fields) > 3 else None
                regdatum = _parse_date(fields[4]) if len(fields) > 4 else None
                sign = fields[5] if len(fields) > 5 else None
                current_ver = Verifikation(
                    serie=serie or None,
                    vernr=vernr or None,
                    verdatum=verdatum,
                    vertext=vertext or None,
                    regdatum=regdatum,
                    sign=sign,
                )
                current_ver_lineno = lineno
                current_ver_raw = raw_line
                current_ver_trans = []
                broken_ver_rad = None

        # --- transaktionsrad (underpost till #VER) ---
        elif label in _TRANS_LABELS:
            if in_ver_block and current_ver is not None:
                # giltig verifikation — tolka, lägg till, och spara i parallellista
                if len(fields) < 3:
                    continue
                kontonr = fields[0]
                objrefs = _parse_objlista(fields[1])
                try:
                    belopp = Decimal(fields[2])
                except InvalidOperation:
                    continue
                transdat = _parse_date(fields[3]) if len(fields) > 3 else None
                transtext = fields[4] if len(fields) > 4 else None
                kvant_str = fields[5] if len(fields) > 5 else ""
                sign = fields[6] if len(fields) > 6 else None
                radtyp: Literal["TRANS", "RTRANS", "BTRANS"] = label[1:]  # type: ignore[assignment]
                trans = Transaktion(
                    kontonr=kontonr,
                    objektreferenser=objrefs,
                    belopp=belopp,
                    transdat=transdat,
                    transtext=transtext,
                    kvantitet=Decimal(kvant_str) if kvant_str else None,
                    sign=sign,
                    radtyp=radtyp,
                )
                current_ver.transaktioner.append(trans)
                current_ver_trans.append((lineno, raw_line, trans))
            elif in_ver_block and broken_ver_rad is not None:
                # brutet block — kaskad till tolkningsbehov
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett=label,
                    anledning="underpost till ogiltig #VER, hoppas över i kaskad",
                    kontext=f"underpost till #VER på rad {broken_ver_rad}",
                ))
            else:
                # utanför alla block — explicit tolkningsbehov
                sie.tolkningsbehov.append(Tolkningsbehov(
                    radnummer=lineno,
                    råtext=raw_line,
                    etikett=label,
                    anledning="transaktionsrad utanför ett {}-block",
                ))

        # all other labels are silently ignored for now

    # EOF: om en verifikation aldrig stängdes med } flushes den till tolkningsbehov
    if current_ver is not None:
        _flush_abandoned_ver(
            sie, current_ver,
            current_ver_lineno, current_ver_raw,  # type: ignore[arg-type]
            current_ver_trans,
            avbrottsorsak="filen tog slut innan verifikationen avslutades",
        )

    # EOF: öppen #KSUMMA-signal utan avslutande post → trolig trunkering
    if ksumma_oppen:
        sie.tolkningsbehov.append(Tolkningsbehov(
            radnummer=ksumma_oppen_lineno,  # type: ignore[arg-type]
            råtext=ksumma_oppen_raw or "",
            etikett="#KSUMMA",
            anledning="kontrollsummering påbörjades men ingen avslutande #KSUMMA-post hittades innan filen tog slut — filen är troligen trunkerad (SIE-spec kap. 10.6)",
        ))

    # Completeness-kontroll: obligatoriska poster som saknas helt i filen
    for etikett in _ALLTID_OBLIGATORISKA_ETIKETTER:
        if etikett not in sedda_etiketter:
            sie.tolkningsbehov.append(Tolkningsbehov(
                radnummer=0,
                råtext="",
                etikett=etikett,
                anledning=f"obligatorisk post {etikett} saknas helt i filen",
            ))

    return sie
