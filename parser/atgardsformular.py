import json
import os
from dataclasses import dataclass, field
from typing import Callable, Any
from utkast import GILTIGA_TYPER

@dataclass(frozen=True)
class Falt:
    nyckel: str
    etikett: str
    typ: str          # "text" | "tal" | "datum" | "kryss" | "val"
    obligatoriskt: bool = True
    alternativ: tuple[str, ...] = ()
    hjalptext: str | None = None

@dataclass(frozen=True)
class Atgardsformular:
    utkasttyp: str
    rubrik: str
    ikon: str
    falt: tuple[Falt, ...]
    bygg_nyttolast: Callable[[dict[str, Any]], dict[str, Any]]
    bygg_sammanfattning: Callable[[dict[str, Any]], list[list[str]]]
    varning: str | None = None
    egen_ritare: Callable[[Any], None] | None = None


# --- BÖCKERNA ---

def _verifikat_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    try:
        rader = json.loads(v.get("rader", "[]"))
    except json.JSONDecodeError:
        raise ValueError("Rader måste vara giltig JSON.")
        
    if not isinstance(rader, list):
        raise ValueError("Rader måste vara en JSON-lista.")
        
    debet = kredit = 0.0
    for rad in rader:
        if not isinstance(rad, dict):
            continue
        debet += float(rad.get("debet") or 0)
        kredit += float(rad.get("kredit") or 0)
        
    if abs(debet - kredit) > 0.005 or not rader:
        raise ValueError(f"Verifikatet balanserar inte. Debet: {debet:.2f}, Kredit: {kredit:.2f}")

    return {
        "beskrivning": v.get("beskrivning", ""),
        "transaktionsdatum": v.get("datum", ""),
        "verifikationsserie": v.get("serie", "A"),
        "rader": rader,
    }

def _verifikat_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Beskrivning", str(v.get("beskrivning", ""))]]

VERIFIKAT = Atgardsformular(
    utkasttyp="verifikat",
    rubrik="Nytt verifikat",
    ikon="⚖️",
    falt=(
        Falt("beskrivning", "Beskrivning", "text"),
        Falt("datum", "Datum", "datum"),
        Falt("serie", "Serie", "text", obligatoriskt=False),
        Falt("rader", "Rader (konto/debet/kredit/text)", "text", hjalptext="JSON-lista med rader"),
    ),
    bygg_nyttolast=_verifikat_nyttolast,
    bygg_sammanfattning=_verifikat_sammanfattning
)

def _sie4import_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "sokvag": v.get("sokvag", ""),
        "ingaende_balans": v.get("ingaende_balans", False),
        "kontonamn": v.get("kontonamn", False),
        "mappa_konton": v.get("mappa_konton", False),
        "arsavslut": v.get("arsavslut", False),
    }

def _sie4import_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    sokvag = v.get("sokvag", "")
    if not os.path.exists(sokvag):
        raise ValueError("Filen finns inte.")
        
    from sie4_parser import parse_sie4
    sie = parse_sie4(sokvag, tyst=True)
    if not sie.verifikationer and not sie.konton:
        raise ValueError("Filen verkar inte vara en SIE4-fil (saknar verifikationer och konton).")
        
    bolag = sie.fnamn or ""
    orgnr = sie.orgnr or ""
    return [
        ["Bolag", bolag],
        ["Orgnr", orgnr],
        ["Antal verifikationer", str(len(sie.verifikationer))],
        ["Antal konton", str(len(sie.konton))],
    ]

SIE4IMPORT = Atgardsformular(
    utkasttyp="sie4import",
    rubrik="SIE4-import",
    ikon="📥",
    falt=(
        Falt("sokvag", "Sökväg till SIE4-fil", "text"),
        Falt("ingaende_balans", "Ingående balans", "kryss", obligatoriskt=False),
        Falt("kontonamn", "Importera kontonamn", "kryss", obligatoriskt=False),
        Falt("mappa_konton", "Mappa konton", "kryss", obligatoriskt=False),
        Falt("arsavslut", "Årsavslut", "kryss", obligatoriskt=False),
    ),
    bygg_nyttolast=_sie4import_nyttolast,
    bygg_sammanfattning=_sie4import_sammanfattning,
    varning="Importen kan inte ångras."
)


