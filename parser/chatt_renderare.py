"""chatt_renderare — deterministisk rendering av strukturerade AI-svar.

Tar ett validerat StruktureratSvar (från svarskontrakt.py) och renderar det
med Streamlit-komponenter: HTML-tabeller med Excel-känsla (zebra-randning,
vertikala kantlinjer, högerställda belopp) och Plotly-diagram.

Valet att använda en egen HTML-tabell via st.markdown(unsafe_allow_html=True)
i stället för st.dataframe motiveras av att st.dataframe inte ger full
CSS-kontroll: vi kan inte applicera zebra-randning, vertikala kantlinjer
eller selektiv högerställning per kolumn med den.

CSS scopas med klassen 'sie-chatt-tabell' — inga andra tabeller i appen
påverkas.

Fail-closed på samma sätt som resten av chattkedjan: rendera_strukturerat_svar
returnerar False i stället för att krascha om ett sparat svar inte går att
tolka, och anroparen (app.py) faller då tillbaka till vanlig text.
"""

from __future__ import annotations

import html
import logging
from typing import Any

import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from fpa_vy import (
    DIAGRAMTITEL_STORLEK,
    FARG_HISTORISKT_SEN_KUND,
    FARG_INTAKT,
    FARG_KASSA,
    FARG_KOSTNAD,
    FARG_MOMS,
    FARG_OVRIGT_TILLGANG,
    FARG_RESULTAT,
    LEGEND_STORLEK,
    TYPSNITT,
    formatera_kr,
    formatera_procent,
)
from svarskontrakt import DiagramBlock, StruktureratSvar, TabellBlock, TextBlock

log = logging.getLogger(__name__)

# Kategorifärger för cirkeldiagram: befintliga appfärger i en fast ordning —
# inget nytt designsystem, bara en cykel över paletten i fpa_vy.py.
_KATEGORIFARGER = (
    FARG_RESULTAT,
    FARG_INTAKT,
    FARG_KOSTNAD,
    FARG_MOMS,
    FARG_HISTORISKT_SEN_KUND,
    FARG_KASSA,
    FARG_OVRIGT_TILLGANG,
)


# ---------------------------------------------------------------------------
# CSS — injiceras en gång per app-laddning (idempotent)
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Formatering per kolumntyp
# ---------------------------------------------------------------------------

# Rensar bort ALLA blanktecken (även icke-brytande) och apostrof — de
# tusentalsavgränsare som dyker upp i modellgenererade belopp.
def _utan_tusentalsavgransare(text: str) -> str:
    return "".join(t for t in text if not t.isspace() and t != "'")


def _till_tal(varde: Any) -> float | None:
    """Tolkar ett värde som tal, tolerant mot modeller som inte lyssnar.

    Schemat säger 'rena tal utan mellanslag eller kr' (se svarskontrakt.py),
    men en svagare modell skickar ändå "24 500,50 kr" ibland. Hellre tolka
    det rätt än att visa en högerställd sträng som inte går att summera
    eller rita. None när det verkligen inte är ett tal — då visas råvärdet
    som text.
    """
    if isinstance(varde, bool) or varde is None:
        return None
    if isinstance(varde, (int, float)):
        return float(varde)
    if not isinstance(varde, str):
        return None
    rensad = _utan_tusentalsavgransare(varde).replace("%", "")
    if rensad.lower().endswith("kr"):
        rensad = rensad[:-2]
    # Svensk decimalkomma, men bara när punkten inte redan används.
    if "," in rensad and "." not in rensad:
        rensad = rensad.replace(",", ".")
    try:
        return float(rensad)
    except ValueError:
        return None


