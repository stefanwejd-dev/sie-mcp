"""app_tillstand.py — Central hantering av session_state och app-specifika hjälparfunktioner."""

from dataclasses import dataclass
from datetime import date
from typing import Any, Tuple, Optional
from decimal import Decimal
import streamlit as st

import app_config
import revisionslogg
import saker_lagring
import sessionslogg
import utkast
import namnreferens
from domain_model import SIEFil
from fpa_vy import (
    berakna_kundbetalbeteende,
    dashboard_rendering_lage,
    likviditetsprognos_fran_reskontra,
    momssaldo_fran_sie,
    rapporter_fran_sie,
)
import spiris_adapter
from fpa_motor import bygg_momsoversikt

@dataclass(frozen=True)
class Rapportunderlag:
    rapporter: dict[str, Any]
    kundbetalbeteende: dict[str, Any]
    likviditetsprognos: list[dict[str, Any]] | None
    lage: str


def initiera(st) -> None:
    if "sie" not in st.session_state:
        st.session_state.sie = None
    if "maskeringsresultat" not in st.session_state:
        st.session_state.maskeringsresultat = None
    if "ai_konfiguration" not in st.session_state:
        st.session_state.ai_konfiguration = None
    if "analys_resultat" not in st.session_state:
        st.session_state.analys_resultat = None
    if "behandlad_fil_id" not in st.session_state:
        st.session_state.behandlad_fil_id = None
    if "samtal_historik" not in st.session_state:
        st.session_state.samtal_historik = []
    if "samtal_senast_behandlat" not in st.session_state:
        st.session_state.samtal_senast_behandlat = -1
    if "visa_eget_svarsfalt" not in st.session_state:
        st.session_state.visa_eget_svarsfalt = False

    if "sessionslogg" not in st.session_state:
        try:
            saker_lagring.initiera_lagring()
        except Exception:
            pass
        sessionslogg.rensa_gamla()
        try:
            utkast.rensa_gamla()
        except Exception:
            pass
        st.session_state.sessionslogg = sessionslogg.starta_session()

    if "aktivt_fakturautkast" not in st.session_state:
        st.session_state.aktivt_fakturautkast = None
    if "konteringsminne" not in st.session_state:
        st.session_state.konteringsminne = app_config.las_konteringsminne()
    if "aktiv_datakälla" not in st.session_state:
        st.session_state.aktiv_datakälla = "Ladda upp lokal SIE4-fil"
    if "spiris_state" not in st.session_state:
        st.session_state.spiris_state = None
    if "spiris_code_verifier" not in st.session_state:
        st.session_state.spiris_code_verifier = None
    if "spiris_tokens" not in st.session_state:
        st.session_state.spiris_tokens = None
    if "spiris_reskontra" not in st.session_state:
        st.session_state.spiris_reskontra = None
    if "spiris_kundreskontra" not in st.session_state:
        st.session_state.spiris_kundreskontra = None
    if "spiris_kundbetalhistorik" not in st.session_state:
        st.session_state.spiris_kundbetalhistorik = None
    if "spiris_dashboarddata" not in st.session_state:
        st.session_state.spiris_dashboarddata = None
    if "datastatus_notiser" not in st.session_state:
        st.session_state.datastatus_notiser = []
    if "periodnotis" not in st.session_state:
        st.session_state.periodnotis = None
    if "spiris_hamtat_ar" not in st.session_state:
        st.session_state.spiris_hamtat_ar = None
    if "spiris_dashboard_period" not in st.session_state:
        st.session_state.spiris_dashboard_period = None
    if "ai_modeller_for" not in st.session_state:
        st.session_state.ai_modeller_for = None

    config = app_config.las_config()
    if "maskeringsliggare" not in st.session_state:
        st.session_state.maskeringsliggare = app_config.las_maskeringsliggare()
    if "undantagslista" not in st.session_state:
        st.session_state.undantagslista = app_config.las_undantagslista()
    if "namnreferens" not in st.session_state:
        st.session_state.namnreferens = namnreferens.las_namnreferens()