# --- PENGAR IN ---

def _fakturautskick_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "fakturanummer": v.get("fakturanummer", ""),
        "amne": v.get("amne", ""),
        "meddelande": v.get("meddelande", ""),
    }

def _fakturautskick_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Fakturanummer", str(v.get("fakturanummer", ""))]]

FAKTURAUTSKICK = Atgardsformular(
    utkasttyp="fakturautskick",
    rubrik="Fakturautskick",
    ikon="✉️",
    falt=(
        Falt("fakturanummer", "Fakturanummer", "text"),
        Falt("amne", "Ämne", "text"),
        Falt("meddelande", "Meddelande", "text"),
    ),
    bygg_nyttolast=_fakturautskick_nyttolast,
    bygg_sammanfattning=_fakturautskick_sammanfattning,
    varning="Ett skickat mejl kan inte kallas tillbaka."
)

def _betalningspaminnelse_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    avgift = v.get("drojsmalsavgift")
    if avgift == "":
        avgift = None
    elif avgift is not None:
        avgift = float(avgift)
    return {
        "fakturanummer": v.get("fakturanummer", ""),
        "drojsmalsavgift": avgift,
        "meddelande": v.get("meddelande", ""),
    }

def _betalningspaminnelse_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Fakturanummer", str(v.get("fakturanummer", ""))]]

BETALNINGSPAMINNELSE = Atgardsformular(
    utkasttyp="betalningspaminnelse",
    rubrik="Betalningspåminnelse",
    ikon="⚠️",
    falt=(
        Falt("fakturanummer", "Fakturanummer", "text"),
        Falt("drojsmalsavgift", "Dröjsmålsavgift", "tal", obligatoriskt=False),
        Falt("meddelande", "Meddelande", "text", obligatoriskt=False),
    ),
    bygg_nyttolast=_betalningspaminnelse_nyttolast,
    bygg_sammanfattning=_betalningspaminnelse_sammanfattning,
    varning="Ett skickat mejl kan inte kallas tillbaka."
)

def _betalningsregistrering_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "fakturanummer": v.get("fakturanummer", ""),
        "belopp": float(v.get("belopp") or 0),
        "betaldatum": v.get("betaldatum", ""),
        "bankkonto_id": v.get("bankkonto_id", ""),
    }

def _betalningsregistrering_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Fakturanummer", str(v.get("fakturanummer", ""))]]

BETALNINGSREGISTRERING = Atgardsformular(
    utkasttyp="betalningsregistrering",
    rubrik="Betalningsregistrering",
    ikon="💰",
    falt=(
        Falt("fakturanummer", "Fakturanummer", "text"),
        Falt("belopp", "Belopp", "tal"),
        Falt("betaldatum", "Betaldatum", "datum"),
        Falt("bankkonto", "Bankkonto", "text"),
    ),
    bygg_nyttolast=_betalningsregistrering_nyttolast,
    bygg_sammanfattning=_betalningsregistrering_sammanfattning
)

def _makulering_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "fakturanummer": v.get("fakturanummer", ""),
    }

def _makulering_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    res = [["Fakturanummer", str(v.get("fakturanummer", ""))]]
    if str(v.get("motivering", "")).strip():
        res.append(["Motivering", str(v.get("motivering", "")).strip()])
    return res

MAKULERING = Atgardsformular(
    utkasttyp="makulering",
    rubrik="Makulering",
    ikon="❌",
    falt=(
        Falt("fakturanummer", "Fakturanummer", "text"),
        Falt("motivering", "Motivering", "text"),
    ),
    bygg_nyttolast=_makulering_nyttolast,
    bygg_sammanfattning=_makulering_sammanfattning,
    varning="Makuleringen kan inte ångras."
)

