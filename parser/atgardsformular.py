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


# --- BÖCKERNA ---

def _verifikat_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    import json
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
        "skriv_over_saldon": v.get("skriv_over_saldon", False),
        "tillat_obrukade_konton": v.get("tillat_obrukade_konton", False),
        "ignorera_varningsflaggor": v.get("ignorera_varningsflaggor", False),
        "invertera_tecken_pa_resultat": v.get("invertera_tecken_pa_resultat", False),
    }

def _sie4import_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    sokvag = v.get("sokvag", "")
    import os
    if not os.path.exists(sokvag):
        raise ValueError("Filen finns inte.")
        
    from sie_parser import parse_sie4
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
        Falt("skriv_over_saldon", "Skriv över saldon", "kryss", obligatoriskt=False),
        Falt("tillat_obrukade_konton", "Tillåt obrukade konton", "kryss", obligatoriskt=False),
        Falt("ignorera_varningsflaggor", "Ignorera varningsflaggor", "kryss", obligatoriskt=False),
        Falt("invertera_tecken_pa_resultat", "Invertera tecken på resultat", "kryss", obligatoriskt=False),
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
        "bankkonto": v.get("bankkonto", ""),
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
        "motivering": v.get("motivering", ""),
    }

def _makulering_sammanfattning(v: dict[str, Any]) -> list[list[str]]:
    return [["Fakturanummer", str(v.get("fakturanummer", ""))]]

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
        "nummer_eller_id": v.get("nummer_eller_id", ""),
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
        "nummer_eller_id": v.get("nummer_eller_id", ""),
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
        "leverantor": v.get("leverantor", ""),
        "fakturanummer": v.get("fakturanummer", ""),
        "datum": v.get("datum", ""),
        "forfallodatum": v.get("forfallodatum", ""),
        "totalbelopp": float(v.get("totalbelopp") or 0),
        "kreditflagga": v.get("kreditflagga", False),
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
        "bankkonto": v.get("bankkonto", ""),
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
        "motivering": v.get("motivering", ""),
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

ALLA_FORMULAR = [
    VERIFIKAT, SIE4IMPORT, 
    FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK, SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD,
    LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST,
    MASTERDATAANDRING, MASTERDATABORTTAGNING
]
