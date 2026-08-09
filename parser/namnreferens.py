"""namnreferens — referenslista över vanliga svenska namn för sekretesslagrets
Lager 3a ("namn som ALLTID maskeras").

Bakgrund (granskningens fynd 6): mekanismen för en referenslista fanns redan i
maskera_siefil (parametern referenslista), men den anropades ALDRIG med något i
produktion — den användes bara i tester. Lager 3a var alltså byggt men aldrig
inkopplat. Den här modulen kopplar in det: den levererar en uppsättning vanliga
svenska för- och efternamn som Lager 3a auto-maskerar, så att versalfallen och
enbart-förnamn-fallen som Lager 3b:s regex missar ändå fångas — deterministiskt,
utan att blockera för granskning.

Om namnen INTE fångas av referenslistan faller de tillbaka på Lager 3b
(regex-fallback), som flaggar för mänsklig granskning. Referenslistan minskar
alltså mängden manuellt arbete; den är inte den enda skyddslinjen.

Datakälla: en KURERAD inbyggd lista (STANDARDNAMN) över de vanligaste svenska
efternamnen (låg risk för falska träffar) och vanliga förnamn. De två xlsx-
filerna i repo-roten ("Namn - nyfödda ... topp 100") används medvetet INTE:
openpyxl saknas i miljön, och granskningen påpekar att topp-100 NYFÖDDA är fel
data — de vanligaste fakturamottagarna heter Lars och Birgitta, inte Alma och
Vera. Vill man bygga ut listan (t.ex. SCB:s topp-1000) läggs namnen, ett per rad,
i en lokal fil (NAMNREFERENS_FIL, gitignorerad) som unionsläggs med den inbyggda.

Avvägning: Lager 3a är "maskera ALLTID", så listan över-maskerar hellre än
under-maskerar (fail-closed). Ett förnamn som också är ett vanligt substantiv
("Sten", "Björn") kan därför maskera en icke-person i sällsynta fall — men i
bokföringstext är riktningen rätt: hellre en maskerad tvetydighet än ett läckt
namn. De mest tvetydiga ord-namnen är medvetet uteslutna ur den inbyggda listan.
"""

from __future__ import annotations

from pathlib import Path

import saker_lagring

# Paket B1: den valfria lokala namnreferensen kan bära riktiga namn (PII) och
# behandlas därför som state — sökvägen löses centralt till den säkra,
# icke-synkade state-katalogen, aldrig projekt-/Drive-mappen.
NAMNREFERENS_NAMN = "namnreferens.txt"

# De vanligaste svenska EFTERNAMNEN (SCB-storleksordning). Efternamn har mycket
# låg risk för falska träffar — de förekommer sällan som vanliga substantiv.
_EFTERNAMN: frozenset[str] = frozenset({
    "Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson",
    "Olsson", "Persson", "Svensson", "Gustafsson", "Pettersson", "Jonsson",
    "Jansson", "Hansson", "Bengtsson", "Jönsson", "Lindberg", "Jakobsson",
    "Magnusson", "Olofsson", "Lindström", "Lindqvist", "Lindgren", "Axelsson",
    "Berg", "Bergström", "Lundberg", "Lundgren", "Lundqvist", "Mattsson",
    "Berglund", "Fredriksson", "Sandberg", "Henriksson", "Forsberg", "Sjöberg",
    "Wallin", "Engström", "Eklund", "Danielsson", "Håkansson", "Lund",
    "Gunnarsson", "Holm", "Björk", "Bergqvist", "Samuelsson", "Fransson",
    "Wikström", "Isaksson", "Bergman", "Nyström", "Holmberg", "Arvidsson",
    "Löfgren", "Söderberg", "Nyberg", "Blomqvist", "Claesson", "Nordström",
    "Mårtensson", "Lindholm", "Åberg", "Dahlberg", "Hermansson", "Falk",
})

# Vanliga svenska FÖRNAMN (bägge kön), viktade mot de åldrar som oftast dyker
# upp i reskontra/löner. De mest tvetydiga ord-namnen (t.ex. "Sten", "Ros")
# är UTELÄMNADE med flit för att hålla falska träffar nere.
_FORNAMN: frozenset[str] = frozenset({
    "Lars", "Anders", "Mikael", "Johan", "Erik", "Per", "Karl", "Nils",
    "Lennart", "Bengt", "Bo", "Hans", "Gunnar", "Leif", "Rolf", "Stefan",
    "Peter", "Fredrik", "Daniel", "Andreas", "Thomas", "Marcus", "Martin",
    "Jonas", "Henrik", "Christer", "Ulf", "Kjell", "Roland", "Kurt",
    "Maria", "Anna", "Margareta", "Elisabeth", "Eva", "Kristina", "Birgitta",
    "Karin", "Ingrid", "Kerstin", "Marianne", "Sara", "Emma", "Malin",
    "Lena", "Helena", "Johanna", "Linda", "Sofia", "Kajsa", "Ulla",
    "Camilla", "Åsa", "Annika", "Gunilla", "Katarina", "Susanne", "Hanna",
    "Emelie", "Julia", "Ida", "Josefin", "Amanda", "Elin", "Frida",
    # Vanliga namn med diakriter (omgranskningens fynd 4) — Lager 3b:s
    # teckenklasser täcker dem numera, men referenslistan fångar dem även
    # utan föregående ord (bart namn i ett fält) och i versalform.
    "André", "Linnéa", "Renée", "Désirée",
})

STANDARDNAMN: frozenset[str] = _EFTERNAMN | _FORNAMN


def _las_extra_namn(fil: Path) -> set[str]:
    """Läser valfria extra namn ur en lokal fil (ett namn per rad). Saknad fil
    eller läsfel -> tomt (fail-safe: referenslistan blir aldrig en kraschkälla).
    Tomma rader och rader som börjar med # (kommentar) hoppas över."""
    try:
        rader = Path(fil).read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {rad.strip() for rad in rader if rad.strip() and not rad.startswith("#")}


def las_namnreferens(extra_fil: Path | None = None) -> set[str]:
    """Referenslistan som skickas till sekretesslager.maskera_siefil (Lager 3a).
    Den inbyggda, kurerade STANDARDNAMN unionsläggs med ev. extra namn ur en
    lokal fil (för den som vill ladda t.ex. SCB:s topp-1000) i den säkra
    state-katalogen. Ren funktion — ingen global state, alltid en ny mängd."""
    fil = saker_lagring.artefakt_sokvag(extra_fil, kategori="state", namn=NAMNREFERENS_NAMN)
    return set(STANDARDNAMN) | _las_extra_namn(fil)