def _efakturautskick_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "fakturanummer": v.get("fakturanummer", ""),
    }

def _efakturautskick_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Fakturanummer", str(v.get("fakturanummer", ""))]]

EFAKTURAUTSKICK = Atgardsformular(
    utkasttyp="efakturautskick",
    rubrik="E-fakturautskick",
    ikon="🌩️",
    falt=(
        Falt("fakturanummer", "Fakturanummer", "text"),
    ),
    bygg_nyttolast=_efakturautskick_nyttolast,
    bygg_sammanfattning=_efakturautskick_sammanfattning,
    varning="Ett skickat mejl kan inte kallas tillbaka."
)

def _saljdokumentutskick_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "dokumenttyp": v.get("dokumenttyp", ""),
        "nummer": v.get("nummer", ""),
        "amne": v.get("amne", ""),
        "meddelande": v.get("meddelande", ""),
    }

def _saljdokumentutskick_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Dokument", str(v.get("nummer_eller_id", ""))]]

SALJDOKUMENTUTSKICK = Atgardsformular(
    utkasttyp="saljdokumentutskick",
    rubrik="Säljdokumentutskick",
    ikon="✉️",
    falt=(
        Falt("dokumenttyp", "Dokumenttyp", "val", alternativ=("offert", "order")),
        Falt("nummer_eller_id", "Nummer eller ID", "text"),
        Falt("amne", "Ämne", "text"),
        Falt("meddelande", "Meddelande", "text"),
    ),
    bygg_nyttolast=_saljdokumentutskick_nyttolast,
    bygg_sammanfattning=_saljdokumentutskick_sammanfattning,
    varning="Ett skickat mejl kan inte kallas tillbaka."
)

def _saljdokumentatgard_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "dokumenttyp": v.get("dokumenttyp", ""),
        "nummer": v.get("nummer", ""),
        "atgard": v.get("atgard", ""),
    }

def _saljdokumentatgard_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Dokument", str(v.get("nummer_eller_id", ""))]]

from spiris_adapter import _SALJDOKUMENTATGARDER
SALJDOKUMENTATGARD = Atgardsformular(
    utkasttyp="saljdokumentatgard",
    rubrik="Säljdokumentåtgärd",
    ikon="🔄",
    falt=(
        Falt("dokumenttyp", "Dokumenttyp", "val", alternativ=("offert", "order")),
        Falt("nummer_eller_id", "Nummer eller ID", "text"),
        Falt("atgard", "Åtgärd", "val", alternativ=tuple(sorted(set(k[1] for k in _SALJDOKUMENTATGARDER.keys())))),
    ),
    bygg_nyttolast=_saljdokumentatgard_nyttolast,
    bygg_sammanfattning=_saljdokumentatgard_sammanfattning,
    varning="Konverteringen kan inte ångras."
)

def _offertutkast_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "kundnamn": v.get("kundnamn", ""),
        "rader": v.get("rader", []),
        "offertdatum": v.get("offertdatum", ""),
        "forfallodatum": v.get("forfallodatum", ""),
        "var_referens": v.get("var_referens", ""),
        "leveransdatum": v.get("leveransdatum", ""),
        "valuta": v.get("valuta", "SEK"),
        "inkl_moms": v.get("inkl_moms", False),
        "kundreferens": v.get("kundreferens", ""),
    }

def _offertutkast_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Kundnamn", str(v.get("kundnamn", ""))]]

OFFERTUTKAST_FORMULAR = Atgardsformular(
    utkasttyp="offertutkast",
    rubrik="Offertutkast",
    ikon="🧾",
    falt=(
        Falt("kundnamn", "Kundnamn", "text"),
        Falt("offertdatum", "Offertdatum", "datum"),
        Falt("forfallodatum", "Förfallodatum", "datum"),
        Falt("rader", "Rader", "text"),
    ),
    bygg_nyttolast=_offertutkast_nyttolast,
    bygg_sammanfattning=_offertutkast_sammanfattning
)

