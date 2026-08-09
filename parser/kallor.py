from datetime import date
from typing import Any
from dataclasses import dataclass

from domain_model import SIEFil
from parser.kalla_protokoll import Bokforingskalla, Formaga, FormagaSaknas, KallaFel
from spiris_klient import SpirisKlient, SpirisKlientFel

class SpirisKalla:
    def __init__(self, klient: SpirisKlient):
        self.klient = klient
        self.id = "spiris"
        self.visningsnamn = "Spiris"

    def formagor(self) -> frozenset[Formaga]:
        return frozenset([
            Formaga.LASA_HUVUDBOK,
            Formaga.LASA_KUNDRESKONTRA,
            Formaga.LASA_LEVERANTORSRESKONTRA,
            Formaga.LASA_RAPPORTER,
            Formaga.LASA_MOMS,
            Formaga.LASA_ORDER_OFFERT,
            Formaga.LASA_ARTIKLAR,
            Formaga.FORESLA_KUND,
            Formaga.FORESLA_KUNDFAKTURA,
            Formaga.FORESLA_VERIFIKAT,
        ])

    def rakenskapsar(self) -> list[dict]:
        from spiris_adapter import hamta_rakenskapsar
        return hamta_rakenskapsar(self.klient)

    def huvudbok(self, ar_id: str) -> SIEFil:
        from spiris_adapter import hamta_huvudbok
        return hamta_huvudbok(self.klient, ar_id)

    def kundreskontra(self) -> list[dict]:
        from spiris_adapter import hamta_reskontra
        return hamta_reskontra(self.klient, "kund")

    def leverantorsreskontra(self) -> list[dict]:
        from spiris_adapter import hamta_reskontra
        return hamta_reskontra(self.klient, "leverantor")

    def rapporter(self, start: date, slut: date) -> dict:
        from spiris_adapter import hamta_rapporter
        return hamta_rapporter(self.klient, start, slut)

    def utfor_utkast(self, logg, **kwargs) -> None:
        from spiris_adapter import utfor_utkast
        try:
            utfor_utkast(self.klient, logg, **kwargs)
        except SpirisKlientFel as fel:
            raise KallaFel(str(fel))

    def skapa_kund(self, orgnr: str, namn: str, logg) -> str:
        from spiris_adapter import skapa_kund
        try:
            return skapa_kund(self.klient, orgnr, namn, logg)
        except SpirisKlientFel as fel:
            raise KallaFel(str(fel))

    def hamta_artikel(self, sokterm: str) -> dict | None:
        from spiris_adapter import hamta_artikel
        try:
            return hamta_artikel(self.klient, sokterm)
        except SpirisKlientFel as fel:
            raise KallaFel(str(fel))

    def hamta_enhet(self, sokterm: str) -> dict | None:
        from spiris_adapter import hamta_enhet
        try:
            return hamta_enhet(self.klient, sokterm)
        except SpirisKlientFel as fel:
            raise KallaFel(str(fel))


class Sie4Kalla:
    def __init__(self, sie_fil: SIEFil, filnamn: str):
        self._sie_fil = sie_fil
        self.id = "sie4"
        self.visningsnamn = filnamn

    def formagor(self) -> frozenset[Formaga]:
        return frozenset([
            Formaga.LASA_HUVUDBOK,
            Formaga.LASA_RAPPORTER,
        ])

    def rakenskapsar(self) -> list[dict]:
        raise FormagaSaknas("Lokala filer har inte ID-baserade räkenskapsår.")

    def huvudbok(self, ar_id: str) -> SIEFil:
        return self._sie_fil

    def kundreskontra(self) -> list[dict]:
        raise FormagaSaknas("Lokala filer innehåller inte kundreskontra.")

    def leverantorsreskontra(self) -> list[dict]:
        raise FormagaSaknas("Lokala filer innehåller inte leverantörsreskontra.")

    def rapporter(self, start: date, slut: date) -> dict:
        from parser.app_tillstand import rapporter_fran_sie
        return rapporter_fran_sie(self._sie_fil)

    def utfor_utkast(self, logg, **kwargs) -> None:
        raise FormagaSaknas("Lokala filer kan inte spara utkast.")

    def skapa_kund(self, orgnr: str, namn: str, logg) -> str:
        raise FormagaSaknas("Lokala filer kan inte skapa kunder.")

    def hamta_artikel(self, sokterm: str) -> dict | None:
        raise FormagaSaknas("Lokala filer har inga artiklar.")

    def hamta_enhet(self, sokterm: str) -> dict | None:
        raise FormagaSaknas("Lokala filer har inga enheter.")


    def sok_kunder(self) -> list[dict]:
        from parser.kalla_protokoll import KallaFel
        try:
            return self.klient.hamta_alla("/customers")
        except Exception as e:
            raise KallaFel(str(e))

    def skapa_kundfaktura(self, payload: dict) -> dict:
        from parser.kalla_protokoll import KallaFel
        from spiris_adapter import skapa_kundfaktura
        try:
            return skapa_kundfaktura(self.klient, payload)
        except Exception as e:
            raise KallaFel(str(e))
