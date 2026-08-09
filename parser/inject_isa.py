import sys
import re

with open('parser/rum_render.py', 'r', encoding='utf-8') as f:
    text = f.read()

isa_code = '''
            st.divider()
            with st.expander("ISA 450 Analys", expanded=False):
                from isa_render import rendera_isa_450
                ai_konfig = st.session_state.get('ai_konfiguration')
                if ai_konfig and ai_konfig.status == 'modeller_hämtade':
                    rendera_isa_450(st, st.session_state.sie, st.session_state.maskeringsresultat, ai_konfig)
                else:
                    st.info("AI-inställningar krävs för ISA 450-analys. Fyll i dem i AI-panelen nedan.")
'''

match = re.search(r'def rendera_rapporter.*?(?=    kontext = AssistentKontext)', text, re.DOTALL)
if match:
    old_func = match.group(0)
    new_func = old_func + isa_code
    text = text.replace(old_func, new_func)

with open('parser/rum_render.py', 'w', encoding='utf-8') as f:
    f.write(text)
