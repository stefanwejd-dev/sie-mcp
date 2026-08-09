"""svarskontrakt — Pydantic-modeller och validering för strukturerade AI-svar.

Definierar det SCHEMA som AI-modellen ska producera när svaret innehåller
strukturerad data (tabeller, diagram). Kontraktet säkerställer att
presentationen är DETERMINISTISK och kontrollerad av vår renderingsmotor
(chatt_renderare.py) — inte av modellens variabla markdown.

Två ingångspunkter:

    validera_svar(raw_json)       för icke-agentläge (modellen svarar med
                                  rå text som KAN vara JSON)
    validera_svar_dict(data)      för agentläge (Anthropics tool use ger
                                  redan parsad dict)

Båda returnerar StruktureratSvar vid framgång, None vid misslyckande.
Fallback sker tyst (loggning, inget fel för användaren).

Modulen är MEDVETET fri från Streamlit och leverantörsberoenden: schemat är
kontraktet BÅDE chatt_klient.py (Anthropic, tool use) och ollama_klient.py
(lokal modell, JSON i text) lutar sig mot, och app.py:s renderingsval
bygger på. Därför bor även promptbeskrivningen av schemat
(KONTRAKT_INSTRUKTION) och verktygsschemat (svarskontrakt_verktygsschema)
här, bredvid modellerna — samma princip som AGENT_VERKTYG i chatt_klient.py:
leverantörerna får ha egna promptTONER, men schemat ska ha EN källa.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema-modeller
# ---------------------------------------------------------------------------

class KolumnDef(BaseModel):
    """Definition av en tabellkolumn."""
    nyckel: str                      # t.ex. "belopp_inkl_moms"
    rubrik: str                      # t.ex. "Belopp inkl. moms"
    typ: Literal["text", "belopp", "datum", "procent"] = "text"
    # hogerstall exponeras MEDVETET inte i verktygsschemat: renderaren
    # högerställer redan allt med typ belopp/procent. Fältet finns kvar som
    # en manuell override för framtida kod som bygger blocken själv.
    hogerstall: bool = False


class TabellBlock(BaseModel):
    """Ett tabellblock i ett strukturerat svar."""
    typ: Literal["tabell"] = "tabell"
    rubrik: str | None = None        # t.ex. "Obetalda leverantörsfakturor"
    # En tabell utan kolumner går inte att rendera — avvisa hellre hela
    # svaret och falla tillbaka till text än att visa en tom ruta.
    kolumner: list[KolumnDef] = Field(min_length=1)
    rader: list[dict[str, Any]]      # varje rad mappar mot kolumnernas nycklar
    summa_rad: dict[str, Any] | None = None  # valfri totalsumma-rad


class DiagramBlock(BaseModel):
    """Ett diagramblock (renderas av Plotly i chatt_renderare.py)."""
    typ: Literal["diagram"] = "diagram"
    diagram_typ: Literal["stapel", "linje", "cirkel"]
    rubrik: str
    kategori_falt: str               # kolumnnyckel för x-axel/etiketter
    varde_falt: str                  # kolumnnyckel för y-axel/värden
    data: list[dict[str, Any]]


class TextBlock(BaseModel):
    """Ett frittextblock (renderas med st.markdown)."""
    typ: Literal["text"] = "text"
    innehall: str = Field(min_length=1)   # markdown tillåten


class StruktureratSvar(BaseModel):
    """Rotkontraktet för ett strukturerat AI-svar."""
    # Minst ett block: ett tomt svar ska falla tillbaka till vanlig text i
    # stället för att rendera en tom chattbubbla.
    block: list[TextBlock | TabellBlock | DiagramBlock] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)\n\s*```",
    re.DOTALL,
)


def _extrahera_json(text: str) -> str | None:
    """Plockar ut JSON ur texten.

    Strategier (i ordning):
    1. Hela texten är JSON (börjar med '{')
    2. JSON inbäddad i ```json ... ``` code fences
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    
    # Fallback 3: Hitta första { och sista } (om AI:n lade till text före/efter utan code fences)
    start_idx = stripped.find("{")
    end_idx = stripped.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return stripped[start_idx:end_idx+1]
        
    return None