# --- PENGAR UT ---

def _leverantorsfakturautkast_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    if not v.get("totalbelopp"):
        raise ValueError("Totalbelopp är obligatoriskt.")
    import json
    rader = []
    try:
        rader_str = v.get("rader", "[]")
        if rader_str.strip():
            rader = json.loads(rader_str)
    except json.JSONDecodeError:
        raise ValueError("Rader måste vara giltig JSON.")
        
    return {
        "leverantor_id": v.get("leverantor_id", ""),
        "fakturanummer": v.get("fakturanummer", ""),
        "fakturadatum": v.get("fakturadatum", ""),
        "forfallodatum": v.get("forfallodatum", ""),
        "totalbelopp": float(v.get("totalbelopp") or 0),
        "rader": rader,
    }

def _leverantorsfakturautkast_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Fakturanummer", str(v.get("fakturanummer", ""))]]

LEVERANTORSFAKTURAUTKAST = Atgardsformular(
    utkasttyp="leverantorsfakturautkast",
    rubrik="Leverantörsfakturautkast",
    ikon="🧾",
    falt=(
        Falt("leverantor", "Leverantör", "text", obligatoriskt=False),
        Falt("fakturanummer", "Fakturanummer", "text"),
        Falt("datum", "Datum", "datum"),
        Falt("forfallodatum", "Förfallodatum", "datum"),
        Falt("totalbelopp", "Totalbelopp", "tal"),
        Falt("kreditflagga", "Kreditfaktura", "kryss", obligatoriskt=False),
        Falt("rader", "Rader", "text", obligatoriskt=False),
    ),
    bygg_nyttolast=_leverantorsfakturautkast_nyttolast,
    bygg_sammanfattning=_leverantorsfakturautkast_sammanfattning
)

def _leverantorsbetalning_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "faktura": v.get("faktura", ""),
        "belopp": float(v.get("belopp") or 0),
        "betaldatum": v.get("betaldatum", ""),
        "bankkonto_id": v.get("bankkonto_id", ""),
    }

def _leverantorsbetalning_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Faktura", str(v.get("faktura", ""))]]

LEVERANTORSBETALNING = Atgardsformular(
    utkasttyp="leverantorsbetalning",
    rubrik="Leverantörsbetalning",
    ikon="💸",
    falt=(
        Falt("faktura", "Faktura (nummer eller ID)", "text"),
        Falt("belopp", "Belopp", "tal"),
        Falt("betaldatum", "Betaldatum", "datum"),
        Falt("bankkonto", "Bankkonto", "text"),
    ),
    bygg_nyttolast=_leverantorsbetalning_nyttolast,
    bygg_sammanfattning=_leverantorsbetalning_sammanfattning
)

def _attest_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "objekttyp": v.get("objekttyp", ""),
        "objekt": v.get("objekt", ""),
        "beslut": v.get("beslut", ""),
    }

def _attest_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Beslut", str(v.get("beslut", ""))]]

ATTEST = Atgardsformular(
    utkasttyp="attest",
    rubrik="Attest",
    ikon="✍️",
    falt=(
        Falt("objekttyp", "Objekttyp", "val", alternativ=("leverantorsfaktura", "annat")),
        Falt("objekt", "Objekt", "text"),
        Falt("beslut", "Beslut", "val", alternativ=("godkann", "avsla"), hjalptext="Ett avslag ändrar status. Vill du meddela någon får du skriva det i affärssystemet."),
    ),
    bygg_nyttolast=_attest_nyttolast,
    bygg_sammanfattning=_attest_sammanfattning,
    varning="Attest är ett ansvarstagande."
)


# --- REGISTER ---

