import sys
with open('parser/ai_sidebar_lines.py', 'r', encoding='utf-8') as f:
    ai_sidebar = f.read()

lines = ai_sidebar.split('\n')
if lines and lines[-1].strip() == '':
    lines = lines[:-1]
if lines and 'sie = st.session_state.sie' in lines[-1]:
    lines = lines[:-1]
ai_sidebar = '\n'.join(lines)

app_content = """import sys
from pathlib import Path

_PARSER_DIR = Path(__file__).resolve().parent / 'parser'
if str(_PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(_PARSER_DIR))

import streamlit as st
import app_tillstand
import app_config
import navigering
import compliance
from formatering_ui import rendera_verktygsrad
from rum import (
    RUM_OVERSIKT,
    RUM_BESLUT,
    RUM_PENGAR_IN,
    RUM_PENGAR_UT,
    RUM_BOCKERNA,
    RUM_RAPPORTER,
    RUM_INVESTERINGSKALKYL
)
import rum_render
import utkast
from ai_konfiguration import AIKonfiguration, LEVERANTÖRER, uppdatera_med_hamtade_modeller
from dataclasses import replace
from kalla_vy import rendera_kallchip

st.set_page_config(
    page_title="Spiris Agent Desktop",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("🤖 Spiris Agent Desktop")
compliance.krav_godkannande(st)

app_tillstand.initiera(st)

config = app_config.las_config()

with st.sidebar:
    st.header("Inställningar")
    rendera_verktygsrad(st)
""" + ai_sidebar + """
rendera_kallchip()

import kommandofalt
kommandofalt.rendera_kommandofalt(st, sidor)

# Badge och navigation
sie = st.session_state.get("sie")
maskeringsresultat = st.session_state.get("maskeringsresultat")
try:
    vantande_utkast = utkast.lista(status=utkast.VANTAR)
except Exception:
    vantande_utkast = []
avvikelser = navigering.hitta_verifikationsavvikelser(sie, maskeringsresultat) if sie and maskeringsresultat else []
atgardsstatus = navigering.bygg_atgardsstatus(
    navigering.ohanterade_maskeringsbehov(maskeringsresultat) if maskeringsresultat else 0,
    avvikelser,
    antal_utkast=len(vantande_utkast),
)

st.session_state.rapportunderlag = app_tillstand.bygg_rapportunderlag(st)

from chatt_renderare import injicera_chatt_css
injicera_chatt_css()

def _rendera_beslut_wrapper():
    rum_render.rendera_beslut(st.session_state.get("spiris_client_id"), st.session_state.get("spiris_client_secret"))

sidor = [
    st.Page(rum_render.rendera_oversikt,            title="Översikt",           icon="🏠", url_path="oversikt", default=True),
    st.Page(_rendera_beslut_wrapper,                title=atgardsstatus.etikett, icon="✅", url_path="beslut"),
    st.Page(rum_render.rendera_pengar_in,           title="Pengar in",          icon="📥", url_path="pengar-in"),
    st.Page(rum_render.rendera_pengar_ut,           title="Pengar ut",          icon="📤", url_path="pengar-ut"),
    st.Page(rum_render.rendera_bockerna,            title="Böckerna",           icon="📚", url_path="bockerna"),
    st.Page(rum_render.rendera_rapporter,           title="Rapporter & analys", icon="📊", url_path="rapporter"),
    st.Page(rum_render.rendera_investeringskalkyl,  title="Investeringskalkyl", icon="📈", url_path="investering"),
]
st.navigation(sidor, position="top").run()
"""
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(app_content)
