"""reskontra_tvatt — GDPR-tvättmaskin för leverantörsreskontra (Alternativ C).

Ren transformationslogik, inget nätverk och ingen domänmodell-koppling: tar
redan hämtade reskontrarader (dict:ar) och avgör per leverantör om namnet får
passera till AI-kontexten. Belopp och betalstatus rörs ALDRIG — bara namnet
kan tvättas.

Affärsregler (bekräftade med användaren):
- Finansiell integritet: ingen faktura får försvinna (len ut == len in, summa
  bevaras) så reskontran alltid matchar huvudboken.
- Juridisk person (t.ex. AB) → namn släpps igenom orört.
- Fysisk person (enskild firma) eller känsligt namn → namnet ersätts med en
  stabil pseudonym, belopp/betalstatus intakt.

Juridisk-vs-fysisk avgörs på den kanoniska svenska regeln: 3:e siffran i ett
organisationsnummer är >= 2, i ett personnummer <= 1 (månadens tiotal). Det är
det PRIMÄRA, pålitliga skyddet. Namndetektorn (ar_kanslig_namn) är default AV
och fungerar som ett valfritt säkerhetsnät för att undvika falska positiva på
legitima AB vars namn råkar likna ett personnamn.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

PSEUDONYM_MARKOR = "[Maskerad: Ej juridisk person]"


def normalisera_spiris_datum(varde: str) -> date:
    """Normaliserar ETT Spiris-datumfält till ett rent kalenderdatum.

    Ingen GDPR-fråga (inget namn inblandat) — detta är en annan sorts "tvätt":
    formatavvikelse, inte sekretess. Hör ändå hemma i den här modulen, inte i
    spiris_adapter.py, eftersom den delas mellan flera fält/endpoints (DueDate
    OCH PaymentDate, kund- OCH leverantörssidan) snarare än att höra till en
    enskild mappningsfunktion.

    Sandbox-verifierat (2026-07-19): samma konceptuella datum kommer i TVÅ
    olika format beroende på Spiris-endpoint — /customerinvoices PaymentDate
    som full ISO-datetime ("2026-06-25T00:00:00Z"), /supplierinvoices samma
    fält som rent datum ("2026-06-24"). date.fromisoformat accepterar inte en
    trailing 'Z' eller en tidskomponent (det är date, inte datetime) — [:10]
    plockar ut just kalenderdatumet oavsett vilketdera formatet gavs in."""
    return date.fromisoformat(varde[:10])

# Beslut A: kända bolagsform-ord räknas som juridisk person även utan svenskt
# org.nr (internationell handel). Matchas som hela ord, aldrig delsträngar.
_BOLAGSFORMER = {
    "AB", "HB", "KB",                       # svenska
    "GMBH", "AG", "UG", "KG",               # tyska
    "LTD", "PLC", "LLP",                    # brittiska/irländska
    "INC", "LLC", "CORP",                   # amerikanska
    "A/S", "APS", "AS", "ASA",              # danska/norska
    "OY", "OYJ",                            # finska
    "BV", "NV",                             # nederländska
    "SA", "SARL", "SAS", "SL", "SPA", "SRL",  # frankofona/spanska/italienska
    "OU",                                   # baltiska
}


def _har_bolagsform_suffix(namn: str) -> bool:
    """True om namnet innehåller ett känt bolagsform-ord (AB, GmbH, Ltd, Inc,
    A/S, Oy…) som helt ord — en 'företagstyp'-signal för juridisk person även
    utan svenskt org.nr. Matchar hela tokens, aldrig delsträngar, så 'Ab' i
    'Abrahamsson' inte råkar räknas."""
    for token in re.split(r"[\s,]+", (namn or "").upper()):
        if token.strip(".") in _BOLAGSFORMER:
            return True
    return False


@dataclass
class Leverantorspost:
    leverantor: str
    belopp: Decimal
    betalstatus: str
    # KLASSNINGEN: ska motparten maskeras innan den lämnar datorn? Sätts vid
    # hämtningen och följer alltid med, oavsett om åtgärden utförts.
    ska_maskeras: bool = False
    # ÅTGÄRDEN: är namnet FAKTISKT utbytt mot en pseudonym? Sätts bara av
    # maskera_for_egress. Att hålla de två isär är det som gör att en lokal vy
    # kan visa riktigt namn medan varje utflödesväg ändå maskerar — och gör
    # tvätten idempotent.
    maskerad: bool = False
    # Krävs av fpa_motor.bygg_likviditetsprognos (dag-för-dag-utflöden).
    # Default None håller befintliga konstruktionsanrop (som inte bryr sig om
    # likviditetsprognosen) oförändrade.
    forfallodatum: date | None = None


@dataclass
class Kundpost:
    kund: str
    belopp: Decimal
    betalstatus: str
    ska_maskeras: bool = False
    maskerad: bool = False
    forfallodatum: date | None = None
    # Spiris CustomerId — INTE personuppgift i sig (ett opakt internt ID), bara
    # nyckeln fpa_motor.bygg_likviditetsprognos slår upp kundens historiska
    # betalbeteende med. Maskeras därför aldrig av tvättmaskinen nedan.
    motpart_id: str = ""


def _ar_juridisk_person(orgnr: str) -> bool:
    """3:e-siffran-regeln. Fail-closed: kan den inte fastställas (tomt, fel
    längd, ej tolkbart) klassas leverantören INTE som juridisk person."""
    siffror = "".join(tecken for tecken in orgnr if tecken.isdigit())
    if len(siffror) == 12:
        # Bara personnummer bär sekelprefix (19/20); org.nr är alltid 10.
        siffror = siffror[2:]
    if len(siffror) != 10:
        return False
    return int(siffror[2]) >= 2


def ar_juridisk_person(namn: str, orgnr: str) -> bool:
    """Publik klassning: juridisk person via org.nr:s 3:e siffra ELLER
    bolagsformssuffix. Fail-closed — otolkbart org.nr utan suffix ger False.

    Utbruten ur `_tvatta` så att listor med en ANNAN form än reskontrans
    (order, offerter, leverantörsfakturor — Steg 3) kan använda exakt samma
    regel i stället för att bygga en egen som glider isär från den här."""
    return _ar_juridisk_person(orgnr or "") or _har_bolagsform_suffix(namn or "")


def _tvatta(
    rå_rader: list[dict],
    pseudonym_prefix: str,
    ar_kanslig_namn: Callable[[str], bool],
) -> list[tuple[str, Decimal, str, bool, date | None]]:
    """Delad GDPR-kärna för både leverantörs- och kundreskontra. Maskerar om
    motparten inte är juridisk person (org.nr-3:e-siffran ELLER bolagsform-
    suffix), om namnet flaggas känsligt, ELLER om raden är märkt privatperson
    (rad['privatperson'] — Spiris CustomerIsPrivatePerson, extra fail-closed-
    signal för kunder). Maskerad motpart får en stabil pseudonym
    ('{prefix} N') så AI:t kan resonera om samma motparts fakturor. Belopp,
    betalstatus och förfallodatum förs alltid vidare oförändrade — bara namnet
    kan tvättas. Returnerar (namn, belopp, status, maskerad, förfallodatum)-
    tupler. förfallodatum läses med .get (inte krav): den här modulen ska vara
    testbar med handbyggda rader utan att känna till likviditetsprognosens
    behov — kravet att fältet FINNS hör hemma i spiris_adapter.py, som är
    steget innan denna tvättmaskin i den skarpa Spiris-vägen."""
    pseudonym_för: dict[str, str] = {}
    resultat: list[tuple[str, Decimal, str, bool, date | None]] = []

    for rad in rå_rader:
        namn = rad["namn"]
        orgnr = rad.get("orgnr", "") or ""

        juridisk = _ar_juridisk_person(orgnr) or _har_bolagsform_suffix(namn)
        maskera = rad.get("privatperson", False) or (not juridisk) or ar_kanslig_namn(namn)

        # Namnet byts INTE här längre — bara klassningen sätts. Bytet sker i
        # maskera_for_egress, vid varje väg ut ur datorn. Det är det som gör
        # att en lokal vy kan visa "Anna Andersson" medan MCP-svaret och
        # AI-kontexten får "Fiktiv Kund 1".
        resultat.append(
            (namn, rad["belopp"], rad["betalstatus"], maskera, rad.get("forfallodatum"))
        )

    return resultat


def tvatta_leverantorsreskontra(
    rå_rader: list[dict],
    *,
    ar_kanslig_namn: Callable[[str], bool] = lambda _namn: False,
) -> list[Leverantorspost]:
    """GDPR-tvättar leverantörsreskontran (se _tvatta). Juridiska leverantörer
    i klartext, känsliga/fysiska pseudonymiseras till 'Fiktiv Leverantör N'."""
    return [
        Leverantorspost(
            leverantor=namn, belopp=belopp, betalstatus=status,
            ska_maskeras=maskerad, maskerad=False, forfallodatum=forfallodatum,
        )
        for namn, belopp, status, maskerad, forfallodatum
        in _tvatta(rå_rader, "Fiktiv Leverantör", ar_kanslig_namn)
    ]


def tvatta_kundreskontra(
    rå_rader: list[dict],
    *,
    ar_kanslig_namn: Callable[[str], bool] = lambda _namn: False,
) -> list[Kundpost]:
    """GDPR-tvättar kundreskontran med exakt samma logik som leverantörer
    (org.nr + bolagsform-suffix + ev. privatperson-flagga). Privatpersoner/
    känsliga pseudonymiseras till 'Fiktiv Kund N'.

    motpart_id (Spiris CustomerId) paras ihop med _tvatta-resultatet efter
    POSITION, inte via _tvatta självt — den tvättas aldrig (det är inget
    namn) och är specifik för kundvägen. Säkert eftersom _tvatta garanterar
    len(ut) == len(in) i oförändrad ordning (samma invariant som resten av
    modulen bygger på: ingen faktura får försvinna eller byta plats)."""
    tvättat = _tvatta(rå_rader, "Fiktiv Kund", ar_kanslig_namn)
    return [
        Kundpost(
            kund=namn, belopp=belopp, betalstatus=status,
            ska_maskeras=maskerad, maskerad=False,
            forfallodatum=forfallodatum, motpart_id=rå_rad.get("motpart_id") or "",
        )
        for (namn, belopp, status, maskerad, forfallodatum), rå_rad in zip(tvättat, rå_rader)
    ]


# --- Egressgränsen ----------------------------------------------------------
# Enda stället i hela kodbasen där ett motpartsnamn byts mot en pseudonym.
#
# Gränsen flyttades hit 2026-08-04 (P0). Tidigare skedde bytet redan vid
# HÄMTNINGEN, vilket gjorde att även lokala vyer i Streamlit-appen visade
# "Fiktiv Kund 3" — data användaren själv äger och ser i Spiris. Maskeringen
# finns för att skydda utflödet till en AI-leverantör, inte för att skydda
# användaren från sin egen bokföring.
#
# Följden: appen håller numera KLARTEXT i minnet, och varje väg ut måste
# anropa den här funktionen. De vägarna är:
#   1. spiris_rag (MCP-verktygen)
#   2. samtalsflode.bygg_saker_kontext (AI-chattens kontext)
#   3. spiris_rag.hamta_likviditetsprognos (motparter i prognosen)
# Egressfunktionerna anropar den SJÄLVA — de litar aldrig på att anroparen
# gjort det. Det är skillnaden mellan ett skydd och en konvention.


def maskera_for_egress(poster: list) -> list:
    """Byter motpartsnamn mot stabila pseudonymer inför utflöde.

    Idempotent: en post som redan är maskerad (`maskerad=True`) lämnas orörd,
    så dubbla anrop är ofarliga. En post som inte ska maskeras
    (`ska_maskeras=False` — verifierad juridisk person) lämnas i klartext.

    Pseudonymen är stabil INOM anropet: samma motpart får samma nummer, så en
    AI kan resonera om "Fiktiv Kund 2:s tre fakturor" utan att veta vem det är.
    """
    from dataclasses import replace as _replace

    pseudonym_for: dict[str, str] = {}
    ut: list = []
    for post in poster:
        ar_kund = type(post).__name__ == "Kundpost"
        namn = post.kund if ar_kund else post.leverantor

        if not getattr(post, "ska_maskeras", False) or post.maskerad:
            ut.append(post)
            continue

        prefix = "Fiktiv Kund" if ar_kund else "Fiktiv Leverantör"
        nyckel = f"{prefix}|{namn}"
        if nyckel not in pseudonym_for:
            nummer = sum(1 for k in pseudonym_for if k.startswith(prefix)) + 1
            pseudonym_for[nyckel] = f"{prefix} {nummer} {PSEUDONYM_MARKOR}"

        pseudonym = pseudonym_for[nyckel]
        if ar_kund:
            ut.append(_replace(post, kund=pseudonym, maskerad=True))
        else:
            ut.append(_replace(post, leverantor=pseudonym, maskerad=True))
    return ut