def _masterdataandring_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    andringar = {}
    objekttyp = v.get("objekttyp", "")
    from spiris_adapter import _MASTERDATA
    if objekttyp in _MASTERDATA:
        _, falt_map = _MASTERDATA[objekttyp]
        for f in falt_map.keys():
            if f in v and str(v[f]).strip() != "":
                andringar[f] = v[f]
    return {
        "objekttyp": objekttyp,
        "objekt_id": v.get("objekt_id", ""),
        "andringar": andringar,
    }

def _masterdataandring_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Objekttyp", str(v.get("objekttyp", ""))]]

from spiris_adapter import _MASTERDATA
MASTERDATAANDRING = Atgardsformular(
    utkasttyp="masterdataandring",
    rubrik="Ändra Masterdata",
    ikon="✏️",
    falt=(
        Falt("objekttyp", "Objekttyp", "val", alternativ=tuple(_MASTERDATA.keys())),
        Falt("objekt_id", "Objekt-ID", "text"),
    ), # The rest is handled dynamically in render
    bygg_nyttolast=_masterdataandring_nyttolast,
    bygg_sammanfattning=_masterdataandring_sammanfattning
)

def _masterdataborttagning_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    from spiris_adapter import _BORTTAGBARA
    if v.get("objekttyp") not in _BORTTAGBARA:
        raise ValueError(f"{v.get('objekttyp')} går inte att ta bort, bara inaktiveras.")
    return {
        "objekttyp": v.get("objekttyp", ""),
        "objekt_id": v.get("objekt_id", ""),
    }

def _masterdataborttagning_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Objekttyp", str(v.get("objekttyp", ""))]]

from spiris_adapter import _BORTTAGBARA
MASTERDATABORTTAGNING = Atgardsformular(
    utkasttyp="masterdataborttagning",
    rubrik="Ta bort Masterdata",
    ikon="🗑️",
    falt=(
        Falt("objekttyp", "Objekttyp", "val", alternativ=tuple(_BORTTAGBARA), hjalptext="Artiklar och projekt saknar DELETE i Spiris och kan bara inaktiveras (ändra masterdata)."),
        Falt("objekt_id", "Objekt-ID", "text"),
        Falt("motivering", "Motivering", "text"),
    ),
    bygg_nyttolast=_masterdataborttagning_nyttolast,
    bygg_sammanfattning=_masterdataborttagning_sammanfattning,
    varning="Borttagningen kan inte ångras."
)

def _utkastandring_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    for k in ["utkasttyp", "utkast_id", "andringar"]:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    return {"utkasttyp": v["utkasttyp"], "utkast_id": v["utkast_id"], "andringar": v["andringar"]}

UTKASTANDRING = Atgardsformular(
    utkasttyp="utkastandring",
    rubrik="Ändra utkast",
    ikon="✏️",
    falt=(
        Falt("utkasttyp", "Utkasttyp", "text", True),
        Falt("utkast_id", "Utkast-ID", "text", True),
        Falt("andringar", "Ändringar (JSON)", "text", True),
    ),
    bygg_nyttolast=_utkastandring_nyttolast,
    bygg_sammanfattning=lambda v: [["Utkasttyp", str(v.get("utkasttyp", ""))]]
)

def _utkastborttagning_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    for k in ["utkasttyp", "utkast_id"]:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    return {"utkasttyp": v["utkasttyp"], "utkast_id": v["utkast_id"]}

UTKASTBORTTAGNING = Atgardsformular(
    utkasttyp="utkastborttagning",
    rubrik="Ta bort utkast",
    ikon="🗑️",
    falt=(
        Falt("utkasttyp", "Utkasttyp", "text", True),
        Falt("utkast_id", "Utkast-ID", "text", True),
    ),
    bygg_nyttolast=_utkastborttagning_nyttolast,
    bygg_sammanfattning=lambda v: [["Utkasttyp", str(v.get("utkasttyp", ""))]],
    varning="Borttagningen kan inte ångras."
)

def _utkastbokforing_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    for k in ["utkasttyp", "utkast_id"]:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    return {"utkasttyp": v["utkasttyp"], "utkast_id": v["utkast_id"]}

UTKASTBOKFORING = Atgardsformular(
    utkasttyp="utkastbokforing",
    rubrik="Bokför utkast",
    ikon="🔒",
    falt=(
        Falt("utkasttyp", "Utkasttyp", "text", True),
        Falt("utkast_id", "Utkast-ID", "text", True),
    ),
    bygg_nyttolast=_utkastbokforing_nyttolast,
    bygg_sammanfattning=lambda v: [["Utkasttyp", str(v.get("utkasttyp", ""))]],
    varning="Bokföringen är oåterkallelig."
)

def _periodisering_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    prefix = v.get("kopplingstyp", "")
    id_val = v.get("kopplings_id", "")
    rad_val = v.get("kopplingsrad", "")
    
    res = {
        "antal_perioder": v.get("antal_perioder", 0),
        "startdatum": v.get("startdatum", ""),
        "belopp": float(v.get("belopp") or 0),
        "konto": v.get("konto", ""),
        "VoucherId": id_val if prefix == "Voucher" else "",
        "VoucherRow": rad_val if prefix == "Voucher" else "",
        "SupplierInvoiceId": id_val if prefix == "SupplierInvoice" else "",
        "SupplierInvoiceRow": rad_val if prefix == "SupplierInvoice" else "",
        "SupplierInvoiceDraftId": id_val if prefix == "SupplierInvoiceDraft" else "",
        "SupplierInvoiceDraftRow": rad_val if prefix == "SupplierInvoiceDraft" else "",
    }
    return res

PERIODISERING = Atgardsformular(
    utkasttyp="periodisering",
    rubrik="Periodisera",
    ikon="📅",
    falt=(
        Falt("kopplingstyp", "Kopplingstyp", "text"),
        Falt("kopplings_id", "Kopplings-ID", "text"),
        Falt("kopplingsrad", "Kopplingsrad", "nummer"),
        Falt("antal_perioder", "Antal perioder", "nummer"),
        Falt("startdatum", "Startdatum", "datum"),
        Falt("belopp", "Belopp", "decimal"),
        Falt("konto", "Konto", "text"),
    ),
    bygg_nyttolast=_periodisering_nyttolast,
    bygg_sammanfattning=lambda v: [["Antal", str(v.get("antal_perioder", ""))]]
)

def _betalningsverifikat_nyttolast(v: dict) -> dict:
    try:
        rader = json.loads(v.get("rader", "[]"))
    except json.JSONDecodeError:
        raise ValueError("Rader måste vara giltig JSON.")
        
    if not isinstance(rader, list):
        raise ValueError("Rader måste vara en JSON-lista.")
        
    debet = kredit = 0.0
    for rad in rader:
        if not isinstance(rad, dict):
            continue
        debet += float(rad.get("debet") or 0)
        kredit += float(rad.get("kredit") or 0)
        
    if abs(debet - kredit) > 0.005 or not rader:
        raise ValueError(f"Verifikatet balanserar inte. Debet: {debet:.2f}, Kredit: {kredit:.2f}")

    return {
        "beskrivning": v.get("beskrivning", ""),
        "transaktionsdatum": v.get("datum", ""),
        "rader": rader,
    }

BETALNINGSVERIFIKAT = Atgardsformular(
    utkasttyp="betalningsverifikat",
    rubrik="Nytt betalningsverifikat",
    ikon="💸",
    falt=(
        Falt("beskrivning", "Beskrivning", "text"),
        Falt("datum", "Datum", "datum"),
        Falt("rader", "Rader (konto/debet/kredit/text)", "text", hjalptext="JSON-lista med rader"),
    ),
    bygg_nyttolast=_betalningsverifikat_nyttolast,
    bygg_sammanfattning=_verifikat_sammanfattning
)

def _ritare_kundfaktura(st: Any) -> None:
    import rum_render
    rum_render._rendera_fakturautkast_formular()

