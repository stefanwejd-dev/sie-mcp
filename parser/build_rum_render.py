import sys

with open('parser/extracted_blocks.txt', 'r', encoding='utf-8') as f:
    text = f.read()

blocks = {}
current = None
for line in text.split('\n'):
    if line.startswith('--- ') and line.endswith(' ---'):
        current = line[4:-4]
        blocks[current] = []
    elif current:
        blocks[current].append(line)

for k in blocks:
    blocks[k] = '\n'.join(blocks[k])

template = '''"""rum_render.py — Den enda ritmodulen för rummen (Streamlit-medveten)."""
import streamlit as st
import datetime
from datetime import date, timedelta
from decimal import Decimal
from ordbok import Begrepp, hamta
import snabbvyer
import snabbvy_render
import navigering
import fpa_dashboard
import sessionslogg
import utkast
import app_config
from app_tillstand import _hitta_originaltext
from fpa_vy import formatera_kr
from formatering_ui import hamta_val
from samtalsflode import ChattMeddelande
from spiris_klient import SpirisKlient, SpirisKlientFel
from spiris_session import SpirisSessionFel
from spiris_auth_vy import SpirisTokens
from app_vy import (
    sok_lika_kunder, 
    bygg_ny_kund_payload,
    bygg_oversikt
)
from spiris_adapter import kraver_rot_flaggning, FAKTURATYP_JURIDISK_PERSON, bygg_kundfaktura_payload, _FAKTURATYP_ETIKETTER
from spiris_adapter import utfor_utkast, skapa_kund
from app_vy import (
    obeslutade_behov,
    unika_namn_behov,
    markera_kanslig_text,
    BESLUT_AVVAKTA,
    BESLUT_MASKERA,
    BESLUT_INGEN_MASKERING,
    bygg_granskade_behov_per_namn,
    tillämpa_liggare,
    namn_att_undanta,
)
from masking_memory import lagg_till_maskeringsminne, verifikation_id
from app_vy import verifikation_till_visningsrad
from app_tillstand import _rendera_notiser
from assistent_funcs import _rendera_utflodeslogg

_BESLUTSETIKETTER = {
    BESLUT_AVVAKTA: "Avvakta",
    BESLUT_MASKERA: "Maskera",
    BESLUT_INGEN_MASKERING: "Ingen maskering",
}

def tomt_lage(st, begrepp: Begrepp, vad_rummet_visar: str) -> None:
    st.header(begrepp.namn)
    st.info(f"{vad_rummet_visar} saknas.")
    col1, col2 = st.columns(2)
    col1.button("Anslut ett affärssystem", disabled=True, help="Kommer i Fas 3")
    col2.button("Ladda upp en SIE4-fil", disabled=True, help="Kommer i Fas 3")
    st.caption(begrepp.forklaring)

%UTKAST%

def rendera_oversikt() -> None:
    st.header("🏠 Översikt")
    datakälla = st.session_state.get("aktiv_datakälla", "Ladda upp lokal SIE4-fil")
    sie = st.session_state.get("sie")
    maskeringsresultat = st.session_state.get("maskeringsresultat")
%DATASTATUS%

def rendera_beslut(spiris_client_id: str, spiris_client_secret: str) -> None:
    datakälla = st.session_state.get("aktiv_datakälla", "Ladda upp lokal SIE4-fil")
    sie = st.session_state.get("sie")
    maskeringsresultat = st.session_state.get("maskeringsresultat")
    vantande_utkast = []
    try:
        vantande_utkast = utkast.lista(status=utkast.VANTAR)
    except Exception:
        pass
    avvikelser = navigering.hitta_verifikationsavvikelser(sie, maskeringsresultat) if sie and maskeringsresultat else []
    atgardsstatus = navigering.bygg_atgardsstatus(
        navigering.ohanterade_maskeringsbehov(maskeringsresultat) if maskeringsresultat else [],
        avvikelser,
        antal_utkast=len(vantande_utkast),
    )
%ATGARDER%

def rendera_pengar_in() -> None:
    st.header("📥 Pengar in")
    if not st.session_state.get("spiris_kundreskontra") and not st.session_state.get("sie"):
        tomt_lage(st, hamta("kundreskontra"), "Reskontra")
        return
        
    snabbvy_render.injicera_snabbvy_css(st)
    vydata = snabbvyer.Vydata(
        idag=datetime.date.today(),
        kundreskontra=st.session_state.spiris_kundreskontra,
        leverantorsreskontra=st.session_state.spiris_reskontra,
        kundbetalbeteende=st.session_state.get("rapportunderlag").kundbetalbeteende if st.session_state.get("rapportunderlag") else {},
        formateringsval=hamta_val(),
    )
    snabbvy_render.rendera_snabbvyfalt(st, snabbvyer.SNABBVYER_KUND, "snabbvy_pengar_in", vydata)

def rendera_pengar_ut() -> None:
    st.header("📤 Pengar ut")
    if not st.session_state.get("spiris_reskontra") and not st.session_state.get("sie"):
        tomt_lage(st, hamta("leverantorsreskontra"), "Reskontra")
        return
        
    snabbvy_render.injicera_snabbvy_css(st)
    vydata = snabbvyer.Vydata(
        idag=datetime.date.today(),
        kundreskontra=st.session_state.spiris_kundreskontra,
        leverantorsreskontra=st.session_state.spiris_reskontra,
        kundbetalbeteende=st.session_state.get("rapportunderlag").kundbetalbeteende if st.session_state.get("rapportunderlag") else {},
        formateringsval=hamta_val(),
    )
    snabbvy_render.rendera_snabbvyfalt(st, snabbvyer.SNABBVYER_LEVERANTOR, "snabbvy_pengar_ut", vydata)

def rendera_bockerna() -> None:
    st.header("📚 Böckerna")
    st.info("Böckerna är under konstruktion (Fas 2).")

def rendera_rapporter() -> None:
%RAPPORTER%

def rendera_investeringskalkyl() -> None:
    st.header("📈 Investeringskalkyl")
    rapporter = st.session_state.get("rapportunderlag")
    if not rapporter or not rapporter.rapporter:
        tomt_lage(st, hamta("investeringskalkyl"), "Investeringskalkyl")
        return
        
    fpa_dashboard.rendera_investeringskalkyl(
        rapporter.rapporter["resultat"],
        rapporter.rapporter["balans"],
    )

'''

datastatus = '\n'.join(l for l in blocks['DATASTATUS'].split('\n')[1:])
atgarder = '\n'.join(l for l in blocks['ATGARDER'].split('\n')[1:])
rapporter = '\n'.join(l for l in blocks['RAPPORTER'].split('\n')[1:])

res = template.replace('%UTKAST%', blocks['UTKAST']).replace('%DATASTATUS%', datastatus).replace('%ATGARDER%', atgarder).replace('%RAPPORTER%', rapporter)

with open('parser/rum_render.py', 'w', encoding='utf-8') as f:
    f.write(res)

from sekretesslager import uppdatera_efter_granskning
