import streamlit as st

def rendera_kommandofalt(st, sidor=[]):
    cmd = st.text_input("🔍 Kommandofält (gå till...)", key="cmd_input", placeholder="T.ex. 'Kundfaktura' eller 'Pengar in'")
    if cmd:
        import difflib
        from parser import ordbok
        
        RUMS_MAPPNING = {
            "översikt": "oversikt",
            "beslut": "beslut",
            "pengar in": "pengar-in",
            "pengar ut": "pengar-ut",
            "böckerna": "bockerna",
            "rapporter": "rapporter",
            "investeringskalkyl": "investering",
            "data in/ut": "data",
        }
        
        BEGREPPS_MAPPNING = {
            "kundreskontra": "pengar-in",
            "kundfaktura": "pengar-in",
            "leverantorsreskontra": "pengar-ut",
            "leverantorsfaktura": "pengar-ut",
            "huvudbok": "bockerna",
            "verifikat": "bockerna",
            "kontoplan": "bockerna",
            "kontosaldo": "bockerna",
            "resultatrapport": "rapporter",
            "balansrapport": "rapporter",
            "nyckeltal": "rapporter",
            "kassaflode": "rapporter",
            "likviditetsprognos": "rapporter",
            "moms": "bockerna",
            "order": "pengar-in",
            "offert": "pengar-in",
            "artikel": "pengar-in",
            "bankkonto": "bockerna",
            "rakenskapsar": "oversikt",
            "vasentlighet": "oversikt",
            "aldersanalys": "pengar-in",
            "paminnelse": "pengar-in",
            "betalningsforslag": "pengar-ut",
            "investeringskalkyl": "investering",
        }
        
        SNABBVY_MAPPNING = {
            "kundfaktura": ("snabbvy_pengar_in", "kund_utestaende"),
            "leverantorsfaktura": ("snabbvy_pengar_ut", "lev_utestaende"),
            "aldersanalys": ("snabbvy_pengar_in", "kund_alder"),
            "paminnelse": ("snabbvy_pengar_in", "kund_paminnelse"),
            "betalningsforslag": ("snabbvy_pengar_ut", "lev_betala"),
            "kundreskontra": ("snabbvy_pengar_in", "kund_utestaende"),
            "leverantorsreskontra": ("snabbvy_pengar_ut", "lev_utestaende"),
        }
        
        soktermer = list(RUMS_MAPPNING.keys())
        for begrepp in ordbok.alla():
            soktermer.append(begrepp.namn.lower())
            
        matches = difflib.get_close_matches(cmd.lower(), soktermer, n=1, cutoff=0.4)
        if matches:
            match = matches[0]
            url_path = None
            if match in RUMS_MAPPNING:
                url_path = RUMS_MAPPNING[match]
            else:
                for begrepp in ordbok.alla():
                    if begrepp.namn.lower() == match:
                        url_path = BEGREPPS_MAPPNING.get(begrepp.id)
                        if begrepp.id in SNABBVY_MAPPNING:
                            nyckel, vy_id = SNABBVY_MAPPNING[begrepp.id]
                            st.session_state[nyckel] = vy_id
                        break
            
            if url_path:
                # st.session_state.cmd_input = ""
                alla_sidor = []
                if isinstance(sidor, dict):
                    for sidlista in sidor.values():
                        alla_sidor.extend(sidlista)
                else:
                    alla_sidor = sidor
                sida = next((p for p in alla_sidor if p.url_path == url_path), None)
                if sida:
                    st.switch_page(sida)
