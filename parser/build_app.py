import sys

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()
    
# Extract docstring: lines 1-35. Let's write a new docstring.
# Imports: new imports.

import_section = """\"\"\"
app.py — Huvudskriptet för SIE-MCP:s gränssnitt.

Nu omstrukturerat enligt Fas 2: endast routing, global state-initiering,
sidomeny och st.navigation. All rendering sker per rum i rum_render.py.
\"\"\"
import streamlit as st
import app_tillstand
import app_config
import navigering
from ui_komponenter import compliance
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
"""

# set_page_config to st.title (lines 181-190)
setup = """
st.set_page_config(
    page_title="Spiris Agent Desktop",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("🤖 Spiris Agent Desktop")
if not compliance.krav_godkannande(st):
    st.stop()
"""

# session_state init
init_call = """
app_tillstand.initiera(st)
"""

# extract sidebar logic (897 to 1339)
sidebar_lines = []
in_sidebar = False
for line in text.split('\\n'):
    if "datakälla = st.sidebar.radio" in line:
        in_sidebar = True
    if "sie = st.session_state.sie" in line and in_sidebar:
        break
    if in_sidebar:
        sidebar_lines.append(line)

sidebar = "\\n".join(sidebar_lines)

# sticky_nav, badge, rapportunderlag
end_logic = """
# Badge och navigation
sie = st.session_state.get("sie")
maskeringsresultat = st.session_state.get("maskeringsresultat")
try:
    vantande_utkast = utkast.lista(status=utkast.VANTAR)
except Exception:
    vantande_utkast = []
avvikelser = navigering.hitta_verifikationsavvikelser(sie, maskeringsresultat) if sie and maskeringsresultat else []
atgardsstatus = navigering.bygg_atgardsstatus(
    navigering.ohanterade_maskeringsbehov(maskeringsresultat) if maskeringsresultat else [],
    avvikelser,
    antal_utkast=len(vantande_utkast),
)

st.session_state.rapportunderlag = app_tillstand.bygg_rapportunderlag(st)

# CSS (sticky_nav_css raderas i Fas 2)
# Men chattens CSS injiceras här:
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

with open('app_new.py', 'w', encoding='utf-8') as f:
    f.write(import_section + setup + init_call + sidebar + end_logic)
