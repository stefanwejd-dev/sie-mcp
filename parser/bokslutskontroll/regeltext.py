"""regeltext — steg 9a i hantverksbok/BOKSLUTSKONTROLLER.md §8.3.

Paragraftext på begäran: slår upp den faktiska lydelsen av den paragraf ett
fynds `Regelhanvisning` redan pekar mot. Ett fynd är fullständigt utan detta
— verktyget gör bara att en människa slipper öppna Riksdagens webbplats
själv. Berikning, aldrig en förutsättning (§8.3).

`quiet_chatt` importeras ALDRIG hårt (§8.2: sie-mcp ska gå att installera
och köra utan quiet_chatt klonat bredvid). Importen sker inne i
`QuietChattRegeltextkalla`, skyddad av `try/except`, och hela vägen är
fail-closed: en källa som inte kan svara ger `None`, aldrig en påhittad
lydelse."""

from __future__ import annotations

import re
from typing import Protocol


class Regeltextkalla(Protocol):
    def hamta(self, sfs: str, beteckning: str) -> str | None: ...


def tolka_beteckning(beteckning: str) -> tuple[str | None, str | None]:
    """"5 kap. 1 §" -> ("5", "1"). "3 §" -> (None, "3"). "3 a §" -> (None, "3a").
    Otolkbart ger (None, None)."""
    match = re.match(r"^\s*(?:(\d+)\s*kap\.?\s*)?(\d+\s*[a-zA-Zåäö]?)\s*§", beteckning or "")
    if not match:
        return None, None
    kapitel = match.group(1)
    paragraf = match.group(2).replace(" ", "") if match.group(2) else None
    return kapitel, paragraf


class RiksdagenRegeltextkalla:
    """Fallbacken: alltid tillgänglig, samma anrop som `sok_lagstiftning`-
    verktyget redan gör mot data.riksdagen.se. Grövre än quiet_chatts index
    (fritextsnutt runt sökordet, inte en riktig paragrafuppslagning) — se
    hantverksbok/BOKSLUTSKONTROLLER.md §8, jämförelsetabellen."""

    def hamta(self, sfs: str, beteckning: str) -> str | None:
        from juridik_api import sok_svensk_lagstiftning

        try:
            svar = sok_svensk_lagstiftning(f"{sfs} {beteckning}".strip())
        except Exception:
            return None
        if not isinstance(svar, dict) or svar.get("status") != "success":
            return None
        for post in svar.get("lagstiftning") or []:
            if post.get("beteckning") == sfs and post.get("utdrag_ur_lagtexten"):
                return post["utdrag_ur_lagtexten"]
        return None


class QuietChattRegeltextkalla:
    """Berikning om quiet_chatt:s lokala lagtextindex råkar vara nåbart i
    körmiljön (t.ex. under utveckling, klonat bredvid). `nabar()` avgör
    tillgänglighet en gång per anrop utan att cacha — en källa som blir
    tillgänglig mellan två anrop ska upptäckas utan omstart av servern."""

    def nabar(self) -> bool:
        try:
            from quiet_oppen_data.adaptrar.lagtext import sok_lag  # noqa: F401
        except Exception:
            return False
        return True

    def hamta(self, sfs: str, beteckning: str) -> str | None:
        try:
            from quiet_oppen_data.adaptrar.lagtext import sok_lag
        except Exception:
            return None

        kapitel, paragraf = tolka_beteckning(beteckning)
        if paragraf is None:
            return None

        try:
            träffar = sok_lag(
                fraga=beteckning,
                max_antal=3,
                sfs_filter=sfs,
                kapitel_filter=kapitel,
                paragraf_filter=paragraf,
            )
        except Exception:
            return None

        for träff in träffar:
            if getattr(träff, "sfs", None) == sfs and getattr(träff, "paragraf_nr", None) == paragraf:
                return getattr(träff, "paragraf_text", None)
        return None


class SammansattRegeltextkalla:
    """quiet_chatt om nåbart, annars Riksdagen — se §8.3 9a. Nåbarhet avgörs
    på infrastrukturnivå (går indexet att importera/nå?), inte på om just
    denna fråga gav träff — annars skulle en källa som verkligen svarat
    "hittar inget" tystas av en sämre källas gissning."""

    def __init__(self) -> None:
        self._quiet_chatt = QuietChattRegeltextkalla()
        self._riksdagen = RiksdagenRegeltextkalla()

    def hamta(self, sfs: str, beteckning: str) -> str | None:
        if self._quiet_chatt.nabar():
            return self._quiet_chatt.hamta(sfs, beteckning)
        return self._riksdagen.hamta(sfs, beteckning)


def valj_regeltextkalla() -> Regeltextkalla:
    return SammansattRegeltextkalla()
