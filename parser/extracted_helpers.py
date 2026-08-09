import fpa_dashboard
import namnreferens
import navigering
import revisionslogg
import saker_lagring
import sessionslogg
import spiris_rag
import spiris_session
from fpa_vy import (
    berakna_kundbetalbeteende,
    dashboard_rendering_lage,
    dashboard_saknar_data,
    formatera_kr,
    innevarande_ar_intervall,
    likviditetsprognos_fran_reskontra,
    momssaldo_fran_sie,
    rapporter_fran_sie,
    valj_rakenskapsar_for_ar,
)
from masking_memory import (
    filtrera_bort_sedda,
    las_maskeringsminne,
    lagg_till_maskeringsminne,
    verifikation_id,
)
from sekretesslager import maskera_chattmeddelande, uppdatera_efter_granskning
from samtalsflode import (
    FÖRESLAGNA_FRÅGOR,
    SVARSLÄGEN,
    ChattMeddelande,
    bygg_saker_kontext,
    ställ_fraga,
    ställ_fraga_till_agent,
)
from spiris_adapter import (
    ARBETSTYP_ROT_BYGGARBETE,
    FAKTURATYP_BYGGMOMS,
    FAKTURATYP_FYSISK_PERSON_MED_ROT,
    FAKTURATYP_FYSISK_PERSON_UTAN_ROT,
    FAKTURATYP_JURIDISK_PERSON,
    bygg_kundfaktura_payload,
    bygg_rot_uppgifter,
    hamta_kundbetalhistorik,
    hamta_kundreskontra,
    hamta_reskontra,
    hamta_siefil_fran_spiris,
    kraver_rot_flaggning,
    losa_artikel_ider_for_fakturarader,
    skapa_kund,
    skapa_kundfaktura,
    utfor_utkast,
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
from svarskontrakt import (
    med_inledande_text,
    text_sammanfattning,
    validera_svar,
    validera_svar_dict,
)
from vasentlighet import berakna_vasentlighet
import compliance
import snabbvy_render
import snabbvyer
import utkast

st.set_page_config(page_title="sie-mcp", layout="wide")
st.title("sie-mcp — granskningsstöd för SIE4-filer")

# Villkorsspärr — FAIL-CLOSED och avsiktligt placerad som allra första sak,
# före all datainhämtning. krav_godkannande() anropar st.stop() om inte
# SAMTLIGA ansvarspunkter är godkända, så inget nedanför körs: ingen
# filuppladdning ritas, ingen Spiris-session byggs, inget AI-anrop kan ske.
# Flytta den aldrig längre ned och gör den aldrig till en expander man kan
# scrolla förbi — det var precis felet i den tidigare versionen.
compliance.krav_godkannande(st)

if "sie" not in st.session_state:
    st.session_state.sie = None
if "maskeringsresultat" not in st.session_state:
    st.session_state.maskeringsresultat = None
if "ai_konfiguration" not in st.session_state:
    st.session_state.ai_konfiguration = None
if "analys_resultat" not in st.session_state:
    st.session_state.analys_resultat = None
if "behandlad_fil_id" not in st.session_state:
    st.session_state.behandlad_fil_id = None
if "samtal_historik" not in st.session_state:
    st.session_state.samtal_historik = []
# Fas 10: idempotens-vakt mot "Fråga om filen"-flikens steg A (se där) —
# indexet i samtal_historik för den senaste FRÅGA som redan fått ett
# AI-anrop. Utan den skulle varje egen rerun i aktivt_fakturautkast-flödet
# (som kan rerunna flera gånger på egen hand medan ett utkast granskas)
# råka trigga om ett helt nytt AI-anrop för samma, redan hanterade fråga.
if "samtal_senast_behandlat" not in st.session_state:
    st.session_state.samtal_senast_behandlat = -1
# Fas 10: tillfälligt "Skriv eget..."-textfält under ett interaktivt
# flervalssteg i chatten — se _rendera_valknappar.
if "visa_eget_svarsfalt" not in st.session_state:
    st.session_state.visa_eget_svarsfalt = False
# Sessionslogg över AI-utflödet: EN markdownfil per körning, med den faktiska
# nyttolast som skickades. Skapas här — "en gång per appstart" är exakt vad en
# ny session_state betyder i Streamlit. Gamla loggar rensas samtidigt, så
# retentionen inte kräver ett eget schemalagt jobb.
if "sessionslogg" not in st.session_state:
    try:
