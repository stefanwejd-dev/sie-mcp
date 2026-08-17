import os
import sys
from pathlib import Path

_PARSER_DIR = Path(__file__).resolve().parent / 'parser'
if str(_PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(_PARSER_DIR))

_BRANDING_DIR = Path(__file__).resolve().parent / 'assets' / 'branding'

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
    RUM_INVESTERINGSKALKYL,
    RUM_SALJDOKUMENT
)
import rum_render
import utkast
from ai_konfiguration import AIKonfiguration, LEVERANTÖRER, uppdatera_med_hamtade_modeller
from dataclasses import replace
from parser.kalla_vy import rendera_kallchip

_SIDIKON = _BRANDING_DIR / "icon-128.png"
st.set_page_config(
    page_title="Quiet Numbers — sie-mcp",
    # Quiet Numbers-badgen som flikikon om filen finns, annars emoji-fallback
    # — en saknad tillgångsfil (t.ex. ett grundare klonat repo) ska aldrig
    # hindra appen från att starta.
    page_icon=str(_SIDIKON) if _SIDIKON.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("Quiet Numbers — sie-mcp")
st.caption("En tjänst från **Quiet Numbers**.")

# I demoläge (t.ex. på webbdemo app.quiet.nu) öppnas appen direkt för besökaren
# med tydlig ansvarsfriskrivning i stället för att blockera demonstrationen.
if not (os.environ.get("SIE_MCP_DEMO") == "1" or "--demo" in sys.argv):
    compliance.krav_godkannande(st)
else:
    with st.expander("⚖️ Användarvillkor & Ansvarsfriskrivning (Demoläge)", expanded=False):
        st.markdown(compliance.villkorstext())

app_tillstand.initiera(st)

if (os.environ.get("SIE_MCP_DEMO") == "1" or "--demo" in sys.argv) and st.session_state.get("sie") is None:
    try:
        from verktyg.demo_data import ladda_demodata
        ladda_demodata(st)
    except Exception:
        pass

config = app_config.las_config()

data_page = st.Page(rum_render.rendera_data, title="Data in/ut", icon="🔄", url_path="data")

with st.sidebar:
    # Utgivarmärke överst: badgen har egen mörk bakgrund (se
    # assets/branding — README:t i logotypmappen) och behöver därför ingen
    # ljus/mörk-variant för att läsas i båda Streamlit-teman.
    _qn_badge = _BRANDING_DIR / "icon-badge.svg"
    if _qn_badge.exists():
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c2:
            st.image(str(_qn_badge), width="stretch")
        
        st.markdown(
            "<div style='text-align: center; margin-top: 5px; margin-bottom: 25px;'>"
            "<div style='font-size: 1.3rem; font-weight: bold; margin-bottom: 4px;'>Quiet Numbers</div>"
            "<div style='font-size: 0.85rem; opacity: 0.8; line-height: 1.2;'>"
            "Utgivare av sie-mcp"
            "</div>"
            "</div>",
            unsafe_allow_html=True
        )
    
    rendera_kallchip(data_page)
    rendera_verktygsrad(st)
    # --- AI-inställningar (alltid synlig, oavsett datakälla) ------------------
    # Automatiserad: när en API-nyckel finns hämtas modeller i bakgrunden (dedup
    # via ai_modeller_for → ingen loop). Leverantör, nyckel och senast valda
    # modell förifylls från .env och persisteras vid ändring.
    with st.expander("AI-inställningar", expanded=False):

        if "ai_leverantör_val" not in st.session_state:
            st.session_state.ai_leverantör_val = (
                config.ai_leverantör if config.ai_leverantör in LEVERANTÖRER else LEVERANTÖRER[0]
            )
        vald_leverantör = st.selectbox("Leverantör", LEVERANTÖRER, key="ai_leverantör_val")

        if vald_leverantör == "Ollama":
            st.markdown("**Lokal AI (Ollama)**")
            st.caption(
                "Körs helt lokalt mot http://localhost:11434 — ingen API-nyckel, "
                "ingen data lämnar datorn. Kräver att Ollama är installerat och "
                "igång, samt att önskad modell är hämtad (kommandot nedan)."
            )
            st.caption("🔒 **100 % lokal körning — Ingen data lämnar datorn, ingen tredjelandsöverföring (GDPR-optimalt)**")
            st.markdown(
                "| Profil | Modell | Kommando | Kommentar |\n"
                "|---|---|---|---|\n"
                "| Snabb och lätt | [Phi-4-mini](https://ollama.com/library/phi4-mini) "
                "| `ollama run phi4-mini` | Enklare frågor, sammanfattning, svagare laptops |\n"
                "| Rekommenderad balans | [Qwen3 8B](https://ollama.com/library/qwen3:8b) "
                "| `ollama run qwen3:8b` | Standardval för svensk ekonomiassistans, "
                "resonemang, strukturerade svar |\n"
                "| Stabil allround | [Llama 3.1 8B](https://ollama.com/library/llama3.1:8b) "
                "| `ollama run llama3.1:8b` | Välkänt, brett ekosystem |\n"
                "| Strukturerad analys | [IBM Granite 3.2 8B](https://ollama.com/ibm/granite3.2:8b) "
                "| `ollama run ibm/granite3.2:8b` | RAG, dokumentarbete, verktygsanrop, "
                "regelstyrda flöden |\n"
                "| Kraftfull lokal analys | [Mistral-Nemo 12B](https://ollama.com/library/mistral-nemo:12b) "
                "| `ollama run mistral-nemo:12b` | Starkare datorer; 128k kontextfönster |\n"
            )
            api_nyckel = ""
        else:
            st.caption(
                f"🌐 **Molnbaserad AI (USA)** — Externa anrop sker under ditt eget avtal med "
                f"**{vald_leverantör}** (BYOK). Du ansvarar för ditt DPA och laglig grund "
                "(se [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md))."
            )
            if "ai_api_nyckel_val" not in st.session_state:
                st.session_state.ai_api_nyckel_val = config.ai_api_nyckel
            api_nyckel = st.text_input("API-nyckel", type="password", key="ai_api_nyckel_val")

        app_config.spara_om_andrad("ai_leverantör", vald_leverantör, config)
        app_config.spara_om_andrad("ai_api_nyckel", api_nyckel, config)

        # Auto-hämta modeller när nyckel finns (eller när leverantören inte
        # kräver någon, dvs. Ollama); vakten sätts FÖRE hämtningen.
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
                ai_konfiguration = replace(ai_konfiguration, vald_modell=vald_modell)
                st.session_state.ai_konfiguration = ai_konfiguration
            app_config.spara_om_andrad("ai_vald_modell", vald_modell, config)
        elif ai_konfiguration.status == "fel":
            st.error(f"Kunde inte hämta modeller: {ai_konfiguration.felmeddelande}")

    with st.expander("🔧 System & Minne", expanded=False):
        if st.button("Glöm sparade uppgifter"):
            app_config.rensa_config()
            for _k in (
                "spiris_client_id", "spiris_client_secret", "ai_leverantör_val",
                "ai_api_nyckel_val", "ai_modeller_for", "ai_konfiguration",
            ):
                st.session_state.pop(_k, None)
            st.rerun()

        _antal_larda = len(st.session_state.maskeringsliggare)
        st.caption(f"Maskeringsminne: {_antal_larda} inlärda namn (krypterat lokalt).")
        if st.button("Töm maskeringsminne"):
            app_config.tom_maskeringsliggare()
            st.session_state.maskeringsliggare = {}
            st.rerun()

        # Undantagslistan är den enda mekanismen som TYSTAR sekretesslagret. Den
        # måste därför alltid gå att inspektera och ångra — en felklickad "Ingen
        # maskering" får aldrig bli en permanent, osynlig lucka.
        _undantag = st.session_state.undantagslista
        st.caption(f"Undantagslista: {len(_undantag)} strängar flaggas aldrig (krypterat lokalt).")
        if _undantag:
            with st.expander("Visa undantagslistan"):
                for _post in _undantag:
                    _kol_text, _kol_bort = st.columns([3, 1])
                    _kol_text.write(_post.get("text", ""))
                    if _kol_bort.button("Ta bort", key=f"ta_bort_undantag_{_post['normaliserad']}"):
                        _kvar = app_config.ta_bort_undantag(_undantag, _post["normaliserad"])
                        app_config.spara_undantagslista(_kvar)
                        st.session_state.undantagslista = _kvar
                        st.rerun()
            if st.button("Töm undantagslistan"):
                app_config.tom_undantagslista()
                st.session_state.undantagslista = []
                st.rerun()

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
# Removed duplicated lines

from chatt_renderare import injicera_chatt_css
injicera_chatt_css()

def _rendera_beslut_wrapper():
    rum_render.rendera_beslut(st.session_state.get("spiris_client_id"), st.session_state.get("spiris_client_secret"))

sidor = {
    "Dagen": [
        st.Page(rum_render.rendera_oversikt,            title="Översikt",           icon="👀", url_path="oversikt", default=True),
        st.Page(_rendera_beslut_wrapper,                title=atgardsstatus.etikett, icon="⚖️", url_path="beslut"),
    ],
    "Pengar": [
        st.Page(rum_render.rendera_pengar_in,           title="Pengar in",          icon="📥", url_path="pengar-in"),
        st.Page(rum_render.rendera_saljdokument,        title="Säljdokument",       icon="🧾", url_path="saljdokument"),
        st.Page(rum_render.rendera_pengar_ut,           title="Pengar ut",          icon="💸", url_path="pengar-ut"),
        st.Page(rum_render.rendera_bank,                title="Bank",               icon="🏦", url_path="bank"),
    ],
    "Bokföring": [
        st.Page(rum_render.rendera_bockerna,            title="Böckerna",           icon="📚", url_path="bockerna"),
        st.Page(rum_render.rendera_bokslut,             title="Bokslut",            icon="🧮", url_path="bokslut"),
        st.Page(rum_render.rendera_register,            title="Register",           icon="📇", url_path="register"),
    ],
    "Analys": [
        st.Page(rum_render.rendera_rapporter,           title="Rapporter & analys", icon="📊", url_path="rapporter"),
        st.Page(rum_render.rendera_investeringskalkyl,  title="Investeringskalkyl", icon="📈", url_path="investering"),
    ],
    "AI-chattar": [
        st.Page(rum_render.rendera_foretags_chatt,      title="Företagsdata",       icon="💬", url_path="foretagsdata"),
        st.Page(rum_render.rendera_juridik,             title="AI Juridik & Skatt", icon="⚖️", url_path="juridik"),
    ],
    "Data": [
        data_page,
    ],
}
import kommandofalt
import kraschlogg
pg = st.navigation(sidor, position="top")
kommandofalt.rendera_kommandofalt(st, sidor)

try:
    pg.run()
except Exception as e:
    kraschlogg.rendera_krasch_ui(e)
