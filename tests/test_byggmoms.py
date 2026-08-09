"""test_byggmoms.py — R-15: omvänd skattskyldighet ska faktiskt bli omvänd.

Sandbox-mätning 2026-08-06 (riktiga utkast, alla raderade efteråt):

    kund oflaggad + radflagga utelämnad/False -> moms 250,00 av 1000
    kund oflaggad + radflagga True            -> HTTP 400
    kund flaggad  + radflagga utelämnad/False -> moms 250,00
    kund flaggad  + radflagga True            -> moms   0,00
    kund flaggad  + BARA fakturanivåns flagga -> moms 250,00

Tre saker följer av mätningen, och alla tre låses här:

1. Radflaggan `ReversedConstructionServicesVatFree` är det ENDA som utlöser
   omvänd skattskyldighet. Kontovalet gör ingenting för momsen —
   `hitta_artikel_for_konto` returnerar samma artikel för 3041 och 3231.
2. Kunden måste vara flaggad. Är hon inte det avvisar Spiris med 400, så en
   kontroll före sändning ger ett begripligt besked i stället för ett HTTP-fel.
3. Den skarpa vägen KAN INTE uttrycka byggmoms: `CustomerInvoiceRowApi` saknar
   fältet helt (bara `CustomerInvoiceDraftRowApi` har det). Direktbokföring av
   en byggmomsfaktura måste därför vägras — den skulle ofrånkomligen få 25 %.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

KUND_FLAGGAD = {
    "Id": "cus-bygg", "Name": "Byggbolaget AB",
    "ReverseChargeOnConstructionServices": True,
}
KUND_OFLAGGAD = {
    "Id": "cus-vanlig", "Name": "Vanliga Bolaget AB",
    "ReverseChargeOnConstructionServices": False,
}


class _FakturaKlient:
    """Fejk med kunder, kodningar och artiklar. Fångar POST:ar."""

    def __init__(self, kunder: list[dict]) -> None:
        self.skickat: list[tuple[str, dict]] = []
        self._kunder = kunder

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/customers":
            return self._kunder
        if path == "/articleaccountcodings":
            # EN kodning som bär BÅDA kontona — precis som sandboxens
            # "Tjänster 25% moms". Det är därför kontovalet inte kan styra
            # momsen: 3041 och 3231 löses ut till samma artikel.
            return [{
                "Id": "kod-1",
                "DomesticSalesSubjectToVatAccountNumber": 3041,
                "DomesticSalesSubjectToReversedConstructionVatAccountNumber": 3231,
            }]
        if path == "/articles":
            return [{"Id": "art-1", "CodingId": "kod-1"}]
        return []

    def skicka(self, path: str, data: dict) -> dict:
        self.skickat.append((path, data))
        return {"Id": "skapad-1"}


def _nyttolast(kundnamn: str, konto: str) -> dict:
    return {
        "kundnamn": kundnamn,
        "rader": [{"beskrivning": "Byggarbete", "pris": 1000,
                   "antal": 1, "konto": konto}],
        "fakturadatum": "2026-08-06",
        "forfallodatum": "2026-09-05",
    }


class TestByggmomskontonHarleds:
    def test_byggmomskonton_kommer_ur_konteringstabellen(self):
        """Hårdkodas mängden glider den isär från tabellen, och en ändring av
        byggmomskontot kopplar tyst bort momshanteringen igen."""
        from spiris_adapter import (
            BYGGMOMSKONTON,
            FAKTURATYP_BYGGMOMS,
            _KONTERINGSTABELL,
        )

        vantade = {
            konto for (typ, _kat), konto in _KONTERINGSTABELL.items()
            if typ == FAKTURATYP_BYGGMOMS
        }
        assert BYGGMOMSKONTON == vantade
        assert "3231" in BYGGMOMSKONTON

    def test_vanliga_konton_ar_inte_byggmoms(self):
        from spiris_adapter import BYGGMOMSKONTON

        assert "3041" not in BYGGMOMSKONTON
        assert "3051" not in BYGGMOMSKONTON


class TestRadflaggan:
    """Radflaggan är det enda som faktiskt utlöser omvänd skattskyldighet."""

    def test_byggmomskonto_ger_radflaggan_true(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient([KUND_FLAGGAD])
        utfor_utkast(klient, "kundfaktura", _nyttolast("Byggbolaget AB", "3231"))

        path, payload = klient.skickat[0]
        assert path == "/customerinvoicedrafts"
        assert payload["Rows"][0]["ReversedConstructionServicesVatFree"] is True

    def test_vanligt_konto_ger_radflaggan_false(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient([KUND_FLAGGAD])
        utfor_utkast(klient, "kundfaktura", _nyttolast("Byggbolaget AB", "3041"))

        payload = klient.skickat[0][1]
        assert payload["Rows"][0]["ReversedConstructionServicesVatFree"] is False

    def test_blandad_faktura_flaggar_bara_byggmomsraden(self):
        """En människa kan ha rättat kontot på en enskild rad i utkastvyn.
        Flaggan följer raden, inte fakturan."""
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient([KUND_FLAGGAD])
        utfor_utkast(klient, "kundfaktura", {
            "kundnamn": "Byggbolaget AB",
            "rader": [
                {"beskrivning": "Bygg", "pris": 1000, "antal": 1, "konto": "3231"},
                {"beskrivning": "Övrigt", "pris": 500, "antal": 1, "konto": "3041"},
            ],
            "fakturadatum": "2026-08-06", "forfallodatum": "2026-09-05",
        })

        rows = klient.skickat[0][1]["Rows"]
        assert rows[0]["ReversedConstructionServicesVatFree"] is True
        assert rows[1]["ReversedConstructionServicesVatFree"] is False


class TestKundkontrollen:
    """Spiris avvisar radflaggan med HTTP 400 för en oflaggad kund. Kontrollen
    före sändning ger ett begripligt besked i stället för ett nätverksfel."""

    def test_oflaggad_kund_vagras_och_inget_skickas(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _FakturaKlient([KUND_OFLAGGAD])
        with pytest.raises(SpirisKlientFel) as fel:
            utfor_utkast(
                klient, "kundfaktura", _nyttolast("Vanliga Bolaget AB", "3231")
            )

        assert klient.skickat == []
        # Beskedet måste säga VAD användaren ska göra, inte bara att det gick fel.
        assert "omvänd skattskyldighet" in str(fel.value)

    def test_oflaggad_kund_pavarkar_inte_vanliga_fakturor(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient([KUND_OFLAGGAD])
        utfor_utkast(
            klient, "kundfaktura", _nyttolast("Vanliga Bolaget AB", "3041")
        )

        assert klient.skickat[0][0] == "/customerinvoicedrafts"


class TestDirektbokforingVagras:
    """CustomerInvoiceRowApi saknar reverse-charge-fältet HELT. En
    direktbokförd byggmomsfaktura skulle ofrånkomligen få 25 % moms."""

    def test_byggmoms_kan_inte_direktbokforas(self):
        from spiris_adapter import MAL_BOKFOR, SpirisKlientFel, utfor_utkast

        klient = _FakturaKlient([KUND_FLAGGAD])
        with pytest.raises(SpirisKlientFel) as fel:
            utfor_utkast(
                klient, "kundfaktura",
                _nyttolast("Byggbolaget AB", "3231"), MAL_BOKFOR,
            )

        assert klient.skickat == []
        assert "utkast" in str(fel.value).lower()

    def test_vanlig_faktura_gar_fortfarande_att_direktbokfora(self):
        from spiris_adapter import MAL_BOKFOR, utfor_utkast

        klient = _FakturaKlient([KUND_FLAGGAD])
        utfor_utkast(
            klient, "kundfaktura",
            _nyttolast("Byggbolaget AB", "3041"), MAL_BOKFOR,
        )

        assert klient.skickat[0][0] == "/customerinvoices"


class TestPayloadbyggaren:
    def test_radantal_som_inte_gar_ihop_hojer_fel(self):
        """Kan raderna inte paras ihop går det inte att avgöra vilken som är
        byggmoms — och en gissning ger fel moms."""
        from spiris_adapter import bygg_kundfakturautkast_payload

        payload = {"CustomerId": "c1", "Rows": [{"ArticleId": "a1"}]}
        with pytest.raises(ValueError):
            bygg_kundfakturautkast_payload(
                payload, [{"kontonr": "3231"}, {"kontonr": "3041"}]
            )

    def test_utan_granskade_rader_behalls_gamla_beteendet(self):
        """Bakåtkompatibelt: anropare som inte skickar rader får False, precis
        som före R-15."""
        from spiris_adapter import bygg_kundfakturautkast_payload

        payload = {"CustomerId": "c1", "Rows": [{"ArticleId": "a1"}]}
        ut = bygg_kundfakturautkast_payload(payload)
        assert ut["Rows"][0]["ReversedConstructionServicesVatFree"] is False

    def test_uttryckligt_varde_skrivs_inte_over(self):
        from spiris_adapter import bygg_kundfakturautkast_payload

        payload = {"CustomerId": "c1", "Rows": [
            {"ArticleId": "a1", "ReversedConstructionServicesVatFree": True}
        ]}
        ut = bygg_kundfakturautkast_payload(payload, [{"kontonr": "3041"}])
        assert ut["Rows"][0]["ReversedConstructionServicesVatFree"] is True

    def test_beloppen_forblir_decimal(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient([KUND_FLAGGAD])
        utfor_utkast(klient, "kundfaktura", _nyttolast("Byggbolaget AB", "3231"))

        rad = klient.skickat[0][1]["Rows"][0]
        assert isinstance(rad["UnitPrice"], Decimal)