KUND_FORMULAR = Atgardsformular(
    utkasttyp="kund",
    rubrik="Skapa kund",
    ikon="👤",
    falt=(),
    bygg_nyttolast=lambda v: {},
    bygg_sammanfattning=lambda v: [["Namn", str(v.get("Name", v.get("kundnamn", "")))]],
    egen_ritare=lambda st: None,
)

def _kundfaktura_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    req = ["rader", "kundnamn", "forfallodatum", "fakturadatum"]
    for k in req:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    return {k: v[k] for k in req}

KUNDFAKTURA_FORMULAR = Atgardsformular(
    utkasttyp="kundfaktura",
    rubrik="Skapa kundfaktura",
    ikon="📄",
    falt=(),
    bygg_nyttolast=_kundfaktura_nyttolast,
    bygg_sammanfattning=lambda v: [
        ["Kundnamn", str(v.get("kundnamn", ""))],
        ["Fakturadatum", str(v.get("fakturadatum", ""))],
        ["Förfallodatum", str(v.get("forfallodatum", ""))]
    ],
    egen_ritare=_ritare_kundfaktura,
)


def _ritare_kvittning(st: Any) -> None:
    import rum_render
    rum_render._rendera_kvittning_formular(st)

def _kvittning_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "kreditfaktura_id": v.get("kreditfaktura_id", ""),
        "payload": {
            "DebitInvoiceIds": v.get("debetfakturor", []),
            "VoucherDate": v.get("verifikatdatum", "")
        }
    }

def _kvittning_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    debet_list = v.get("debetfakturor", [])
    if isinstance(debet_list, list):
        debet = ", ".join(map(str, debet_list))
    else:
        debet = str(debet_list)
    return [
        ["Kreditfaktura", str(v.get("kreditfaktura_id", ""))],
        ["Debetfakturor", debet]
    ]

KVITTNING = Atgardsformular(
    utkasttyp="kvittning",
    rubrik="Kvittning",
    ikon="💸",
    falt=(),
    bygg_nyttolast=_kvittning_nyttolast,
    bygg_sammanfattning=_kvittning_sammanfattning,
    varning="Kvittningen kan inte ångras.",
    egen_ritare=_ritare_kvittning,
)

def _ritare_underlagskoppling(st: Any) -> None:
    import rum_render
    rum_render._rendera_underlagskoppling_formular(st)

def _underlagskoppling_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    from spiris_adapter import bygg_underlagskopplingspayload
    underlag_id = v.get("underlag_id", "")
    dokument_id = v.get("dokument_id", "")
    dokument_typ = v.get("dokument_typ", "")
    return bygg_underlagskopplingspayload(underlag_id, dokument_id, dokument_typ)

def _underlagskoppling_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [
        ["Underlag", str(v.get("underlag_id", ""))],
        ["Kopplas till", f"{v.get('dokument_typ', '')} {v.get('dokument_id', '')}"]
    ]

UNDERLAGSKOPPLING = Atgardsformular(
    utkasttyp="underlagskoppling",
    rubrik="Koppla underlag",
    ikon="🔗",
    falt=(),
    bygg_nyttolast=_underlagskoppling_nyttolast,
    bygg_sammanfattning=_underlagskoppling_sammanfattning,
    egen_ritare=_ritare_underlagskoppling,
)

def _ritare_konto(st: Any) -> None:
    import rum_render
    rum_render._rendera_konto_formular(st)

def _konto_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    req = ["kontonr", "kontonamn", "rakenskapsar_id", "aktiv"]
    for k in req:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    res = {k: v[k] for k in req}
    for k in ["kontotyp", "momskod_id", "projekt_tillatet", "kostnadsstalle_tillatet", "sparrat_for_manuell_bokning"]:
        if k in v:
            res[k] = v[k]
    return res

def _konto_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [
        ["Kontonummer", str(v.get("kontonr", ""))],
        ["Kontonamn", str(v.get("kontonamn", ""))],
        ["Aktiv", "Ja" if v.get("aktiv") else "Nej"]
    ]