# ---------------------------------------------------------------------------
# Publika valideringsfunktioner
# ---------------------------------------------------------------------------

def validera_svar(raw_text: str) -> StruktureratSvar | None:
    """Försök parsa och validera ett modellsvar (rå text) mot kontraktet.

    Returnerar None om svaret inte följer kontraktet — anroparen faller
    tillbaka till vanlig markdown-rendering. Inga fel visas för användaren;
    misslyckanden loggas tyst.

    Tolerant parsning:
    - Accepterar JSON som hela texten
    - Accepterar JSON inbäddad i ```json code fences
    """
    json_str = _extrahera_json(raw_text)
    if json_str is None:
        return None  # Inte JSON alls — vanlig markdown, inget att logga
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        log.debug("Svarskontraktet: ogiltig JSON: %s", exc)
        return None
    return validera_svar_dict(data)


def validera_svar_dict(data: dict[str, Any] | Any) -> StruktureratSvar | None:
    """Validera en redan parsad dict mot kontraktet.

    Används i agentläge där Anthropics tool use levererar dict direkt
    (indata från verktygsanropet). Returnerar None vid valideringsfel.
    """
    if not isinstance(data, dict):
        log.debug("Svarskontraktet: data är inte en dict: %s", type(data))
        return None
    try:
        svar = StruktureratSvar.model_validate(data)
    except ValidationError as exc:
        log.debug("Svarskontraktet: Pydantic-valideringsfel: %s", exc)
        return None
    # Kontrollera att alla rader har giltiga nycklar relativt kolumndefinitionerna
    for block in svar.block:
        if isinstance(block, TabellBlock):
            giltiga_nycklar = {k.nyckel for k in block.kolumner}
            for rad_index, rad in enumerate(block.rader):
                okanda = set(rad.keys()) - giltiga_nycklar
                if okanda:
                    log.debug(
                        "Svarskontraktet: rad %d har okända nycklar %s "
                        "(tillåtna: %s) — ignoreras",
                        rad_index, okanda, giltiga_nycklar,
                    )
                    # Ta inte bort okända nycklar — tolerant, men logga
    return svar


# ---------------------------------------------------------------------------
# Verktygsschema (agentläge) och promptinstruktion (icke-agentläge)
# ---------------------------------------------------------------------------

# MEDVETET handskrivet i stället för StruktureratSvar.model_json_schema():
# Pydantic genererar $defs/$ref och anyOf-unioner, och stödet för dem är
# ojämnt både i Anthropics tool use och (särskilt) i de mindre lokala
# modellerna bakom Ollama. Här är allt inlinat och block-objektet är ETT
# permissivt objekt där bara "typ" är obligatoriskt — vilka fält som gäller
# per typ står i beskrivningarna. Den RIKTIGA kontrollen görs ändå av
# Pydantic i validera_svar_dict; ett block som saknar sina fält faller
# tillbaka till vanlig text i stället för att renderas trasigt.
#
# test_svarskontrakt.py vaktar att nycklarna här inte glider isär från
# modellernas fältnamn.
_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "typ": {
            "type": "string",
            "enum": ["text", "tabell", "diagram"],
            "description": (
                "Blockets typ: 'text' för löpande resonemang, 'tabell' för "
                "listor/tabelldata, 'diagram' när en graf säger mer än raderna."
            ),
        },
        "innehall": {
            "type": "string",
            "description": "Endast typ=text: själva texten (markdown tillåten).",
        },
        "rubrik": {
            "type": "string",
            "description": (
                "Rubrik ovanför tabellen eller diagrammet (typ=tabell/diagram). "
                "Obligatorisk för diagram."
            ),
        },
        "kolumner": {
            "type": "array",
            "description": (
                "Endast typ=tabell: kolumndefinitioner i den ordning de ska visas."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "nyckel": {
                        "type": "string",
                        "description": (
                            "Fältnamnet raderna använder, t.ex. 'belopp_inkl_moms'."
                        ),
                    },
                    "rubrik": {
                        "type": "string",
                        "description": "Kolumnrubriken som visas, t.ex. 'Inkl. moms'.",
                    },
                    "typ": {
                        "type": "string",
                        "enum": ["text", "belopp", "datum", "procent"],
                        "description": (
                            "Styr formatering och högerställning. 'belopp' ger "
                            "svensk tusentalsformatering och 'kr'."
                        ),
                    },
                },
                "required": ["nyckel", "rubrik"],
            },
        },
        "rader": {
            "type": "array",
            "description": (
                "Endast typ=tabell: ett objekt per rad. Nycklarna MÅSTE vara "
                "exakt de 'nyckel'-värden som angetts i kolumner. Belopp som "
                "rena tal utan mellanslag, valutatecken eller 'kr' (24500.5, "
                "inte '24 500,50 kr') — appen formaterar dem. Procent som "
                "decimaltal där 0.15 betyder 15 %."
            ),
            "items": {"type": "object"},
        },
        "summa_rad": {
            "type": "object",
            "description": (
                "Valfri totalsummerad rad, samma nycklar som raderna. Visas "
                "avskild med linje och fet stil."
            ),
        },
        "diagram_typ": {
            "type": "string",
            "enum": ["stapel", "linje", "cirkel"],
            "description": "Endast typ=diagram.",
        },
        "kategori_falt": {
            "type": "string",
            "description": "Endast typ=diagram: nyckeln för kategori-/x-axeln.",
        },
        "varde_falt": {
            "type": "string",
            "description": "Endast typ=diagram: nyckeln för värde-/y-axeln.",
        },
        "data": {
            "type": "array",
            "description": (
                "Endast typ=diagram: ett objekt per datapunkt med "
                "kategori_falt och varde_falt som nycklar."
            ),
            "items": {"type": "object"},
        },
    },
    "required": ["typ"],
}

_VERKTYGSSCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "block": {
            "type": "array",
            "description": (
                "Svarets block i visningsordning. Typiskt ett kort textblock "
                "följt av en tabell."
            ),
            "items": _BLOCK_SCHEMA,
        },
    },
    "required": ["block"],
}


# Promptbeskrivning för det JSON-baserade spåret (icke-agentläge, där ingen
# tool use finns att luta sig mot). Bor här och inte i chatt_klient.py/
# ollama_klient.py för att schemat ska beskrivas på EXAKT ett ställe —
# leverantörsfilerna har egna kopior av sina systemprompter i övrigt, men
# två divergerande beskrivningar av samma schema vore en tyst felkälla.
KONTRAKT_INSTRUKTION = """Presentation av listor och tabelldata:
- Innehåller svaret en LISTA eller TABELL (t.ex. obetalda leverantörs-
  fakturor, kontosaldon, transaktioner) ska HELA svaret vara ETT
  JSON-objekt enligt schemat nedan — ingen text före eller efter, inga
  kodstaket. Appen renderar då raka kolumner, högerställda belopp och en
  diagramknapp åt dig.
- Är svaret ren löpande text utan lista eller tabell: svara som vanligt i
  vanlig text. Tvinga aldrig in ett resonemang i JSON.
- Belopp skrivs som RENA TAL utan mellanslag, valutatecken eller "kr"
  (24500.5, inte "24 500,50 kr"). Procent skrivs som decimaltal, där 0.15
  betyder 15 %. Appen sköter all formatering.
- Varje rad i "rader" använder EXAKT de nycklar du angett i "kolumner".
- Maskerade namn ([BOLAG_1], [PERSON_2]) skrivs av precis som de står.

Schema (exempel som visar alla delar):
{"block": [
  {"typ": "text", "innehall": "Fyra fakturor är obetalda."},
  {"typ": "tabell", "rubrik": "Obetalda leverantörsfakturor",
   "kolumner": [
     {"nyckel": "leverantor", "rubrik": "Leverantör", "typ": "text"},
     {"nyckel": "forfaller", "rubrik": "Förfaller", "typ": "datum"},
     {"nyckel": "exkl_moms", "rubrik": "Exkl. moms", "typ": "belopp"},
     {"nyckel": "inkl_moms", "rubrik": "Inkl. moms", "typ": "belopp"}],
   "rader": [
     {"leverantor": "[BOLAG_1]", "forfaller": "2026-08-15",
      "exkl_moms": 19600, "inkl_moms": 24500}],
   "summa_rad": {"leverantor": "Summa", "exkl_moms": 19600,
                 "inkl_moms": 24500}}]}"""


