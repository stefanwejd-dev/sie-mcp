"""Motorn: registret över kontroller, körningen och sorteringen.

Motorn känner inte till någon enskild kontroll (B-3) — den itererar över ett
register som fylls genom dekoratorn `registrera`."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal

from domain_model import SIEFil
from vasentlighet import berakna_vasentlighet
from analysflode import berakna_standardtroskelvarden

from .modell import Fynd, Kontext, Kontroll
from .regelkalla import hamta_parameter, hamta_regel, kontroll_ider, las_register

_logger = logging.getLogger(__name__)

KONTROLLER: dict[str, Kontroll] = {}

_ALLVARLIGHETSRANG = {"avvikelse": 0, "observation": 1, "upplysning": 2}


def registrera(kontroll_id: str):
    """Dekorator. Kastar vid dubblettregistrering."""

    def dekorator(funktion: Kontroll) -> Kontroll:
        if kontroll_id in KONTROLLER:
            raise ValueError(f"Kontroll {kontroll_id} är redan registrerad.")
        KONTROLLER[kontroll_id] = funktion
        return funktion

    return dekorator


def _bygg_kontext(
    sie: SIEFil,
    *,
    idag: date,
    arsnr: int,
    utdrag=None,
    avstamningskonto: str | None = None,
) -> Kontext:
    register = las_register()
    parametrar = dict(register["parametrar"])
    parametrar["kontolistor"] = register["kontolistor"]

    vasentlighetstal: Decimal | None = None
    utfallsvasentlighet: Decimal | None = None
    try:
        tal = berakna_vasentlighet(sie)
        if tal.omsattning != 0:
            vasentlighetstal, utfallsvasentlighet = berakna_standardtroskelvarden(
                tal.omsattning
            )
    except Exception:
        vasentlighetstal = None
        utfallsvasentlighet = None

    tolerans = hamta_parameter("tolerans_kronor")
    if tolerans is None:
        tolerans = Decimal("1.00")

    return Kontext(
        sie=sie,
        idag=idag,
        arsnr=arsnr,
        vasentlighetstal=vasentlighetstal,
        utfallsvasentlighet=utfallsvasentlighet,
        parametrar=parametrar,
        tolerans=tolerans,
        utdrag=utdrag,
        avstamningskonto=avstamningskonto,
    )


def _sorteringsnyckel(fynd: Fynd):
    belopp = abs(fynd.belopp) if fynd.belopp is not None else Decimal("0")
    return (
        _ALLVARLIGHETSRANG.get(fynd.allvarlighet, 99),
        -belopp,
        fynd.kontroll_id,
        fynd.konton,
        fynd.verifikationer,
    )


def kor_kontroller(
    sie: SIEFil,
    *,
    idag: date,
    arsnr: int = 0,
    endast: set[str] | None = None,
    utdrag=None,
    avstamningskonto: str | None = None,
) -> list[Fynd]:
    # I-4: varje registrerad kontroll måste finnas i regelregistret. Fail-closed.
    kända_ider = kontroll_ider()
    for kontroll_id in KONTROLLER:
        if kontroll_id not in kända_ider:
            raise ValueError(
                f"Kontroll {kontroll_id} är registrerad men saknas i regelregistret."
            )

    kontext = _bygg_kontext(
        sie, idag=idag, arsnr=arsnr, utdrag=utdrag, avstamningskonto=avstamningskonto
    )

    kontroller_att_köra = KONTROLLER
    if endast is not None:
        kontroller_att_köra = {
            kontroll_id: funktion
            for kontroll_id, funktion in KONTROLLER.items()
            if kontroll_id in endast
        }

    alla_fynd: list[Fynd] = []
    for kontroll_id, funktion in kontroller_att_köra.items():
        try:
            fynd_lista = funktion(kontext)
        except Exception:
            # Undantagstexten stannar LOKALT. `motivering` går rakt ut till
            # MCP-klienten (spiris_rag._fynd_till_dict), och ett undantag bär
            # okontrollerad text — en KeyError bär sin nyckel, en ValueError vad
            # som helst kontrollen råkade formatera in. Maskeringen (I-3) täcker
            # SIEFil:ens fritextfält, inte vad en modul stoppar i ett undantag.
            # Samma disciplin som mcp_server._fel_vid_inlasning: logga lokalt,
            # returnera generiskt. Kontroll-id:t räcker för att I-6 ska fylla
            # sin funktion — det säger VILKEN kontroll som föll.
            _logger.exception("Kontroll %s kastade ett fel", kontroll_id)
            alla_fynd.append(
                Fynd(
                    kontroll_id="K-00",
                    rubrik="Kontrollen kunde inte köras",
                    allvarlighet="upplysning",
                    motivering=(
                        f"Kontroll {kontroll_id} kunde inte köras. "
                        f"Felet är loggat lokalt."
                    ),
                )
            )
            continue
        alla_fynd.extend(fynd_lista)

    # Steg 6: väsentlighet och regelhänvisning sätts centralt, inte per kontroll.
    berikade: list[Fynd] = []
    for fynd in alla_fynd:
        regel = fynd.regel
        if regel is None:
            regel = hamta_regel(fynd.kontroll_id)

        vasentlig = fynd.vasentlig
        if (
            vasentlig is None
            and fynd.belopp is not None
            and kontext.utfallsvasentlighet is not None
        ):
            vasentlig = abs(fynd.belopp) >= kontext.utfallsvasentlighet

        fynd = replace(fynd, regel=regel, vasentlig=vasentlig)
        berikade.append(fynd)

    berikade.sort(key=_sorteringsnyckel)
    return berikade
