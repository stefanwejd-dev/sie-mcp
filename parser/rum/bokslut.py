from vy_modell import Rum

# Tom vyer-tupel med avsikt — se hantverksbok/UI_ATGARDER_I_VYN.md §2.0/§4.0.
# Vy-nivån renderas aldrig (bara rummen är bundna till appen); knapparna bor i
# snabbvyer.SNABBVYER_BOKSLUT och ritas av parser/rum_render.py:rendera_bokslut.
RUM_BOKSLUT = Rum(
    id="bokslut",
    namn="Bokslut",
    ikon="🧮",
    vyer=()
)
