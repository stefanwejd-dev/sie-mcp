"""snabbvyer — deterministiska ett-klicks-vyer för vanliga frågor.

**Varför de INTE går genom AI:n.** "Visa mina förfallna kundfakturor" är en
filtrering och en sortering. Att skicka den frågan till en språkmodell ger
latens, kostnad, dataegress till en AI-leverantör och risk för hallucinerade
siffror — utan en enda fördel. Snabbvyerna räknar lokalt och renderas
deterministiskt; AI:n behåller det den är bra på (varför-frågor, uppföljning,
resonemang).

En följd värd att känna till: **snabbvyerna fungerar utan AI-nyckel.**

Modulen är UI-fri och därmed testbar utan Streamlit-runtime — samma skiktning
som fpa_vy/fpa_dashboard. Den bygger `Snabbvyresultat`; `snabbvy_render.py`
ritar dem.

**Klartext är avsiktligt.** Sedan maskeringsgränsen flyttades (P0) håller appen
riktiga motpartsnamn, och vyerna visar dem. Maskeringen sker vid utflödet, inte
på skärmen — se `reskontra_tvatt.maskera_for_egress` och DATASKYDD §3.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from kalla_protokoll import Formaga
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fpa_motor import bygg_aldersanalys, bygg_paminnelseforslag
from formatering import Formateringsval, formatera_tal
from svarskontrakt import KolumnDef, TabellBlock
from stil import Harkomstmarke, HARKOMST_LOKAL, HARKOMST_KALLA

# Färgnivå för en sektion. "rod"/"gul" används av påminnelseförslaget; övriga
# vyer är neutrala.
Niva = Literal["neutral", "rod", "gul", "gron"]


@dataclass(frozen=True)
class Nyckeltal:
    etikett: str
    varde: str
    hjalptext: str | None = None


@dataclass(frozen=True)
class Sektion:
    """Ett avsnitt i en vy: rubrik, valfri förklaring och en tabell.

    `drill_typ` styr drill-down i renderaren: 'leverantor' respektive 'kund'
    g\u00f6r att anv\u00e4ndaren kan klicka sig ner i fakturaniv\u00e5n fr\u00e5n
    registertabellen.
    """

    rubrik: str
    tabell: TabellBlock | None = None
    niva: Niva = "neutral"
    beskrivning: str | None = None
    tomtext: str = "Inget att visa."
    drill_typ: str | None = None  # 'leverantor' | 'kund' | None
    dold_detalj: bool = False



@dataclass(frozen=True)
class Snabbvyresultat:
    rubrik: str
    harkomst: Harkomstmarke = HARKOMST_LOKAL
    nyckeltal: list[Nyckeltal] = field(default_factory=list)
    sektioner: list[Sektion] = field(default_factory=list)
    fotnot: str | None = None


@dataclass(frozen=True)
class Snabbvy:
    """En knapp i snabbvyfältet."""

    id: str
    etikett: str
    ikon: str
    bygg: Callable[["Vydata"], Snabbvyresultat]
    hjalptext: str | None = None
    kraver: frozenset = frozenset()


@dataclass
class Vydata:
    """Allt en vy kan behöva. Fält som saknas är None — varje vy ansvarar för
    att säga det tydligt i stället för att visa en tom tabell utan förklaring."""

    idag: date
    kundreskontra: list | None = None
    leverantorsreskontra: list | None = None
    kundbetalbeteende: dict[str, Decimal] | None = None
    formateringsval: Formateringsval = field(default_factory=Formateringsval)
    kontoplan: list[dict] | None = None
    kontosaldon: list | None = None
    verifikationer: list | None = None
    verifikatutkast: list[dict] | None = None
    momsoversikt: dict | None = None
    ingaende_balanser: list[dict] | None = None
    kontotransaktioner: list[dict] | None = None
    verifikationer_alla: list[dict] | None = None
    enskilt_verifikat: dict | None = None
    periodiseringar: list[dict] | None = None
    kontoplan_alla: list[dict] | None = None
    momsrapporter: list[dict] | None = None
    momskoder: list[dict] | None = None
    soktext: str = ""
    vasentlighet: Any = None
    kontotyp_avvikelser: list | None = None
    # Bank
    bankkonton: list[dict] | None = None
    avstamningslage: list[dict] | None = None
    bankhandelser: list[dict] | None = None
    bankkonto_id: str = ""
    # Register
    kunder: list[dict] | None = None
    leverantorer: list[dict] | None = None
    artiklar: list[dict] | None = None
    projekt: list[dict] | None = None
    kostnadsstallen: list[dict] | None = None
    referensdata: list[dict] | None = None
    vald_referenstyp: str = ""
    # Drill-down: fakturor per motpart (None = inte h\u00e4mtat \u00e4n)
    leverantorsfakturor: list[dict] | None = None
    kundfakturor: list[dict] | None = None
    prislistor: list[dict] | None = None
    rabattavtal: list[dict] | None = None
    etiketter: list[dict] | None = None
    anlaggningstillgangar: list[dict] | None = None
    foretagsinfo: dict | None = None
    anvandare: list[dict] | None = None
    valutakurs: dict | None = None
    kundreskontraposter: list[dict] | None = None
    underlag: list[dict] | None = None
    ordrar: list[dict] | None = None
    offerter: list[dict] | None = None
    offertutkast: list[dict] | None = None



def _kr(varde: Decimal | int | float, val: Formateringsval) -> str:
    return formatera_tal(varde, val) + " kr"


def _saknas(rubrik: str, vad: str) -> Snabbvyresultat:
    """Enhetligt svar när data inte hämtats. Aldrig en tom tabell utan orsak —
    användaren ska veta om det är tomt eller om inget är inläst."""
    return Snabbvyresultat(
        rubrik=rubrik,
        sektioner=[
            Sektion(
                rubrik=vad,
                beskrivning=f"{vad} har inte hämtats.",
                tomtext=f"{vad} saknas. Ladda om sidan eller kontrollera anslutningen.",
            )
        ],
    )


# --- ETAPP 1: Böckerna ---

def bygg_kontoplan(data: Vydata) -> Snabbvyresultat:
    if data.kontoplan is None:
        return _saknas("Kontoplan", "Kontoplan")
        
    antal_konton = len(data.kontoplan)
    antal_aktiva = sum(1 for k in data.kontoplan if k.get("aktivt", False))
    antal_utan_typ = sum(1 for k in data.kontoplan if k.get("kontotyp") is None)
    
    rader = []
    for k in data.kontoplan:
        kontotyp_str = k.get("kontotyp") if k.get("kontotyp") is not None else "—"
        rader.append({
            "kontonr": str(k.get("kontonr", "")),
            "kontonamn": str(k.get("kontonamn", "")),
            "kontotyp": str(kontotyp_str),
            "aktivt": "Ja" if k.get("aktivt", False) else "Nej"
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="kontonr", rubrik="Kontonr", typ="text"),
            KolumnDef(nyckel="kontonamn", rubrik="Kontonamn", typ="text"),
            KolumnDef(nyckel="kontotyp", rubrik="Kontotyp", typ="text"),
            KolumnDef(nyckel="aktivt", rubrik="Aktivt", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Kontoplan",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[
            Nyckeltal("Antal konton", str(antal_konton)),
            Nyckeltal("Antal aktiva", str(antal_aktiva)),
            Nyckeltal("Antal utan kontotyp", str(antal_utan_typ))
        ],
        sektioner=[
            Sektion(rubrik="Konton", tabell=tabell, tomtext="Inga konton hittades.")
        ]
    )


def bygg_kontosaldon(data: Vydata) -> Snabbvyresultat:
    if data.kontosaldon is None:
        return _saknas("Kontosaldon", "Kontosaldon")
        
    kontoplan_map = {str(k.get("kontonr")): str(k.get("kontonamn", "")) for k in data.kontoplan} if data.kontoplan else {}
    
    antal = len(data.kontosaldon)
    summa_tillgangar = Decimal("0")
    summa_skulder = Decimal("0")
    
    rader = []
    for s in data.kontosaldon:
        knr = str(getattr(s, "kontonr", getattr(s, "konto", "")))
        saldo = getattr(s, "saldo", Decimal("0"))
        
        if knr.startswith("1"):
            summa_tillgangar += saldo
        elif knr.startswith("2"):
            summa_skulder += saldo
            
        rader.append({
            "kontonr": knr,
            "kontonamn": kontoplan_map.get(knr, ""),
            "saldo": _kr(saldo, data.formateringsval)
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="kontonr", rubrik="Kontonr", typ="text"),
            KolumnDef(nyckel="kontonamn", rubrik="Kontonamn", typ="text"),
            KolumnDef(nyckel="saldo", rubrik="Saldo", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Kontosaldon",
        harkomst=HARKOMST_LOKAL,
        nyckeltal=[
            Nyckeltal("Antal konton med saldo", str(antal)),
            Nyckeltal("Summa tillgångar", _kr(summa_tillgangar, data.formateringsval)),
            Nyckeltal("Summa skulder/EK", _kr(summa_skulder, data.formateringsval))
        ],
        sektioner=[
            Sektion(rubrik="Saldon", tabell=tabell if antal > 0 else None, tomtext="Inga saldon hittades.")
        ]
    )


def bygg_verifikatsokning(data: Vydata) -> Snabbvyresultat:
    if data.verifikationer is None:
        return _saknas("Verifikatsökning", "Verifikationer")
        
    traffar = []
    soktext = data.soktext.lower() if data.soktext else ""
    
    if not soktext:
        # Tom söktext -> 20 senaste
        traffar = sorted(data.verifikationer, key=lambda v: getattr(v, "verdatum", date.today()), reverse=True)[:20]
        beskrivning = "Visar de 20 senaste verifikationerna."
    else:
        for v in data.verifikationer:
            match_found = False
            if soktext in (getattr(v, "vertext", "") or "").lower():
                match_found = True
            else:
                for r in getattr(v, "transaktioner", []):
                    if soktext in (getattr(r, "transtext", "") or "").lower():
                        match_found = True
                        break
            if match_found:
                traffar.append(v)
        beskrivning = None
        
    rader = []
    for v in traffar:
        summa_debet = sum(getattr(r, "belopp", Decimal("0")) for r in getattr(v, "transaktioner", []) if getattr(r, "belopp", Decimal("0")) > 0)
        rader.append({
            "serie": str(getattr(v, "serie", "") or ""),
            "vernr": str(getattr(v, "vernr", "") or ""),
            "verdatum": str(getattr(v, "verdatum", "") or ""),
            "vertext": str(getattr(v, "vertext", "") or ""),
            "summa": _kr(summa_debet, data.formateringsval)
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="serie", rubrik="Serie", typ="text"),
            KolumnDef(nyckel="vernr", rubrik="Vernr", typ="text"),
            KolumnDef(nyckel="verdatum", rubrik="Datum", typ="datum"),
            KolumnDef(nyckel="vertext", rubrik="Vertext", typ="text"),
            KolumnDef(nyckel="summa", rubrik="Summa", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Verifikatsökning",
        harkomst=HARKOMST_LOKAL,
        nyckeltal=[
            Nyckeltal("Antal träffar", str(len(traffar))),
            Nyckeltal("Antal genomsökta verifikationer", str(len(data.verifikationer)))
        ],
        sektioner=[
            Sektion(
                rubrik="Resultat", 
                tabell=tabell if rader else None, 
                tomtext="Hittade inga verifikationer som matchar sökningen.",
                beskrivning=beskrivning
            )
        ]
    )


def bygg_momsoversikt_vy(data: Vydata) -> Snabbvyresultat:
    if data.momsoversikt is None:
        return _saknas("Momsöversikt (beräknad ur kontosaldon)", "Momsöversikt")
        
    poster = data.momsoversikt.get("poster", {})
    utgaende = poster.get("utgaende_moms", Decimal("0"))
    ingaende = poster.get("ingaende_moms", Decimal("0"))
    netto = poster.get("att_betala", Decimal("0"))
    
    rader = []
    for k in data.momsoversikt.get("konton", []):
        rader.append({
            "kontonr": str(k.get("kontonr", "")),
            "kontonamn": str(k.get("kontonamn", "")),
            "saldo": _kr(k.get("saldo", Decimal("0")), data.formateringsval)
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="kontonr", rubrik="Kontonr", typ="text"),
            KolumnDef(nyckel="kontonamn", rubrik="Kontonamn", typ="text"),
            KolumnDef(nyckel="saldo", rubrik="Saldo", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Momsöversikt (beräknad ur kontosaldon)",
        harkomst=HARKOMST_LOKAL,
        nyckeltal=[
            Nyckeltal("Utgående moms", _kr(utgaende, data.formateringsval)),
            Nyckeltal("Ingående moms", _kr(ingaende, data.formateringsval)),
            Nyckeltal("Att betala/få tillbaka", _kr(netto, data.formateringsval))
        ],
        fotnot="Detta är inte en momsdeklaration. Inlämnade deklarationer visas separat.",
        sektioner=[
            Sektion(rubrik="Momskonton", tabell=tabell if rader else None, tomtext="Inga momskonton med saldo hittades.")
        ]
    )


def bygg_verifikatutkast(data: Vydata) -> Snabbvyresultat:
    if data.verifikatutkast is None:
        return _saknas("Verifikatutkast", "Verifikatutkast")
        
    antal = len(data.verifikatutkast)
    summa_debet = Decimal("0")
    
    rader = []
    for u in data.verifikatutkast:
        u_rader = u.get("rader", [])
        debet = sum(Decimal(str(r.get("belopp", 0))) for r in u_rader if Decimal(str(r.get("belopp", 0))) > 0)
        summa_debet += debet
        
        rader.append({
            "verdatum": str(u.get("verdatum", "")),
            "serie": str(u.get("serie", "")),
            "vertext": str(u.get("vertext", "")),
            "rader": str(len(u_rader)),
            "summa": _kr(debet, data.formateringsval)
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="verdatum", rubrik="Datum", typ="datum"),
            KolumnDef(nyckel="serie", rubrik="Serie", typ="text"),
            KolumnDef(nyckel="vertext", rubrik="Vertext", typ="text"),
            KolumnDef(nyckel="rader", rubrik="Rader", typ="text"),
            KolumnDef(nyckel="summa", rubrik="Summa", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Verifikatutkast",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[
            Nyckeltal("Antal utkast", str(antal)),
            Nyckeltal("Summa debet", _kr(summa_debet, data.formateringsval))
        ],
        sektioner=[
            Sektion(
                rubrik="Väntande utkast i affärssystemet", 
                tabell=tabell if rader else None, 
                tomtext="Inga utkast hittades.",
                beskrivning="Utkasten påverkar inte räkenskaperna förrän du bokför dem i affärssystemet."
            )
        ]
    )




# --- Vy: Väsentlighet ---
def bygg_vasentlighet(data: Vydata) -> Snabbvyresultat:
    if data.vasentlighet is None:
        return _saknas("Väsentlighet", "Väsentlighetsdata")
        
    v = data.vasentlighet
    return Snabbvyresultat(
        rubrik="Väsentlighet",
        nyckeltal=[
            Nyckeltal("Omsättning", _kr(v.omsattning, data.formateringsval)),
            Nyckeltal("Resultat", _kr(v.resultat, data.formateringsval)),
            Nyckeltal("Balansomslutning", _kr(v.balansomslutning, data.formateringsval)),
            Nyckeltal("Eget kapital", _kr(v.eget_kapital, data.formateringsval)),
        ],
        sektioner=[
            Sektion(
                rubrik="Om beräkningen",
                beskrivning="Väsentlighetstalen är beräknade på SIE-filen och används som utgångspunkt för revision och analys."
            )
        ]
    )

def bygg_kontotyp_avvikelser(data: Vydata) -> Snabbvyresultat:
    if data.kontotyp_avvikelser is None:
        return _saknas("Kontotypavvikelser", "Data för kontotypavvikelser")
        
    rader = []
    for a in data.kontotyp_avvikelser:
        rader.append({
            "konto": a.kontonr,
            "namn": getattr(a, "kontonamn", ""),
            "forvantad": a.forvantad_typ,
            "angiven": a.angiven_typ,
            "motivering": a.motivering,
        })
        
    tomtext = "Inga avvikelser hittades."
    if data.kontoplan and all(k.get("kontotyp") is None for k in data.kontoplan):
        tomtext = "Kontotyper saknas i underlaget — avvikelser kan inte bedömas."
        
    return Snabbvyresultat(
        rubrik="Kontotypavvikelser",
        sektioner=[
            Sektion(
                rubrik="Avvikelser",
                beskrivning="Konton vars klassificering verkar avvika från standard." if rader else tomtext,
                tabell=TabellBlock(
                    rubrik=None,
                    kolumner=[
                        KolumnDef(nyckel="konto", rubrik="Konto", typ="text"),
                        KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
                        KolumnDef(nyckel="forvantad", rubrik="Förväntad", typ="text"),
                        KolumnDef(nyckel="angiven", rubrik="Angiven", typ="text"),
                        KolumnDef(nyckel="motivering", rubrik="Motivering", typ="text"),
                    ],
                    rader=rader
                ) if rader else None
            )
        ]
    )

def bygg_ingaende_balanser(data: Vydata) -> Snabbvyresultat:
    if data.ingaende_balanser is None:
        return _saknas("Ingående balanser", "Data")
    rader = []
    for b in data.ingaende_balanser:
        rader.append({
            "kontonr": b.get("kontonr", ""),
            "kontonamn": b.get("kontonamn", ""),
            "saldo": _kr(b.get("saldo", Decimal("0")), data.formateringsval)
        })
    return Snabbvyresultat(
        rubrik="Ingående balanser",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Saldon",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="kontonr", rubrik="Konto", typ="text"), KolumnDef(nyckel="kontonamn", rubrik="Namn", typ="text"), KolumnDef(nyckel="saldo", rubrik="Saldo", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Inga ingående balanser."
        )]
    )

def bygg_kontotransaktioner(data: Vydata) -> Snabbvyresultat:
    if data.kontotransaktioner is None:
        return _saknas("Kontotransaktioner", "Välj ett konto för att visa dess transaktioner.")
    rader = []
    for t in data.kontotransaktioner:
        rader.append({
            "plats": t.get("plats", ""),
            "datum": t.get("verdatum", ""),
            "text": t.get("transtext", ""),
            "belopp": _kr(t.get("belopp", Decimal("0")), data.formateringsval)
        })
    return Snabbvyresultat(
        rubrik="Kontotransaktioner",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Transaktioner",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="plats", rubrik="Verifikat", typ="text"), KolumnDef(nyckel="datum", rubrik="Datum", typ="text"), KolumnDef(nyckel="text", rubrik="Text", typ="text"), KolumnDef(nyckel="belopp", rubrik="Belopp", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Inga transaktioner hittades."
        )]
    )

def bygg_verifikationer_alla(data: Vydata) -> Snabbvyresultat:
    if data.verifikationer_alla is None:
        return _saknas("Verifikationer (alla år)", "Data")
    rader = []
    for v in data.verifikationer_alla:
        rader.append({
            "serie": v.get("serie", ""),
            "nr": str(v.get("vernr", "")),
            "datum": str(v.get("verdatum", "")),
            "text": v.get("vertext", ""),
            "reg": str(v.get("regdatum", "")),
            "rader": str(len(v.get("rader", [])))
        })
    return Snabbvyresultat(
        rubrik="Verifikationer (alla år)",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Verifikationer",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="serie", rubrik="Serie", typ="text"), KolumnDef(nyckel="nr", rubrik="Nr", typ="text"), KolumnDef(nyckel="datum", rubrik="Datum", typ="text"), KolumnDef(nyckel="text", rubrik="Text", typ="text"), KolumnDef(nyckel="reg", rubrik="Reg.datum", typ="text"), KolumnDef(nyckel="rader", rubrik="Rader", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Inga verifikationer hittades."
        )]
    )

def bygg_enskilt_verifikat(data: Vydata) -> Snabbvyresultat:
    if data.enskilt_verifikat is None:
        return _saknas("Enskilt verifikat", "Sök eller välj ett verifikat för att visa detaljer.")
    v = data.enskilt_verifikat
    rader = []
    for t in v.get("rader", []):
        rader.append({
            "konto": t.get("kontonr", ""),
            "text": t.get("transtext", ""),
            "belopp": _kr(t.get("belopp", Decimal("0")), data.formateringsval)
        })
    return Snabbvyresultat(
        rubrik=f"Verifikat {v.get('serie')} {v.get('vernr')}",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik=f"{v.get('verdatum')} - {v.get('vertext')}",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="konto", rubrik="Konto", typ="text"), KolumnDef(nyckel="text", rubrik="Text", typ="text"), KolumnDef(nyckel="belopp", rubrik="Belopp", typ="text")],
                rader=rader
            ) if rader else None
        )]
    )

def bygg_periodiseringar(data: Vydata) -> Snabbvyresultat:
    if data.periodiseringar is None:
        return _saknas("Periodiseringar", "Data")
    rader = []
    for p in data.periodiseringar:
        rader.append({
            "konto": p.get("kontonr", ""),
            "start": p.get("startdatum", ""),
            "perioder": str(p.get("antal_perioder", 0)),
            "belopp": _kr(p.get("belopp", Decimal("0")), data.formateringsval),
            "kalla": p.get("kall_id", "")
        })
    return Snabbvyresultat(
        rubrik="Periodiseringar",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Upplagda periodiseringar",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="konto", rubrik="Konto", typ="text"), KolumnDef(nyckel="start", rubrik="Start", typ="text"), KolumnDef(nyckel="perioder", rubrik="Månader", typ="text"), KolumnDef(nyckel="belopp", rubrik="Månadsbelopp", typ="text"), KolumnDef(nyckel="kalla", rubrik="Källa", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Inga periodiseringar hittades."
        )]
    )

def bygg_kontoplan_alla(data: Vydata) -> Snabbvyresultat:
    if data.kontoplan_alla is None:
        return _saknas("Kontoplan (alla år)", "Data")
    rader = []
    for k in data.kontoplan_alla:
        rader.append({
            "ar": k.get("rakenskapsar_id", ""),
            "konto": k.get("kontonr", ""),
            "namn": k.get("kontonamn", ""),
            "typ": k.get("kontotypstext", ""),
            "moms": k.get("momskod_id", "")
        })
    return Snabbvyresultat(
        rubrik="Kontoplan (alla år)",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Konton",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="ar", rubrik="År ID", typ="text"), KolumnDef(nyckel="konto", rubrik="Konto", typ="text"), KolumnDef(nyckel="namn", rubrik="Namn", typ="text"), KolumnDef(nyckel="typ", rubrik="Typ", typ="text"), KolumnDef(nyckel="moms", rubrik="Moms", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Kontoplanen var tom."
        )]
    )

def bygg_momsrapporter(data: Vydata) -> Snabbvyresultat:
    if data.momsrapporter is None:
        return _saknas("Momsrapporter", "Data")
    rader = []
    for r in data.momsrapporter:
        rader.append({
            "id": str(r.get("id", "")),
            "period": f"{r.get('from_datum')} - {r.get('tom_datum')}",
            "status": r.get("status", "")
        })
    return Snabbvyresultat(
        rubrik="Momsrapporter",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Rapporter i Spiris",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="id", rubrik="ID", typ="text"), KolumnDef(nyckel="period", rubrik="Period", typ="text"), KolumnDef(nyckel="status", rubrik="Status", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Inga momsrapporter hittades."
        )]
    )

def bygg_momskoder(data: Vydata) -> Snabbvyresultat:
    if data.momskoder is None:
        return _saknas("Momskoder", "Data")
    rader = []
    for m in data.momskoder:
        rader.append({
            "kod": m.get("kod", ""),
            "namn": m.get("namn", ""),
            "procent": str(m.get("momssats_procent", 0))
        })
    return Snabbvyresultat(
        rubrik="Momskoder",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Tillgängliga koder",
            tabell=TabellBlock(
                kolumner=[KolumnDef(nyckel="kod", rubrik="Kod", typ="text"), KolumnDef(nyckel="namn", rubrik="Namn", typ="text"), KolumnDef(nyckel="procent", rubrik="Sats %", typ="text")],
                rader=rader
            ) if rader else None,
            tomtext="Inga momskoder hittades."
        )]
    )

def bygg_underlag(data: Vydata) -> Snabbvyresultat:
    if data.underlag is None:
        return _saknas("Underlag", "Underlag")
    rader = []
    for u in data.underlag:
        rader.append({
            "id": str(u.get("id", "")),
            "beskrivning": str(u.get("beskrivning", "")),
            "status": str(u.get("status", "")),
        })
    return Snabbvyresultat(
        rubrik="Underlag",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Alla underlag",
            tabell=TabellBlock(
                kolumner=[
                    KolumnDef(nyckel="id", rubrik="ID", typ="text"),
                    KolumnDef(nyckel="beskrivning", rubrik="Beskrivning", typ="text"),
                    KolumnDef(nyckel="status", rubrik="Status", typ="text")
                ],
                rader=rader
            ) if rader else None,
            tomtext="Inga underlag hittades."
        )]
    )

SNABBVYER_BOCKERNA = [
    Snabbvy("vasentlighet", "Väsentlighet", "📏", bygg_vasentlighet),
    Snabbvy("kontotyp_avvikelser", "Kontotypavvikelser", "⚠️", bygg_kontotyp_avvikelser),
    Snabbvy("kontoplan", "Kontoplan", "📑", bygg_kontoplan),
    Snabbvy("kontosaldon", "Kontosaldon", "⚖️", bygg_kontosaldon),
    Snabbvy("verifikatsokning", "Verifikatsökning", "🔍", bygg_verifikatsokning),
    Snabbvy("momsoversikt", "Momsöversikt", "💰", bygg_momsoversikt_vy),
    Snabbvy("verifikatutkast", "Verifikatutkast i Spiris", "📝", bygg_verifikatutkast),
    Snabbvy("ingaende_balanser", "Ingående balanser", "🧾", bygg_ingaende_balanser),
    Snabbvy("kontotransaktioner", "Kontotransaktioner", "📝", bygg_kontotransaktioner),
    Snabbvy("verifikationer_alla", "Verifikationer (alla år)", "📚", bygg_verifikationer_alla),
    Snabbvy("enskilt_verifikat", "Enskilt verifikat", "🔍", bygg_enskilt_verifikat),
    Snabbvy("periodiseringar", "Periodiseringar", "📅", bygg_periodiseringar),
    Snabbvy("kontoplan_alla", "Kontoplan (alla år)", "📑", bygg_kontoplan_alla),
    Snabbvy("momsrapporter", "Momsrapporter", "📈", bygg_momsrapporter),
    Snabbvy("momskoder", "Momskoder", "⚙️", bygg_momskoder),
    Snabbvy("underlag", "Underlag", "📎", bygg_underlag),
]



def bygg_order(data: Vydata) -> Snabbvyresultat:
    if data.ordrar is None:
        return _saknas("Ordrar", "Ordrar")
    rader = []
    for o in data.ordrar:
        rader.append({
            "id": str(o.get("id", o.get("Id", ""))),
            "kund": str(o.get("kundnamn", o.get("CustomerName", ""))),
            "status": str(o.get("status", "")),
            "belopp": _kr(Decimal(str(o.get("totalbelopp", o.get("Total", 0)))), data.formateringsval)
        })
    return Snabbvyresultat(
        rubrik="Ordrar",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Ordrar i Spiris",
            tabell=TabellBlock(
                kolumner=[
                    KolumnDef(nyckel="id", rubrik="ID", typ="text"),
                    KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
                    KolumnDef(nyckel="status", rubrik="Status", typ="text"),
                    KolumnDef(nyckel="belopp", rubrik="Belopp", typ="text")
                ],
                rader=rader
            ) if rader else None,
            tomtext="Inga ordrar hittades."
        )]
    )

def bygg_offerter(data: Vydata) -> Snabbvyresultat:
    if data.offerter is None:
        return _saknas("Offerter", "Offerter")
    rader = []
    for o in data.offerter:
        rader.append({
            "id": str(o.get("id", o.get("Id", ""))),
            "kund": str(o.get("kundnamn", o.get("CustomerName", ""))),
            "status": str(o.get("status", "")),
            "belopp": _kr(Decimal(str(o.get("totalbelopp", o.get("Total", 0)))), data.formateringsval)
        })
    return Snabbvyresultat(
        rubrik="Offerter",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Offerter i Spiris",
            tabell=TabellBlock(
                kolumner=[
                    KolumnDef(nyckel="id", rubrik="ID", typ="text"),
                    KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
                    KolumnDef(nyckel="status", rubrik="Status", typ="text"),
                    KolumnDef(nyckel="belopp", rubrik="Belopp", typ="text")
                ],
                rader=rader
            ) if rader else None,
            tomtext="Inga offerter hittades."
        )]
    )

def bygg_offertutkast(data: Vydata) -> Snabbvyresultat:
    if data.offertutkast is None:
        return _saknas("Offertutkast", "Offertutkast")
    rader = []
    for o in data.offertutkast:
        rader.append({
            "id": str(o.get("id", o.get("Id", ""))),
            "kund": str(o.get("kundnamn", o.get("CustomerName", ""))),
            "belopp": _kr(Decimal(str(o.get("totalbelopp", o.get("Total", 0)))), data.formateringsval)
        })
    return Snabbvyresultat(
        rubrik="Offertutkast",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(
            rubrik="Offertutkast i Spiris",
            tabell=TabellBlock(
                kolumner=[
                    KolumnDef(nyckel="id", rubrik="ID", typ="text"),
                    KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
                    KolumnDef(nyckel="belopp", rubrik="Belopp", typ="text")
                ],
                rader=rader
            ) if rader else None,
            tomtext="Inga offertutkast hittades."
        )]
    )

SNABBVYER_SALJDOKUMENT = [
    Snabbvy("order", "Ordrar", "📦", bygg_order),
    Snabbvy("offerter", "Offerter", "📄", bygg_offerter),
    Snabbvy("offertutkast", "Offertutkast", "📝", bygg_offertutkast),
]


# --- Vy: utestående kundfakturor -------------------------------------------


def bygg_utestaende_kundfakturor(data: Vydata) -> Snabbvyresultat:
    if data.kundreskontra is None:
        return _saknas("Utestående kundfakturor", "Kundreskontran")

    poster = sorted(
        data.kundreskontra,
        key=lambda p: (p.forfallodatum or date.max),
    )
    total = sum((abs(p.belopp) for p in poster), Decimal("0"))
    forfallna = [
        p for p in poster
        if p.forfallodatum is not None and (data.idag - p.forfallodatum).days > 0
    ]

    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
            KolumnDef(nyckel="forfallodatum", rubrik="Förfaller", typ="datum"),
            KolumnDef(nyckel="dagar", rubrik="Dagar kvar", typ="text"),
            KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
        ],
        rader=[
            {
                "kund": p.kund,
                "forfallodatum": p.forfallodatum.isoformat() if p.forfallodatum else "—",
                "dagar": (
                    str((p.forfallodatum - data.idag).days)
                    if p.forfallodatum and p.forfallodatum >= data.idag
                    else (f"−{(data.idag - p.forfallodatum).days}" if p.forfallodatum else "—")
                ),
                "belopp": abs(p.belopp),
            }
            for p in poster
        ],
        summa_rad={"kund": "Summa", "belopp": total},
    )

    return Snabbvyresultat(
        rubrik="Utestående kundfakturor",
        nyckeltal=[
            Nyckeltal("Totalt utestående", f"{_kr(total, data.formateringsval)}"),
            Nyckeltal("Antal fakturor", str(len(poster))),
            Nyckeltal(
                "Varav förfallet",
                f"{_kr(sum((abs(p.belopp) for p in forfallna), Decimal('0')), data.formateringsval)}",
                f"{len(forfallna)} st",
            ),
        ],
        sektioner=[Sektion(rubrik="Alla öppna poster", tabell=tabell)],
    )


# --- Vy: förfallna ----------------------------------------------------------


def bygg_forfallna_kundfakturor(data: Vydata) -> Snabbvyresultat:
    if data.kundreskontra is None:
        return _saknas("Förfallna kundfakturor", "Kundreskontran")

    forfallna = [
        p for p in data.kundreskontra
        if p.forfallodatum is not None and (data.idag - p.forfallodatum).days > 0
    ]
    forfallna.sort(key=lambda p: (data.idag - p.forfallodatum).days, reverse=True)
    total = sum((abs(p.belopp) for p in forfallna), Decimal("0"))

    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
            KolumnDef(nyckel="forfallodatum", rubrik="Förföll", typ="datum"),
            KolumnDef(nyckel="dagar", rubrik="Dagar sedan", typ="text"),
            KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
        ],
        rader=[
            {
                "kund": p.kund,
                "forfallodatum": p.forfallodatum.isoformat(),
                "dagar": str((data.idag - p.forfallodatum).days),
                "belopp": abs(p.belopp),
            }
            for p in forfallna
        ],
        summa_rad={"kund": "Summa", "belopp": total},
    ) if forfallna else None

    return Snabbvyresultat(
        rubrik="Förfallna kundfakturor",
        nyckeltal=[
            Nyckeltal("Förfallet belopp", f"{_kr(total, data.formateringsval)}"),
            Nyckeltal("Antal fakturor", str(len(forfallna))),
        ],
        sektioner=[
            Sektion(
                rubrik="Förfallna, äldst först",
                tabell=tabell,
                niva="rod" if forfallna else "gron",
                tomtext="Inga förfallna kundfakturor. 🎉",
            )
        ],
    )


# --- Vy: åldersanalys -------------------------------------------------------


def _aldersvy(poster: list | None, idag: date, rubrik: str, vad: str, formateringsval: Formateringsval) -> Snabbvyresultat:
    if poster is None:
        return _saknas(rubrik, vad)

    analys = bygg_aldersanalys(poster, idag)
    ordning = ["ej_forfallna", "0–30", "31–60", "61–90", "91+", "okant"]
    etiketter = {
        "ej_forfallna": "Ej förfallna",
        "0–30": "1–30 dagar",
        "31–60": "31–60 dagar",
        "61–90": "61–90 dagar",
        "91+": "Över 90 dagar",
        "okant": "Saknar förfallodatum",
    }
    rader = [
        {
            "intervall": etiketter[n],
            "antal": str(analys["hinkar"][n]["antal"]),
            "belopp": analys["hinkar"][n]["belopp"],
        }
        for n in ordning
        if analys["hinkar"][n]["antal"]
    ]

    return Snabbvyresultat(
        rubrik=rubrik,
        nyckeltal=[
            Nyckeltal("Totalt", f"{_kr(analys['totalt_belopp'], formateringsval)}"),
            Nyckeltal("Antal poster", str(analys["totalt_antal"])),
        ],
        sektioner=[
            Sektion(
                rubrik="Fördelning efter ålder",
                tabell=TabellBlock(
                    kolumner=[
                        KolumnDef(nyckel="intervall", rubrik="Ålder", typ="text"),
                        KolumnDef(nyckel="antal", rubrik="Antal", typ="text"),
                        KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
                    ],
                    rader=rader,
                    summa_rad={"intervall": "Summa", "belopp": analys["totalt_belopp"]},
                ) if rader else None,
            )
        ],
        fotnot="Åldern räknas från förfallodatum, inte fakturadatum.",
    )


def bygg_aldersanalys_kund(data: Vydata) -> Snabbvyresultat:
    return _aldersvy(data.kundreskontra, data.idag, "Åldersanalys — kundfordringar",
                     "Kundreskontran", data.formateringsval)


# --- Vy: påminnelseförslag (röd/gul) ----------------------------------------


def _paminnelsetabell(rader: list[dict], visa_monster: bool) -> TabellBlock | None:
    if not rader:
        return None
    kolumner = [
        KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
        KolumnDef(nyckel="forfallodatum", rubrik="Förföll", typ="datum"),
        KolumnDef(nyckel="dagar_forsent", rubrik="Dagar sen", typ="text"),
    ]
    if visa_monster:
        kolumner.append(KolumnDef(nyckel="monster", rubrik="Kundens mönster", typ="text"))
    kolumner.append(KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"))

    return TabellBlock(
        kolumner=kolumner,
        rader=[
            {
                "kund": r["kund"],
                "forfallodatum": r["forfallodatum"].isoformat(),
                "dagar_forsent": str(r["dagar_forsent"]),
                "monster": (
                    "okänt — ny kund"
                    if r["saknar_historik"]
                    else f"betalar normalt {r['normalt_monster_dagar']:.0f} dgr sent"
                ),
                "belopp": r["belopp"],
            }
            for r in rader
        ],
        summa_rad={"kund": "Summa", "belopp": sum((r["belopp"] for r in rader), Decimal("0"))},
    )


def bygg_paminnelsevy(data: Vydata) -> Snabbvyresultat:
    """Påminnelseförslag i två nivåer, efter kundens EGET betalmönster."""
    if data.kundreskontra is None:
        return _saknas("Påminnelseförslag", "Kundreskontran")

    forslag = bygg_paminnelseforslag(
        data.kundreskontra, data.kundbetalbeteende, data.idag
    )

    return Snabbvyresultat(
        rubrik="Påminnelseförslag",
        nyckeltal=[
            Nyckeltal("🔴 Bruten betalvana", f"{_kr(forslag['rod_belopp'], data.formateringsval)}",
                      f"{len(forslag['rod'])} fakturor"),
            Nyckeltal("🟡 Förfallen men väntat", f"{_kr(forslag['gul_belopp'], data.formateringsval)}",
                      f"{len(forslag['gul'])} fakturor"),
        ],
        sektioner=[
            Sektion(
                rubrik="🔴 Kontakta först — kunden har brutit sitt normala mönster",
                beskrivning=(
                    "Fakturan är förfallen OCH kunden är senare än den brukar vara. "
                    "Kunder utan känd betalhistorik hamnar också här."
                ),
                tabell=_paminnelsetabell(forslag["rod"], visa_monster=True),
                niva="rod",
                tomtext="Ingen kund har brutit sitt betalmönster.",
            ),
            Sektion(
                rubrik="🟡 Bevaka — förfallen, men inom kundens vanliga mönster",
                beskrivning=(
                    "Fakturan är förfallen, men kunden brukar betala ungefär så här "
                    "sent. En påminnelse är sällan brådskande."
                ),
                tabell=_paminnelsetabell(forslag["gul"], visa_monster=True),
                niva="gul",
                tomtext="Inga poster i det här läget.",
            ),
        ],
        fotnot=(
            f"Gränsen går vid kundens snitt + {forslag['marginal_dagar']} dagars "
            "marginal. Rangordnat efter belopp × dagar över mönstret. "
            "Betalmönstret bygger på historiskt betalda fakturor och är en "
            "uppskattning, inte en utfästelse."
        ),
    )


# --- Vyer: Leverantörsfakturor ----------------------------------------------


def bygg_utestaende_leverantorsfakturor(data: Vydata) -> Snabbvyresultat:
    if data.leverantorsreskontra is None:
        return _saknas("Utestående leverantörsfakturor", "Leverantörsreskontran")

    poster = sorted(
        data.leverantorsreskontra,
        key=lambda p: (p.forfallodatum or date.max),
    )
    total = sum((abs(p.belopp) for p in poster), Decimal("0"))
    forfallna = [
        p for p in poster
        if p.forfallodatum is not None and (data.idag - p.forfallodatum).days > 0
    ]

    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="leverantor", rubrik="Leverantör", typ="text"),
            KolumnDef(nyckel="forfallodatum", rubrik="Förfaller", typ="datum"),
            KolumnDef(nyckel="dagar", rubrik="Dagar kvar", typ="text"),
            KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
        ],
        rader=[
            {
                "leverantor": p.leverantor,
                "forfallodatum": p.forfallodatum.isoformat() if p.forfallodatum else "—",
                "dagar": (
                    str((p.forfallodatum - data.idag).days)
                    if p.forfallodatum and p.forfallodatum >= data.idag
                    else (f"−{(data.idag - p.forfallodatum).days}" if p.forfallodatum else "—")
                ),
                "belopp": abs(p.belopp),
            }
            for p in poster
        ],
        summa_rad={"leverantor": "Summa", "belopp": total},
    )

    return Snabbvyresultat(
        rubrik="Utestående leverantörsfakturor",
        nyckeltal=[
            Nyckeltal("Totalt utestående", f"{_kr(total, data.formateringsval)}"),
            Nyckeltal("Antal fakturor", str(len(poster))),
            Nyckeltal(
                "Varav förfallet",
                f"{_kr(sum((abs(p.belopp) for p in forfallna), Decimal('0')), data.formateringsval)}",
                f"{len(forfallna)} st",
            ),
        ],
        sektioner=[Sektion(rubrik="Alla öppna leverantörsposter", tabell=tabell)],
    )


def bygg_forfallna_leverantorsfakturor(data: Vydata) -> Snabbvyresultat:
    if data.leverantorsreskontra is None:
        return _saknas("Förfallna leverantörsfakturor", "Leverantörsreskontran")

    forfallna = [
        p for p in data.leverantorsreskontra
        if p.forfallodatum is not None and (data.idag - p.forfallodatum).days > 0
    ]
    forfallna.sort(key=lambda p: (data.idag - p.forfallodatum).days, reverse=True)
    total = sum((abs(p.belopp) for p in forfallna), Decimal("0"))

    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="leverantor", rubrik="Leverantör", typ="text"),
            KolumnDef(nyckel="forfallodatum", rubrik="Förföll", typ="datum"),
            KolumnDef(nyckel="dagar", rubrik="Dagar sedan", typ="text"),
            KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
        ],
        rader=[
            {
                "leverantor": p.leverantor,
                "forfallodatum": p.forfallodatum.isoformat(),
                "dagar": str((data.idag - p.forfallodatum).days),
                "belopp": abs(p.belopp),
            }
            for p in forfallna
        ],
        summa_rad={"leverantor": "Summa", "belopp": total},
    ) if forfallna else None

    return Snabbvyresultat(
        rubrik="Förfallna leverantörsfakturor",
        nyckeltal=[
            Nyckeltal("Förfallet belopp", f"{_kr(total, data.formateringsval)}"),
            Nyckeltal("Antal fakturor", str(len(forfallna))),
        ],
        sektioner=[
            Sektion(
                rubrik="Förfallna, äldst först",
                tabell=tabell,
                niva="rod" if forfallna else "gron",
                tomtext="Inga förfallna leverantörsfakturor. 🎉",
            )
        ],
    )


def bygg_aldersanalys_leverantor(data: Vydata) -> Snabbvyresultat:
    return _aldersvy(data.leverantorsreskontra, data.idag, "Åldersanalys — leverantörsskulder",
                     "Leverantörsreskontran", data.formateringsval)


def _betalningsforslag_tabell(rader: list[dict]) -> TabellBlock | None:
    if not rader:
        return None
    kolumner = [
        KolumnDef(nyckel="leverantor", rubrik="Leverantör", typ="text"),
        KolumnDef(nyckel="forfallodatum", rubrik="Förfaller", typ="datum"),
        KolumnDef(nyckel="status_text", rubrik="Status", typ="text"),
        KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
    ]
    return TabellBlock(
        kolumner=kolumner,
        rader=rader,
        summa_rad={"leverantor": "Summa", "belopp": sum((r["belopp"] for r in rader), Decimal("0"))},
    )


def bygg_betalningsforslag_vy(data: Vydata) -> Snabbvyresultat:
    """Betalningsförslag — vilka leverantörsfakturor som är förfallna eller förfaller inom 7 dagar."""
    if data.leverantorsreskontra is None:
        return _saknas("Betalningsförslag", "Leverantörsreskontran")

    poster = data.leverantorsreskontra
    rod_poster = [
        p for p in poster
        if p.forfallodatum is not None and (data.idag - p.forfallodatum).days > 0
    ]
    rod_poster.sort(key=lambda p: (data.idag - p.forfallodatum).days, reverse=True)
    rod_total = sum((abs(p.belopp) for p in rod_poster), Decimal("0"))

    gul_poster = [
        p for p in poster
        if p.forfallodatum is not None and 0 <= (p.forfallodatum - data.idag).days <= 7
    ]
    gul_poster.sort(key=lambda p: (p.forfallodatum - data.idag).days)
    gul_total = sum((abs(p.belopp) for p in gul_poster), Decimal("0"))

    def _bygg_rader(lista: list) -> list[dict]:
        rader = []
        for p in lista:
            diff = (data.idag - p.forfallodatum).days if p.forfallodatum else 0
            if diff > 0:
                status_text = f"{diff} dgr försenad"
            elif diff == 0:
                status_text = "förfaller idag"
            else:
                status_text = f"om {abs(diff)} dgr"
            rader.append({
                "leverantor": p.leverantor,
                "forfallodatum": p.forfallodatum.isoformat() if p.forfallodatum else "—",
                "status_text": status_text,
                "belopp": abs(p.belopp),
            })
        return rader

    return Snabbvyresultat(
        rubrik="Betalningsförslag",
        nyckeltal=[
            Nyckeltal("🔴 Förfallet att betala", f"{_kr(rod_total, data.formateringsval)}",
                      f"{len(rod_poster)} fakturor"),
            Nyckeltal("🟡 Förfaller inom 7 dgr", f"{_kr(gul_total, data.formateringsval)}",
                      f"{len(gul_poster)} fakturor"),
        ],
        sektioner=[
            Sektion(
                rubrik="🔴 Betala omgående — förfallna leverantörsfakturor",
                beskrivning=(
                    "Fakturan har passerat sitt förfallodatum till betalning "
                    "och riskerar påminnelseavgift eller dröjsmålsränta."
                ),
                tabell=_betalningsforslag_tabell(_bygg_rader(rod_poster)),
                niva="rod",
                tomtext="Inga förfallna leverantörsfakturor. 🎉",
            ),
            Sektion(
                rubrik="🟡 Förbered betalning — förfaller de närmaste 7 dagarna",
                beskrivning=(
                    "Fakturor som förfaller till betalning den närmaste veckan."
                ),
                tabell=_betalningsforslag_tabell(_bygg_rader(gul_poster)),
                niva="gul",
                tomtext="Inga leverantörsfakturor förfaller de närmaste 7 dagarna.",
            ),
        ],
        fotnot="Rangordnat efter brådskandegrad och förfallodatum.",
    )


# --- Registret --------------------------------------------------------------

SNABBVYER_KUND: tuple[Snabbvy, ...] = (
    Snabbvy("kund_utestaende", "Utestående kundfakturor", "📄", bygg_utestaende_kundfakturor,
            "Alla öppna kundfakturor", frozenset([Formaga.LASA_KUNDRESKONTRA])),
    Snabbvy("kund_forfallna", "Förfallna kundfakturor", "⏰", bygg_forfallna_kundfakturor,
            "Fakturor vars förfallodag passerat", frozenset([Formaga.LASA_KUNDRESKONTRA])),
    Snabbvy("kund_alder", "Åldersanalys av kundfakturor", "📊", bygg_aldersanalys_kund,
            "Hur länge fordringarna varit förfallna", frozenset([Formaga.LASA_KUNDRESKONTRA])),
    Snabbvy("kund_paminnelse", "Påminnelser", "🔔", bygg_paminnelsevy,
            "Vem bör kontaktas först", frozenset([Formaga.LASA_KUNDRESKONTRA])),
)

SNABBVYER_LEVERANTOR: tuple[Snabbvy, ...] = (
    Snabbvy("lev_utestaende", "Utestående leverantörsfakturor", "📄", bygg_utestaende_leverantorsfakturor,
            "Alla öppna leverantörsfakturor", frozenset([Formaga.LASA_LEVERANTORSRESKONTRA])),
    Snabbvy("lev_forfallna", "Förfallna leverantörsfakturor", "⏰", bygg_forfallna_leverantorsfakturor,
            "Leverantörsfakturor vars förfallodag passerat", frozenset([Formaga.LASA_LEVERANTORSRESKONTRA])),
    Snabbvy("lev_alder", "Åldersanalys av leverantörsfakturor", "📊", bygg_aldersanalys_leverantor,
            "Hur länge leverantörsskulderna varit förfallna", frozenset([Formaga.LASA_LEVERANTORSRESKONTRA])),
    Snabbvy("lev_betala", "Betalningsförslag", "💳", bygg_betalningsforslag_vy,
            "Vilka leverantörsfakturor som bör betalas först", frozenset([Formaga.LASA_LEVERANTORSRESKONTRA])),
)
def hitta_vy(vyer: tuple[Snabbvy, ...], vy_id: str | None) -> Snabbvy | None:
    """Vyn med angivet id, annars None. Ett okänt id (t.ex. från ett gammalt
    session_state efter en uppdatering) ska ge None, inte en krasch."""
    return next((v for v in vyer if v.id == vy_id), None)


# --- ETAPP 2: Bank ---

def bygg_bankkonton(data: Vydata) -> Snabbvyresultat:
    if data.bankkonton is None:
        return _saknas("Bankkonton", "Bankkonton")
    antal = len(data.bankkonton)
    summa = sum((Decimal(str(k.get("saldo", "0"))) for k in data.bankkonton), Decimal("0"))
    
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="bas_konto", rubrik="Bokföringskonto", typ="text"),
            KolumnDef(nyckel="saldo", rubrik="Saldo", typ="belopp"),
            KolumnDef(nyckel="valuta", rubrik="Valuta", typ="text"),
        ],
        rader=[
            {
                "namn": str(k.get("namn", "")),
                "bas_konto": str(k.get("bas_konto", "")),
                "saldo": _kr(Decimal(str(k.get("saldo", "0"))), data.formateringsval),
                "valuta": str(k.get("valuta", "")),
            }
            for k in data.bankkonton
        ]
    )
    
    return Snabbvyresultat(
        rubrik="Bankkonton",
        nyckeltal=(
            Nyckeltal("Antal konton", str(antal)),
            Nyckeltal("Summa saldo", _kr(summa, data.formateringsval)),
        ),
        sektioner=[Sektion(rubrik="Kontolista", tabell=tabell)],
    )

def bygg_avstamningslage(data: Vydata) -> Snabbvyresultat:
    if data.avstamningslage is None:
        return _saknas("Avstämningsläge", "Avstämningsläge")
        
    antal_omatchade = sum(int(a.get("antal_omatchade", 0)) for a in data.avstamningslage)
    summa_omatchade = sum((Decimal(str(a.get("summa_omatchade", "0"))) for a in data.avstamningslage), Decimal("0"))
    
    sektioner = []
    if not data.avstamningslage:
        sektioner.append(Sektion(
            rubrik="Avstämning",
            beskrivning="Inga obokförda banktransaktioner. Saknar bolaget bankkoppling visas inga händelser här."
        ))
    
    for a in data.avstamningslage:
        omatch = int(a.get("antal_omatchade", 0))
        niva = "neutral"
        if omatch == 0:
            niva = "framgang"
        elif omatch < 10:
            niva = "varning"
        else:
            niva = "fara"
            
        aldsta = str(a.get("aldsta_omatchad", "")) if a.get("aldsta_omatchad") else ""
        tabell = TabellBlock(
            rubrik=None,
            kolumner=[
                KolumnDef(nyckel="antal", rubrik="Antal omatchade", typ="text"),
                KolumnDef(nyckel="summa", rubrik="Summa omatchade", typ="belopp"),
                KolumnDef(nyckel="aldsta", rubrik="Äldsta omatchade", typ="text"),
            ],
            rader=[{
                "antal": str(omatch),
                "summa": _kr(Decimal(str(a.get("summa_omatchade", "0"))), data.formateringsval),
                "aldsta": aldsta,
            }]
        )
        sektioner.append(Sektion(
            rubrik=f"Konto: {a.get('bankkonto', '')}",
            tabell=tabell,
            niva=niva,
        ))
        
    return Snabbvyresultat(
        rubrik="Avstämningsläge",
        nyckeltal=(
            Nyckeltal("Totalt antal omatchade", str(antal_omatchade)),
            Nyckeltal("Summa omatchat", _kr(summa_omatchade, data.formateringsval)),
        ),
        sektioner=sektioner,
    )

def bygg_bankhandelser(data: Vydata) -> Snabbvyresultat:
    if not data.bankkonto_id:
        return Snabbvyresultat(
            rubrik="Bankhändelser",
            sektioner=[Sektion(rubrik="Kräver val", beskrivning="Välj ett bankkonto för att se dess händelser.")]
        )
    if data.bankhandelser is None:
        return _saknas("Bankhändelser", "Bankhändelser")
        
    antal = len(data.bankhandelser)
    summa = sum((Decimal(str(h.get("belopp", "0"))) for h in data.bankhandelser), Decimal("0"))
    avstamda = sum(1 for h in data.bankhandelser if h.get("avstamd"))
    
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="datum", rubrik="Datum", typ="text"),
            KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
            KolumnDef(nyckel="avgift", rubrik="Avgift", typ="belopp"),
            KolumnDef(nyckel="rader", rubrik="Konteringsrader", typ="text"),
        ],
        rader=[
            {
                "datum": str(h.get("datum", "")),
                "belopp": _kr(Decimal(str(h.get("belopp", "0"))), data.formateringsval),
                "avgift": _kr(Decimal(str(h.get("avgift", "0"))), data.formateringsval),
                "rader": str(h.get("antal_konteringsrader", 0)),
            }
            for h in data.bankhandelser
        ]
    )
    
    return Snabbvyresultat(
        rubrik="Bankhändelser",
        nyckeltal=(
            Nyckeltal("Antal händelser", str(antal)),
            Nyckeltal("Summa belopp", _kr(summa, data.formateringsval)),
            Nyckeltal("Antal avstämda", str(avstamda)),
        ),
        sektioner=[Sektion(rubrik="Händelser", tabell=tabell)],
    )

# --- ETAPP 2: Register ---

def _bygg_kunder_leverantorer(data: Vydata, is_kund: bool) -> Snabbvyresultat:
    l_data = data.kunder if is_kund else data.leverantorer
    if l_data is None:
        namn = "Kunder" if is_kund else "Leverantörer"
        return _saknas(namn, namn)
        
    antal = len(l_data)
    aktiva = sum(1 for x in l_data if x.get("aktiv"))
    obetalt = sum((Decimal(str(x.get("obetalt_belopp", "0"))) for x in l_data), Decimal("0"))
    
    rader = []
    for x in l_data:
        markor = " 🔒" if x.get("maskerad") else ""
        rader.append({
            "nummer": str(x.get("kundnummer" if is_kund else "leverantorsnummer", "")),
            "namn": str(x.get("namn", "")) + markor,
            "land": str(x.get("land", "")),
            "obetalt": _kr(Decimal(str(x.get("obetalt_belopp", "0"))), data.formateringsval),
            "aktiv": "Ja" if x.get("aktiv") else "Nej",
        })
        
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="nummer", rubrik="Nummer", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="land", rubrik="Land", typ="text"),
            KolumnDef(nyckel="obetalt", rubrik="Obetalt", typ="belopp"),
            KolumnDef(nyckel="aktiv", rubrik="Aktiv", typ="text"),
        ],
        rader=rader
    )
    
    rubrik = "Kunder" if is_kund else "Leverantörer"
    drill_typ = "leverantor" if not is_kund else "kund"
    return Snabbvyresultat(
        rubrik=rubrik,
        nyckeltal=(
            Nyckeltal("Antal", str(antal)),
            Nyckeltal("Antal aktiva", str(aktiva)),
            Nyckeltal("Summa obetalt", _kr(obetalt, data.formateringsval)),
        ),
        sektioner=[Sektion(
            rubrik=rubrik,
            tabell=tabell,
            beskrivning="🔒 = Namnet är pseudonymiserat — personen är en privatperson eller ett okänt namn. Välj nedan för att se fakturor.",
            drill_typ=drill_typ,
        )],
    )

def bygg_kunder(data: Vydata) -> Snabbvyresultat:
    return _bygg_kunder_leverantorer(data, is_kund=True)

def bygg_leverantorer(data: Vydata) -> Snabbvyresultat:
    return _bygg_kunder_leverantorer(data, is_kund=False)

def bygg_artiklar(data: Vydata) -> Snabbvyresultat:
    if data.artiklar is None:
        return _saknas("Artiklar", "Artiklar")
        
    antal = len(data.artiklar)
    aktiva = sum(1 for a in data.artiklar if a.get("aktiv"))
    
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="artikelnr", rubrik="Artikelnr", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="pris", rubrik="Pris", typ="belopp"),
            KolumnDef(nyckel="enhet", rubrik="Enhet", typ="text"),
            KolumnDef(nyckel="konto", rubrik="Konto", typ="text"),
            KolumnDef(nyckel="aktiv", rubrik="Aktiv", typ="text"),
        ],
        rader=[
            {
                "artikelnr": str(a.get("artikelnr", "")),
                "namn": str(a.get("namn", "")),
                "pris": _kr(Decimal(str(a.get("pris", "0"))), data.formateringsval),
                "enhet": str(a.get("enhet", "")),
                "konto": str(a.get("konto", "")),
                "aktiv": "Ja" if a.get("aktiv") else "Nej",
            }
            for a in data.artiklar
        ]
    )
    
    return Snabbvyresultat(
        rubrik="Artiklar",
        nyckeltal=(
            Nyckeltal("Antal", str(antal)),
            Nyckeltal("Antal aktiva", str(aktiva)),
        ),
        sektioner=[Sektion(rubrik="Artikellista", tabell=tabell)],
    )

def bygg_projekt(data: Vydata) -> Snabbvyresultat:
    if data.projekt is None:
        return _saknas("Projekt", "Projekt")
        
    antal = len(data.projekt)
    
    rader = []
    for p in data.projekt:
        markor = " 🔒" if p.get("maskerad") else ""
        rader.append({
            "nummer": str(p.get("nummer", "")),
            "namn": str(p.get("namn", "")),
            "startdatum": str(p.get("startdatum", "")),
            "slutdatum": str(p.get("slutdatum", "")),
            "kund": str(p.get("kund", "")) + markor,
            "status": str(p.get("status", "")),
        })
        
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="nummer", rubrik="Nummer", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="startdatum", rubrik="Startdatum", typ="text"),
            KolumnDef(nyckel="slutdatum", rubrik="Slutdatum", typ="text"),
            KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
            KolumnDef(nyckel="status", rubrik="Status", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Projekt",
        nyckeltal=(
            Nyckeltal("Antal", str(antal)),
        ),
        sektioner=[Sektion(
            rubrik="Projektlista", 
            tabell=tabell,
            beskrivning="🔒 på kundnamnet betyder att kunden är pseudonymiserad."
        )],
    )

def bygg_kostnadsstallen(data: Vydata) -> Snabbvyresultat:
    if data.kostnadsstallen is None:
        return _saknas("Kostnadsställen", "Kostnadsställen")
        
    antal = len(data.kostnadsstallen)
    aktiva = sum(1 for k in data.kostnadsstallen if k.get("aktiv"))
    
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="nummer", rubrik="Nummer", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="aktiv", rubrik="Aktiv", typ="text"),
        ],
        rader=[
            {
                "nummer": str(k.get("nummer", "")),
                "namn": str(k.get("namn", "")),
                "aktiv": "Ja" if k.get("aktiv") else "Nej",
            }
            for k in data.kostnadsstallen
        ]
    )
    
    return Snabbvyresultat(
        rubrik="Kostnadsställen",
        nyckeltal=(
            Nyckeltal("Antal", str(antal)),
            Nyckeltal("Antal aktiva", str(aktiva)),
        ),
        sektioner=[Sektion(rubrik="Kostnadsställen", tabell=tabell)],
    )

def bygg_prislistor(data: Vydata) -> Snabbvyresultat:
    if data.prislistor is None:
        return _saknas("Prislistor", "Prislistor")
    
    rader = []
    for p in data.prislistor:
        rader.append({
            "id": str(p.get("Id", "")),
            "namn": str(p.get("Name", "")),
            "nummer": str(p.get("Number", "")),
            "aktiv": "Ja" if p.get("IsActive") else "Nej"
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="id", rubrik="ID", typ="text"),
            KolumnDef(nyckel="nummer", rubrik="Nummer", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="aktiv", rubrik="Aktiv", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Prislistor",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[Nyckeltal("Antal prislistor", str(len(data.prislistor)))],
        sektioner=[Sektion(rubrik="Tillgängliga prislistor", tabell=tabell if rader else None, tomtext="Inga prislistor hittades.")]
    )


def bygg_rabattavtal(data: Vydata) -> Snabbvyresultat:
    if data.rabattavtal is None:
        return _saknas("Rabattavtal", "Rabattavtal")
        
    rader = []
    for r in data.rabattavtal:
        rader.append({
            "id": str(r.get("Id", "")),
            "beskrivning": str(r.get("Description", "")),
            "rabatt": f"{r.get('DiscountPercent', 0)} %",
            "aktiv": "Ja" if r.get("IsActive") else "Nej"
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="id", rubrik="ID", typ="text"),
            KolumnDef(nyckel="beskrivning", rubrik="Beskrivning", typ="text"),
            KolumnDef(nyckel="rabatt", rubrik="Rabatt %", typ="text"),
            KolumnDef(nyckel="aktiv", rubrik="Aktiv", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Rabattavtal",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[Nyckeltal("Antal avtal", str(len(data.rabattavtal)))],
        sektioner=[Sektion(rubrik="Avtal", tabell=tabell if rader else None, tomtext="Inga rabattavtal hittades.")]
    )


def bygg_etiketter(data: Vydata) -> Snabbvyresultat:
    if data.etiketter is None:
        return _saknas("Etiketter", "Etiketter")
        
    rader = []
    for e in data.etiketter:
        rader.append({
            "typ": str(e.get("Typ", "")),
            "id": str(e.get("Id", "")),
            "namn": str(e.get("Name", "")),
            "beskrivning": str(e.get("Description", ""))
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="typ", rubrik="Typ", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="beskrivning", rubrik="Beskrivning", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Etiketter",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[Nyckeltal("Antal etiketter", str(len(data.etiketter)))],
        sektioner=[Sektion(rubrik="Etiketter", tabell=tabell if rader else None, tomtext="Inga etiketter hittades.")]
    )


def bygg_anlaggningstillgangar(data: Vydata) -> Snabbvyresultat:
    if data.anlaggningstillgangar is None:
        return _saknas("Anläggningstillgångar", "Anläggningstillgångar")
        
    rader = []
    for a in data.anlaggningstillgangar:
        rader.append({
            "id": str(a.get("Id", "")),
            "namn": str(a.get("Description", "")),
            "nummer": str(a.get("Number", "")),
            "konto": str(a.get("AssetAccountId", ""))
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="nummer", rubrik="Nummer", typ="text"),
            KolumnDef(nyckel="namn", rubrik="Beskrivning", typ="text"),
            KolumnDef(nyckel="konto", rubrik="Konto ID", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Anläggningstillgångar",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[Nyckeltal("Antal tillgångar", str(len(data.anlaggningstillgangar)))],
        sektioner=[Sektion(rubrik="Anläggningstillgångar", tabell=tabell if rader else None, tomtext="Inga tillgångar hittades.")]
    )


def bygg_foretagsinfo(data: Vydata) -> Snabbvyresultat:
    if data.foretagsinfo is None:
        return _saknas("Företagsinformation", "Företagsinformation")
        
    f = data.foretagsinfo
    rader = [
        {"egenskap": "Namn", "varde": str(f.get("Name", ""))},
        {"egenskap": "Org.nummer", "varde": str(f.get("OrganizationNumber", ""))},
        {"egenskap": "Adress", "varde": str(f.get("Address1", ""))},
        {"egenskap": "Postnummer", "varde": str(f.get("ZipCode", ""))},
        {"egenskap": "Ort", "varde": str(f.get("City", ""))},
        {"egenskap": "E-post", "varde": str(f.get("Email", ""))},
        {"egenskap": "Telefon", "varde": str(f.get("Phone", ""))},
    ]
    
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="egenskap", rubrik="Egenskap", typ="text"),
            KolumnDef(nyckel="varde", rubrik="Värde", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Företagsinformation",
        harkomst=HARKOMST_KALLA,
        sektioner=[Sektion(rubrik="Detaljer", tabell=tabell)]
    )


def bygg_anvandare(data: Vydata) -> Snabbvyresultat:
    if data.anvandare is None:
        return _saknas("Användare", "Användare")
        
    rader = []
    for a in data.anvandare:
        rader.append({
            "namn": str(a.get("Name", "")),
            "epost": str(a.get("Email", "")),
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="namn", rubrik="Namn", typ="text"),
            KolumnDef(nyckel="epost", rubrik="E-post", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Användare",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[Nyckeltal("Antal användare", str(len(data.anvandare)))],
        sektioner=[Sektion(rubrik="Användarlista", tabell=tabell if rader else None, tomtext="Inga användare hittades.", dold_detalj=True)]
    )


def bygg_valutakurs(data: Vydata) -> Snabbvyresultat:
    if data.valutakurs is None:
        return Snabbvyresultat(
            rubrik="Valutakurs",
            sektioner=[Sektion(rubrik="Välj valuta", beskrivning="Välj valutapar och datum ovan för att hämta kurs.")]
        )
        
    v = data.valutakurs
    return Snabbvyresultat(
        rubrik="Valutakurs",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[
            Nyckeltal("Kurs", str(v.get("Rate", ""))),
            Nyckeltal("Från", str(v.get("Code", ""))),
            Nyckeltal("Datum", str(v.get("Date", ""))),
        ],
        sektioner=[]
    )


def bygg_kundreskontraposter(data: Vydata) -> Snabbvyresultat:
    if data.kundreskontraposter is None:
        return _saknas("Kundreskontraposter", "Kundreskontraposter")
        
    rader = []
    for p in data.kundreskontraposter:
        rader.append({
            "faktura": str(p.get("InvoiceNumber", "")),
            "kund": str(p.get("CustomerName", "")),
            "datum": str(p.get("InvoiceDate", "")),
            "forfaller": str(p.get("DueDate", "")),
            "total": _kr(Decimal(str(p.get("Total") or "0")), data.formateringsval),
            "saldo": _kr(Decimal(str(p.get("Balance") or "0")), data.formateringsval)
        })
        
    tabell = TabellBlock(
        kolumner=[
            KolumnDef(nyckel="faktura", rubrik="Fakturanr", typ="text"),
            KolumnDef(nyckel="kund", rubrik="Kund", typ="text"),
            KolumnDef(nyckel="datum", rubrik="Datum", typ="datum"),
            KolumnDef(nyckel="forfaller", rubrik="Förfaller", typ="datum"),
            KolumnDef(nyckel="total", rubrik="Total", typ="text"),
            KolumnDef(nyckel="saldo", rubrik="Saldo", typ="text"),
        ],
        rader=rader
    )
    
    return Snabbvyresultat(
        rubrik="Kundreskontraposter",
        harkomst=HARKOMST_KALLA,
        nyckeltal=[Nyckeltal("Antal poster", str(len(data.kundreskontraposter)))],
        sektioner=[Sektion(rubrik="Poster", tabell=tabell if rader else None, tomtext="Inga poster hittades.")]
    )

def bygg_referensdata(data: Vydata) -> Snabbvyresultat:
    if not data.vald_referenstyp:
        return Snabbvyresultat(
            rubrik="Referensdata",
            sektioner=[Sektion(rubrik="Kräver val", beskrivning="Välj en referenstyp för att visa listan.")]
        )
    if data.referensdata is None:
        return _saknas("Referensdata", "Referensdata")
        
    antal = len(data.referensdata)
    
    if not data.referensdata:
        return Snabbvyresultat(
            rubrik="Referensdata",
            sektioner=[Sektion(rubrik="Referensdata", tomtext="Listan är tom.")]
        )
        
    keys = list(data.referensdata[0].keys()) if data.referensdata else []
    
    tabell = TabellBlock(
        rubrik=None,
        kolumner=[KolumnDef(nyckel=k, rubrik=k.capitalize(), typ="text") for k in keys],
        rader=[
            {k: str(row.get(k, "")) for k in keys}
            for row in data.referensdata
        ]
    )
    
    return Snabbvyresultat(
        rubrik="Referensdata",
        nyckeltal=(
            Nyckeltal("Antal", str(antal)),
        ),
        sektioner=[Sektion(
            rubrik="Lista",
            tabell=tabell,
            beskrivning="Referensdata (som måttenheter och landskoder) saknar PII och maskeras medvetet inte."
        )],
    )

SNABBVYER_BANK: tuple[Snabbvy, ...] = (
    Snabbvy("bankkonton", "Bankkonton", "🏦", bygg_bankkonton, "Bolagets bankkonton"),
    Snabbvy("avstamningslage", "Avstämningsläge", "⚖️", bygg_avstamningslage, "Kontrollera obokförda händelser"),
    Snabbvy("bankhandelser", "Bankhändelser", "🧾", bygg_bankhandelser, "Transaktioner på kontot"),
)

SNABBVYER_REGISTER: tuple[Snabbvy, ...] = (
    Snabbvy("kunder", "Kunder", "👥", bygg_kunder, "Kundregistret"),
    Snabbvy("leverantorer", "Leverantörer", "🏢", bygg_leverantorer, "Leverantörsregistret"),
    Snabbvy("artiklar", "Artiklar", "📦", bygg_artiklar, "Artikelregistret"),
    Snabbvy("projekt", "Projekt", "🏗️", bygg_projekt, "Aktiva och avslutade projekt"),
    Snabbvy("kostnadsstallen", "Kostnadsställen", "🏷️", bygg_kostnadsstallen, "Bokföringens resultatenheter"),
    Snabbvy("referensdata", "Referensdata", "📚", bygg_referensdata, "Systemets gemensamma referenslistor"),
    Snabbvy("prislistor", "Prislistor", "🏷", bygg_prislistor),
    Snabbvy("rabattavtal", "Rabattavtal", "🤝", bygg_rabattavtal),
    Snabbvy("etiketter", "Etiketter", "🔖", bygg_etiketter),
    Snabbvy("anlaggningstillgangar", "Anläggningstillgångar", "🏗️", bygg_anlaggningstillgangar),
    Snabbvy("foretagsinfo", "Företagsinformation", "🏢", bygg_foretagsinfo),
    Snabbvy("anvandare", "Användare", "👤", bygg_anvandare),
    Snabbvy("valutakurs", "Valutakurs", "💱", bygg_valutakurs),
    Snabbvy("kundreskontraposter", "Kundreskontraposter", "🧾", bygg_kundreskontraposter),
)