KONTO = Atgardsformular(
    utkasttyp="konto",
    rubrik="Nytt konto",
    ikon="➕",
    falt=(),
    bygg_nyttolast=_konto_nyttolast,
    bygg_sammanfattning=_konto_sammanfattning,
    egen_ritare=_ritare_konto,
)

def _ritare_kontoandring(st: Any) -> None:
    import rum_render
    rum_render._rendera_kontoandring_formular(st)

def _kontoandring_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    req = ["rakenskapsar_id", "kontonr", "nuvarande", "andringar"]
    for k in req:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    return {k: v[k] for k in req}

def _kontoandring_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [
        ["Kontonummer", str(v.get("kontonr", ""))],
        ["Ändringar", str(len(v.get("andringar", {}))) + " fält"]
    ]

KONTOANDRING = Atgardsformular(
    utkasttyp="kontoandring",
    rubrik="Ändra konto",
    ikon="✏️",
    falt=(),
    bygg_nyttolast=_kontoandring_nyttolast,
    bygg_sammanfattning=_kontoandring_sammanfattning,
    egen_ritare=_ritare_kontoandring,
)

def _ritare_periodiseringsandring(st: Any) -> None:
    import rum_render
    rum_render._rendera_periodiseringsandring_formular(st)

def _periodiseringsandring_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    return _periodisering_nyttolast(v)

def _periodiseringsandring_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [
        ["Nuvarande perioder", str(v.get("nuvarande_perioder", ""))],
        ["Nya perioder", str(v.get("antal_perioder", ""))],
        ["Nuvarande belopp", str(v.get("nuvarande_belopp", ""))],
        ["Nytt belopp", str(v.get("belopp", ""))]
    ]

PERIODISERINGSANDRING = Atgardsformular(
    utkasttyp="periodiseringsandring",
    rubrik="Ändra periodisering",
    ikon="✏️",
    falt=(),
    bygg_nyttolast=_periodiseringsandring_nyttolast,
    bygg_sammanfattning=_periodiseringsandring_sammanfattning,
    egen_ritare=_ritare_periodiseringsandring,
)

def _ritare_periodiseringsborttagning(st: Any) -> None:
    import rum_render
    rum_render._rendera_periodiseringsborttagning_formular(st)

def _periodiseringsborttagning_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    if "leverantorsfakturautkast_id" not in v:
        raise ValueError("Saknar obligatorisk nyckel: leverantorsfakturautkast_id")
    return {"leverantorsfakturautkast_id": v["leverantorsfakturautkast_id"]}

def _periodiseringsborttagning_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [
        ["Utkast", str(v.get("leverantorsfakturautkast_id", ""))],
        ["Antal perioder som försvinner", str(v.get("antal_perioder_som_forsvinner", ""))]
    ]

PERIODISERINGSBORTTAGNING = Atgardsformular(
    utkasttyp="periodiseringsborttagning",
    rubrik="Ta bort periodisering",
    ikon="🗑️",
    falt=(),
    bygg_nyttolast=_periodiseringsborttagning_nyttolast,
    bygg_sammanfattning=_periodiseringsborttagning_sammanfattning,
    varning="Tar bort ALLA periodiseringar på utkastet. Oåterkalleligt — det finns ingen väg tillbaka.",
    egen_ritare=_ritare_periodiseringsborttagning,
)

ALLA_FORMULAR = [
    BETALNINGSVERIFIKAT,
    VERIFIKAT, SIE4IMPORT, 
    FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK, SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD, OFFERTUTKAST_FORMULAR,
    LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST,
    MASTERDATAANDRING, MASTERDATABORTTAGNING,
    UTKASTANDRING, UTKASTBORTTAGNING, UTKASTBOKFORING,
    PERIODISERING,
    KUND_FORMULAR,
    KUNDFAKTURA_FORMULAR, KVITTNING, UNDERLAGSKOPPLING, KONTO, KONTOANDRING, PERIODISERINGSANDRING, PERIODISERINGSBORTTAGNING,
]
