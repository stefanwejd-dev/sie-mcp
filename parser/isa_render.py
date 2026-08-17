import streamlit as st
from decimal import Decimal
import app_config
import revisionslogg
from ai_adapter import bygg_analysanropare, AnalysanropareFel
from analysflode import (
    kor_analys,
    berakna_vasentlighet, berakna_standardtroskelvarden, 
    belopp_fran_procent, procent_fran_belopp, tolka_troskelvarden,
    VASENTLIGHETSTAL_HELP, UTFALLSVASENTLIGHET_HELP, TröskelvärdeFel
)
from fpa_vy import formatera_kr
from ai_adapter import leverantor_har_analysstod
from stil import HARKOMST_LOKAL, HARKOMST_AI


def _procent_caption(proc: str, ref: str) -> str:
    return f"Motsvarar: {proc} % (baserat på {ref})"

def rendera_isa_450(st, sie, maskeringsresultat, ai_konfiguration):
    if sie is None or maskeringsresultat is None:
        st.info("Ladda in data i sidomenyn innan analys kan köras.")
        return

    ai_aktiv = (
        ai_konfiguration is not None
        and ai_konfiguration.status == "modeller_hämtade"
        and ai_konfiguration.vald_modell is not None
        and leverantor_har_analysstod(ai_konfiguration.leverantör)
    )

    if ai_aktiv:
        st.caption(
            f"Analysen körs mot {ai_konfiguration.leverantör}, modell "
            f"{ai_konfiguration.vald_modell} — enligt ditt val i sidomenyn."
        )
    else:
        st.caption(
            "Deterministisk analys (ISA 320/450). Ange en API-nyckel i sidomenyn för att även aktivera djupgående AI-kontomatchning."
        )

        _v = berakna_vasentlighet(sie)

        st.subheader(f"Väsentlighet (Modul 1) {HARKOMST_LOKAL.tecken}")
        kol_o, kol_r, kol_b, kol_e = st.columns(4)
        kol_o.metric("Omsättning", formatera_kr(_v.omsattning))
        kol_r.metric("Resultat", formatera_kr(_v.resultat))
        kol_b.metric("Balansomslutning", formatera_kr(_v.balansomslutning))
        kol_e.metric("Eget kapital", formatera_kr(_v.eget_kapital))

        _std_väsentlighetstal, _std_utfall = berakna_standardtroskelvarden(_v.omsattning)
        omsattning = _v.omsattning

        st.subheader(f"Tröskelvärden {HARKOMST_LOKAL.tecken}")
        st.caption(
            "Väsentlighetstalet baseras på omsättningen, utfallsväsentligheten på "
            "väsentlighetstalet. Tänk i procent eller i kronor — systemet räknar om "
            "åt dig. Hovra över ℹ️ för förklaring; värdena styr Modul 5:s ackumulering."
        )
        inmatningslage = st.radio(
            "Inmatningsläge",
            ["Ange i Procent (%)", "Ange i Belopp (kr)"],
            horizontal=True,
        )

        # Oavsett läge slutar vi med två absoluta kr-belopp (Decimal). number_input är
        # en float-gräns (Streamlit); vi går via Decimal(str(...)) och den redan
        # testade tolka_troskelvarden när analysen körs.
        kol_vt, kol_uv = st.columns(2)
        if inmatningslage == "Ange i Procent (%)":
            with kol_vt:
                procent_vt = st.number_input(
                    "Väsentlighetstal (%)", min_value=0.0, value=0.5, step=0.1,
                    format="%.2f", help=VASENTLIGHETSTAL_HELP,
                )
                väsentlighetstal_kr = belopp_fran_procent(Decimal(str(procent_vt)), omsattning)
                st.caption(
                    f"Motsvarar: {formatera_kr(väsentlighetstal_kr)} (baserat på Omsättning)"
                )
            with kol_uv:
                procent_uv = st.number_input(
                    "Utfallsväsentlighet (%)", min_value=0.0, value=75.0, step=1.0,
                    format="%.1f", help=UTFALLSVASENTLIGHET_HELP,
                )
                utfallsväsentlighet_kr = belopp_fran_procent(
                    Decimal(str(procent_uv)), väsentlighetstal_kr
                )
                st.caption(
                    f"Motsvarar: {formatera_kr(utfallsväsentlighet_kr)} "
                    "(baserat på Väsentlighetstalet)"
                )
        else:
            with kol_vt:
                belopp_vt = st.number_input(
                    "Väsentlighetstal (kr)", min_value=0.0, value=float(_std_väsentlighetstal),
                    step=1000.0, format="%.0f", help=VASENTLIGHETSTAL_HELP,
                )
                väsentlighetstal_kr = Decimal(str(belopp_vt))
                st.caption(
                    _procent_caption(
                        procent_fran_belopp(väsentlighetstal_kr, omsattning), "Omsättningen"
                    )
                )
            with kol_uv:
                belopp_uv = st.number_input(
                    "Utfallsväsentlighet (kr)", min_value=0.0, value=float(_std_utfall),
                    step=1000.0, format="%.0f", help=UTFALLSVASENTLIGHET_HELP,
                )
                utfallsväsentlighet_kr = Decimal(str(belopp_uv))
                st.caption(
                    _procent_caption(
                        procent_fran_belopp(utfallsväsentlighet_kr, väsentlighetstal_kr),
                        "Väsentlighetstalet",
                    )
                )

        if st.button("Kör analys"):
            try:
                utfallsväsentlighet, väsentlighetstal = tolka_troskelvarden(
                    str(utfallsväsentlighet_kr), str(väsentlighetstal_kr)
                )
            except TröskelvärdeFel as fel:
                st.session_state.analys_resultat = None
                st.error(str(fel))
            else:
                if ai_aktiv:
                    try:
                        haiku_anropare = bygg_analysanropare(
                            ai_konfiguration,
                            maskeringsresultat.maskerad_siefil.konton,
                            logg=st.session_state.sessionslogg,
                        )
                    except AnalysanropareFel as fel:
                        st.session_state.analys_resultat = None
                        st.error(str(fel))
                        haiku_anropare = None
                else:
                    haiku_anropare = lambda items, sys_prompt: []

                if haiku_anropare is not None:
                    st.session_state.analys_resultat = kor_analys(
                        sie, maskeringsresultat, haiku_anropare,
                        utfallsväsentlighet, väsentlighetstal,
                    )
                    if ai_aktiv:
                        revisionslogg.logga_ai_utflode(
                            ai_konfiguration.leverantör, ai_konfiguration.vald_modell,
                            "analys",
                            datakategorier=[
                                "kontoplan", "sandningsbara_verifikationer",
                                "väsentlighetstal",
                            ],
                            maskeringsstatistik=(
                                revisionslogg.maskeringsstatistik_fran_resultat(
                                    maskeringsresultat
                                )
                            ),
                        )

    # Läs om: knapptrycket ovan kan just ha satt ETT nytt resultat eller
    # nollställt det. Frågefliken nedan läser samma variabel.
    analys_resultat = st.session_state.analys_resultat
    if analys_resultat is not None:
        if analys_resultat.felmeddelande is not None:
            st.error(analys_resultat.felmeddelande)
        else:
            st.success(f"Analys klar. {HARKOMST_AI.tecken}")
            ack = analys_resultat.ackumulering
            kol1, kol2, kol3, kol4 = st.columns(4)
            kol1.metric(
                "Nettosumma", formatera_kr(ack.summa_netto),
                delta=ack.status_netto, delta_color="off",
            )
            kol2.metric(
                "Bruttosumma", formatera_kr(ack.summa_brutto),
                delta=ack.status_brutto, delta_color="off",
            )
            kol3.metric("Antal felaktigheter", ack.antal_felaktigheter)
            kol4.metric("Okänd riktning", ack.antal_okänd_riktning)

            if ack.felaktigheter:
                st.dataframe(
                    [
                        {
                            "Källa": f.källa,
                            "Belopp": str(f.belopp),
                            "Riktning": f.riktning,
                            "Konto": f.kontonr,
                            "Kontonamn": f.kontonamn,
                            "Motivering": f.motivering,
                            "Plats": f.plats or "",
                        }
                        for f in ack.felaktigheter
                    ]
                )
            else:
                st.write("Inga felaktigheter identifierade.")

