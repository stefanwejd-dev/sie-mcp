"""sessionslogg — läsbar logg över DET SOM FAKTISKT SKICKADES till AI:t.

Syftet är användarens eget: att i efterhand kunna gå tillbaka och se exakt
vilken information som lämnade datorn, och därmed själv kunna bedöma om en
personuppgiftsincident eller ett brott mot personuppgiftsbiträdesavtalet
har skett. Det är ett stöd för ansvarsskyldigheten (GDPR art. 5.2) och ett
underlag vid en begäran om registerutdrag (art. 15).

FÖRHÅLLANDE TILL revisionslogg.py
---------------------------------
De två loggarna tjänar olika syften och ersätter inte varandra:

    revisionslogg.py   METADATA — att en behandling skedde. Aldrig nyttolast.
                       En kompakt JSONL-rad per anrop, art. 30-register.
    sessionslogg.py    NYTTOLASTEN — vad som skickades och vad som kom
                       tillbaka. En läsbar markdownfil per session.

DEN BÄRANDE REGELN
------------------
Loggen får innehålla EXAKT det som skickades — varken mer eller mindre. Då
innehåller den per definition ingenting som inte redan lämnats ut till tredje
part, och blir inte en ny exponering utöver den som redan skett. Två följder,
och båda är säkerhetskrav, inte stilval:

1. Ett meddelande som BLOCKERADES av maskeringens fail-closed-lager skickades
   aldrig — och loggas därför inte. Att logga det vore att skriva ned
   klartextnamn som medvetet stoppades.
2. Kodnyckeln (mappningen [BOLAG_1] -> verkligt namn) loggas ALDRIG. Utan den
   går tokens inte att vända tillbaka, och loggen förblir precis så känslig
   som utflödet var — inte känsligare.

LAGRINGSPLATS
-------------
Filerna innehåller verkliga belopp, kontonamn, verifikationstexter och de
motpartsnamn som är juridiska personer. De är alltså en känslig artefakt och
går via saker_lagring — samma fail-closed-guard som hemligheterna, aldrig i
den (potentiellt molnsynkade) projektmappen.

FORMAT
------
Markdown, en fil per session. Vald för att den ska fungera i BÅDA riktningar:
läsbar rakt av i Notepad, och samtidigt något en språkmodell tolkar utan
förarbete — användaren ska kunna bifoga filen till en AI och resonera om den.

Filen skrivs om i sin helhet vid varje ny post (atomiskt, via temporärfil +
os.replace) i stället för att bara appendas. Det kostar skrivningar men är
priset för sammanfattningen HÖGST UPP i filen: den som öppnar loggen ska se
omfattningen direkt, inte behöva scrolla till slutet. Atomiciteten gör att en
avbruten skrivning aldrig lämnar en trasig fil.

FAIL-SAFE
---------
Loggningen får ALDRIG krascha appen eller blockera ett AI-anrop. Allt I/O är
best-effort; fel sväljs. En logg som inte kan skrivas är ett problem, men ett
mindre problem än en app som slutar fungera.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import saker_lagring

# Hur länge sessionsloggarna sparas. Avvägning mellan att kunna gå tillbaka
# till en incident som upptäcks sent och dataminimering (art. 5.1 e).
STANDARD_LAGRINGSTID_DAGAR = 90

FILPREFIX = "AI-utflode"

# Verktygsdefinitionerna (AGENT_VERKTYG) skickas med varje agentanrop men är
# statisk kod utan personuppgifter. Namnen loggas, inte hela JSON-schemana —
# annars dränks den intressanta datan i hundratals rader oföränderligt schema.
_VERKTYG_NOT = "(namn loggas; schemana är statisk kod utan personuppgifter)"


def _tidsstampel(nu: datetime) -> str:
    return nu.strftime("%Y-%m-%d_%H%M%S")


def _kodblock(text: str, sprak: str = "text") -> str:
    """Lägger text i ett markdown-kodblock med en staketlängd som garanterat
    är längre än den längsta backtick-sekvensen i innehållet. Utan det kan ett
    AI-svar som självt innehåller ``` bryta ut ur blocket och göra resten av
    filen oläsbar — både för Notepad-läsaren och för en tolkande modell."""
    langsta = max((len(m) for m in re.findall(r"`+", text)), default=0)
    stangsel = "`" * max(3, langsta + 1)
    return f"{stangsel}{sprak}\n{text}\n{stangsel}"


