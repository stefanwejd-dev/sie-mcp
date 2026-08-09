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
    """SEAM (platshållare): obehandlade avvikelser i verifikationerna.

    Returnerar tills vidare ALLTID en tom lista — ingen avvikelseregel är
    beslutad än. Signaturen tar redan emot den maskerade SIEFil:en och
    maskeringsresultatet, så en riktig regel (obalanserade verifikat, saknad
    vertext, kontotypavvikelser från kontotyp_vakt, ISA 450-felaktigheter …)
    kan kopplas in här utan att vare sig badge-logiken, fliken eller app.py rörs.

    När regeln byggs: returnera avvikelser, kasta aldrig. Ett fel i sökningen
    får inte tyst tömma åtgärdslistan och måla badgen grön."""
    return []


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


