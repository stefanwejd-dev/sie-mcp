from vy_modell import Rum, Vy
from ordbok import hamta
from snabbvyer import (
    bygg_bankkonton,
    bygg_avstamningslage,
    bygg_bankhandelser,
)

RUM_BANK = Rum(
    id="bank",
    namn="Bank",
    ikon="🏦",
    vyer=(
        Vy("bankkonton", hamta("bankkonto"), "🏦", bygg_bankkonton),
        Vy("avstamningslage", hamta("bankkonto"), "⚖️", bygg_avstamningslage),
        Vy("bankhandelser", hamta("bankkonto"), "🧾", bygg_bankhandelser),
    )
)