@dataclass
class Utflode:
    """Ett AI-anrop: vad som skickades och vad som kom tillbaka."""

    forbindelse: str                 # "Anthropic" | "Ollama (lokal)" | "MCP-klient"
    modell: str
    formaga: str                     # "analys" | "samtal" | "agent" | "mcp_rag"
    lamnade_datorn: bool
    tidpunkt: str = ""
    systemprompt: str | None = None
    meddelanden: list[dict[str, str]] = field(default_factory=list)
    verktyg: list[str] = field(default_factory=list)
    svar: str | None = None
    verktygsanrop: str | None = None
    fel: str | None = None

    def tecken_ut(self) -> int:
        """Ungefärlig mängd data som lämnade datorn, i tecken. Ger användaren
        en känsla för omfattningen utan att behöva läsa varje post."""
        delar = [self.systemprompt or ""]
        delar += [str(m.get("innehall", "")) for m in self.meddelanden]
        return sum(len(d) for d in delar)


def _rendera_utflode(post: Utflode, nummer: int) -> str:
    rader = [
        f"## [{nummer}] {post.tidpunkt} · {post.forbindelse} · {post.formaga}",
        "",
        "| | |",
        "|---|---|",
        f"| Mottagare | {post.forbindelse} |",
        f"| Modell | {post.modell or '(ej angiven)'} |",
        f"| Förmåga | {post.formaga} |",
        (
            "| Lämnade datorn | **Ja — skickades till en extern part** |"
            if post.lamnade_datorn
            else "| Lämnade datorn | Nej — behandlades lokalt på din dator |"
        ),
        f"| Tecken skickade | {post.tecken_ut():,} |".replace(",", " "),
    ]
    if post.verktyg:
        rader.append(f"| Verktyg som erbjöds | {', '.join(post.verktyg)} {_VERKTYG_NOT} |")
    if post.fel:
        rader.append(f"| Fel | {post.fel} |")
    rader.append("")

    if post.systemprompt:
        rader += ["### Systemprompt", "", _kodblock(post.systemprompt), ""]

    if post.meddelanden:
        rader += ["### Skickade meddelanden", ""]
        for i, meddelande in enumerate(post.meddelanden, start=1):
            roll = meddelande.get("roll", "?")
            rader += [
                f"**{i}. {roll}**",
                "",
                _kodblock(str(meddelande.get("innehall", ""))),
                "",
            ]

    if post.svar is not None:
        rader += ["### Svar från AI:t", "", _kodblock(post.svar), ""]
    if post.verktygsanrop:
        rader += ["### Verktygsanrop AI:t begärde", "", _kodblock(post.verktygsanrop), ""]

    return "\n".join(rader)