def _nollstall_samtalshistorik() -> None:
    st.session_state.samtal_historik = []
    st.session_state.samtal_senast_behandlat = -1
    st.session_state.visa_eget_svarsfalt = False

def _nollstall_inlast_data() -> None:
    st.session_state.sie = None
    st.session_state.maskeringsresultat = None
    st.session_state.analys_resultat = None
    _nollstall_samtalshistorik()
    st.session_state.behandlad_fil_id = None
    st.session_state.spiris_reskontra = None
    st.session_state.spiris_kundreskontra = None
    st.session_state.spiris_kundbetalhistorik = None
    st.session_state.spiris_dashboarddata = None
    st.session_state.spiris_hamtat_ar = None
    st.session_state.spiris_dashboard_period = None
    st.session_state.datastatus_notiser = []
    st.session_state.periodnotis = None

_NOTISRENDERARE = {
    "success": st.success,
    "info": st.info,
    "warning": st.warning,
    "error": st.error,
    "caption": st.caption,
}

def _notera(nivå: str, text: str) -> None:
    st.session_state.datastatus_notiser.append((nivå, text))

def _notera_period(nivå: str, text: str) -> None:
    st.session_state.periodnotis = (nivå, text)

def _rendera_notiser() -> None:
    notiser = list(st.session_state.datastatus_notiser)
    if st.session_state.periodnotis is not None:
        notiser.append(st.session_state.periodnotis)
    for nivå, text in notiser:
        _NOTISRENDERARE[nivå](text)

def _hitta_originaltext(sie: SIEFil, behov: Any) -> str:
    misstänkt = behov.misstänkt_text
    for verifikation in sie.verifikationer:
        if verifikation.vertext and misstänkt in verifikation.vertext:
            return verifikation.vertext
        for transaktion in verifikation.transaktioner:
            if transaktion.transtext and misstänkt in transaktion.transtext:
                return transaktion.transtext
    if sie.prosa and misstänkt in sie.prosa:
        return sie.prosa
    return misstänkt

def _procent_caption(procent: Decimal | None, basnamn: str) -> str:
    if procent is None:
        return f"Motsvarar: – ({basnamn} är 0 kr)"
    return f"Motsvarar: {float(procent):.1f} % av {basnamn}".replace(".", ",")


def bygg_rapportunderlag(st) -> Rapportunderlag | None:
    datakälla = st.session_state.get("aktiv_datakälla", "Ladda upp lokal SIE4-fil")
    sie = st.session_state.get("sie")
    _dashboard_lage = dashboard_rendering_lage(
        datakälla_ar_spiris=(datakälla == "Koppla till Spiris"),
        sie_finns=sie is not None,
        spiris_data_finns=st.session_state.get("spiris_dashboarddata") is not None,
    )
    if _dashboard_lage == "spiris":
        rapporter = st.session_state.spiris_dashboarddata
    elif _dashboard_lage == "fil":
        rapporter = rapporter_fran_sie(sie)
    else:
        rapporter = None

    likviditetsprognos = None
    kundbetalbeteende = {}
    if _dashboard_lage == "spiris" and rapporter is not None:
        kundbetalbeteende = berakna_kundbetalbeteende(
            st.session_state.get("spiris_kundbetalhistorik") or []
        )
        momssaldo = momssaldo_fran_sie(sie) if sie is not None else None
        likviditetsprognos = likviditetsprognos_fran_reskontra(
            st.session_state.get("spiris_reskontra"),
            st.session_state.get("spiris_kundreskontra"),
            rapporter["balans"]["poster"]["kassa_och_bank"],
            date.today(),
            kundbetalbeteende=kundbetalbeteende,
            momssaldo=momssaldo,
        )

    return Rapportunderlag(rapporter, kundbetalbeteende, likviditetsprognos, _dashboard_lage)

