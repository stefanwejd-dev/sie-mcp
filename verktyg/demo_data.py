"""demo_data.py — Reproducerbart demoläge för sie-mcp (Steg 27).

Laddar samples/SIE4_Exempelfil.SE och initierar alla app-tillstånd
så att samtliga rum i Streamlit-appen har fullständigt och representativt
innehåll — helt utan Spiris-anslutning och utan extern AI-nyckel.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

_ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROT))
sys.path.insert(0, str(_ROT / "parser"))

from sie4_parser import parse_sie4
from sekretesslager import maskera_siefil
from analysflode import kor_analys
import app_config
import namnreferens


def ladda_demodata(st) -> None:
    """Laddar exempelfilen och sätter session_state så alla vyer fungerar direkt."""
    exempelfil = _ROT / "samples" / "SIE4_Exempelfil.SE"
    if not exempelfil.exists():
        raise FileNotFoundError(f"Exempelfilen saknas: {exempelfil}")

    sie = parse_sie4(exempelfil)

    # 1. Grundläggande SIE-data
    st.session_state.sie = sie
    st.session_state.behandlad_fil_id = "SIE4_Exempelfil.SE"
    st.session_state.aktiv_datakälla = "Ladda upp lokal SIE4-fil"
    st.session_state.demolage = True

    # 2. Maskering & sekretesslager
    liggare = getattr(st.session_state, "maskeringsliggare", None) or app_config.las_maskeringsliggare()
    undantag = getattr(st.session_state, "undantagslista", None) or app_config.las_undantagslista()
    referens = getattr(st.session_state, "namnreferens", None) or namnreferens.las_namnreferens()

    maskeringsresultat = maskera_siefil(
        sie=sie,
        referenslista=referens,
        undantagslista=undantag,
    )
    st.session_state.maskeringsresultat = maskeringsresultat

    # 3. Analysresultat (väsentlighetstal och kontroller)
    from vasentlighet import berakna_vasentlighet
    from analysflode import berakna_standardtroskelvarden
    v_tal = berakna_vasentlighet(sie)
    v_troskel, u_troskel = berakna_standardtroskelvarden(v_tal.omsattning)

    analys = kor_analys(
        sie=sie,
        maskeringsresultat=maskeringsresultat,
        haiku_anropare=lambda items, sys_prompt: [],
        utfallsväsentlighet=u_troskel,
        väsentlighetstal=v_troskel,
    )
    st.session_state.analys_resultat = analys

    # 4. Spiris-liknande fyllig reskontra för snabbvyer & rapporter i demoläget
    from reskontra_tvatt import Kundpost, Leverantorspost
    from datetime import timedelta

    idag = date.today()

    st.session_state.spiris_kundreskontra = [
        Kundpost(
            kund="Almgren Fastigheter AB",
            belopp=Decimal("437500.00"),
            betalstatus="Utestående",
            forfallodatum=idag + timedelta(days=14),
            ska_maskeras=False,
            motpart_id="KUND-001",
        ),
        Kundpost(
            kund="Sjölunds Bygg & Anläggning AB",
            belopp=Decimal("125000.00"),
            betalstatus="Förfallen",
            forfallodatum=idag - timedelta(days=12),
            ska_maskeras=False,
            motpart_id="KUND-002",
        ),
        Kundpost(
            kund="Lindqvist Entreprenad AB",
            belopp=Decimal("250000.00"),
            betalstatus="Utestående",
            forfallodatum=idag + timedelta(days=5),
            ska_maskeras=False,
            motpart_id="KUND-003",
        ),
    ]

    st.session_state.spiris_reskontra = [
        Leverantorspost(
            leverantor="Bäckströms Elinstallation AB",
            belopp=Decimal("73000.00"),
            betalstatus="Utestående",
            forfallodatum=idag + timedelta(days=8),
            ska_maskeras=False,
        ),
        Leverantorspost(
            leverantor="Kvarnbergets Fastighets AB",
            belopp=Decimal("75000.00"),
            betalstatus="Utestående",
            forfallodatum=idag + timedelta(days=20),
            ska_maskeras=False,
        ),
        Leverantorspost(
            leverantor="Nordvik Datorservice AB",
            belopp=Decimal("38400.00"),
            betalstatus="Förfallen",
            forfallodatum=idag - timedelta(days=4),
            ska_maskeras=False,
        ),
    ]

    # 5. Skapa ett representativt utkast i utkastkön för skärmbild
    try:
        import utkast
        befintliga = utkast.lista()
        if not befintliga:
            utkast.skapa(
                typ="kundfaktura",
                nyttolast={
                    "kund": "Nordic Solutions AB",
                    "belopp": "45000.00",
                    "fakturadatum": idag.isoformat(),
                    "rader": [
                        {"beskrivning": "Konsultarvode bokslut", "belopp": "45000.00", "konto": "3011"}
                    ],
                },
                sammanfattning=[
                    ["Kund", "Nordic Solutions AB"],
                    ["Belopp", "45 000,00 kr"],
                    ["Typ", "Konsulttjänster"],
                ],
            )
    except Exception:
        pass


if __name__ == "__main__":
    print("Startar sie-mcp i demoläge...")
    os.environ["SIE_MCP_DEMO"] = "1"
    os.system(f"streamlit run {str(_ROT / 'app.py')}")
