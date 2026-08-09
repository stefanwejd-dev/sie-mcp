"""formatering_ui — UI-komponent för formateringsval i Streamlit."""
from __future__ import annotations
import streamlit as st
from formatering import Formateringsval

def hamta_val() -> Formateringsval:
    try:
        from streamlit import runtime
        if not runtime.exists():
            return Formateringsval()
        
        if "formateringsval" not in st.session_state:
            st.session_state.formateringsval = Formateringsval()
        return st.session_state.formateringsval
    except ImportError:
        return Formateringsval()

def rendera_verktygsrad(st) -> None:
    val = hamta_val()
    
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚙️ Sifferformatering (Excel-stil)", expanded=False):
        # 2 rader i sidomenyn är bättre än 1 lång rad.
        k1, k2 = st.columns(2)
        if k1.button("Comma Style", help="Slå på/av tusentalsavgränsare", width="stretch"):
            val.comma_style = not val.comma_style
            st.rerun()
            
        avgr = k2.selectbox(
            "Tusentalsavgränsare",
            options=[" ", ".", ",", "'"],
            index=[" ", ".", ",", "'"].index(val.tusentalsavgransare) if val.tusentalsavgransare in [" ", ".", ",", "'"] else 0,
            key="fmt_avgransare_selectbox",
            label_visibility="collapsed"
        )
        if avgr != val.tusentalsavgransare:
            val.tusentalsavgransare = avgr
            st.rerun()

        k3, k4 = st.columns(2)
        if k3.button("+.0", help="Öka antal decimaler", width="stretch"):
            val.decimaler += 1
            st.rerun()
        if k4.button("-.0", help="Minska antal decimaler", width="stretch"):
            val.decimaler = max(0, val.decimaler - 1)
            st.rerun()
