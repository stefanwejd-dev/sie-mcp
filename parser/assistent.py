import streamlit as st
from dataclasses import dataclass, replace
from decimal import Decimal

import app_config
import revisionslogg
import sessionslogg
from ai_konfiguration import AIKonfiguration, LEVERANTÖRER, uppdatera_med_hamtade_modeller
from ai_adapter import leverantor_har_analysstod, leverantor_har_samtalsstod, bygg_chattanropare, bygg_agentanropare, SamtalanropareFel
from chatt_renderare import rendera_strukturerat_svar
from samtalsflode import (
    FÖRESLAGNA_FRÅGOR, SVARSLÄGEN, ChattMeddelande, bygg_saker_kontext, ställ_fraga, ställ_fraga_till_agent,
)
from sekretesslager import maskera_chattmeddelande
from svarskontrakt import validera_svar, text_sammanfattning, validera_svar_dict, med_inledande_text
from app_vy import tolka_valverktygsanrop, tolka_fakturaverktygsanrop, tolka_kundverktygsanrop
from fpa_vy import likviditetsprognos_fran_reskontra

@dataclass
class AssistentKontext:
    sie: "Any"
    maskeringsresultat: "Any"
    analys_resultat: "Any" = None
    reskontra: list | None = None
    kundreskontra: list | None = None
    likviditetsprognos: dict | None = None

def _rendera_valknappar(alternativ: list[str]) -> None:
    bas = len(st.session_state.samtal_historik)
    kolumner = st.columns(len(alternativ) + 1)
    for i, (kolumn, val) in enumerate(zip(kolumner, alternativ)):
        if kolumn.button(val, key=f"valknapp_{bas}_{i}"):
            st.session_state.samtal_historik.append(ChattMeddelande(roll="user", text=val))
            st.session_state.visa_eget_svarsfalt = False
            st.rerun()

    if kolumner[-1].button("✏️ Skriv eget...", key=f"valknapp_eget_{bas}"):
        st.session_state.visa_eget_svarsfalt = True

    if st.session_state.visa_eget_svarsfalt:
        eget_svar = st.text_input(
            "Skriv ditt eget svar", key=f"eget_svar_{bas}", label_visibility="collapsed",
        )
        if st.button("Skicka", key=f"skicka_eget_{bas}") and eget_svar.strip():
            st.session_state.samtal_historik.append(
                ChattMeddelande(roll="user", text=eget_svar.strip())
            )
            st.session_state.visa_eget_svarsfalt = False
            st.rerun()

def _rendera_utflodeslogg() -> None:
    logg = st.session_state.sessionslogg
    with st.expander("🔍 AI-utflödeslogg — vad har skickats till AI:t?"):
        if getattr(logg, "sokvag", None) is None:
            st.warning("Ingen säker lagringsplats för loggarna kunde lösas ut.")
            return

        st.markdown(
            "Varje körning av appen får en egen loggfil med **exakt den text "
            "som skickades** till AI-leverantören, och svaret. Filerna ligger "
            "utanför projektmappen och raderas automatiskt efter "
            f"{sessionslogg.STANDARD_LAGRINGSTID_DAGAR} dagar."
        )
        st.caption("Mapp med alla loggfiler:")
        st.code(str(logg.sokvag.parent.parent), language=None)

        try:
            innehall = logg.sokvag.read_text(encoding="utf-8")
        except OSError:
            innehall = None
        if innehall is not None:
            st.download_button(
                "⬇️ Ladda ned den här sessionens logg",
                data=innehall,
                file_name=logg.sokvag.name,
                mime="text/markdown",
                key="download_log"
            )

        sessioner = sessionslogg.lista_sessioner()
        if sessioner:
            st.caption(f"Sparade loggar ({len(sessioner)} senaste):")
            st.dataframe(
                [{"Fil": s["namn"], "Ändrad": s["andrad"], "Storlek (kB)": s["storlek_kb"]} for s in sessioner],
                hide_index=True,
                width="stretch",
            )

def _rendera_ai_installningar() -> None:
    config = app_config.las_config()
    st.subheader("⚙️ AI-inställningar")
    if "ai_leverantör_val" not in st.session_state:
        st.session_state.ai_leverantör_val = (
            config.ai_leverantör if config.ai_leverantör in LEVERANTÖRER else LEVERANTÖRER[0]
        )
    vald_leverantör = st.selectbox("Leverantör", LEVERANTÖRER, key="ai_leverantör_val")

    if vald_leverantör == "Ollama":
        st.caption("🔒 **100 % lokal körning — Ingen data lämnar datorn (GDPR-optimalt)**")
        api_nyckel = ""
    else:
        st.caption(f"🌐 **Molnbaserad AI (USA)** — Externa anrop sker till **{vald_leverantör}**.")
        if "ai_api_nyckel_val" not in st.session_state:
            st.session_state.ai_api_nyckel_val = config.ai_api_nyckel
        api_nyckel = st.text_input("API-nyckel", type="password", key="ai_api_nyckel_val")

    app_config.spara_om_andrad("ai_leverantör", vald_leverantör, config)
    app_config.spara_om_andrad("ai_api_nyckel", api_nyckel, config)

    _kraver_nyckel = vald_leverantör != "Ollama"
    _ai_id = (vald_leverantör, api_nyckel)
    if (api_nyckel or not _kraver_nyckel) and st.session_state.ai_modeller_for != _ai_id:
        st.session_state.ai_modeller_for = _ai_id
        with st.spinner("Hämtar modeller…"):
            st.session_state.ai_konfiguration = uppdatera_med_hamtade_modeller(
                AIKonfiguration(leverantör=vald_leverantör, api_nyckel=api_nyckel)
            )
    elif not api_nyckel and _kraver_nyckel:
        st.session_state.ai_konfiguration = None
        st.session_state.ai_modeller_for = None

    ai_konfiguration = st.session_state.ai_konfiguration
    if ai_konfiguration is None:
        st.caption("Ange en API-nyckel så laddas modellerna automatiskt.")
    elif ai_konfiguration.status == "modeller_hämtade":
        _modeller = ai_konfiguration.tillgängliga_modeller
        _def_idx = _modeller.index(config.ai_vald_modell) if config.ai_vald_modell in _modeller else 0
        vald_modell = st.selectbox("Modell", _modeller, index=_def_idx)
        if vald_modell != ai_konfiguration.vald_modell:
            st.session_state.ai_konfiguration = replace(ai_konfiguration, vald_modell=vald_modell)
        app_config.spara_om_andrad("ai_vald_modell", vald_modell, config)
    elif ai_konfiguration.status == "fel":
        st.error(f"Kunde inte hämta modeller: {ai_konfiguration.felmeddelande}")

def rendera_panel(st, rum_id: str, kontext: AssistentKontext, som_expander: bool = True) -> None:
    """AI-panelen, tillgänglig i varje rum och förladdad med rummets kontext."""
    if som_expander:
        with st.expander("💬 Fråga om det här", expanded=False):
            _rendera_panel_innehall(st, rum_id, kontext)
    else:
        _rendera_panel_innehall(st, rum_id, kontext)

