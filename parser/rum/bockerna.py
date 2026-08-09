from vy_modell import Rum, Vy
from ordbok import hamta
from snabbvyer import (
    bygg_kontoplan,
    bygg_kontosaldon,
    bygg_verifikatsokning,
    bygg_momsoversikt_vy,
    bygg_verifikatutkast,
)

RUM_BOCKERNA = Rum(
    id="bockerna",
    namn="Böckerna",
    ikon="📚",
    vyer=(
        Vy("kontoplan", hamta("bokforing"), "📋", bygg_kontoplan),
        Vy("kontosaldon", hamta("bokforing"), "💰", bygg_kontosaldon),
        Vy("verifikatsokning", hamta("bokforing"), "🔍", bygg_verifikatsokning),
        Vy("momsoversikt", hamta("bokforing"), "📊", bygg_momsoversikt_vy),
        Vy("verifikatutkast", hamta("bokforing"), "📝", bygg_verifikatutkast),
    )
)
