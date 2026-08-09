from vy_modell import Rum, Vy
from ordbok import hamta
from snabbvyer import (
    bygg_kunder,
    bygg_leverantorer,
    bygg_artiklar,
    bygg_projekt,
    bygg_kostnadsstallen,
    bygg_referensdata,
)

RUM_REGISTER = Rum(
    id="register",
    namn="Register",
    ikon="📇",
    vyer=(
        Vy("kunder", hamta("kund"), "👥", bygg_kunder),
        Vy("leverantorer", hamta("leverantor"), "🏢", bygg_leverantorer),
        Vy("artiklar", hamta("artikel"), "📦", bygg_artiklar),
        Vy("projekt", hamta("projekt"), "🏗️", bygg_projekt),
        Vy("kostnadsstallen", hamta("kostnadsstalle"), "🏷️", bygg_kostnadsstallen),
        Vy("referensdata", hamta("referensdata"), "📚", bygg_referensdata),
    )
)
