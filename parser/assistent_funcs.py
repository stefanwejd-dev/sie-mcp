import streamlit as st
import sessionslogg
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
    """Var loggen över AI-utflödet ligger, och vad den innehåller.

    Poängen med hela loggen är att användaren SJÄLV ska kunna granska vad som
    skickats — då måste filerna gå att hitta. Sökvägen visas i klartext (den
    ligger utanför projektmappen och är inte uppenbar), och den pågående
    sessionens fil går att ladda ned direkt, så den kan bifogas i ett samtal
    med en AI utan att användaren behöver leta i Utforskaren."""
    logg = st.session_state.sessionslogg
    with st.expander("🔍 AI-utflödeslogg — vad har skickats till AI:t?"):
        if getattr(logg, "sokvag", None) is None:
            st.warning(
                "Ingen säker lagringsplats för loggarna kunde lösas ut, så inget "
                "loggas den här sessionen. Appen fungerar i övrigt som vanligt."
            )
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
            )

        sessioner = sessionslogg.lista_sessioner()
        if sessioner:
            st.caption(f"Sparade loggar ({len(sessioner)} senaste):")
            st.dataframe(
                [
                    {"Fil": s["namn"], "Ändrad": s["andrad"], "Storlek (kB)": s["storlek_kb"]}
                    for s in sessioner
                ],
                hide_index=True,
                width="stretch",
            )

