"""vy_modell — den deklarativa primitiven för appens alla ytor.

Generaliserar snabbvyer.Snabbvy till hela gränssnittet. Ett rum är en lista
vyer; en vy är en ren funktion Vydata -> Vyresultat. Ingen Streamlit-import,
någonsin: det är det som gör att ritlagret kan bytas ut utan att röra
innehållet."""

from dataclasses import dataclass
from typing import Callable
from ordbok import Begrepp
from snabbvyer import Nyckeltal, Sektion, Vydata
from stil import Harkomstmarke

@dataclass(frozen=True)
class Vyresultat:
    rubrik: str
    harkomst: Harkomstmarke
    nyckeltal: tuple[Nyckeltal, ...] = ()
    sektioner: tuple[Sektion, ...] = ()
    fotnot: str | None = None

@dataclass(frozen=True)
class Vy:
    id: str
    begrepp: Begrepp
    ikon: str
    bygg: Callable[[Vydata], Vyresultat]
    kraver: frozenset[str] = frozenset()
    hjalptext: str | None = None

@dataclass(frozen=True)
class Rum:
    id: str
    namn: str
    ikon: str
    vyer: tuple[Vy, ...] = ()

