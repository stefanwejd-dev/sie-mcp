from vy_modell import Rum, Vy

# Uppslag mot Bolagsverkets fria API för värdefulla datamängder. Ligger under
# gruppen Data i navigeringen: det är extern myndighetsdata som kommer in, inte
# något som räknas fram ur räkenskaperna.
RUM_BOLAGSVERKET = Rum(
    id="bolagsverket",
    namn="Bolagsverket",
    ikon="🏛️",
    vyer=()
)