def ladda_bockerna_data(st, klient) -> None:
    sie = st.session_state.get("sie")
    st.session_state.bockerna_kontoplan = None
    st.session_state.bockerna_kontosaldon = None
    st.session_state.bockerna_verifikationer = None
    st.session_state.bockerna_momsoversikt = None
    st.session_state.bockerna_verifikatutkast = None
    
    st.session_state.bockerna_ingaende_balanser = None
    st.session_state.bockerna_verifikationer_alla = None
    st.session_state.bockerna_periodiseringar = None
    st.session_state.bockerna_kontoplan_alla = None
    st.session_state.bockerna_momsrapporter = None
    st.session_state.bockerna_momskoder = None
    
    ar_id = st.session_state.get("spiris_hamtat_ar")
    if klient and ar_id:
        try:
            st.session_state.bockerna_kontoplan = spiris_adapter.hamta_kontoplan(klient, ar_id)
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_verifikatutkast = [
                {
                    "utkast_id": v.vernr,
                    "serie": v.serie,
                    "verdatum": str(v.verdatum),
                    "vertext": v.vertext,
                    "rader": [
                        {
                            "kontonr": t.kontonr,
                            "belopp": t.belopp,
                            "transtext": t.transtext,
                        }
                        for t in v.transaktioner
                    ],
                }
                for v in spiris_adapter.hamta_verifikatutkast(klient)
            ]
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_ingaende_balanser = spiris_adapter.hamta_ingaende_balans(klient)
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_verifikationer_alla = spiris_adapter.hamta_verifikationer_alla(klient)
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_periodiseringar = spiris_adapter.hamta_periodiseringar(klient)
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_kontoplan_alla = spiris_adapter.hamta_kontoplan_alla(klient)
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_momsrapporter = spiris_adapter.hamta_momsrapporter(klient)
        except Exception:
            pass
            
        try:
            st.session_state.bockerna_momskoder = spiris_adapter.hamta_momskoder(klient)
        except Exception:
            pass
            
    if sie:
        if hasattr(sie, "konton") and sie.konton:
            if st.session_state.bockerna_kontoplan is None:
                # Fallback om inte kontoplan kunde hämtas separat
                st.session_state.bockerna_kontoplan = [
                    {"kontonr": k.kontonr, "kontonamn": k.namn, "kontotyp": k.typ, "aktivt": True}
                    for k in sie.konton.values()
                ]
        st.session_state.bockerna_verifikationer = sie.verifikationer
        st.session_state.bockerna_kontosaldon = sie.utgående_balanser
        if sie.utgående_balanser:
            try:
                per_datum = str(date.today())
                if sie.resultat and len(sie.resultat) > 0:
                    per_datum = str(sie.resultat[0].slut_datum)
                konton_saldon = [
                    {"kontonr": str(getattr(s, "kontonr", getattr(s, "konto", ""))), "saldo": getattr(s, "saldo", Decimal("0"))}
                    for s in sie.utgående_balanser
                ]
                st.session_state.bockerna_momsoversikt = bygg_momsoversikt(konton_saldon, per_datum=per_datum)
            except Exception:
                pass


def ladda_bank_data(st, klient) -> None:
    if not klient:
        return
        
    if "bankkonton" not in st.session_state:
        from spiris_adapter import hamta_bankkonton
        try:
            st.session_state.bankkonton = hamta_bankkonton(klient)
        except Exception:
            pass
            
    if "avstamningslage" not in st.session_state:
        from spiris_adapter import hamta_avstamningslage
        try:
            st.session_state.avstamningslage = hamta_avstamningslage(klient)
        except Exception:
            pass

def ladda_register_data(st, klient) -> None:
    from spiris_adapter import (
        hamta_kunder, hamta_leverantorer, hamta_artiklar, 
        hamta_projekt, hamta_kostnadsstallen
    )
    
    funcs = {
        "kunder": hamta_kunder,
        "leverantorer": hamta_leverantorer,
        "artiklar": hamta_artiklar,
        "projekt": hamta_projekt,
        "kostnadsstallen": hamta_kostnadsstallen,
    }
    
    for key, func in funcs.items():
        if key not in st.session_state:
            if not klient:
                st.session_state[key] = None
            else:
                try:
                    st.session_state[key] = func(klient)
                except Exception as e:
                    import logging
                    logging.error(f"Kunde inte hämta {key}: {repr(e)}")
                    st.error(f"🚨 Ett internt fel uppstod när {key} skulle hämtas från Spiris: {repr(e)}")
                    st.session_state[key] = None