def _formatera_cellvarde(varde: Any, typ: str) -> str:
    """Formatera ett cellvärde utifrån kolumnens typ.

    Använder samma formatering som resten av appen (fpa_vy.py) för
    konsekvent UX. Allt som inte går att tolka som tal skrivs ut som
    HTML-escapad text — modellsvar renderas som rå HTML här, så inget
    ovaliderat värde får slippa igenom oescapat.
    """
    if varde is None:
        return "–"
    if typ in ("belopp", "procent"):
        tal = _till_tal(varde)
        if tal is None:
            return html.escape(str(varde))
        return formatera_kr(tal) if typ == "belopp" else formatera_procent(tal)
    # text och datum — modellens sträng rakt av, escapad
    return html.escape(str(varde))


# ---------------------------------------------------------------------------
# HTML-tabellrendering
# ---------------------------------------------------------------------------

def _bygg_tabellhtml(tabell: TabellBlock) -> str:
    """Bygger en komplett HTML-tabell från ett TabellBlock.

    Returnerar en HTML-sträng redo att injiceras via
    st.markdown(html, unsafe_allow_html=True).
    """
    kolumner = tabell.kolumner
    hogerstallda = {k.nyckel for k in kolumner if k.hogerstall or k.typ in ("belopp", "procent")}

    delar: list[str] = []

    # Rubrik
    if tabell.rubrik:
        delar.append(f'<div class="sie-chatt-tabell-rubrik">{html.escape(tabell.rubrik)}</div>')

    # Wrappern gör breda tabeller sidscrollbara i stället för att spränga
    # chattbubblan på en smal skärm.
    delar.append('<div class="sie-chatt-tabell-wrap">')
    delar.append('<table class="sie-chatt-tabell">')

    # Thead
    delar.append("<thead><tr>")
    for kol in kolumner:
        klass = ' class="sie-hoger"' if kol.nyckel in hogerstallda else ""
        delar.append(f"<th{klass}>{html.escape(kol.rubrik)}</th>")
    delar.append("</tr></thead>")

    # Tbody — datarader
    delar.append("<tbody>")
    for rad in tabell.rader:
        delar.append("<tr>")
        for kol in kolumner:
            varde = rad.get(kol.nyckel)
            formaterat = _formatera_cellvarde(varde, kol.typ)
            klass = ' class="sie-hoger"' if kol.nyckel in hogerstallda else ""
            delar.append(f"<td{klass}>{formaterat}</td>")
        delar.append("</tr>")

    # Summa-rad (om den finns)
    if tabell.summa_rad:
        delar.append('<tr class="sie-summa-rad">')
        for kol in kolumner:
            varde = tabell.summa_rad.get(kol.nyckel)
            if varde is not None:
                formaterat = _formatera_cellvarde(varde, kol.typ)
            else:
                formaterat = ""
            klass = ' class="sie-hoger"' if kol.nyckel in hogerstallda else ""
            delar.append(f"<td{klass}>{formaterat}</td>")
        delar.append("</tr>")

    delar.append("</tbody></table></div>")

    return "".join(delar)


# ---------------------------------------------------------------------------
# Plotly-diagramgenerering
# ---------------------------------------------------------------------------

def _auto_diagram_typ(tabell: TabellBlock) -> str:
    """Välj lämpligaste diagramtyp automatiskt utifrån tabellens kolumner.

    Finns en datumkolumn är raderna en tidsserie → linje. Allt annat är en
    jämförelse mellan kategorier → stapel.
    """
    for kol in tabell.kolumner:
        if kol.typ == "datum":
            return "linje"
    return "stapel"


def _forsta_beloppskolumn(tabell: TabellBlock) -> str | None:
    """Returnerar nyckeln för den första belopps-/procentkolumnen."""
    for kol in tabell.kolumner:
        if kol.typ in ("belopp", "procent"):
            return kol.nyckel
    return None


def _forsta_kategorikolumn(tabell: TabellBlock, diagram_typ: str) -> str | None:
    """Returnerar nyckeln för kategori-/x-axeln.

    För ett linjediagram är datumkolumnen x-axeln även om en textkolumn
    står först (en fakturalista börjar typiskt med leverantören men ska
    ritas över förfallodatum). Annars första text-/datumkolumnen.
    """
    if diagram_typ == "linje":
        for kol in tabell.kolumner:
            if kol.typ == "datum":
                return kol.nyckel
    for kol in tabell.kolumner:
        if kol.typ in ("text", "datum"):
            return kol.nyckel
    return None


