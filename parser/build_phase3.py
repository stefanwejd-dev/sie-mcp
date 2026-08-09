import sys
from pathlib import Path
import re

with open("parser/sidebar.py", "r", encoding="utf-8") as f:
    sidebar_text = f.read()

# Kalla_vy logic
kalla_vy_content = """import asyncio
import sys
import tempfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import streamlit as st

import app_config
from app_tillstand import (
    _nollstall_inlast_data,
    _nollstall_samtalshistorik,
    _notera,
    _notera_period,
)
from app_vy import läs_och_maskera_fil
from fpa_vy import dashboard_saknar_data, innevarande_ar_intervall, valj_rakenskapsar_for_ar
from masking_memory import filtrera_bort_sedda, las_maskeringsminne
from app_vy import maskera_inlast_siefil

from spiris_adapter import (
    hamta_kundbetalhistorik,
    hamta_kundreskontra,
    hamta_reskontra,
    hamta_siefil_fran_spiris,
)
from spiris_auth_vy import (
    REDIRECT_URI,
    SpirisAuthFel,
    SpirisTokens,
    bygg_auktoriserings_url,
    extrahera_kod,
    generera_pkce,
    generera_state,
    vaxla_kod_mot_token,
)
from spiris_klient import SpirisKlient, SpirisKlientFel
import spiris_rag
import spiris_session

@st.dialog("Källa och period", width="large")
def oppna_kalladan():
    config = app_config.las_config()
    
    datakälla = st.radio(
        "Källa",
        ("Ladda upp lokal SIE4-fil", "Koppla till Spiris"),
        key="datakälla_val",
    )

    if datakälla != st.session_state.aktiv_datakälla:
        st.session_state.aktiv_datakälla = datakälla
        _nollstall_inlast_data()

    if datakälla == "Ladda upp lokal SIE4-fil":
        st.subheader("Anslutning")
        uppladdad_fil = st.file_uploader("Ladda upp en SIE4-fil", type=["se", "si", "txt"])

        if uppladdad_fil is not None:
            st.caption(f"Fil: {uppladdad_fil.name}")
            if uppladdad_fil.file_id != st.session_state.behandlad_fil_id:
                st.session_state.behandlad_fil_id = uppladdad_fil.file_id
                st.session_state.analys_resultat = None
                _nollstall_samtalshistorik()
                st.session_state.datastatus_notiser = []

                with tempfile.NamedTemporaryFile(delete=False, suffix=".se") as temp:
                    temp.write(uppladdad_fil.getvalue())
                    temp_sökväg = temp.name

                inläsningsresultat = läs_och_maskera_fil(
                    temp_sökväg,
                    liggare=st.session_state.maskeringsliggare,
                    undantagslista=app_config.normaliserade_undantag(
                        st.session_state.undantagslista
                    ),
                    referenslista=st.session_state.namnreferens,
                )
                Path(temp_sökväg).unlink(missing_ok=True)

                if inläsningsresultat.felmeddelande is not None:
                    st.session_state.sie = None
                    st.session_state.maskeringsresultat = None
                    _notera("error", inläsningsresultat.felmeddelande)
                else:
                    st.session_state.sie = inläsningsresultat.sie
                    st.session_state.maskeringsresultat = inläsningsresultat.maskeringsresultat
                    _notera("success", f"Läste och maskerade {uppladdad_fil.name}.")
                    
            if st.session_state.sie is not None:
                if st.button("Klar"):
                    st.rerun()

    else:
        st.subheader("Anslutning")
        if "spiris_client_id" not in st.session_state:
            st.session_state.spiris_client_id = config.spiris_client_id
        if "spiris_client_secret" not in st.session_state:
            st.session_state.spiris_client_secret = config.spiris_client_secret
        spiris_client_id = st.text_input("Client ID", key="spiris_client_id")
        spiris_client_secret = st.text_input(
            "Client Secret", type="password", key="spiris_client_secret"
        )
        app_config.spara_om_andrad("spiris_client_id", spiris_client_id, config)
        app_config.spara_om_andrad("spiris_client_secret", spiris_client_secret, config)
        
        if not spiris_client_id or not spiris_client_secret:
            st.info("Ange Client ID och Client Secret ovan för att logga in mot Spiris.")
        elif st.session_state.spiris_tokens is None:
            if st.session_state.spiris_state is None:
                st.session_state.spiris_state = generera_state()
                verifierare, _challenge = generera_pkce()
                st.session_state.spiris_code_verifier = verifierare
                st.session_state.spiris_code_challenge = _challenge
            auktoriserings_url = bygg_auktoriserings_url(
                spiris_client_id, REDIRECT_URI, st.session_state.spiris_state,
                code_challenge=st.session_state.get("spiris_code_challenge"),
            )
            st.markdown(f"**Steg 1.** [Logga in och godkänn åtkomst hos Spiris]({auktoriserings_url})")
            st.caption("Kopiera hela adressen ur webbläsarens adressfält.")
            inklistrad = st.text_input("**Steg 2.** Klistra in adressen (eller bara koden):", key="spiris_redirect_inmatning")
            if st.button("Slutför inloggning"):
                try:
                    kod = extrahera_kod(inklistrad, förväntat_state=st.session_state.spiris_state)
                    st.session_state.spiris_tokens = vaxla_kod_mot_token(
                        kod, spiris_client_id, spiris_client_secret,
                        code_verifier=st.session_state.spiris_code_verifier,
                    )
                except SpirisAuthFel as fel:
                    st.error(str(fel))
                else:
                    st.session_state.pop("spiris_redirect_inmatning", None)
                    st.rerun()
        else:
            st.success("Inloggad mot Spiris.")
            _kol_spara, _kol_ut = st.columns(2)
            if _kol_spara.button("Spara session för MCP-servern"):
                _res = spiris_session.persist_session(st.session_state.spiris_tokens)
                if _res.sparad:
                    st.success("Sessionen sparades lokalt för MCP-servern.")
                else:
                    st.error(f"Sessionen kunde inte sparas (status: {_res.statuskod}).")
            if _kol_ut.button("Logga ut"):
                spiris_session.radera_session()
                st.session_state.spiris_tokens = None
                st.session_state.spiris_state = None
                st.session_state.spiris_code_verifier = None
                st.session_state.spiris_code_challenge = None
                st.rerun()

            st.divider()
            st.subheader("Räkenskapsår")
            spiris_klient = SpirisKlient(
                access_token=st.session_state.spiris_tokens.access_token,
                refresh_token=st.session_state.spiris_tokens.refresh_token,
                client_id=spiris_client_id,
                client_secret=spiris_client_secret,
            )
            try:
                räkenskapsår = spiris_klient.hamta_alla("/fiscalyears")
            except SpirisKlientFel as fel:
                st.error(str(fel))
                räkenskapsår = []
            st.session_state.spiris_tokens = SpirisTokens(spiris_klient.access_token, spiris_klient.refresh_token)

            if räkenskapsår:
                etiketter = {f"{str(f.get('StartDate'))[:10]} – {str(f.get('EndDate'))[:10]}": f for f in räkenskapsår}
                _labels = list(etiketter.keys())
                _innevarande = valj_rakenskapsar_for_ar(räkenskapsår, datetime.now().year)
                _default_idx = 0
                if _innevarande is not None:
                    for _i, _f in enumerate(etiketter.values()):
                        if _f is _innevarande:
                            _default_idx = _i
                            break
                valt_år = st.selectbox("Välj år", _labels, index=_default_idx)
                valt = etiketter[valt_år]
                
                if st.session_state.spiris_hamtat_ar != valt["Id"]:
                    st.session_state.spiris_hamtat_ar = valt["Id"]
                    st.session_state.datastatus_notiser = []
                    with st.spinner("Hämtar och maskerar data från Spiris…"):
                        try:
                            sie_rå = hamta_siefil_fran_spiris(spiris_klient, valt["Id"], str(valt["EndDate"])[:10])
                        except SpirisKlientFel as fel:
                            _notera("error", str(fel))
                        else:
                            _sedda = las_maskeringsminne()
                            _antal_fore = len(sie_rå.verifikationer)
                            sie_rå = replace(sie_rå, verifikationer=filtrera_bort_sedda(sie_rå.verifikationer, _sedda))
                            _antal_bortfiltrerade = _antal_fore - len(sie_rå.verifikationer)
                            if _antal_bortfiltrerade:
                                _notera("caption", f"{_antal_bortfiltrerade} verifikat filtrerades bort (redan granskade).")
                            st.session_state.spiris_tokens = SpirisTokens(spiris_klient.access_token, spiris_klient.refresh_token)
                            
                            inläsningsresultat = maskera_inlast_siefil(
                                sie_rå,
                                liggare=st.session_state.maskeringsliggare,
                                undantagslista=app_config.normaliserade_undantag(st.session_state.undantagslista),
                                referenslista=st.session_state.namnreferens,
                            )
                            if inläsningsresultat.felmeddelande is not None:
                                st.session_state.sie = None
                                st.session_state.maskeringsresultat = None
                                _notera("error", inläsningsresultat.felmeddelande)
                            else:
                                st.session_state.analys_resultat = None
                                _nollstall_samtalshistorik()
                                st.session_state.sie = inläsningsresultat.sie
                                st.session_state.maskeringsresultat = inläsningsresultat.maskeringsresultat
                                try:
                                    st.session_state.spiris_reskontra = hamta_reskontra(spiris_klient)
                                except SpirisKlientFel:
                                    st.session_state.spiris_reskontra = None
                                try:
                                    st.session_state.spiris_kundreskontra = hamta_kundreskontra(spiris_klient)
                                except SpirisKlientFel:
                                    st.session_state.spiris_kundreskontra = None
                                try:
                                    st.session_state.spiris_kundbetalhistorik = hamta_kundbetalhistorik(spiris_klient)
                                except SpirisKlientFel:
                                    st.session_state.spiris_kundbetalhistorik = None
                                st.session_state.spiris_tokens = SpirisTokens(spiris_klient.access_token, spiris_klient.refresh_token)

                if st.session_state.sie is not None:
                    st.divider()
                    st.subheader("Rapportperiod")
                    _fpa_start, _fpa_slut = innevarande_ar_intervall()
                    if "fpa_startdatum" not in st.session_state:
                        st.session_state.fpa_startdatum = _fpa_start
                    if "fpa_slutdatum" not in st.session_state:
                        st.session_state.fpa_slutdatum = _fpa_slut
                    fpa_startdatum = st.date_input("Startdatum", key="fpa_startdatum")
                    fpa_slutdatum = st.date_input("Slutdatum", key="fpa_slutdatum")

                    _period_id = (str(fpa_startdatum), str(fpa_slutdatum))
                    if st.session_state.spiris_dashboard_period != _period_id:
                        st.session_state.spiris_dashboard_period = _period_id
                        with st.spinner("Hämtar FP&A-dashboard live från Spiris…"):
                            try:
                                _fpa_data = asyncio.run(spiris_rag.hamta_dashboard(spiris_klient, *_period_id))
                            except Exception as fel:
                                st.session_state.spiris_dashboarddata = None
                                _notera_period("warning", "Kunde inte hämta FP&A-data från Spiris.")
                            else:
                                st.session_state.spiris_tokens = SpirisTokens(spiris_klient.access_token, spiris_klient.refresh_token)
                                if dashboard_saknar_data(_fpa_data):
                                    st.session_state.spiris_dashboarddata = None
                                    _notera_period("info", "Sandboxen saknar bokförd data för vald period.")
                                else:
                                    st.session_state.spiris_dashboarddata = _fpa_data
                                    
                    if st.button("Klar"):
                        st.rerun()

def rendera_kallchip():
    import streamlit as st
    from parser.kalla_vy import oppna_kalladan
    
    col1, col2 = st.columns([4, 1])
    
    datakälla = st.session_state.get("aktiv_datakälla", "Ladda upp lokal SIE4-fil")
    
    if datakälla == "Ladda upp lokal SIE4-fil":
        if st.session_state.get("sie") is not None:
            namn = st.session_state.sie.foretag.namn if st.session_state.sie.foretag else "Lokal fil"
            text = f"🟢 {namn}"
        else:
            text = "⚪ Ingen källa ansluten"
    else:
        if st.session_state.get("spiris_tokens") is not None:
            if st.session_state.get("sie") is not None:
                namn = st.session_state.sie.foretag.namn if st.session_state.sie.foretag else "Spiris"
                period = st.session_state.get("spiris_dashboard_period")
                period_str = f" · {period[0]} – {period[1]}" if period else ""
                text = f"🟢 Spiris · {namn}{period_str}"
            else:
                text = "🟡 Spiris ansluten (ingen data)"
        else:
            text = "⚪ Ingen källa ansluten"
            
    with col1:
        st.markdown(text)
    with col2:
        if st.button("Byt källa"):
            oppna_kalladan()
"""
with open("parser/kalla_vy.py", "w", encoding="utf-8") as f:
    f.write(kalla_vy_content)
