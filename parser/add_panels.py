import re
import sys

with open('parser/rum_render.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Make sure assistent.py is imported
if 'from assistent import rendera_panel, AssistentKontext' not in text:
    text = text.replace('import snabbvy_render', 'import snabbvy_render\nfrom assistent import rendera_panel, AssistentKontext')

# We will define a function to append the rendera_panel call to a room function
def append_to_func(func_name, room_id, include_reskontra=False, include_kundreskontra=False, include_likviditetsprognos=False):
    global text
    
    # Construct AssistentKontext based on the arguments
    reskontra_arg = 'st.session_state.spiris_reskontra' if include_reskontra else 'None'
    kundreskontra_arg = 'st.session_state.spiris_kundreskontra' if include_kundreskontra else 'None'
    likviditetsprognos_arg = 'likviditetsprognos' if include_likviditetsprognos else 'None'
    
    kontext_call = f"""
    kontext = AssistentKontext(
        sie=st.session_state.sie,
        maskeringsresultat=st.session_state.maskeringsresultat,
        analys_resultat=st.session_state.analys_resultat,
        reskontra={reskontra_arg},
        kundreskontra={kundreskontra_arg},
        likviditetsprognos={likviditetsprognos_arg}
    )
    rendera_panel(st, '{room_id}', kontext)
"""
    
    # We find the end of the function by looking for the start of the next function
    # or the end of the file.
    # Since these functions don't have return statements at the very end, we just append to the last line.
    
    # Find the function definition
    pattern = r'(def ' + func_name + r'\(.*?\).*?:)(.*?)(?=\ndef |\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        print(f"Could not find {func_name}")
        return
        
    func_body = match.group(2)
    new_func = match.group(1) + func_body + '\n' + kontext_call
    
    text = text[:match.start()] + new_func + text[match.end():]

# append_to_func for each room
append_to_func('rendera_oversikt', 'oversikt')
append_to_func('rendera_beslut', 'beslut', include_reskontra=True, include_kundreskontra=True)
append_to_func('rendera_pengar_in', 'pengar-in', include_kundreskontra=True)
append_to_func('rendera_pengar_ut', 'pengar-ut', include_reskontra=True)
append_to_func('rendera_bockerna', 'bockerna')
append_to_func('rendera_rapporter', 'rapporter', include_likviditetsprognos=True)
append_to_func('rendera_investeringskalkyl', 'investering')

with open('parser/rum_render.py', 'w', encoding='utf-8') as f:
    f.write(text)