def _kolumnrubrik(tabell: TabellBlock, nyckel: str) -> str:
    """Hämta rubriken för en kolumnnyckel."""
    for kol in tabell.kolumner:
        if kol.nyckel == nyckel:
            return kol.rubrik
    return nyckel


def _bygg_diagram_fran_tabell(tabell: TabellBlock) -> go.Figure | None:
    """Generera ett Plotly-diagram från ett TabellBlock.

    Returnerar None om tabellen inte har tillräcklig data för ett diagram
    (inga rader, ingen kategorikolumn eller inga siffror att rita) — då
    visar renderaren en förklarande caption i stället för ett tomt diagram.
    """
    diagram_typ = _auto_diagram_typ(tabell)
    kategori_nyckel = _forsta_kategorikolumn(tabell, diagram_typ)
    varde_nyckel = _forsta_beloppskolumn(tabell)

    if kategori_nyckel is None or varde_nyckel is None or not tabell.rader:
        return None

    kategorier = [str(rad.get(kategori_nyckel, "")) for rad in tabell.rader]
    varden = [_till_tal(rad.get(varde_nyckel)) for rad in tabell.rader]
    if all(v is None for v in varden):
        return None
    varden = [0.0 if v is None else v for v in varden]

    namn = _kolumnrubrik(tabell, varde_nyckel)
    if diagram_typ == "linje":
        fig = go.Figure(go.Scatter(
            x=kategorier,
            y=varden,
            mode="lines+markers",
            marker=dict(size=8, color=FARG_INTAKT),
            line=dict(color=FARG_INTAKT, width=2.5),
            name=namn,
        ))
    else:  # stapel — negativa belopp i kostnadsfärgen, som resten av appen
        fig = go.Figure(go.Bar(
            x=kategorier,
            y=varden,
            marker_color=[FARG_INTAKT if v >= 0 else FARG_KOSTNAD for v in varden],
            name=namn,
        ))

    _standardlayout(fig, tabell.rubrik or namn)
    return fig


def _standardlayout(fig: go.Figure, rubrik: str) -> None:
    """Gemensam layout för chattens diagram — samma typsnitt och titelstorlek
    som dashboardens diagram (fpa_vy.py), så chatten inte får ett eget
    utseende."""
    fig.update_layout(
        title=dict(text=rubrik, font=dict(size=DIAGRAMTITEL_STORLEK, family=TYPSNITT)),
        font=dict(family=TYPSNITT, size=LEGEND_STORLEK),
        margin=dict(t=50, b=40, l=10, r=24),
        height=380,
        yaxis=dict(separatethousands=True),
        showlegend=False,
    )


def _diagramdata(block: DiagramBlock) -> tuple[list[str], list[float]]:
    """Kategorier och värden ur ett DiagramBlock. Värden som inte går att
    tolka som tal blir 0 — ett diagram ska aldrig krascha renderingen."""
    kategorier = [str(rad.get(block.kategori_falt, "")) for rad in block.data]
    varden = [_till_tal(rad.get(block.varde_falt)) or 0.0 for rad in block.data]
    return kategorier, varden


def _bygg_cirkeldiagram(block: DiagramBlock) -> go.Figure:
    """Bygg ett cirkeldiagram (donut) från ett DiagramBlock."""
    kategorier, varden = _diagramdata(block)
    fig = go.Figure(go.Pie(
        labels=kategorier,
        values=varden,
        hole=0.4,
        marker=dict(
            colors=[_KATEGORIFARGER[i % len(_KATEGORIFARGER)] for i in range(len(kategorier))]
        ),
    ))
    _standardlayout(fig, block.rubrik)
    # Cirkeldiagrammet behöver sin legend — färgerna är enda kopplingen
    # mellan tårtbit och kategori.
    fig.update_layout(showlegend=True)
    return fig


