import sys
import re

with open('app.py.bak', 'r', encoding='utf-8') as f:
    text = f.read()

start_idx = text.find('    with analys_avsnitt:\n') + len('    with analys_avsnitt:\n')

end_idx = text.find('    with fraga_avsnitt:')

isa_logic = text[start_idx:end_idx]
if not isa_logic.strip():
    print("Could not find ISA 450 logic")
    sys.exit(1)

# fix indents
lines = isa_logic.split('\n')
# base indent is 8 spaces (since it was inside `with analys_avsnitt:`)
# we want to dedent by 4 spaces
new_lines = []
for line in lines:
    if line.startswith('    '):
        new_lines.append(line[4:])
    else:
        new_lines.append(line)
isa_logic = '\n'.join(new_lines)

# Inject provenance marks
isa_logic = isa_logic.replace('st.subheader("Väsentlighet (Modul 1)")', 'st.subheader(f"Väsentlighet (Modul 1) {HARKOMST_LOKAL.tecken}")')
isa_logic = isa_logic.replace('st.subheader("Tröskelvärden")', 'st.subheader(f"Tröskelvärden {HARKOMST_LOKAL.tecken}")')
isa_logic = isa_logic.replace('st.success("Analys klar.")', 'st.success(f"Analys klar. {HARKOMST_AI.tecken}")')

imports = '''import streamlit as st
from decimal import Decimal
import app_config
import revisionslogg
from ai_adapter import bygg_analysanropare, AnalysanropareFel
from analysflode import (
    kor_analys,
    berakna_vasentlighet, berakna_standardtroskelvarden, 
    belopp_fran_procent, procent_fran_belopp, tolka_troskelvarden,
    VASENTLIGHETSTAL_HELP, UTFALLSVASENTLIGHET_HELP, TröskelvärdeFel
)
from fpa_vy import formatera_kr
from ai_adapter import leverantor_har_analysstod
from stil import HARKOMST_LOKAL, HARKOMST_AI

'''

func_def = '''
def _procent_caption(proc: str, ref: str) -> str:
    return f"Motsvarar: {proc} % (baserat på {ref})"

def rendera_isa_450(st, sie, maskeringsresultat, ai_konfiguration):
'''

with open('parser/isa_render.py', 'w', encoding='utf-8') as f:
    f.write(imports + func_def + isa_logic)
