"""Brygga till quiet_oppen_data — "facit"-implementationen av den källbundna
myndighetschatten (62 författningar + femton myndighetskällor: Riksbanken,
SCB, Riksdagen/lagtext, Skatteverket, Kronofogden, Kolada, TED, VIES, SMHI,
Skolverket, Trafikanalys, Polisens händelser, JobTech, Sveriges dataportal).

Ersätter det gamla, smala juridik-rummet (parser/juridik_chatt.py +
parser/juridik_api.py, två handskrivna verktyg) med samma motor som körs
bakom api.quiet.nu — men HÄR, i sie-mcps egen process, med sie-mcps egen
ANTHROPIC_API_KEY (BYOK, se README.md "Snabbstart"). Ingen nätverksväg till
quiet.nu, ingen delad kvot med webbplatsens besökare.

Förutsättningar (se README.md "Juridik & skatt"):
    1. quiet_oppen_data installerat, se requirements.txt.
    2. sie-mcp/quiet_config.toml finns (checkas in, rör inte den).
    3. sie-mcp/data/quiet_index.sqlite byggd:
           python -m quiet_oppen_data.index.ingest
           python -m quiet_oppen_data.index.lag_ingest
       körda med sie-mcps rotmapp som arbetskatalog (path i quiet_config.toml
       är relativ till cwd, se quiet_oppen_data/index/sok.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_SIE_MCP_ROT = Path(__file__).resolve().parent.parent
_KONFIG_FIL = _SIE_MCP_ROT / "quiet_config.toml"

# MÅSTE sättas innan quiet_oppen_data importeras första gången (i _motorer()
# nedan) — register.py, lagregister.py och konfig.py läser miljövariabeln vid
# modulimport, inte lat. kallor/, lagar/ och quiet_config.toml ligger i
# sie-mcps rot, inte i det installerade paketet — se register.py:s
# QUIET_OPPEN_DATA_ROOT-kommentar för bakgrunden.
os.environ.setdefault("QUIET_OPPEN_DATA_ROOT", str(_SIE_MCP_ROT))

_fas_a = None
_fas_c = None


@dataclass(frozen=True)
class KallHanvisning:
    nr: int
    etikett: str
    myndighet: str
    period: str | None
    lank_manniska: str
    lank_maskin: str
    licens: str


@dataclass(frozen=True)
class KalletSvar:
    kan_besvaras: bool
    text: str                              # svarstext, fotnoter som [1] [2] inline
    kallor: list[KallHanvisning] = field(default_factory=list)
    forbehall: str | None = None
    attribution: list[str] = field(default_factory=list)
    fel: str | None = None                 # satt vid tekniskt fel — text/kallor är då tomma


def _motorer():
    """Bygger (eller återanvänder) FasALopp/FasCValidator.

    Lat instansiering — importerar quiet_oppen_data först här, inte vid
    modulimport, så att sie-mcp fungerar även om paketet inte är
    installerat och det här rummet aldrig används.
    """
    global _fas_a, _fas_c
    if _fas_a is None:
        from quiet_oppen_data.konfig import las as las_quiet_konfig
        from quiet_oppen_data.motor.hamtning import FasALopp
        from quiet_oppen_data.motor.syntes import FasBSyntes
        from quiet_oppen_data.motor.validator import FasCValidator

        las_quiet_konfig(_KONFIG_FIL)
        _fas_a = FasALopp()
        _fas_c = FasCValidator(syntes=FasBSyntes())
    return _fas_a, _fas_c


def fraga_myndighetskallor(fraga: str, *, api_nyckel: str | None = None) -> KalletSvar:
    """Ställer en fråga till quiet_oppen_datas källbundna motor.

    Args:
        fraga: Användarens fråga, fri text.
        api_nyckel: Anthropic-nyckel att använda. Ges den, sätts den som
            ANTHROPIC_API_KEY i processens miljö innan motorn byggs (första
            gången) — så att Streamlit-rummet kan använda nyckeln användaren
            faktiskt valt i sina inställningar, i stället för en eventuell
            annan ANTHROPIC_API_KEY som redan låg i miljön. MCP-verktyget
            (mcp_server/server.py) skickar normalt ingen — där gäller
            processens egen miljövariabel, som är hur en MCP-server
            konfigureras av sin klient.

    Returns:
        KalletSvar. Vid ett tekniskt fel sätts `fel`, övriga fält är tomma —
        anropande kod (Streamlit-rummet, MCP-verktyget) avgör hur det visas.
    """
    if api_nyckel and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = api_nyckel

    try:
        fas_a, fas_c = _motorer()
        hamtningsresultat = fas_a.hamta(fraga)
        svar = fas_c.kor(fraga, hamtningsresultat.register)
    except Exception as e:  # noqa: BLE001 — visas som ett vanligt "kan inte svara", inte en krasch
        return KalletSvar(kan_besvaras=False, text="", fel=str(e))

    if not svar.kan_besvaras:
        return KalletSvar(kan_besvaras=False, text="", forbehall=svar.forbehall)

    fotnr: dict[str, int] = {}
    stycken_text: list[str] = []
    for stycke in svar.stycken:
        text = stycke.text
        for kall_id in stycke.kallor:
            if kall_id not in fotnr:
                fotnr[kall_id] = len(fotnr) + 1
            text += f" [{fotnr[kall_id]}]"
        stycken_text.append(text)

    kallor: list[KallHanvisning] = []
    for kall_id, nr in sorted(fotnr.items(), key=lambda kv: kv[1]):
        post = hamtningsresultat.register.hamta(kall_id)
        if post is None:
            continue
        kallor.append(KallHanvisning(
            nr=nr,
            etikett=post.etikett,
            myndighet=post.myndighet,
            period=post.period,
            lank_manniska=post.lank_manniska,
            lank_maskin=post.lank_maskin,
            licens=post.licens,
        ))

    return KalletSvar(
        kan_besvaras=True,
        text="\n\n".join(stycken_text),
        kallor=kallor,
        forbehall=svar.forbehall,
        attribution=list(svar.attribution or []),
    )