class Sessionslogg:
    """En loggfil för EN körning av appen. Skapas vid start och fylls på för
    varje AI-anrop.

    Filen skrivs även när inget anrop sker: att en session inte skickade något
    är också ett svar på frågan "vad skickades den 3 augusti?"."""

    def __init__(self, sokvag: Path, startad: datetime, session_id: str) -> None:
        self.sokvag = sokvag
        self.startad = startad
        self.session_id = session_id
        self.poster: list[Utflode] = []
        self._skriv()

    # --- publikt API ------------------------------------------------------

    def logga(self, post: Utflode) -> None:
        """Lägger till ett anrop och skriver om filen. Fail-safe: ett I/O-fel
        får aldrig störa AI-anropet som just gjordes."""
        if not post.tidpunkt:
            post.tidpunkt = datetime.now().strftime("%H:%M:%S")
        self.poster.append(post)
        self._skriv()

    # --- internt ----------------------------------------------------------

    def _sammanfattning(self) -> str:
        externa = [p for p in self.poster if p.lamnade_datorn]
        mottagare = sorted({p.forbindelse for p in externa}) or ["–"]
        tecken = sum(p.tecken_ut() for p in externa)
        sista = self.poster[-1].tidpunkt if self.poster else "–"
        return "\n".join([
            "| Fält | Värde |",
            "|---|---|",
            f"| Session startad | {self.startad.strftime('%Y-%m-%d %H:%M:%S')} |",
            f"| Session-ID | {self.session_id} |",
            f"| Senaste anrop | {sista} |",
            f"| Antal AI-anrop | {len(self.poster)} |",
            f"| Varav skickade utanför datorn | {len(externa)} |",
            f"| Mottagare | {', '.join(mottagare)} |",
            f"| Tecken skickade utanför datorn | {tecken:,} |".replace(",", " "),
        ])

    def _innehall(self) -> str:
        delar = [
            "# AI-utflödeslogg — sie-mcp",
            "",
            "Den här filen visar **exakt vad som skickades till AI:t** under en "
            "körning av sie-mcp, och vad som kom tillbaka. Den finns för att du "
            "själv ska kunna kontrollera vilken information som lämnade din "
            "dator.",
            "",
            self._sammanfattning(),
            "",
            "> **Så här läser du filen.** Varje avsnitt nedan är ett AI-anrop, i "
            "tidsordning. Tabellen visar vem som tog emot datan och om den "
            "lämnade datorn. Därefter följer den exakta texten som skickades.",
            ">",
            "> **Om innehållet.** Namn på personer och känsliga motparter är "
            "redan ersatta med koder som `[BOLAG_1]` och `[PERSON_2]` när de når "
            "AI:t — och de visas likadant här. Nyckeln som översätter koderna "
            "tillbaka till verkliga namn finns aldrig i den här filen. Belopp, "
            "kontonamn och namn på juridiska personer står däremot i klartext, "
            "precis som de gjorde när de skickades.",
            ">",
            "> **Vad som INTE står här.** Meddelanden som stoppades av "
            "maskeringens säkerhetsspärr skickades aldrig, och loggas därför "
            "inte. Saknar du något du skrev är det sannolikt just det som hände.",
            ">",
            f"> **Filen raderas automatiskt efter {STANDARD_LAGRINGSTID_DAGAR} "
            "dagar.** Behöver du spara den längre: kopiera den någon annanstans.",
            "",
            "---",
            "",
        ]
        if not self.poster:
            delar += [
                "## Inga AI-anrop i den här sessionen",
                "",
                "Appen startades, men ingen information skickades till någon "
                "AI-leverantör.",
                "",
            ]
        else:
            delar += [_rendera_utflode(post, i) for i, post in enumerate(self.poster, start=1)]
        return "\n".join(delar).rstrip() + "\n"

    def _skriv(self) -> None:
        """Atomisk helskrivning: temporärfil + os.replace. En avbruten skrivning
        lämnar då den föregående, hela filen orörd i stället för en stympad."""
        try:
            self.sokvag.parent.mkdir(parents=True, exist_ok=True)
            temp = self.sokvag.with_suffix(".md.tmp")
            temp.write_text(self._innehall(), encoding="utf-8")
            os.replace(temp, self.sokvag)
        except OSError:
            pass


class TystSessionslogg:
    """Null-objekt: används när ingen säker lagringsplats kunde lösas ut. Sväljer
    allt. Gör att anroparna slipper None-kontroller — och att en app utan
    skrivbar loggkatalog fortsätter fungera i övrigt."""

    sokvag: Path | None = None

    def logga(self, post: Utflode) -> None:  # noqa: D102
        return


def logga_sakert(logg: Any, **falt: Any) -> None:
    """Loggar ett utflöde om en logg finns, och sväljer ALLT som går fel.

    Den här funktionen är avsedd att anropas från AI-klienterna, precis vid
    tråden. Den finns för att de ska slippa både None-kontroller och
    try/except: loggningen får aldrig vara anledningen till att ett AI-anrop
    misslyckas."""
    if logg is None:
        return
    try:
        logg.logga(Utflode(**falt))
    except Exception:  # noqa: BLE001 — loggning får aldrig fälla ett AI-anrop
        pass


