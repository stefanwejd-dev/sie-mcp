import re
with open('parser/rum_render.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_tomt_lage = r'def tomt_lage\(st, begrepp: Begrepp, vad_rummet_visar: str\) -> None:.*?st\.caption\(begrepp\.forklaring\)'

new_tomt_lage = '''def tomt_lage(st, begrepp: Begrepp, vad_rummet_visar: str) -> None:
    """Ett tomt läge som ERBJUDER handlingen i stället för att peka bort mot
    en annan del av gränssnittet (Shneiderman 4 och 7)."""
    st.subheader("Ingen data inläst")
    st.write(f"{vad_rummet_visar} saknar underlag.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Anslut ett affärssystem"):
            from kalla_vy import oppna_kalladan
            oppna_kalladan()
    with col2:
        if st.button("Ladda upp en SIE4-fil"):
            from kalla_vy import oppna_kalladan
            oppna_kalladan()
            
    st.caption(begrepp.forklaring)'''

text = re.sub(old_tomt_lage, new_tomt_lage, text, flags=re.DOTALL)
with open('parser/rum_render.py', 'w', encoding='utf-8') as f:
    f.write(text)
