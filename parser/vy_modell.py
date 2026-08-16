"""vy_modell — den deklarativa primitiven för appens alla ytor.

Generaliserar snabbvyer.Snabbvy till hela gränssnittet. Ett rum är en lista
vyer; en vy är en ren funktion Vydata -> Vyresultat. Ingen Streamlit-import,
någonsin: det är det som gör att ritlagret kan bytas ut utan att röra
innehållet."""

from dataclasses import dataclass
from typing import Callable, Literal
from ordbok import Begrepp
from stil import Harkomstmarke


@dataclass(frozen=True)
class Atgardsknapp:
    """En handling användaren kan begära från vyn.

    UI-fri: detta är en BESKRIVNING av en knapp, inte en knapp. Ritlagret
    avgör hur den ser ut; vy-lagret avgör att den finns och vad den betyder.
    Definierad här, importerad av snabbvyer.py — se hantverksbok/
    UI_ATGARDER_I_VYN.md §2.1: `Snabbvyresultat` är den typ som faktiskt
    ritas, men typerna hör hemma i den beroendefria modulen.

    Måste stå FÖRE `from snabbvyer import ...` nedan: snabbvyer importerar i
    sin tur `Atgardsforslag` härifrån, och den ömsesidiga importen är bara
    säker om varje sida redan har definierat det den andra behöver innan den
    når sin egen importrad (se motsvarande kommentar i snabbvyer.py)."""
    etikett: str
    utkasttyp: str                  # måste finnas i utkast.GILTIGA_TYPER
    nyttolast: dict                 # färdig, validerad — vyn har redan räknat
    bekraftelsetext: str            # vad användaren godkänner, i klartext
    varning: str | None = None


@dataclass(frozen=True)
class Atgardsforslag:
    """Ett fynd med en möjlig åtgärd, redo att visas där användaren står."""
    rubrik: str
    allvarlighet: str               # samma tre nivåer som Fynd
    motivering: str
    belopp: str | None = None       # redan formaterad
    konton: tuple[str, ...] = ()
    regel_text: str | None = None
    regel_lank: str | None = None
    rader: tuple[tuple[str, str, str], ...] = ()   # konto, debet, kredit
    knapp: Atgardsknapp | None = None               # None = inget att göra


from snabbvyer import Nyckeltal, Sektion, Vydata  # noqa: E402


@dataclass(frozen=True)
class Vyresultat:
    """Spegling av `snabbvyer.Snabbvyresultat` — den senare är normativ (den
    som faktiskt ritas, se §2.0 i hantverksboken). Hålls i synk manuellt."""
    rubrik: str
    harkomst: Harkomstmarke
    nyckeltal: tuple[Nyckeltal, ...] = ()
    sektioner: tuple[Sektion, ...] = ()
    fotnot: str | None = None
    atgarder: tuple[Atgardsforslag, ...] = ()

@dataclass(frozen=True)
class Vy:
    """Spegling av `snabbvyer.Snabbvy` — `status` läses aldrig härifrån av
    ritlagret (§2.0); fältet finns för att den deklarativa tvillingen inte
    ska ruttna."""
    id: str
    begrepp: Begrepp
    ikon: str
    bygg: Callable[[Vydata], Vyresultat]
    kraver: frozenset[str] = frozenset()
    hjalptext: str | None = None
    status: Literal["byggd", "kommande"] = "byggd"

@dataclass(frozen=True)
class Rum:
    id: str
    namn: str
    ikon: str
    vyer: tuple[Vy, ...] = ()