def svarskontrakt_verktygsschema() -> dict[str, Any]:
    """Returnerar input_schema för verktyget presentera_strukturerat_svar.

    Djupkopia varje gång: schemat hamnar i AGENT_VERKTYG som i sin tur
    skickas vidare till både Anthropic och (omskrivet) Ollama — ingen av
    dem ska kunna mutera modulens egen dict.
    """
    return copy.deepcopy(_VERKTYGSSCHEMA)


def svarskontrakt_json_schema() -> dict[str, Any]:
    """Pydantics egengenererade JSON Schema för StruktureratSvar.

    Används INTE som verktygsschema (se kommentaren vid _BLOCK_SCHEMA) —
    finns kvar som referens vid felsökning och för schema-tester.
    """
    return StruktureratSvar.model_json_schema()


# ---------------------------------------------------------------------------
# Text-representation (historik och fallback)
# ---------------------------------------------------------------------------

_MAX_RADER_I_SAMMANFATTNING = 20


def _celltext(varde: Any) -> str:
    """Rå cellrepresentation för textsammanfattningen — ingen formatering
    (modellen läser den, inte användaren). Pipe-tecken escapas så en cell
    inte spräcker markdown-tabellen, radbrytningar plattas till."""
    if varde is None:
        return ""
    return str(varde).replace("|", "\\|").replace("\n", " ")


def _tabell_som_text(tabell: TabellBlock, max_rader: int) -> str:
    rubriker = [kol.rubrik for kol in tabell.kolumner]
    rader = [
        "| " + " | ".join(rubriker) + " |",
        "|" + "---|" * len(rubriker),
    ]
    for rad in tabell.rader[:max_rader]:
        rader.append(
            "| " + " | ".join(_celltext(rad.get(kol.nyckel)) for kol in tabell.kolumner) + " |"
        )
    if tabell.summa_rad:
        rader.append(
            "| "
            + " | ".join(_celltext(tabell.summa_rad.get(kol.nyckel)) for kol in tabell.kolumner)
            + " |"
        )
    if len(tabell.rader) > max_rader:
        rader.append(f"… ({len(tabell.rader)} rader totalt)")
    if tabell.rubrik:
        rader.insert(0, f"**{tabell.rubrik}**")
    return "\n".join(rader)


def text_sammanfattning(
    svar: StruktureratSvar, max_rader: int = _MAX_RADER_I_SAMMANFATTNING
) -> str:
    """Plattar ut ett strukturerat svar till vanlig text.

    Två syften, båda nödvändiga:

    1. ChattMeddelande.text måste vara NÅGOT — i agentläget återsänds hela
       historiken (inklusive assistentens svar) vid varje nytt anrop, och
       ett tomt meddelande avvisas av API:t. Här får modellen dessutom
       tillbaka vad den faktiskt svarade, så en följdfråga ("vilken är
       störst?") går att besvara.
    2. Fallback i UI:t om renderingen av någon anledning inte går igenom.

    Långa tabeller kapas vid max_rader — historiken ska inte svälla med
    hundratals rader som redan finns i kontexten.
    """
    delar: list[str] = []
    for block in svar.block:
        if isinstance(block, TextBlock):
            delar.append(block.innehall)
        elif isinstance(block, TabellBlock):
            delar.append(_tabell_som_text(block, max_rader))
        elif isinstance(block, DiagramBlock):
            delar.append(f"[Diagram: {block.rubrik}]")
    return "\n\n".join(delar).strip() or "(strukturerat svar)"


def med_inledande_text(svar: StruktureratSvar, text: str | None) -> StruktureratSvar:
    """Lägger modellens fria kommentar först som ett textblock.

    I agentläget kan modellen skicka BÅDE en kommentar ("Här är de fyra
    obetalda fakturorna:") och verktygsanropet i samma svar. Kommentaren
    skulle annars tappas bort, eftersom renderingen bara visar blocken.
    Tom eller blank text lämnar svaret orört.
    """
    if text is None or not text.strip():
        return svar
    svar.block.insert(0, TextBlock(innehall=text.strip()))
    return svar