def sessionsfil(nu: datetime | None = None, session_id: str | None = None) -> Path:
    """Sökvägen till en ny sessionsfil.

    Arkivstrukturen är vald för att vara begriplig i Utforskaren: en mapp per
    månad, och filnamn som börjar med datum så att sorteringen blir
    kronologisk av sig själv.

        .../logs/ai-utflode/2026-08/AI-utflode_2026-08-03_143052_a1b2c3.md

    Prefixet gör filen självförklarande även när den ligger lösryckt i en
    nedladdningsmapp eller bifogas i ett samtal med en AI."""
    nu = nu or datetime.now()
    session_id = session_id or uuid4().hex[:6]
    manad = nu.strftime("%Y-%m")
    namn = f"{FILPREFIX}_{_tidsstampel(nu)}_{session_id}.md"
    return saker_lagring.ai_utflode_dir() / manad / namn


def starta_session(nu: datetime | None = None) -> Sessionslogg | TystSessionslogg:
    """Öppnar en ny sessionslogg. Anropas EN gång per appstart.

    Fail-safe: går ingen säker lagringsplats att lösa ut (SakerLagringFel på en
    molnsynkad eller relativ rot) returneras en tyst logg i stället för att
    appen stoppas. Loggen är ett skyddsnät, inte en förutsättning för drift."""
    nu = nu or datetime.now()
    session_id = uuid4().hex[:6]
    try:
        return Sessionslogg(sessionsfil(nu, session_id), nu, session_id)
    except (saker_lagring.SakerLagringFel, OSError):
        return TystSessionslogg()


def _ar_sessionsfil(p: Path) -> bool:
    return p.is_file() and p.name.startswith(FILPREFIX) and p.suffix == ".md"


def rensa_gamla(dagar: int = STANDARD_LAGRINGSTID_DAGAR) -> int:
    """Raderar sessionsloggar äldre än `dagar`. Returnerar antalet raderade.

    Kallas vid appstart. Dataminimering (art. 5.1 e): en logg över utflöde ska
    finnas så länge den kan behövas för uppföljning, inte för alltid. Tomma
    månadsmappar städas bort på köpet.

    Fail-safe: fel sväljs, och bara filer som ser ut som våra egna
    sessionsloggar rörs — aldrig något annat som råkar ligga i katalogen."""
    if dagar <= 0:
        return 0
    try:
        rot = saker_lagring.ai_utflode_dir()
    except saker_lagring.SakerLagringFel:
        return 0
    if not rot.exists():
        return 0

    gransen = time.time() - dagar * 86400
    raderade = 0
    for manadsmapp in sorted(p for p in rot.iterdir() if p.is_dir()):
        for fil in list(manadsmapp.iterdir()):
            try:
                if _ar_sessionsfil(fil) and fil.stat().st_mtime < gransen:
                    fil.unlink()
                    raderade += 1
            except OSError:
                continue
        try:
            if not any(manadsmapp.iterdir()):
                manadsmapp.rmdir()
        except OSError:
            pass
    return raderade


def lista_sessioner(max_antal: int = 50) -> list[dict[str, Any]]:
    """Sessionsloggarna, nyast först — för en översikt i gränssnittet.
    Returnerar sökväg, namn, storlek och ändringstid. Fail-safe: en oläsbar
    katalog ger en tom lista."""
    try:
        rot = saker_lagring.ai_utflode_dir()
    except saker_lagring.SakerLagringFel:
        return []
    if not rot.exists():
        return []

    filer: list[Path] = []
    for manadsmapp in rot.iterdir():
        if manadsmapp.is_dir():
            filer += [p for p in manadsmapp.iterdir() if _ar_sessionsfil(p)]
    filer.sort(key=lambda p: p.name, reverse=True)

    poster = []
    for fil in filer[:max_antal]:
        try:
            stat = fil.stat()
        except OSError:
            continue
        poster.append({
            "sokvag": fil,
            "namn": fil.name,
            "storlek_kb": round(stat.st_size / 1024, 1),
            "andrad": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return poster