def _bygg_diagram_fran_block(block: DiagramBlock) -> go.Figure:
    """Bygg ett Plotly-diagram från ett DiagramBlock (modellen har valt typ
    själv, till skillnad från tabellknappens auto-val)."""
    if block.diagram_typ == "cirkel":
        return _bygg_cirkeldiagram(block)

    kategorier, varden = _diagramdata(block)
    if block.diagram_typ == "linje":
        fig = go.Figure(go.Scatter(
            x=kategorier, y=varden,
            mode="lines+markers",
            marker=dict(size=8, color=FARG_INTAKT),
            line=dict(color=FARG_INTAKT, width=2.5),
        ))
    else:  # stapel
        fig = go.Figure(go.Bar(
            x=kategorier, y=varden,
            marker_color=[FARG_INTAKT if v >= 0 else FARG_KOSTNAD for v in varden],
        ))

    _standardlayout(fig, block.rubrik)
    return fig


# ---------------------------------------------------------------------------
# Publika Streamlit-renderingsfunktioner
# ---------------------------------------------------------------------------

import stil

def injicera_chatt_css() -> None:
    """Injicera CSS för chattabeller. Idempotent — säkert att anropa flera
    gånger per Streamlit-rerun."""
    tematyp = getattr(getattr(getattr(st, "context", None), "theme", None), "type", None)
    st.markdown(stil.global_css(stil.bakgrundsfarg(tematyp)), unsafe_allow_html=True)


def _rendera_tabell(tabell: TabellBlock, meddelande_index: int, block_index: int) -> None:
    """Tabell + diagramknapp. Diagrammet är MEDVETET manuellt: ett svar med
    fem fakturarader behöver sällan en graf, och en automatisk sådan skulle
    knuffa ned nästa fråga utanför skärmen."""
    st.markdown(_bygg_tabellhtml(tabell), unsafe_allow_html=True)

    diagram_nyckel = f"visa_diagram_{meddelande_index}_{block_index}"
    visas = st.session_state.get(diagram_nyckel, False)
    if st.button(
        "📊 Dölj diagram" if visas else "📊 Visa som diagram",
        key=f"knapp_diagram_{meddelande_index}_{block_index}",
    ):
        # Samma mönster som chattens valknappar i app.py: sätt läget och kör
        # om direkt, så knappens egen etikett hinner uppdateras.
        st.session_state[diagram_nyckel] = not visas
        st.rerun()

    if visas:
        fig = _bygg_diagram_fran_tabell(tabell)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")
        else:
            st.caption(
                "Tabellen saknar tillräckliga belopps-/kategorikolumner "
                "för att generera ett diagram."
            )


def rendera_strukturerat_svar(data: dict, meddelande_index: int) -> bool:
    """Rendera ett strukturerat svar (dict från ChattMeddelande.strukturerat).

    Hanterar TextBlock, TabellBlock och DiagramBlock i ordning. Under varje
    TabellBlock visas en '📊 Visa som diagram'-knapp.

    Returnerar False utan att rita något om dicten inte går att tolka mot
    kontraktet — anroparen (app.py) visar då meddelandets vanliga text i
    stället. Fail-closed: ett trasigt sparat svar ska aldrig kunna släcka
    hela chatten.

    Parametrar
    ----------
    data : dict
        Serialiserat StruktureratSvar (via .model_dump()).
    meddelande_index : int
        Meddelandets index i samtal_historik — ger diagramknapparna unika
        keys mellan meddelanden.
    """
    try:
        svar = StruktureratSvar.model_validate(data)
    except ValidationError as exc:
        log.debug("Chattrenderaren: sparat svar följer inte kontraktet: %s", exc)
        return False

    for block_index, block in enumerate(svar.block):
        if isinstance(block, TextBlock):
            st.markdown(block.innehall)
        elif isinstance(block, TabellBlock):
            _rendera_tabell(block, meddelande_index, block_index)
        elif isinstance(block, DiagramBlock):
            st.plotly_chart(_bygg_diagram_fran_block(block), width="stretch")

    return True
