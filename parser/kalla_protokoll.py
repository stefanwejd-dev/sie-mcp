from typing import Protocol
from enum import StrEnum
from datetime import date
from domain_model import SIEFil

class FormagaSaknas(Exception):
    """Kastas när en källa saknar begärd förmåga."""
    pass

class KallaFel(Exception):
    """Kastas när en källa misslyckas med en operation (t.ex. nätverksfel)."""
    pass

class Formaga(StrEnum):
    LASA_HUVUDBOK = "lasa_huvudbok"
    LASA_KUNDRESKONTRA = "lasa_kundreskontra"
    LASA_LEVERANTORSRESKONTRA = "lasa_leverantorsreskontra"
    LASA_RAPPORTER = "lasa_rapporter"
    LASA_MOMS = "lasa_moms"
    LASA_ORDER_OFFERT = "lasa_order_offert"
    LASA_ARTIKLAR = "lasa_artiklar"
    FORESLA_KUND = "foresla_kund"
    FORESLA_KUNDFAKTURA = "foresla_kundfaktura"
    FORESLA_VERIFIKAT = "foresla_verifikat"

class Bokforingskalla(Protocol):
    id: str
    visningsnamn: str
    
    def formagor(self) -> frozenset[Formaga]:
        ...
        
    def rakenskapsar(self) -> list[dict]:
        ...
        
    def huvudbok(self, ar_id: str) -> SIEFil:
        ...
        
    def kundreskontra(self) -> list[dict]:
        ...
        
    def leverantorsreskontra(self) -> list[dict]:
        ...
        
    def rapporter(self, start: date, slut: date) -> dict:
        ...

    def utfor_utkast(self, logg, **kwargs) -> None:
        ...

    def skapa_kund(self, orgnr: str, namn: str, logg) -> str:
        ...

    def hamta_artikel(self, sokterm: str) -> dict | None:
        ...

    def hamta_enhet(self, sokterm: str) -> dict | None:
        ...

    def sok_kunder(self) -> list[dict]:
        ...

    def skapa_kundfaktura(self, payload: dict) -> dict:
        ...