def _rendera_panel_innehall(st, rum_id: str, kontext: AssistentKontext) -> None:
    ai_konfiguration = st.session_state.get("ai_konfiguration")
    if ai_konfiguration is None or ai_konfiguration.status != "modeller_hämtade":
        st.info("AI-modeller saknas. Fyll i AI-inställningarna i vänstermenyn.")
        return
            
    svarsläge = st.radio("Svarsstil", options=SVARSLÄGEN, index=SVARSLÄGEN.index("pedagogisk"), horizontal=True, key=f"svarsstil_{rum_id}")

    st.write("Föreslagna frågor:")
    exempel_fraga: str | None = None
    for rad_start in range(0, len(FÖRESLAGNA_FRÅGOR), 3):
        rad_frågor = FÖRESLAGNA_FRÅGOR[rad_start : rad_start + 3]
        kolumner = st.columns(3)
        for kolumn, föreslagen_fråga in zip(kolumner, rad_frågor):
            if kolumn.button(föreslagen_fråga.etikett, key=f"fraga_{rum_id}_{föreslagen_fråga.etikett}"):
                exempel_fraga = föreslagen_fråga.fråga

    datakälla = st.session_state.get("aktiv_datakälla")
    agentlage = datakälla == "Koppla till Spiris" and st.session_state.get("spiris_tokens") is not None

    if (st.session_state.samtal_historik 
        and st.session_state.samtal_historik[-1].roll == "user" 
        and len(st.session_state.samtal_historik) - 1 > st.session_state.get("samtal_senast_behandlat", -1)):
        
        user_message_index = len(st.session_state.samtal_historik) - 1
        senaste_maskering = maskera_chattmeddelande(
            st.session_state.samtal_historik[-1].text,
            st.session_state.maskeringsliggare,
            st.session_state.namnreferens,
        )
        senaste_fraga = senaste_maskering.text
        
        byggd_kontext = bygg_saker_kontext(
            kontext.sie,
            kontext.maskeringsresultat,
            kontext.analys_resultat,
            reskontra=kontext.reskontra,
            kundreskontra=kontext.kundreskontra,
            likviditetsprognos=kontext.likviditetsprognos,
        )

        _chatt_kategorier = ["filöversikt", "kontosaldon", "användarfråga"]
        if kontext.reskontra or kontext.kundreskontra:
            _chatt_kategorier.append("reskontra")
        if kontext.analys_resultat is not None and kontext.analys_resultat.felmeddelande is None:
            _chatt_kategorier.append("ackumuleringsresultat")

        def _logga_utflode() -> None:
            revisionslogg.logga_ai_utflode(
                ai_konfiguration.leverantör, ai_konfiguration.vald_modell,
                "agent" if agentlage else "samtal",
                datakategorier=_chatt_kategorier,
                maskeringsstatistik=revisionslogg.maskeringsstatistik_fran_resultat(
                    kontext.maskeringsresultat
                ),
            )

        if senaste_maskering.blockerad:
            st.session_state.samtal_historik.append(ChattMeddelande(
                roll="assistant",
                text="⚠️ Meddelandet blockerat (fail-closed) då ett namn inte kunde säkert avidentifieras."
            ))
        elif not agentlage:
            _logga_utflode()
            try:
                anropare = bygg_chattanropare(ai_konfiguration, logg=st.session_state.sessionslogg)
                svar = ställ_fraga(senaste_fraga, byggd_kontext, anropare, svarsläge=svarsläge)
            except SamtalanropareFel as fel:
                svar = str(fel)
            strukturerat = validera_svar(svar)
            if strukturerat is None:
                st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=svar))
            else:
                st.session_state.samtal_historik.append(ChattMeddelande(
                    roll="assistant",
                    text=text_sammanfattning(strukturerat),
                    strukturerat=strukturerat.model_dump(),
                ))
        else:
            _logga_utflode()
            try:
                anropare = bygg_agentanropare(ai_konfiguration, logg=st.session_state.sessionslogg)
            except SamtalanropareFel as fel:
                st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=str(fel)))
            else:
                api_meddelanden = []
                for m in st.session_state.samtal_historik:
                    if m.roll != "user":
                        api_meddelanden.append({"roll": m.roll, "text": m.text})
                        continue
                    _mask = maskera_chattmeddelande(
                        m.text, st.session_state.maskeringsliggare,
                        st.session_state.namnreferens,
                    )
                    api_meddelanden.append({
                        "roll": m.roll,
                        "text": "[meddelande kunde inte avidentifieras]" if _mask.blockerad else _mask.text,
                    })
                agentsvar = ställ_fraga_till_agent(api_meddelanden, byggd_kontext, anropare, svarsläge=svarsläge)
                if agentsvar.verktygsanrop is not None and agentsvar.verktygsanrop.namn == "efterfraga_val":
                    try:
                        valfraga = tolka_valverktygsanrop(agentsvar.verktygsanrop.indata)
                    except ValueError as fel:
                        st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=f"⚠️ Fel: {fel}"))
                    else:
                        st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=valfraga.fraga, alternativ=valfraga.alternativ))
                elif agentsvar.verktygsanrop is not None and agentsvar.verktygsanrop.namn == "presentera_strukturerat_svar":
                    strukturerat = validera_svar_dict(agentsvar.verktygsanrop.indata)
                    if strukturerat is None:
                        st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=agentsvar.text or "⚠️ Oformaterat svar"))
                    else:
                        strukturerat = med_inledande_text(strukturerat, agentsvar.text)
                        st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=text_sammanfattning(strukturerat), strukturerat=strukturerat.model_dump()))
                else:
                    if agentsvar.text:
                        st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=agentsvar.text))
                    if agentsvar.verktygsanrop is None:
                        pass
                    elif agentsvar.verktygsanrop.namn == "skapa_kund":
                        try:
                            förslag = tolka_kundverktygsanrop(agentsvar.verktygsanrop.indata)
                            st.session_state.aktivt_fakturautkast = {"typ": "kund", "fas": "sok_kund", "kundnamn": förslag.kundnamn, "ar_privatperson": förslag.ar_privatperson}
                            st.rerun()
                        except ValueError as fel:
                            st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=f"⚠️ Fel: {fel}"))
                    elif agentsvar.verktygsanrop.namn == "skapa_kundfaktura":
                        try:
                            faktura_tillstand = tolka_fakturaverktygsanrop(agentsvar.verktygsanrop.indata)
                            st.session_state.aktivt_fakturautkast = {"typ": "faktura", "fas": "sok_kund", **faktura_tillstand}
                            st.rerun()
                        except ValueError as fel:
                            st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=f"⚠️ Fel: {fel}"))
                    else:
                        st.session_state.samtal_historik.append(ChattMeddelande(roll="assistant", text=f"⚠️ Okänt verktyg: {agentsvar.verktygsanrop.namn!r}"))

        # Markera det ursprungliga användarmeddelandet som behandlat först NÄR svaret är sparat
        st.session_state.samtal_senast_behandlat = user_message_index

    for i, meddelande in enumerate(st.session_state.samtal_historik):
        with st.chat_message(meddelande.roll):
            renderat = False
            if getattr(meddelande, "strukturerat", None):
                renderat = rendera_strukturerat_svar(meddelande.strukturerat, meddelande_index=i)
            if not renderat:
                st.write(meddelande.text)
            sista = i == len(st.session_state.samtal_historik) - 1
            if sista and meddelande.alternativ:
                _rendera_valknappar(meddelande.alternativ)

    ny_fraga = st.chat_input(f"Din fråga till AI-assistenten i rummet...", key=f"chat_{rum_id}")
    vald_fraga = exempel_fraga or ny_fraga
    if vald_fraga:
        st.session_state.samtal_historik.append(ChattMeddelande(roll="user", text=vald_fraga))
        st.rerun()
        
    st.divider()
    st.caption("Det här har lämnat datorn i den här sessionen:")
    _rendera_utflodeslogg()
    
    st.divider()
    st.caption("**Förklaring av härkomstmärken:**")
    from stil import ALLA_HARKOMST
    for marke in ALLA_HARKOMST:
        st.caption(f"{marke.tecken} **{marke.namn}** — {marke.forklaring}")
