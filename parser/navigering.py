"""navigering — dashboardlayoutens flikstruktur: etiketter, åtgärdsbadge och
den sticky-CSS som håller toppnavigeringen synlig vid scroll.

UI-fri (ingen streamlit-import) av exakt samma skäl som app_vy.py och fpa_vy.py:
både badge-beslutet och etikettbygget ska kunna beteendetestas utan UI-runtime.
app.py gör bara `st.tabs(flikettiketter(status), key=NAV_NYCKEL)` och renderar
CSS-strängen — ingen layoutlogik lever i skriptet.

Varje flik är en egen funktionsyta:

  ⚙️ Datastatus        — passiv systeminformation om den inlästa datan.
  🔴/🟢 Åtgärder        — allt som kräver ett mänskligt beslut (human-in-the-loop).
  📊 Rapporter          — FP&A-dashboarden (P&L, balans, KPI, kassaflöde).
  📈 Investeringskalkyl — what-if, Sankey och (kommande) capital stack.
  🤖 AI-Assistent       — ISA 450-analysen och samtalsytan.

Badgen på Åtgärder är röd så snart NÅGOT väntar på handläggning, annars grön.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from domain_model import SIEFil
from sekretesslager import Maskeringsresultat

# st.tabs(key=...) sätter CSS-klassen .st-key-<key> på samma element som redan
# bär .stTabs. Det gör att sticky-regeln kan riktas mot ENBART toppnavigeringen.
NAV_NYCKEL = "huvudnav"

FLIK_DATASTATUS = "⚙️ Datastatus"
FLIK_RAPPORTER = "📊 Rapporter"
FLIK_INVESTERINGSKALKYL = "📈 Investeringskalkyl"
FLIK_AI_ASSISTENT = "🤖 AI-Assistent"

_ATGARDER_BASNAMN = "Åtgärder"

BADGE_ATGARD_KRAVS = "🔴"
BADGE_INGET_ATT_GORA = "🟢"

# Streamlits egen apphuvud är fixerat överst; sticky-offseten måste börja under
# det, annars glider flikraden in bakom huvudet. Justerbar på ett ställe.

# Streamlit exponerar ingen CSS-variabel för bakgrundsfärgen (temat appliceras
# via JS), så den sticky flikraden måste få en egen ogenomskinlig bakgrund —
# annars scrollar innehållet synligt igenom den.


@dataclass(frozen=True)
class Verifikationsavvikelse:
    """En obehandlad avvikelse i en verifikation, redo att listas i Åtgärder."""

    plats: str
    beskrivning: str


@dataclass(frozen=True)
class Åtgärdsstatus:
    """Vad som väntar på ett mänskligt beslut, plus den färdiga fliketiketten.

    Härledda fält (badge, etikett) lagras i stället för att räknas ut i UI-lagret
    — samma mönster som app_vy.Risksammanfattning."""

    antal_maskeringsbehov: int
    antal_verifikationsavvikelser: int
    antal_totalt: int
    kräver_åtgärd: bool
    badge: str
    etikett: str
    # Steg 2: utkast som en MCP-klient föreslagit och som väntar på användarens
    # godkännande. Default 0 håller befintliga konstruktionsanrop oförändrade.
    antal_utkast: int = 0


def ohanterade_maskeringsbehov(maskeringsresultat: Maskeringsresultat | None) -> int:
    """Antal maskeringsbehov som fortfarande väntar på ett mänskligt beslut.

    "väntar_granskning" är sekretesslagrets egen status för just detta — vi
    räknar aldrig hela behovslistan, eftersom den bär med sig även redan
    granskade behov. Ingen data inläst betyder 0 att åtgärda (inte "okänt")."""
    if maskeringsresultat is None:
        return 0
    return sum(
        1
        for behov in maskeringsresultat.maskeringsbehov
        if behov.status == "väntar_granskning"
    )


def hitta_verifikationsavvikelser(
    sie: SIEFil | None, maskeringsresultat: Maskeringsresultat | None
) -> list[Verifikationsavvikelse]:
    """Obehandlade avvikelser i bokföringen, för den röda badgen på Åtgärder.

    Se hantverksbok/UI_ATGARDER_I_VYN.md §5. Kopplad till
    bokslutskontroll.kor_kontroller (lager 1) — bara fynd med allvarlighet
    `avvikelse` räknas in; `observation` och `upplysning` syns i Bokslut-
    rummet men gör inte navigeringen röd (annars är badgen alltid röd och
    slutar betyda något).

    `sie` är den RÅA SIEFil:en (samma som Bokslut-rummet kör motorn på, U-2)
    — `maskeringsresultat` tas fortfarande emot i signaturen men används inte
    här; badgen räknar bara, den visar ingen fritext.

    "Obehandlat": i dag ger ingen av grupp A–C:s kontroller ett förslag med
    knapp (`Fynd.forslag` är alltid `None`), så det finns ännu ingen handling
    att markera ett fynd som åtgärdat med. Alla `avvikelse`-fynd räknas
    därför in tills vidare — filtreringen blir en riktig fråga först när
    lager 2 börjar producera förslag.

    Kastar aldrig: ett fel i sökningen får inte tyst tömma listan och måla
    badgen grön — det fångas här och loggas lokalt, listan blir tom."""
    if sie is None:
        return []
    try:
        from datetime import date as _date

        from bokslutskontroll import kor_kontroller

        fynd = kor_kontroller(sie, idag=_date.today())
    except Exception as e:  # noqa: BLE001 — badgen får aldrig fällas av detta
        print(f"[navigering] Kunde inte köra bokslutskontroll ({type(e).__name__}).", file=sys.stderr)
        return []

    return [
        Verifikationsavvikelse(
            plats=", ".join(f.verifikationer) or ", ".join(f.konton) or f.kontroll_id,
            beskrivning=f"{f.kontroll_id}: {f.rubrik}",
        )
        for f in fynd
        if f.allvarlighet == "avvikelse"
    ]


def bygg_atgardsstatus(
    antal_maskeringsbehov: int,
    avvikelser: list[Verifikationsavvikelse],
    antal_utkast: int = 0,
) -> Åtgärdsstatus:
    """Slår ihop åtgärdskällorna till en status. Röd badge så snart minst en
    post väntar — grön bara när alla källor är tomma.

    Utkasten (Steg 2) räknas med: ett förslag från en MCP-klient som ligger
    ogranskat är precis lika mycket ett väntande mänskligt beslut som ett
    maskeringsbehov är det, och ska synas i badgen. Utan det kan ett utkast bli
    liggande utan att någon märker det — och blir det liggande ett dygn kan det
    inte längre godkännas."""
    antal_avvikelser = len(avvikelser)
    antal_totalt = antal_maskeringsbehov + antal_avvikelser + antal_utkast
    kräver_åtgärd = antal_totalt > 0
    badge = BADGE_ATGARD_KRAVS if kräver_åtgärd else BADGE_INGET_ATT_GORA
    etikett = f"{badge} {_ATGARDER_BASNAMN}"
    if kräver_åtgärd:
        etikett = f"{etikett} ({antal_totalt})"

    return Åtgärdsstatus(
        antal_maskeringsbehov=antal_maskeringsbehov,
        antal_verifikationsavvikelser=antal_avvikelser,
        antal_totalt=antal_totalt,
        kräver_åtgärd=kräver_åtgärd,
        badge=badge,
        etikett=etikett,
        antal_utkast=antal_utkast,
    )


