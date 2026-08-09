import re

def extract_block(lines, start_marker, end_marker=None, end_regex=None):
    start = -1
    end = -1
    for i, line in enumerate(lines):
        if start == -1 and start_marker in line:
            start = i
        elif start != -1:
            if (end_marker and end_marker in line) or (end_regex and re.search(end_regex, line)):
                end = i
                break
    if end == -1: end = len(lines)
    return lines[start:end]

with open('app.py', 'r', encoding='utf-8') as f:
    app_lines = f.readlines()

utkast_code = extract_block(app_lines, "def _bygg_spiris_klient_fran_session", "def _rendera_valknappar")
valknappar_code = extract_block(app_lines, "def _rendera_valknappar", "def _rendera_utflodeslogg")
utflodeslogg_code = extract_block(app_lines, "def _rendera_utflodeslogg", "datakälla = st.sidebar.radio")

datastatus_code = extract_block(app_lines, "with flik_datastatus:", "with flik_atgarder:")
atgarder_code = extract_block(app_lines, "with flik_atgarder:", "# --- Flikarna \U0001F4CA Rapporter och \U0001F4C8 Investeringskalkyl")
rapporter_code = extract_block(app_lines, "with flik_rapporter:", "with flik_investering:")
investering_code = extract_block(app_lines, "with flik_investering:", "# --- Flik: \U0001F916 AI-Assistent")
ai_analys_code = extract_block(app_lines, "with analys_avsnitt:", "with fraga_avsnitt:")
ai_fraga_code = extract_block(app_lines, "with fraga_avsnitt:", "# EOF or similar")

with open('parser/extracted_blocks.txt', 'w', encoding='utf-8') as f:
    f.write("--- UTKAST ---\n" + "".join(utkast_code))
    f.write("--- DATASTATUS ---\n" + "".join(datastatus_code))
    f.write("--- ATGARDER ---\n" + "".join(atgarder_code))
    f.write("--- RAPPORTER ---\n" + "".join(rapporter_code))
    f.write("--- AI_ANALYS ---\n" + "".join(ai_analys_code))
