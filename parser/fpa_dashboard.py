"""fpa_dashboard — Streamlit-rendering av FP&A-dashboarden (Resultatrapport +
Balansräkning).

Hålls isär från app.py av två skäl: (1) app.py förblir tunn, (2) både appen och
en fristående preview-demo kan anropa EXAKT samma rendering (rendera(sie)).

Strikt renderande, "dum frontend": ingen tecken- eller grupperingslogik. Poster,
grupper och normaliserade tecken kommer FÄRDIGA från den frikopplade motorn
(fpa_motor) via fpa_vy — här görs bara st.*-anrop som loopar över dem.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from domain_model import SIEFil
from stil import bakgrundsfarg, Harkomstmarke, HARKOMST_LOKAL
from fpa_motor import BOLAGSSKATT, Finansieringspost
from fpa_vy import (
    BALANS_EK_SKULDER,
    BALANS_TILLGANGAR,
    AXELTITEL_STORLEK,
    BALANSVYER,
    DEFAULT_NYCKELTAL,
    DIAGRAMTITEL_STORLEK,
    FARG_HISTORISKT_SEN_KUND,
    FARG_INTAKT,
    FARG_KOSTNAD,
    FARG_LIKVIDITET_ROD,
    FARG_MOMS,
    FARG_RESULTAT,
    GRAFTYPER,
    INLINE_TEXT_STORLEK,
    KASSAFLODE_BLOCK,
    LEGEND_STORLEK,
    NYCKELTAL_KATALOG,
    RAPPORTFLIKAR,
    KAPITALSTACK_KOSTNADSFALT,
    KAPITALSTACK_STANDARD_ALTERNATIVKOSTNAD,
    KAPITALSTACK_STANDARD_LEASINGRANTA,
    KAPITALSTACK_STANDARD_LOPTID_AR,
    KAPITALSTACK_STANDARDRANTA,
    KAPITALSTACK_TYPER,
    LEASING_VAL_HJALP,
    LEASINGMETOD_ETIKETT,
    LEASINGMETOD_FORKLARING,
    LEASINGMETODER,
    NARRATIV_TABELL_CSS,
    SIMULERADE_NYCKELTAL,
    STAPEL_KAPITAL,
    SIMULERING_STEG,
    TYPETIKETT,
    TYPFORKLARING,
    TYPSNITT,
    TYP_FACKTERM,
    balansrapport_fran_sie,
    dela_uppstallning,
    formatera_kr,
    formatera_nyckeltal,
    formatera_procent,
    formatera_procentenheter,
    foreslaget_avkastningskrav_procent,
    kapitalstack,
    kapitalstapel,
    narrativtabell_html,
    kassaflodesanalys_fran_sie,
    konton_i_grupp,
    likviditetsdagar_ur_punkter,
    likviditetsgraf_data,
    likviditetsprognos_med_varningstroskel,
    nyckeltal_fran_sie,
    nyckeltal_med_personalkostnad,
    radbryt,
    konton_i_segment,
    resultatrapport_fran_sie,
    resultattabell_rader,
    kvot_fran_procent,
    procent_fran_belopp,
    procentsumma,
    ryms_inline_text,
    sankey_data,
    sortera_drilldown,
    stapeldata_balans,
    stapeldata_resultat_bi,
    text_farg,
    valda_segment_ur_punkter,
    valj_nyckeltal,
    vattenfall_kassaflode,
    vattenfall_resultat,
)

# Max antal KPI-kort per rad innan layouten bryts på nästa rad.
_KPI_PER_RAD = 4


# Beloppen i uppställningen högerställs, som i en tryckt årsredovisning: siffrorna
# ska ligga i en kolumn med ental över ental, inte ragga vänsterkant mot etiketten.
_HOGERSTALLT = "<div style='text-align:right;font-variant-numeric:tabular-nums'>{}</div>"
_HOGERSTALLT_FET = (
    "<div style='text-align:right;font-variant-numeric:tabular-nums;"
    "font-weight:700;font-size:1.05rem'>{}</div>"
)
_FET_ETIKETT = "<div style='font-weight:700;font-size:1.05rem'>{}</div>"


def _rendera_uppstallning(rapport: dict, uppstallning: list) -> None:
    """Renderar en display-uppställnings KROPPSRADER strikt: drill-down-grupper som
    expanders med sina ingående konton, delsummor som rader. Slutsummeraden ingår
    inte — den renderas av _rendera_summafot, gemensamt för båda sidor. Inga tecken
    vänds och inga grupper räknas ut här."""
    for nyckel, etikett, radtyp in uppstallning:
        belopp = formatera_kr(rapport["poster"][nyckel])
        if radtyp == "grupp":
            konton = konton_i_grupp(rapport, nyckel)
            with st.expander(f"{etikett} — {belopp}"):
                if konton:
                    st.dataframe(
                        [
                            {
                                "Konto": konto["kontonr"],
                                "Benämning": konto["kontonamn"],
                                "Saldo": formatera_kr(konto["saldo"]),
                            }
                            for konto in konton
                        ],
                        hide_index=True,
                    )
                    # Reskontra-drill-down om konton innehåller ett känt konto
                    for konto in konton:
                        knr = str(konto.get("kontonr", ""))
                        if knr in _RESKONTRA_KONTON and konto.get("saldo", 0) != 0:
                            rk, nf, fk, dt = _RESKONTRA_KONTON[knr]
                            _rendera_reskontra_drill(knr, konto.get("kontonamn", knr), rk, nf, fk, dt, f"upp_{nyckel}")
                            break
                else:
                    st.caption("Inga konton med saldo i den här gruppen.")
        else:
            kol_etikett, kol_belopp = st.columns([3, 1])
            kol_etikett.write(etikett)
            kol_belopp.markdown(_HOGERSTALLT.format(belopp), unsafe_allow_html=True)


def _rendera_summafot(rapport: dict, vanster: tuple, hoger: tuple) -> None:
    """De två slutsummorna som EN rad över hela bredden.

    Renderade inne i var sin kolumn hade de hamnat på olika höjd: sidorna har olika
    många rader, och en expander är högre än en textrad — att fylla ut med tomma
    rader tills antalet stämmer räcker alltså inte. Utanför kolumnerna ligger de
    garanterat på samma linje. Kolumnvikterna [3, 1, 3, 1] speglar kroppsradernas
    [3, 1] i var halva, så beloppen står rakt under beloppen ovanför."""
    kol_v_etikett, kol_v_belopp, kol_h_etikett, kol_h_belopp = st.columns([3, 1, 3, 1])
    for kol_etikett, kol_belopp, (nyckel, etikett, _) in (
        (kol_v_etikett, kol_v_belopp, vanster),
        (kol_h_etikett, kol_h_belopp, hoger),
    ):
        kol_etikett.markdown(_FET_ETIKETT.format(etikett), unsafe_allow_html=True)
        kol_belopp.markdown(
            _HOGERSTALLT_FET.format(formatera_kr(rapport["poster"][nyckel])),
            unsafe_allow_html=True,
        )


def _bygg_stapelfigur(rapport: dict) -> go.Figure:
    """Tre distinkta staplar: Intäkter (grön) − Kostnader (röd) = Resultat (blå).
    Beloppen horisontellt vid stapeln, kategorinamnen horisontellt på x-axeln —
    inga vertikala etiketter."""
    stapel = stapeldata_resultat_bi(rapport)
    figur = go.Figure(
        go.Bar(
            x=[etikett for etikett, _, _ in stapel],
            y=[belopp for _, belopp, _ in stapel],
            marker_color=[färg for _, _, färg in stapel],
            text=[formatera_kr(belopp) for _, belopp, _ in stapel],
            textposition="outside",
        )
    )
    figur.update_traces(textangle=0, cliponaxis=False)
    figur.update_layout(
        title="Resultatresan: Intäkter − Kostnader = Resultat",
        showlegend=False,
        margin={"t": 40, "b": 0, "l": 0, "r": 0},
    )
    figur.update_xaxes(tickangle=0)
    return figur


def _bygg_vattenfallsfigur(rapport: dict) -> go.Figure:
    """P&L-resan som vattenfall: från Totala intäkter, ned genom kostnadsslagen,
    landar i Resultat. Samma färgspråk som staplarna (intäkt grön, kostnad röd,
    total blå) och samma slutvärde."""
    steg = vattenfall_resultat(rapport)
    figur = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=[measure for _, _, measure in steg],
            x=[etikett for etikett, _, _ in steg],
            y=[belopp for _, belopp, _ in steg],
            text=[formatera_kr(belopp) for _, belopp, _ in steg],
            textposition="outside",
            connector={"line": {"color": "rgb(120,120,120)"}},
            increasing={"marker": {"color": FARG_INTAKT}},
            decreasing={"marker": {"color": FARG_KOSTNAD}},
            totals={"marker": {"color": FARG_RESULTAT}},
        )
    )
    figur.update_traces(textangle=0, cliponaxis=False)
    figur.update_layout(
        title="Resultatresan: från intäkter, genom kostnaderna, till resultat",
        showlegend=False,
        margin={"t": 40, "b": 0, "l": 0, "r": 0},
    )
    figur.update_xaxes(tickangle=0)
    return figur


def _rendera_resultatflik(rapport: dict) -> None:
    st.info(
        "📈 **Resultatrapport (P&L)** — periodens intäkter, kostnader och resultat "
        "enligt BAS. Klicka på en grupp längst ned för att fälla ut kontona."
    )
    period = rapport["period"]
    st.caption(f"Period: {period['start_datum']} – {period['slut_datum']}")

    poster = rapport["poster"]
    kol1, kol2, kol3, kol4 = st.columns(4)
    kol1.metric("Totala intäkter", formatera_kr(poster["totala_intakter"]))
    kol2.metric("Bruttovinst", formatera_kr(poster["bruttovinst"]))
    kol3.metric("Rörelseresultat", formatera_kr(poster["rorelseresultat"]))
    kol4.metric("Årets resultat", formatera_kr(poster["arets_resultat"]))

    # Användaren väljer själv graftyp — olika ekonomer läser P&L olika.
    graftyp = st.radio("Graftyp", GRAFTYPER, horizontal=True)
    figur = (
        _bygg_stapelfigur(rapport)
        if graftyp == GRAFTYPER[0]
        else _bygg_vattenfallsfigur(rapport)
    )
    st.plotly_chart(figur, width="stretch")

    st.divider()
    st.subheader("Uppställning")
    # Ren, professionell tabell: numeriskt Belopp (högerjusteras av st.dataframe,
    # tusentalsformateras av column_config) och feta summeringsrader via Styler.
    _df = pd.DataFrame(resultattabell_rader(rapport))
    _summa_index = _df.index[_df["_summa"]].tolist()
    _styler = _df[["Post", "Belopp"]].style.apply(
        lambda rad: ["font-weight: bold" if rad.name in _summa_index else "" for _ in rad],
        axis=1,
    )
    st.dataframe(
        _styler,
        hide_index=True,
        width="stretch",
        column_config={
            "Post": st.column_config.TextColumn("Post"),
            "Belopp": st.column_config.NumberColumn("Belopp (kr)", format="localized"),
        },
    )
    st.caption(rapport["info"])


def _rgba(hexfarg: str, alpha: float) -> str:
    """Hex -> halvtransparent rgba, så Sankey-strömmarna kan färgas som sin
    källnod utan att dölja varandra där de korsas."""
    r, g, b = (int(hexfarg[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _bygg_sankeyfigur(data: dict, titel: str) -> go.Figure:
    """Ett flöde som Sankey: källor till vänster, mottagare till höger. Strömmens
    tjocklek är beloppet. Noder, färger och länkar kommer FÄRDIGA från
    fpa_vy.sankey_data (hela balansräkningen, pro rata). Kapitalstacken ritas
    numera som staplade skikt i stället, se _bygg_kapitalstapelfigur."""
    lankar = data["lankar"]
    figur = go.Figure(
        go.Sankey(
            valueformat=",.0f",
            valuesuffix=" kr",
            node={
                "label": data["noder"],
                "color": data["nodfarger"],
                "pad": 20,
                "thickness": 18,
                "line": {"color": "rgba(0,0,0,0.25)", "width": 0.5},
            },
            link={
                "source": [länk["kalla"] for länk in lankar],
                "target": [länk["mal"] for länk in lankar],
                "value": [länk["varde"] for länk in lankar],
                "color": [_rgba(data["nodfarger"][länk["kalla"]], 0.35) for länk in lankar],
            },
        )
    )
    figur.update_layout(
        title={"text": titel, "font": {"size": DIAGRAMTITEL_STORLEK, "family": TYPSNITT}},
        font={"family": TYPSNITT, "size": LEGEND_STORLEK},
        # Luft runt om: utan den klipps den understa nodens flöde av underkanten,
        # och etiketten på den högraste noden ("Ny investering") skärs av höger
        # kant. Båda syntes först när figuren faktiskt renderades och granskades.
        margin={"t": 50, "b": 40, "l": 10, "r": 24},
        height=480,
    )
    return figur


def _bygg_kapitalstapelfigur(data: dict, titel: str) -> go.Figure:
    """Kapitalstacken som EN staplad stapel — ett färgskikt per källa, med
    namn, belopp och andel skrivet i skiktet.

    Skikten kommer FÄRDIGA från fpa_vy.kapitalstapel (färg, textfärg, etikett
    och om etiketten alls ryms). Här görs bara Plotly-anropen.

    Listan vänds: Plotly staplar nerifrån, och skikten kommer i läsordning
    (formulärets rader, översta först). Utan reversed() hamnar första raden
    längst ned."""
    figur = go.Figure()
    for skikt in reversed(data["skikt"]):
        figur.add_trace(
            go.Bar(
                x=[STAPEL_KAPITAL],
                y=[float(skikt["belopp"])],
                name=skikt["namn"],
                # Stående, inte liggande: en capital stack ÄR skikt ovanpå
                # varandra, och varje skikt får då hela stapelbredden åt sin
                # etikett i stället för en smal remsa.
                width=[0.55],
                marker={
                    "color": skikt["farg"],
                    "line": {"color": _ytfarg(), "width": 2},
                },
                text=[skikt["etikett"] if skikt["visa_etikett"] else ""],
                textposition="inside",
                insidetextanchor="middle",
                textfont={
                    "color": skikt["textfarg"],
                    "family": TYPSNITT,
                    "size": INLINE_TEXT_STORLEK,
                },
                hovertemplate=(
                    f"<b>{skikt['namn']}</b><br>"
                    f"{formatera_kr(skikt['belopp'])} · "
                    f"{formatera_procent(skikt['andel'])}<extra></extra>"
                ),
            )
        )
    figur.update_layout(
        barmode="stack",
        title={"text": titel, "font": {"size": DIAGRAMTITEL_STORLEK, "family": TYPSNITT}},
        font={"family": TYPSNITT, "size": LEGEND_STORLEK},
        margin={"t": 50, "b": 20, "l": 10, "r": 24},
        height=440,
        showlegend=True,
        legend={"orientation": "h", "yanchor": "top", "y": -0.05},
        # Axlarna bär ingen information här — stapeln ÄR hela investeringen,
        # och varje skikt skriver ut sitt eget belopp. En beloppsaxel hade
        # bara upprepat det.
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figur


def _rendera_ai_panel(sim: dict) -> None:
    """Det narrativa lagret: nyckeltalskorten med verkligt delta (i procent-
    enheter) plus de deterministiskt genererade raderna från fpa_vy, som en
    kalkylbladslik tabell. Ingen LLM och ingen omräkning här — både texten och
    tabellens HTML kommer färdiga från vy-lagret."""
    st.markdown("### 🤖 AI Insights (Narrative Layer)")

    kolumner = st.columns(len(SIMULERADE_NYCKELTAL))
    for kolumn, (nyckel, etikett) in zip(kolumner, SIMULERADE_NYCKELTAL):
        fore, efter = sim["nyckeltal_fore"].get(nyckel), sim["nyckeltal_efter"].get(nyckel)
        kolumn.metric(
            etikett,
            formatera_procent(efter),
            delta=formatera_procentenheter(fore, efter),
            help=f"Före simuleringen: {formatera_procent(fore)}",
        )

    st.markdown(NARRATIV_TABELL_CSS, unsafe_allow_html=True)
    st.markdown(narrativtabell_html(sim["narrativ"]), unsafe_allow_html=True)


_STACK_NYCKEL = "kapitalstack_rader"
_LAGE_PROCENT = "Procent (%)"
_LAGE_BELOPP = "Belopp (kr)"


def _ny_rad(typ: str, namn: str | None = None, andel: int = 0) -> dict:
    """En ny formulärrad. id:t är det som gör att widgetarna behåller sina
    värden när rader läggs till, dubbleras eller tas bort — ett index hade
    flyttat användarens inmatning till fel rad så fort något togs bort."""
    return {
        "id": uuid4().hex[:8],
        "typ": typ,
        "namn": namn if namn is not None else TYPETIKETT[typ],
        "andel": andel,
    }


def _standardrader() -> list[dict]:
    """Utgångspunkten: ett lån och bolagets egna pengar, 50/50. Bara en
    startpunkt som summerar till 100 %, aldrig en rekommendation."""
    return [_ny_rad("lan", andel=50), _ny_rad("egna_pengar", andel=50)]


def _standardkostnad(typ: str, forslag: float | None) -> float:
    """Förifylld kapitalkostnad per typ. Avkastningskravet förifylls med årets
    ROE; går den inte att härleda förifylls INGEN siffra — 0 % vore ett
    påstående, inte ett tomt fält."""
    if typ == "agarinsats":
        return forslag if forslag is not None else 0.0
    if typ == "lan":
        return KAPITALSTACK_STANDARDRANTA
    if typ == "leasing":
        return KAPITALSTACK_STANDARD_LEASINGRANTA
    return KAPITALSTACK_STANDARD_ALTERNATIVKOSTNAD


def _initiera(nyckel: str, standard) -> str:
    """Sätter widgetens startvärde i session_state EN gång och returnerar
    nyckeln. Låter fälten styras via nyckeln i stället för value=, vilket är
    det enda sättet att också kunna skriva värdet programmatiskt utan att
    Streamlit varnar för dubbelstyrning."""
    if nyckel not in st.session_state:
        st.session_state[nyckel] = standard
    return nyckel


def _folj_typbyte(rad: dict) -> None:
    """Låter radens namn följa med när användaren byter typ — men bara om
    namnet fortfarande är den gamla typens standardetikett. Ett namn
    användaren skrivit själv ('Banklån Swedbank') rörs aldrig.

    Utan det här hamnar fel etikett i narrativet och i Sankey-diagrammet: en
    rad som bytts till Leasing skulle fortsätta heta 'Bolagets egna pengar'.
    Skrivningen till session_state sker FÖRE textfältet instansieras — annars
    ignoreras den."""
    ny_typ = st.session_state.get(f"stack_typ_{rad['id']}", rad["typ"])
    if ny_typ == rad["typ"]:
        return
    if rad["namn"] == TYPETIKETT[rad["typ"]]:
        rad["namn"] = TYPETIKETT[ny_typ]
        st.session_state[f"stack_namn_{rad['id']}"] = TYPETIKETT[ny_typ]
    rad["typ"] = ny_typ


def _synka_lagesbyte(rader: list[dict], lage: str, investering: int) -> None:
    """Överför fördelningen mellan procent- och beloppsfälten när användaren
    byter läge, så de två lägena är två VYER av samma stack — inte två
    oberoende inmatningar som glider isär.

    Widgetarnas session_state skrivs innan de instansieras; efteråt hade
    Streamlit ignorerat värdet."""
    forra = st.session_state.get("stack_lage_forra")
    st.session_state["stack_lage_forra"] = lage
    if forra is None or forra == lage:
        return

    for rad in rader:
        rid = rad["id"]
        if lage == _LAGE_BELOPP:
            andel = st.session_state.get(f"stack_andel_{rid}", rad["andel"])
            st.session_state[f"stack_belopp_{rid}"] = int(
                Decimal(str(investering)) * Decimal(str(andel)) / Decimal("100")
            )
        else:
            belopp = Decimal(str(st.session_state.get(f"stack_belopp_{rid}", 0)))
            andel = procent_fran_belopp(Decimal(str(investering)), [belopp])[0]
            st.session_state[f"stack_andel_{rid}"] = int(round(andel))


def _rendera_leasingfalt(rad: dict, investering: int) -> tuple[Decimal | None, int | None, str]:
    """Leasingradens extrafält: utköpspris, löptid och metodval, plus den
    pedagogiska rutan om vad valet innebär. Returnerar (utköpspris, löptid,
    metod)."""
    rid = rad["id"]
    kol_utkop, kol_loptid, kol_metod = st.columns([1, 1, 1.4])
    utkopspris = kol_utkop.number_input(
        "Utköpspris vid periodens slut (kr)",
        min_value=0,
        value=0,
        step=SIMULERING_STEG,
        key=f"stack_utkop_{rid}",
        help=(
            "Vad det kostar att lösa ut tillgången när leasingen löper ut. "
            "Slås ut över löptiden och läggs på leasingräntan i WACC:en."
        ),
    )
    loptid = kol_loptid.number_input(
        "Leasingperiod (år)",
        min_value=1,
        max_value=30,
        value=KAPITALSTACK_STANDARD_LOPTID_AR,
        step=1,
        key=f"stack_loptid_{rid}",
    )
    metod = kol_metod.radio(
        "Typ av leasingavtal",
        options=LEASINGMETODER,
        format_func=lambda m: LEASINGMETOD_ETIKETT[m],
        horizontal=True,
        key=f"stack_leasingmetod_{rid}",
        help=LEASING_VAL_HJALP,
    )

    with st.expander("❓ Vad är skillnaden mellan operationell och finansiell leasing?"):
        for val in LEASINGMETODER:
            st.markdown(LEASINGMETOD_FORKLARING[val])
            st.markdown("")
        st.caption(
            "Kalkylen följer ditt val: operationell leasing hamnar aldrig i "
            "den projicerade balansräkningen, finansiell gör det. Klassifi"
            "ceringen ska bygga på avtalets ekonomiska innebörd, inte på vad "
            "det kallas (K3 p. 20.3) — det här är en what-if-kalkyl, inte ett "
            "bokföringsbeslut."
        )

    return (
        Decimal(str(utkopspris)) if utkopspris else None,
        int(loptid),
        metod,
    )


def _rendera_stackrad(
    rad: dict, index: int, lage: str, investering: int, forslag: float | None
) -> Finansieringspost:
    """En finansieringsrad: namn, typ, andel/belopp, kostnad — plus
    leasingfälten när typen kräver dem."""
    rid = rad["id"]
    _folj_typbyte(rad)
    kol_namn, kol_typ, kol_del, kol_kostnad = st.columns([1.5, 1.3, 1.2, 1.2])

    # Nyckeln — inte value= — är sanningen för de fält vars värde också kan
    # skrivas programmatiskt (_folj_typbyte, _synka_lagesbyte). Att skicka
    # både value= och skriva till session_state får Streamlit att varna, och
    # då är det value= som är överflödigt.
    rad["namn"] = kol_namn.text_input(
        "Namn", key=_initiera(f"stack_namn_{rid}", rad["namn"]),
        help="Din egen etikett — t.ex. 'Banklån Swedbank'. Syns i diagram och narrativ.",
    )
    rad["typ"] = kol_typ.selectbox(
        "Typ",
        options=KAPITALSTACK_TYPER,
        index=KAPITALSTACK_TYPER.index(rad["typ"]),
        format_func=lambda t: TYPETIKETT[t],
        key=f"stack_typ_{rid}",
        help="Typen — inte namnet — avgör vad posten gör med balansräkningen.",
    )
    kol_typ.caption(TYP_FACKTERM[rad["typ"]])

    if lage == _LAGE_PROCENT:
        rad["andel"] = kol_del.slider(
            "Andel (%)", min_value=0, max_value=100, step=1,
            key=_initiera(f"stack_andel_{rid}", int(rad["andel"])),
        )
        belopp = (
            Decimal(str(investering)) * Decimal(rad["andel"]) / Decimal("100")
        ).quantize(Decimal("0.01"))
        kol_del.caption(formatera_kr(belopp))
    else:
        belopp_in = kol_del.number_input(
            "Belopp (kr)", min_value=0, step=SIMULERING_STEG,
            key=_initiera(
                f"stack_belopp_{rid}",
                int(Decimal(str(investering)) * Decimal(str(rad["andel"])) / Decimal("100")),
            ),
        )
        belopp = Decimal(str(belopp_in))
        andel = procent_fran_belopp(Decimal(str(investering)), [belopp])[0]
        rad["andel"] = andel
        kol_del.caption(f"{andel:.1f} %".replace(".", ","))

    etikett, hjalp = KAPITALSTACK_KOSTNADSFALT[rad["typ"]]
    kostnad = kol_kostnad.number_input(
        etikett, min_value=0.0, value=_standardkostnad(rad["typ"], forslag),
        step=0.1, format="%.2f", help=hjalp, key=f"stack_kostnad_{rid}_{rad['typ']}",
    )
    if rad["typ"] == "agarinsats" and forslag is None:
        kol_kostnad.caption(
            "Årets ROE kunde inte härledas (eget kapital ≤ 0 eller negativt "
            "resultat) — ange avkastningskravet själv."
        )
    elif rad["typ"] == "agarinsats":
        kol_kostnad.caption(f"Förslag: årets ROE {forslag:.1f} %".replace(".", ","))

    utkopspris = loptid = None
    metod = "operationell"
    if rad["typ"] == "leasing":
        utkopspris, loptid, metod = _rendera_leasingfalt(rad, investering)

    st.caption(TYPFORKLARING[rad["typ"]])

    return Finansieringspost(
        id=rid,
        namn=rad["namn"].strip() or TYPETIKETT[rad["typ"]],
        typ=rad["typ"],
        belopp=belopp,
        kostnad=kvot_fran_procent(kostnad),
        utkopspris=utkopspris,
        loptid_ar=loptid,
        leasingmetod=metod,
    )


def _rendera_radknappar(rad: dict, index: int, rader: list[dict]) -> bool:
    """Duplicera/ta bort för en rad. Returnerar True om listan ändrats och
    sidan måste köras om."""
    kol_dubblera, kol_bort, _ = st.columns([1, 1, 4])
    if kol_dubblera.button(
        "⧉ Dubblera", key=f"stack_dubblera_{rad['id']}",
        help="Samma typ och andel, egen rad — t.ex. ett andra lån med annan ränta.",
    ):
        kopia = _ny_rad(rad["typ"], namn=f"{rad['namn']} (2)", andel=rad["andel"])
        rader.insert(index + 1, kopia)
        st.session_state[_STACK_NYCKEL] = rader
        return True
    if kol_bort.button(
        "🗑 Ta bort", key=f"stack_bort_{rad['id']}", disabled=len(rader) <= 1,
        help="Stacken måste ha minst en källa." if len(rader) <= 1 else None,
    ):
        rader.pop(index)
        st.session_state[_STACK_NYCKEL] = rader
        return True
    return False


def _rendera_investeringsformular(resultatrapport: dict, balansrapport: dict) -> dict | None:
    """Formuläret 'Ny investering' + kapitalstacken. Returnerar de inmatade
    värdena, eller None när stacken inte går ihop — då ska ingenting nedanför
    räknas eller ritas.

    Medvetet INTE en st.form: fördelningen måste kunna valideras live medan
    reglagen dras. Ett formulär hade dolt att stacken inte går ihop tills man
    tryckt på knappen.

    Raderna bor i session_state (_STACK_NYCKEL) eftersom antalet är
    användarstyrt — de överlever rerun, och varje rads id håller widgetarna
    knutna till RÄTT rad när något läggs till eller tas bort."""
    st.subheader("💰 Ny investering")
    belopp = st.number_input(
        "Investeringsbelopp (kr)",
        min_value=0,
        value=0,
        step=SIMULERING_STEG,
        help="Aktiveras som materiell anläggningstillgång, t.ex. en ny serverhall.",
    )

    st.markdown("##### 🏗️ Capital Stack — hur finansieras den?")
    st.caption(
        "Fördela investeringen över källorna. Fördelningen måste gå jämnt ut "
        "— stacken normaliseras aldrig i tysthet."
    )

    if _STACK_NYCKEL not in st.session_state:
        st.session_state[_STACK_NYCKEL] = _standardrader()
    rader: list[dict] = st.session_state[_STACK_NYCKEL]

    lage = st.radio(
        "Ange fördelningen som",
        options=(_LAGE_PROCENT, _LAGE_BELOPP),
        horizontal=True,
        key="stack_lage",
        help="Procent räknas om till kronor och tvärtom — samma stack, två sätt att skriva den.",
    )

    _synka_lagesbyte(rader, lage, belopp)

    forslag = foreslaget_avkastningskrav_procent(resultatrapport, balansrapport)

    poster: list[Finansieringspost] = []
    for index, rad in enumerate(list(rader)):
        with st.container(border=True):
            poster.append(_rendera_stackrad(rad, index, lage, belopp, forslag))
            if _rendera_radknappar(rad, index, rader):
                st.rerun()

    if st.button("➕ Lägg till finansieringskälla", key="stack_lagg_till"):
        rader.append(_ny_rad("lan", namn="Ny källa", andel=0))
        st.session_state[_STACK_NYCKEL] = rader
        st.rerun()

    return _validera_stack(belopp, poster, lage)


def _validera_stack(
    belopp: int, poster: list[Finansieringspost], lage: str
) -> dict | None:
    """Går stacken ihop? Felet formuleras i den enhet användaren själv skriver
    i — procent i procentläge, kronor i beloppsläge — så meddelandet pekar på
    det fält som ska rättas."""
    summa = sum((post.belopp for post in poster), Decimal("0"))
    investering = Decimal(str(belopp))

    if investering == 0:
        st.info("Ange ett investeringsbelopp ovan för att räkna kalkylen.")
        return None

    if summa != investering:
        diff = summa - investering
        if lage == _LAGE_PROCENT:
            st.error(
                f"Kapitalstacken summerar till "
                f"{procentsumma([int(round(float(p.belopp / investering * 100))) for p in poster])} %, "
                "inte 100 %. Justera andelarna för att räkna kalkylen."
            )
        else:
            riktning = "för mycket" if diff > 0 else "för lite"
            st.error(
                f"Källorna summerar till {formatera_kr(summa)} — "
                f"{formatera_kr(abs(diff))} {riktning} mot investeringens "
                f"{formatera_kr(investering)}."
            )
        return None

    st.success(f"Kapitalstacken går ihop på {formatera_kr(investering)}.")
    return {"belopp": belopp, "poster": poster}


def _rendera_wacc(wacc: dict) -> None:
    """WACC före och efter skatt, plus vad varje källa bidrar med. Talen kommer
    FÄRDIGA från fpa_motor.berakna_wacc — här formateras de bara."""
    st.markdown("##### 🧮 Vägd kapitalkostnad (WACC)")
    if wacc["wacc_fore_skatt"] is None:
        st.info(
            "Ingen investering angiven — en investering som inte görs har ingen "
            "kapitalkostnad. (Noll procent hade påstått gratis kapital.)"
        )
        return

    kol_fore, kol_efter, kol_skold = st.columns(3)
    kol_fore.metric("WACC före skatt", formatera_procent(wacc["wacc_fore_skatt"]))
    kol_efter.metric(
        "WACC efter skatt",
        formatera_procent(wacc["wacc_efter_skatt"]),
        delta=f"−{formatera_procent(wacc['skatteskold'])} skattesköld",
        delta_color="off",
        help="Räntan på skuldkapital är avdragsgill: kd × (1 − bolagsskatt).",
    )
    kol_skold.metric(
        "Bolagsskatt",
        formatera_procent(BOLAGSSKATT),
        help="Samma konstant som används för den dolda ägarandelen i obeskattade reserver.",
    )

    st.dataframe(
        [
            {
                "Källa": post["kalla"],
                "Belopp": formatera_kr(post["belopp"]),
                "Vikt": formatera_procent(post["vikt"]),
                "Kostnad": formatera_procent(post["kostnad_fore_skatt"]),
                "Kostnad efter skatt": formatera_procent(post["kostnad_efter_skatt"]),
                "Bidrag till WACC": formatera_procent(post["bidrag_efter_skatt"]),
            }
            for post in wacc["poster"]
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Vikterna är källornas andel av DEN HÄR investeringen, inte av bolagets "
        "hela balansräkning. Bara skuldräntan får skattesköld; avkastningskravet "
        "på eget kapital betalas ur beskattad vinst, och kassans alternativkostnad "
        "är ingen avdragsgill kostnad."
    )


def rendera_investeringskalkyl(resultatrapport: dict, balansrapport: dict) -> None:
    """Fliken Investeringskalkyl: formulär för en ny investering, kapitalstack
    med flera finansieringskällor, Sankey över hur källorna finansierar den nya
    tillgången, WACC, och den projicerade balansräkningens effekter.

    Datakälle-agnostisk: tar samma FÄRDIGA rapport-dicts som rendera_rapporter,
    oavsett om de byggts ur en SIEFil eller hämtats live."""
    st.header("📈 Investeringskalkyl")
    st.info(
        "🔮 **Framtidens balansräkning** — projicera en investering och dess "
        "finansiering på balansräkningen och se direkt vad den kostar och hur "
        "nyckeltalen rör sig. Ingenting här är bokfört."
    )

    inmatning = _rendera_investeringsformular(resultatrapport, balansrapport)
    if inmatning is None:
        return

    kalkyl = kapitalstack(
        resultatrapport,
        balansrapport,
        inmatning["belopp"],
        inmatning["poster"],
    )
    if kalkyl["varning"]:
        st.warning(kalkyl["varning"])

    # Stapeln och narrativet ligger under varandra i FULL bredd. Sida vid sida
    # (2:1) klämde ihop diagrammet och pressade narrativet till en meterlång
    # remsa på en rad i taget.
    st.divider()
    st.markdown("##### 📈 Så finansieras den nya tillgången")
    data = kapitalstapel(kalkyl["poster"])
    if data["varning"]:
        st.info(data["varning"])
    else:
        st.plotly_chart(
            _bygg_kapitalstapelfigur(data, titel="Kapitalstacken: skikt för skikt"),
            width="stretch",
        )
        st.caption(
            "Varje skikt är en finansieringskälla och visar sitt eget belopp och "
            "sin andel av hela finansieringen. Ingenting fördelas pro rata här — "
            "delbeloppen är kända, inte uppskattade."
        )

    st.divider()
    _rendera_ai_panel(kalkyl)

    st.divider()
    _rendera_wacc(kalkyl["wacc"])

    st.divider()
    with st.expander("⚖️ Balansräkningen efter investeringen (flöde)"):
        efter = sankey_data(kalkyl["balans_efter"])
        if efter["varning"]:
            st.warning(efter["varning"])
        if efter["lankar"]:
            st.plotly_chart(
                _bygg_sankeyfigur(efter, titel="Så finansieras tillgångarna efter investeringen"),
                width="stretch",
            )
            st.caption(
                "Här ÄR flödena fördelade pro rata: bokföringen kopplar ingen "
                "enskild skuld till en enskild tillgång — kapital är fungibelt."
            )
        else:
            st.info("Inga flöden att visa.")


def _ytfarg() -> str:
    """Diagrammets ytfärg, matchad mot aktivt tema. Används som 2 px avskiljare
    mellan de staplade fyllningarna — utan den flyter två angränsande segment
    ihop till ett fält."""
    tematyp = getattr(getattr(st.context, "theme", None), "type", None)
    return bakgrundsfarg(tematyp)


def _bygg_balansstapelfigur(segment: list[dict]) -> go.Figure:
    """Balansräkningen som två staplar: Tillgångar mot Finansiering. En trace per
    segment — det är det som ger varje segment egen färg, egen legendrad och en
    egen customdata-nyckel att klicka på. Segmenten kommer FÄRDIGA (belopp, färg,
    ordning) från fpa_vy.stapeldata_balans; ingen matematik här."""
    ytfarg = _ytfarg()
    figur = go.Figure()
    for del_ in segment:
        figur.add_trace(
            go.Bar(
                name=del_["etikett"],
                x=[del_["stapel"]],
                y=[del_["belopp"]],
                marker_color=del_["farg"],
                # 2 px yt-gap mellan fyllningarna.
                marker_line_color=ytfarg,
                marker_line_width=2,
                # Nyckeln följer med tillbaka i Plotly-selectionen vid klick.
                customdata=[[del_["nyckel"]]],
                # Reliefregeln: flera segment ligger under 3:1 kontrast mot ytan,
                # så NAMN och belopp skrivs synligt inuti segmentet — identiteten
                # bärs aldrig av färgen ensam. Bara om segmentet är högt nog;
                # beslutet (på andel av stapeln) bor i fpa_vy.ryms_inline_text.
                # Staplarna är breda, så en enda rad ryms i ett mycket tunnare
                # block än två — därav "namn — belopp" och inte ett radbrytet par.
                text=[
                    f"{del_['kortnamn']} — {formatera_kr(del_['belopp'])}"
                    if ryms_inline_text(del_["andel"])
                    else ""
                ],
                textposition="inside",
                insidetextanchor="middle",
                # Textfärgen räknas ut per segment (fpa_vy.text_farg) i stället
                # för att hårdkodas till vit: sex av tolv fyllningar är för ljusa
                # för vit text. Så blir sämsta kontrasten i diagrammet 4,75:1.
                textfont={
                    "size": INLINE_TEXT_STORLEK,
                    "color": text_farg(del_["farg"]),
                    "family": TYPSNITT,
                    "weight": "bold",
                },
                hovertemplate=f"<b>{del_['etikett']}</b><br>%{{y:,.0f}} kr<extra></extra>",
            )
        )
    figur.update_layout(
        barmode="stack",
        title={
            "text": "Balansräkningen: vad bolaget äger, och vem som finansierat det",
            "font": {"size": DIAGRAMTITEL_STORLEK, "family": TYPSNITT},
        },
        font={"family": TYPSNITT},
        # Liggande legend UNDER diagrammet: staplarna får hela bredden, och de
        # långa svenska posternamnen slipper knuffa in plotytan från höger.
        legend={
            "traceorder": "normal",
            "orientation": "h",
            "yanchor": "top",
            "y": -0.1,
            "xanchor": "center",
            "x": 0.5,
            # entrywidth=0 låter varje post bli precis så bred som sin text.
            # Utan den får alla poster den bredaste postens bredd, och legenden
            # glesnar till ett rutnät med stora hål i.
            "entrywidth": 0,
            "font": {"size": LEGEND_STORLEK, "family": TYPSNITT},
        },
        # Luft i botten åt kategorinamnen OCH den liggande legenden, som annars
        # klipps av diagramkanten. Höjden är tilltagen så att plotytan blir hög
        # nog att rymma inline-etiketterna även i de smalare segmenten — legenden
        # under diagrammet äter annars upp just den höjden.
        margin={"t": 60, "b": 150, "l": 10, "r": 10},
        height=760,
        # Skyddsnät: ryms_inline_text har redan tömt de tunna segmentens etiketter,
        # men Plotly får ändå aldrig krympa den kvarvarande texten till oläslighet
        # — då göms den hellre helt.
        uniformtext={"minsize": INLINE_TEXT_STORLEK, "mode": "hide"},
    )
    # Varje segment är direktmärkt med sitt belopp och slutsummorna står i
    # metrikerna ovanför — en y-axel hade bara lagt till skala utan information,
    # dessutom med engelsk tusentalsavgränsare mitt bland svenskformaterade tal.
    figur.update_yaxes(visible=False)
    figur.update_xaxes(
        tickangle=0,
        tickfont={"size": AXELTITEL_STORLEK, "family": TYPSNITT, "weight": "bold"},
    )
    return figur


# Konton som har en känd reskontra-koppling i session_state.
# Varje kontonummer mappar till (session_state-nyckel, namnfält-på-posten,
# drill_typ för faktura-drill-down).
# Formatet är: kontonr_prefix → (reskontra_nyckel, namnfalt, faktura_nyckel, drill_typ)
_RESKONTRA_KONTON: dict[str, tuple[str, str, str, str]] = {
    "1510": ("kundreskontra",       "kund",        "register_kundfakturor",        "kund"),
    "1511": ("kundreskontra",       "kund",        "register_kundfakturor",        "kund"),
    "1512": ("kundreskontra",       "kund",        "register_kundfakturor",        "kund"),
    "1513": ("kundreskontra",       "kund",        "register_kundfakturor",        "kund"),
    "2440": ("leverantorsreskontra","leverantor",  "register_leverantorsfakturor", "leverantor"),
    "2441": ("leverantorsreskontra","leverantor",  "register_leverantorsfakturor", "leverantor"),
    "2442": ("leverantorsreskontra","leverantor",  "register_leverantorsfakturor", "leverantor"),
}


def _kontorader(konton: list[dict]) -> list[dict]:
    return [
        {
            "Konto": konto["kontonr"],
            "Benämning": konto["kontonamn"],
            "Saldo": formatera_kr(konto["saldo"]),
        }
        for konto in konton
    ]


def _rendera_drilldown(rapport: dict, del_: dict) -> None:
    """Kontona bakom ett klickat segment, enligt manage by exception: de aktiva
    kontona först, sorterade fallande på absolut belopp, och nollkontona hopfällda
    bakom en expander. Sorteringen bor i fpa_vy.sortera_drilldown; här bara
    tabeller.

    Om segmentet innehåller ett känt reskontra-konto (t.ex. 1510 Kundfordringar)
    visas en andra nivå: motparter med respektive obetalt belopp, och därifrån en
    tredje nivå med de enskilda fakturorna."""
    konton = konton_i_segment(rapport, del_["undergrupper"])
    st.markdown(f"**{del_['etikett']} — {formatera_kr(del_['belopp'])}**")
    if not konton:
        st.caption("Inga konton i det här segmentet.")
        return

    aktiva, nollkonton = sortera_drilldown(konton)
    if aktiva:
        st.dataframe(_kontorader(aktiva), hide_index=True, width="stretch")
    else:
        st.caption("Inga konton med saldo i det här segmentet.")

    if nollkonton:
        with st.expander(f"Visa övriga konton (0 kr) — {len(nollkonton)} st"):
            st.dataframe(_kontorader(nollkonton), hide_index=True, width="stretch")

    # --- Nivå 2: Reskontra-drill-down ---
    # Kolla om något aktivt konto är ett känt reskontra-konto.
    for konto in aktiva:
        knr = str(konto.get("kontonr", ""))
        if knr in _RESKONTRA_KONTON:
            reskontra_nyckel, namnfalt, faktura_nyckel, drill_typ = _RESKONTRA_KONTON[knr]
            _rendera_reskontra_drill(knr, konto.get("kontonamn", knr), reskontra_nyckel, namnfalt, faktura_nyckel, drill_typ, del_["nyckel"])
            break  # visa bara en drill-down per segment-klick


def _rendera_reskontra_drill(
    kontonr: str,
    kontonamn: str,
    reskontra_nyckel: str,
    namnfalt: str,
    faktura_nyckel: str,
    drill_typ: str,
    segment_nyckel: str,
) -> None:
    """Visar motparternas obetalda saldon ur reskontra-datan (session_state),
    och vid val av motpart en tredje nivå med fakturadetaljer.

    Läser från session_state:
      - reskontra_nyckel: lista av Kundpost / Leverantorspost-objekt (dataclasses)
      - faktura_nyckel: lista av faktura-dicts (cachas av registerfliken)
    """
    from decimal import Decimal

    reskontra = st.session_state.get(reskontra_nyckel)
    if reskontra is None:
        st.info(
            f"💡 **{kontonamn}** — reskontran är inte inläst. "
            "Öppna Bokföring → Register och vänta tills data laddats, "
            "klicka sedan tillbaka hit."
        )
        return

    # Aggregera obetalt saldo per motpart (reskontra-poster är dataclass-objekt).
    from collections import defaultdict
    saldo_per_motpart: dict[str, Decimal] = defaultdict(Decimal)
    for post in reskontra:
        namn = getattr(post, namnfalt, "")
        belopp = getattr(post, "belopp", Decimal("0"))
        saldo_per_motpart[namn] += abs(belopp)

    if not saldo_per_motpart:
        st.caption(f"Reskontran för {kontonamn} är tom.")
        return

    st.markdown(f"**🔍 {kontonamn} — per motpart**")

    # Bygg sorterad lista (störst skuld/fordring överst)
    motparter_sorterade = sorted(saldo_per_motpart.items(), key=lambda x: x[1], reverse=True)

    # Visa motparts-tabell
    from chatt_renderare import _bygg_tabellhtml
    from svarskontrakt import TabellBlock, KolumnDef
    from formatering import formatera_tal, Formateringsval
    fmt = Formateringsval()

    motpart_rader = [
        {
            "motpart": namn,
            "saldo": formatera_tal(saldo, fmt) + " kr",
        }
        for namn, saldo in motparter_sorterade
    ]
    motpart_tabell = TabellBlock(
        rubrik=None,
        kolumner=[
            KolumnDef(nyckel="motpart", rubrik=("Kund" if drill_typ == "kund" else "Leverantör"), typ="text"),
            KolumnDef(nyckel="saldo", rubrik="Obetalt", typ="belopp"),
        ],
        rader=motpart_rader,
    )
    st.markdown(_bygg_tabellhtml(motpart_tabell), unsafe_allow_html=True)

    # Selectbox för att klicka ner till fakturanivå
    motpartsnamn_lista = [namn for namn, _ in motparter_sorterade]
    drill_key = f"balans_drill_{segment_nyckel}_{kontonr}"
    vald_motpart = st.selectbox(
        f"🔍 Välj {'kund' if drill_typ == 'kund' else 'leverantör'} för att se fakturor",
        options=[""] + motpartsnamn_lista,
        format_func=lambda n: "Välj en motpart..." if not n else n,
        key=drill_key,
    )

    if vald_motpart:
        fakturor = st.session_state.get(faktura_nyckel)
        if fakturor is None:
            st.info(
                "💡 Fakturadetaljer kräver att **Register**-fliken har öppnats "
                "minst en gång (Bokföring → Register → Leverantörer/Kunder). "
                "Gå dit och kom sedan tillbaka."
            )
            return

        from snabbvy_render import _rendera_drill_fakturor
        from snabbvyer import Vydata
        from datetime import date

        # Minimal Vydata med bara idag och formateringsval — det enda _rendera_drill_fakturor behöver
        mini_vydata = Vydata(idag=date.today(), formateringsval=Formateringsval())
        _rendera_drill_fakturor(st, vald_motpart, fakturor, drill_typ, mini_vydata)


def _rendera_balansgraf(rapport: dict) -> None:
    """Den grafiska vyn: staplad stapel + drill-down på klick. Selectionen läses
    tillbaka ur Plotly-eventet och översätts av fpa_vy.valda_segment_ur_punkter,
    som tål allt frontend kan skicka."""
    data = stapeldata_balans(rapport)
    if data["varning"]:
        st.warning(data["varning"])
    if not data["segment"]:
        return

    händelse = st.plotly_chart(
        _bygg_balansstapelfigur(data["segment"]),
        width="stretch",
        key="balans_stapel",
        on_select="rerun",
        selection_mode="points",
    )
    st.caption(
        "Klicka på ett segment för att fälla ut de underliggande kontona. "
        "Shift-klick markerar flera; dubbelklick i grafen rensar markeringen."
    )

    punkter = (händelse.get("selection") or {}).get("points") or []
    valda = valda_segment_ur_punkter(punkter)
    if not valda:
        return

    # Övrigt-hinkens undergrupper bestäms av datat, inte av konfigurationen, så
    # drill-downen måste utgå från det renderade segmentet — inte från BALANS_SEGMENT.
    per_nyckel = {del_["nyckel"]: del_ for del_ in data["segment"]}
    st.divider()
    st.subheader("Drill-down")
    for nyckel in valda:
        if nyckel in per_nyckel:
            _rendera_drilldown(rapport, per_nyckel[nyckel])


def _rendera_balansflik(rapport: dict) -> None:
    st.info(
        "⚖️ **Balansräkning** — tillgångar mot eget kapital och skulder vid "
        "periodens slut. Health check-bannern nedan bevisar att debet = kredit."
    )
    poster = rapport["poster"]
    kontrolldiff = poster["kontrolldiff"]

    # Health check högst upp: kontrolldiff = Tillgångar − (EK + skulder).
    if kontrolldiff == 0:
        st.success(
            "✅ Balanserar: debet = kredit. "
            "Summa tillgångar = Summa eget kapital och skulder."
        )
    else:
        st.error(
            f"⚠️ Obalans: kontrolldiff = {formatera_kr(kontrolldiff)} "
            "(debet ≠ kredit — kontrollera datakällan)."
        )

    st.caption(f"Per: {rapport['per_datum']}")
    kol_t, kol_ek, kol_diff = st.columns(3)
    kol_t.metric("Summa tillgångar", formatera_kr(poster["summa_tillgangar"]))
    kol_ek.metric(
        "Summa EK & skulder", formatera_kr(poster["summa_eget_kapital_och_skulder"])
    )
    kol_diff.metric("Kontrolldiff", formatera_kr(kontrolldiff))

    st.divider()
    # Vyväxlaren är lokal för den här fliken: ett val i taget, samma siffror.
    # Den grafiska vyn drillar ned via klick, uppställningen via expanders.
    vy = st.radio("Vy", BALANSVYER, horizontal=True, key="balansvy")
    if vy == BALANSVYER[0]:
        _rendera_balansgraf(rapport)
    else:
        kropp_tillgangar, summa_tillgangar = dela_uppstallning(BALANS_TILLGANGAR)
        kropp_skulder, summa_skulder = dela_uppstallning(BALANS_EK_SKULDER)

        kol_tillgangar, kol_skulder = st.columns(2)
        with kol_tillgangar:
            st.markdown("**Tillgångar**")
            _rendera_uppstallning(rapport, kropp_tillgangar)
        with kol_skulder:
            st.markdown("**Eget kapital & skulder**")
            _rendera_uppstallning(rapport, kropp_skulder)

        # Foten ligger UTANFÖR kolumnerna — därför på samma linje för båda sidor.
        st.divider()
        _rendera_summafot(rapport, summa_tillgangar, summa_skulder)
    st.caption(rapport["info"])


def _rendera_nyckeltalsflik(resultatrapport: dict, rapport: dict) -> None:
    nyckeltal = rapport["nyckeltal"]

    st.info(
        "📊 **Nyckeltal** — välj vilka mått du vill följa nedan. Korten ritas ut "
        "i samma **ordning som du markerar dem** (din drag-and-drop). Delta visar "
        "förändring mot föregående period (kommer i nästa steg)."
    )

    # Dynamiskt val av vilka nyckeltal som visas (default: de fyra kärntalen).
    valda_etiketter = st.multiselect(
        "Nyckeltal att visa",
        options=[d.etikett for d in NYCKELTAL_KATALOG],
        default=DEFAULT_NYCKELTAL,
        help="Lägg till fler nyckeltal från listan. Nyckeltal utan färdig formel "
        "visas som platshållare (🚧) tills matten är på plats.",
    )

    # Två toggles styr BARA formateringen/vilket värde som visas — ingen
    # omräkning. Antal anställda gör en verklig omräkning: SIE4 saknar
    # personalstyrka helt, så Personalkostnad per anställd kan bara räknas ut
    # när användaren anger den här, live.
    kol_procent, kol_jek, kol_anstallda = st.columns(3)
    som_procent = kol_procent.toggle(
        "Visa som procent",
        value=True,
        help="Av: visa som kvot/multipel (t.ex. 0,57x) i stället för procent.",
    )
    inkludera_jek = kol_jek.toggle(
        "Inkludera obeskattade reserver (JEK)",
        value=False,
        help="Räknar soliditeten på justerat eget kapital (JEK) i stället för "
        "bokfört EK.",
    )
    antal_anstallda_indata = kol_anstallda.number_input(
        "Antal anställda",
        min_value=0,
        value=0,
        step=1,
        help="SIE4 innehåller ingen personalstyrka (den finns bara i "
        "förvaltningsberättelsen). Ange antalet för att räkna ut Personalkostnad "
        "per anställd — lämna på 0 för att visa \"–\".",
    )
    nyckeltal = nyckeltal_med_personalkostnad(
        nyckeltal, resultatrapport, antal_anstallda_indata or None
    )

    st.divider()

    if not valda_etiketter:
        st.info("Välj minst ett nyckeltal ovan.")
        return

    # Rendering FÖLJER multiselect-ordningen (drag-and-drop), inte katalogen, och
    # bryts på flera rader när många valts.
    valda = valj_nyckeltal(valda_etiketter)
    for rad in radbryt(valda, _KPI_PER_RAD):
        kolumner = st.columns(_KPI_PER_RAD)
        for kolumn, definition in zip(kolumner, rad):
            # Soliditet: JEK-toggeln styr vilket värde + etikett som visas.
            if definition.nyckel == "soliditet" and inkludera_jek:
                värde, etikett = nyckeltal.get("soliditet_jek"), "Soliditet (JEK)"
            else:
                värde, etikett = nyckeltal.get(definition.nyckel), definition.etikett
            if not definition.implementerad:
                # Platshållare tills formeln byggts — inget delta.
                kolumn.metric(etikett, "🚧", help=definition.hjalp)
            else:
                text = formatera_nyckeltal(värde, definition.format, som_procent)
                # delta hårdkodat till 0 (neutralt grått) tills periodjämförelse
                # byggs — undviker att antyda en falsk +/- förändring.
                kolumn.metric(
                    etikett, text, delta=0, delta_color="off", help=definition.hjalp
                )

    st.caption(rapport["info"])


def _rendera_kassaflodesflik(rapport: dict) -> None:
    st.info(
        "💧 **Kassaflödesanalys (indirekt metod)** — bryggan från rörelseresultat "
        "till årets kassaflöde. Vattenfallet nedan visar hur pengarna rör sig."
    )
    kontrolldiff = rapport["kontrolldiff"]

    # Health check högst upp: årets kassaflöde måste matcha Δ kassa & bank.
    if kontrolldiff == 0:
        st.success(
            "✅ Kassaflödet balanserar: Årets kassaflöde = förändringen i "
            "kassa & bank."
        )
    else:
        st.error(
            f"⚠️ Obalans: kontrolldiff = {formatera_kr(kontrolldiff)} "
            "(årets kassaflöde matchar inte förändringen i kassa & bank)."
        )

    period = rapport["period"]
    st.caption(f"Period: {period['start_datum']} – {period['slut_datum']}")
    kol1, kol2, kol3 = st.columns(3)
    kol1.metric("Årets kassaflöde", formatera_kr(rapport["arets_kassaflode"]))
    kol2.metric("Förändring kassa & bank", formatera_kr(rapport["forandring_kassa"]))
    kol3.metric("Kontrolldiff", formatera_kr(kontrolldiff))

    # Vattenfallsdiagram: bryggan Rörelseresultat -> Årets kassaflöde.
    steg = vattenfall_kassaflode(rapport)
    figur = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=[measure for _, _, measure in steg],
            x=[etikett for etikett, _, _ in steg],
            y=[belopp for _, belopp, _ in steg],
            connector={"line": {"color": "rgb(120,120,120)"}},
            decreasing={"marker": {"color": "#d9534f"}},
            increasing={"marker": {"color": "#5cb85c"}},
            totals={"marker": {"color": "#0d6efd"}},
        )
    )
    figur.update_layout(
        title="Brygga: Rörelseresultat → Årets kassaflöde",
        showlegend=False,
        margin={"t": 40, "b": 0, "l": 0, "r": 0},
    )
    st.plotly_chart(figur, width="stretch")

    st.divider()
    st.subheader("Uppställning")
    for block_nyckel, block_etikett, rader in KASSAFLODE_BLOCK:
        block = rapport[block_nyckel]
        with st.expander(f"{block_etikett} — {formatera_kr(block['summa'])}"):
            st.dataframe(
                [
                    {
                        "Post": post_etikett,
                        "Belopp": formatera_kr(block["poster"][post_nyckel]),
                    }
                    for post_nyckel, post_etikett in rader
                ],
                hide_index=True,
            )
    st.caption(rapport["info"])


def _bygg_likviditetsfigur(data: dict, varningströskel: Decimal | None) -> go.Figure:
    """Dagsserien som linje, punkterna färgade efter status (grön/gul/röd), plus
    två egna overlay-serier: dagar med minst en historiskt sen kundinbetalning
    (FARG_HISTORISKT_SEN_KUND, diamant) och EN eventuell momshändelse
    (FARG_MOMS, kvadrat) — båda med EGEN färg OCH egen markörform, så
    identiteten aldrig bärs av färg ensam.

    Grön/röd är inte pålitligt särskiljbara för en deuteranop användare (ΔE 4,1,
    under dataviz-golvet på 8 — se fpa_vy:s kommentar ovanför
    FARG_LIKVIDITET_GRON). Mitigeringen här är POSITIONELL, inte en ny färg: en
    nollinje markerar röd-gränsen, och — ges en varningströskel — en till linje
    markerar gul-gränsen. Båda gränserna går alltså att läsa av var punkten
    ligger på Y-axeln, inte bara av dess hue."""
    figur = go.Figure()
    figur.add_trace(
        go.Scatter(
            x=data["datum"],
            y=[float(kassa) for kassa in data["kassa"]],
            mode="lines+markers",
            line={"color": "rgba(120,120,120,0.55)", "width": 2},
            marker={"color": data["farg"], "size": 8},
            customdata=[[dag_nr] for dag_nr in data["dag_nr"]],
            hovertemplate="%{x|%Y-%m-%d}<br>Kassa: %{y:,.0f} kr<extra></extra>",
            name="Kassaprognos",
        )
    )
    if data["sen_kund_dag_nr"]:
        figur.add_trace(
            go.Scatter(
                x=data["sen_kund_datum"],
                y=[float(kassa) for kassa in data["sen_kund_kassa"]],
                mode="markers",
                marker={
                    "symbol": "diamond",
                    "size": 15,
                    "color": FARG_HISTORISKT_SEN_KUND,
                    "line": {"width": 2, "color": "#ffffff"},
                },
                customdata=[[dag_nr] for dag_nr in data["sen_kund_dag_nr"]],
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>Historiskt sen kund väntas betala"
                    "<extra></extra>"
                ),
                name="Historiskt sen kund",
            )
        )
    if data["moms_dag_nr"]:
        figur.add_trace(
            go.Scatter(
                x=data["moms_datum"],
                y=[float(kassa) for kassa in data["moms_kassa"]],
                mode="markers",
                marker={
                    "symbol": "square",
                    "size": 13,
                    "color": FARG_MOMS,
                    "line": {"width": 2, "color": "#ffffff"},
                },
                customdata=[[dag_nr] for dag_nr in data["moms_dag_nr"]],
                hovertemplate="%{x|%Y-%m-%d}<br>Momsbetalning/-återbäring<extra></extra>",
                name="Moms",
            )
        )
    figur.add_hline(
        y=0, line_dash="dash", line_color=FARG_LIKVIDITET_ROD,
        annotation_text="Negativ kassa", annotation_position="bottom right",
    )
    if varningströskel is not None:
        figur.add_hline(
            y=float(varningströskel), line_dash="dot", line_color="rgba(120,120,120,0.7)",
            annotation_text="Varningströskel", annotation_position="top right",
        )
    figur.update_layout(
        title="Likviditetsprognos — kassa dag för dag",
        xaxis_title="Datum",
        yaxis_title="Kassa (kr)",
        font={"family": TYPSNITT},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.25, "x": 0.5, "xanchor": "center"},
        margin={"t": 40, "b": 0, "l": 0, "r": 0},
    )
    return figur


_HANDELSE_TYP_ETIKETT: dict[str, str] = {
    "kundinbetalning": "Kundinbetalning",
    "leverantorsutbetalning": "Leverantörsutbetalning",
}


def _handelse_typ_etikett(h: dict) -> str:
    """Momshändelsen kan gå åt BÅDA håll (skuld ELLER fordran) — till
    skillnad från kund-/leverantörshändelserna, som redan har sin riktning
    inbyggd i typ-fältet, avgörs momsetiketten av belopp_signerats tecken."""
    if h["typ"] == "moms":
        return "Momsåterbäring" if h["belopp_signerat"] > 0 else "Momsbetalning"
    return _HANDELSE_TYP_ETIKETT.get(h["typ"], h["typ"])


def _rendera_likviditetshandelser(dag: dict) -> None:
    st.markdown(f"**{dag['datum'].isoformat()}** (dag {dag['dag_nr']})")
    st.dataframe(
        [
            {
                "Typ": _handelse_typ_etikett(h),
                "Motpart": h["motpart"] or h["fakturanr"] or "",
                "Belopp": formatera_kr(h["belopp"]),
                "Förfallodatum": h["forfallodatum"].isoformat(),
                "Justerat datum": h["justerat_datum"].isoformat(),
                "Historiskt sen kund": "Ja" if h["har_historisk_justering"] else "Nej",
            }
            for h in dag["handelser"]
        ],
        hide_index=True,
        width="stretch",
    )


def _rendera_likviditetsflik(prognos: dict | None) -> None:
    st.info(
        "💧 **Likviditetsprognos** — dag-för-dag kassaflöde de kommande "
        "90 dagarna, byggt på obetalda leverantörs- och kundfakturor från "
        "Spiris, plus den aktuella momsskulden/momsfordran (konto 2650 el. "
        "motsv.) på nästa standardförfallodag. Kundinbetalningar justeras "
        "efter kundens historiska betalbeteende där sådant är känt. Kräver "
        "en live Spiris-koppling — en uppladdad SIE-fil bär ingen "
        "fakturanivå-data (inga förfallodatum)."
    )
    if prognos is None:
        st.caption(
            "Ingen likviditetsprognos tillgänglig. Koppla upp mot Spiris i "
            "sidomenyn för att se den här."
        )
        return

    kol1, kol2, kol3 = st.columns(3)
    kol1.metric("Nuvarande kassa", formatera_kr(prognos["nuvarande_kassa"]))
    kol2.metric("Lägsta prognostiserad kassa", formatera_kr(prognos["lagsta_kassa"]))
    kol3.metric(
        "Första underskottsdag",
        prognos["forsta_dag_med_underskott"].isoformat()
        if prognos["forsta_dag_med_underskott"] is not None
        else "Inget underskott väntas",
    )
    if prognos["forsta_dag_med_underskott"] is not None:
        st.warning(prognos["info"])
    else:
        st.success(prognos["info"])

    # Varningströskeln är ANVÄNDARENS val, inte en gissning: fpa_motor vägrar
    # hitta på en procentsats själv (se bygg_likviditetsprognos-docstringen),
    # så "gul" existerar bara när användaren aktivt sätter ett kronbelopp här.
    troskel_kr = st.number_input(
        "Varningströskel (kr) — kassa under denna nivå flaggas gul. 0 = av (bara grön/röd).",
        min_value=0, value=0, step=10_000, key="likviditet_varningstroskel",
    )
    varningströskel = Decimal(troskel_kr) if troskel_kr > 0 else None
    # Tröskeln blir känd först här (vid rendering) — fpa_vy räknar om ENDAST
    # statusfältet med motorns egen likviditetsstatus, ingen dubblerad logik.
    prognos = likviditetsprognos_med_varningstroskel(prognos, varningströskel)

    data = likviditetsgraf_data(prognos)
    händelse = st.plotly_chart(
        _bygg_likviditetsfigur(data, varningströskel),
        width="stretch",
        key="likviditet_graf",
        on_select="rerun",
        selection_mode="points",
    )
    st.caption(
        "🟢 Grön = sund kassa · 🟡 Gul = under varningströskeln · 🔴 Röd = "
        "negativ kassa (markerad med den streckade nollinjen). "
        "💠 Lila diamant = minst en historiskt sen kund väntas betala den "
        "dagen. Klicka på en punkt för att se dagens händelser i detalj."
    )

    punkter = (händelse.get("selection") or {}).get("points") or []
    valda_dagnummer = likviditetsdagar_ur_punkter(punkter)
    if not valda_dagnummer:
        return

    st.divider()
    st.subheader("Dagens händelser")
    per_dag_nr = {dag["dag_nr"]: dag for dag in prognos["dagar"]}
    for dag_nr in valda_dagnummer:
        dag = per_dag_nr.get(dag_nr)
        if dag is None or not dag["handelser"]:
            continue
        _rendera_likviditetshandelser(dag)


def rendera_rapporter(
    resultatrapport: dict,
    balansrapport: dict,
    nyckeltalrapport: dict,
    kassaflodesanalys: dict,
    likviditetsprognos: dict | None = None,
    harkomst: Harkomstmarke = HARKOMST_LOKAL,
) -> None:
    """Renderar hela FP&A-dashboarden ur FÄRDIGA rapport-dicts — helt
    datakälle-agnostiskt. Samma rendering oavsett om dictarna byggts ur en
    SIEFil (fil-vägen) eller hämtats live från Spiris (API-vägen).

    likviditetsprognos är SPIRIS-ENDAST (se fpa_vy.likviditetsprognos_fran_
    reskontra) — fil-vägen skickar alltid None, och fliken visar då en
    förklarande text i stället för grafen."""
    st.header(f"📊 Rapporter {harkomst.tecken}", help=f"{harkomst.namn}: {harkomst.forklaring}")
    # Undernavigering: de två finansiella grundrapporterna hör ihop och delar
    # sida. Nyckeltalen och kassaflödet är egna analyser med egna kontroller
    # (multiselect respektive health check) och behåller därför egna flikar —
    # att gömma kassaflödet under en annan rubrik hade dolt det.
    flik_rapport, flik_nyckeltal, flik_kassa, flik_likviditet = st.tabs(RAPPORTFLIKAR)
    with flik_rapport:
        _rendera_resultatflik(resultatrapport)
        st.divider()
        _rendera_balansflik(balansrapport)
    with flik_nyckeltal:
        _rendera_nyckeltalsflik(resultatrapport, nyckeltalrapport)
    with flik_kassa:
        _rendera_kassaflodesflik(kassaflodesanalys)
    with flik_likviditet:
        _rendera_likviditetsflik(likviditetsprognos)


def rendera(sie: SIEFil) -> None:
    """Bekvämlighet för fil-vägen: bygger de fyra rapporterna ur en (maskerad)
    SIEFil via de frikopplade motorerna och renderar dem. Spiris-vägen anropar
    i stället rendera_rapporter direkt med live-hämtade dicts (inklusive
    likviditetsprognos, som fil-vägen aldrig kan ha).

    Renderar ENBART rapportflikarna. Investeringskalkylen är en egen
    funktionsyta (rendera_investeringskalkyl) och en egen toppflik i app.py."""
    rendera_rapporter(
        resultatrapport_fran_sie(sie),
        balansrapport_fran_sie(sie),
        nyckeltal_fran_sie(sie),
        kassaflodesanalys_fran_sie(sie),
    )
