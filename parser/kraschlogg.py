"""parser/kraschlogg.py — Automatisk felloggning och kraschhantering för sie-mcp.

Fångar oväntade undantag, sparar fullständig stacktrace och kontext till en
strukturerad loggfil, och visar ett tryggt och professionellt gränssnitt för
användaren.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

LOGG_KATALOG = Path("logs")
KRASCHLOGG_FIL = LOGG_KATALOG / "kraschlogg.jsonl"


def _sakra_loggkatalog() -> None:
    LOGG_KATALOG.mkdir(parents=True, exist_ok=True)


def registrera_krasch(
    undantag: Exception,
    kontext: dict[str, Any] | None = None,
    sida: str | None = None,
) -> dict[str, Any]:
    """Registrerar ett kraschfel strukturerat till kraschloggen och returnerar felobjektet."""
    _sakra_loggkatalog()

    feltyp = type(undantag).__name__
    felmeddelande = str(undantag)
    tb_rader = traceback.format_exception(type(undantag), undantag, undantag.__traceback__)
    stacktrace = "".join(tb_rader)

    # Extrahera sista kodraden och filen där felet uppstod
    filnamn = "okänd"
    radnummer = 0
    if undantag.__traceback__:
        tb_last = traceback.extract_tb(undantag.__traceback__)[-1]
        filnamn = os.path.basename(tb_last.filename)
        radnummer = tb_last.lineno

    rapport = {
        "timestamp": datetime.now().isoformat(),
        "feltyp": feltyp,
        "felmeddelande": felmeddelande,
        "fil": filnamn,
        "rad": radnummer,
        "sida": sida or st.session_state.get("aktiv_sida", "okänd"),
        "stacktrace": stacktrace,
        "kontext": kontext or {},
    }

    try:
        with open(KRASCHLOGG_FIL, "a", encoding="utf-8") as f:
            f.write(json.dumps(rapport, ensure_ascii=False) + "\n")
    except Exception as logg_fel:
        print(f"Kunde inte skriva till kraschlogg: {logg_fel}", file=sys.stderr)

    return rapport


def hamta_senaste_krasch() -> dict[str, Any] | None:
    """Hämtar den senaste registrerade kraschen ur loggen."""
    if not KRASCHLOGG_FIL.exists():
        return None
    try:
        with open(KRASCHLOGG_FIL, "r", encoding="utf-8") as f:
            rader = [r.strip() for r in f if r.strip()]
            if rader:
                return json.loads(rader[-1])
    except Exception:
        return None
    return None


def hamta_alla_krascher() -> list[dict[str, Any]]:
    """Hämtar samtliga sparade kraschrapporter."""
    if not KRASCHLOGG_FIL.exists():
        return []
    rapporter = []
    try:
        with open(KRASCHLOGG_FIL, "r", encoding="utf-8") as f:
            for rad in f:
                rad = rad.strip()
                if rad:
                    rapporter.append(json.loads(rad))
    except Exception:
        pass
    return rapporter


def rendera_krasch_ui(undantag: Exception, sida: str = "okänd") -> None:
    """Visar en professionell felruta för användaren och loggar händelsen."""
    rapport = registrera_krasch(undantag, sida=sida)

    st.error("⚠️ Ett oväntat fel inträffade i denna vy.")
    st.info(
        f"En automatisk felrapport har genererats och sparats i systemloggen.\n\n"
        f"**Feltyp:** `{rapport['feltyp']}` i `{rapport['fil']}:{rapport['rad']}`\n\n"
        f"**Meddelande:** {rapport['felmeddelande']}"
    )

    with st.expander("🔍 Visa teknisk felrapport (för AI / utvecklare)"):
        st.code(rapport["stacktrace"], language="python")
        if st.button("Kopiera fellogg"):
            st.code(json.dumps(rapport, indent=2, ensure_ascii=False), language="json")
