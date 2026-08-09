"""test_masterdata.py — Steg 7: ändring och borttagning av registerobjekt.

Sandbox-mätt 2026-08-06, på en egen testkund som skapades och raderades:

    PUT med bara Id + Name              -> HTTP 400 (obligatoriska fält krävs)
    PUT med alla OBLIGATORISKA fält     -> accepterad, men EmailAddress,
                                           InvoiceAddress1, Telephone och Note
                                           blev None

**PUT nollar alltså utelämnade fält.** Det gör read-modify-write obligatoriskt,
och kopplar ihop med kodbasens integritetsdesign på ett skarpt sätt:
`hamta_kunder` hämtar med flit ALDRIG e-post, telefon eller adress, så en AI
kan inte förse oss med dem. En naiv uppdatering hade därför raderat precis de
fält AI:n aldrig fick läsa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

_KUND = {
    "Id": "cus-1",
    "Name": "Kundbolaget AB",
    "IsActive": True,
    "IsPrivatePerson": False,
    "CurrencyCode": "SEK",
    "TermsOfPaymentId": "villkor-1",
    "InvoiceCity": "Storstad",
    "InvoicePostalCode": "12345",
    # Fälten nedan når ALDRIG en AI (hamta_kunder hämtar dem inte) och måste
    # ändå överleva en uppdatering.
    "EmailAddress": "faktura@kundbolaget.se",
    "Telephone": "0700000000",
    "InvoiceAddress1": "Storgatan 1",
    "Note": "Viktig kund",
    "ReverseChargeOnConstructionServices": False,
}


class _MasterdataKlient:
    def __init__(self, objekt: dict | None = None) -> None:
        self.uppdaterat: list[tuple[str, dict]] = []
        self.borttaget: list[str] = []
        self._objekt = dict(objekt or _KUND)

    def hamta_en(self, path: str, params: dict | None = None) -> dict:
        return dict(self._objekt)

    def uppdatera(self, path: str, data: dict) -> dict:
        self.uppdaterat.append((path, data))
        return {"Id": self._objekt.get("Id")}

    def ta_bort(self, path: str) -> None:
        self.borttaget.append(path)


class TestReadModifyWrite:
    """Kärnan i Steg 7: hela objektet skrivs tillbaka, inte bara ändringen."""

    def test_ofragade_falt_overlever_en_namnandring(self):
        from spiris_adapter import andra_masterdata

        klient = _MasterdataKlient()
        andra_masterdata(klient, "kund", "cus-1", {"namn": "Nytt Namn AB"})

        _, payload = klient.uppdaterat[0]
        assert payload["Name"] == "Nytt Namn AB"
        # Det avgörande: fälten AI:n aldrig såg finns kvar.
        assert payload["EmailAddress"] == "faktura@kundbolaget.se"
        assert payload["Telephone"] == "0700000000"
        assert payload["InvoiceAddress1"] == "Storgatan 1"
        assert payload["Note"] == "Viktig kund"

    def test_obligatoriska_falt_foljer_med(self):
        """En PUT utan dem avvisas med 400 — mätt mot sandbox."""
        from spiris_adapter import andra_masterdata

        klient = _MasterdataKlient()
        andra_masterdata(klient, "kund", "cus-1", {"namn": "Nytt Namn AB"})

        payload = klient.uppdaterat[0][1]
        for falt in ("IsActive", "IsPrivatePerson", "InvoiceCity",
                     "InvoicePostalCode", "TermsOfPaymentId"):
            assert falt in payload

    def test_ratt_sokvag(self):
        from spiris_adapter import andra_masterdata

        klient = _MasterdataKlient()
        andra_masterdata(klient, "kund", "cus-1", {"namn": "X"})

        assert klient.uppdaterat[0][0] == "/customers/cus-1"

    def test_flera_falt_i_samma_andring(self):
        from spiris_adapter import andra_masterdata

        klient = _MasterdataKlient()
        andra_masterdata(klient, "kund", "cus-1", {
            "namn": "Nytt AB", "aktiv": False, "valuta": "EUR",
        })

        payload = klient.uppdaterat[0][1]
        assert payload["Name"] == "Nytt AB"
        assert payload["IsActive"] is False
        assert payload["CurrencyCode"] == "EUR"


class TestAndringsallowlisten:
    """Lika viktig som läsallowlisten: utan den kunde ett AI-förslag sätta
    vilket fält som helst i ett objekt människan bara ombetts godkänna en
    namnändring på."""

    def test_okant_falt_vagras(self):
        from spiris_adapter import SpirisKlientFel, andra_masterdata

        klient = _MasterdataKlient()
        with pytest.raises(SpirisKlientFel) as fel:
            andra_masterdata(
                klient, "kund", "cus-1", {"epost": "ny@example.com"}
            )

        assert klient.uppdaterat == []
        assert "epost" in str(fel.value)

    def test_falt_fran_en_annan_objekttyp_vagras(self):
        """`land` finns på kund men heter olika på leverantör — och `pris`
        hör inte hemma på någon av dem."""
        from spiris_adapter import SpirisKlientFel, andra_masterdata

        klient = _MasterdataKlient()
        with pytest.raises(SpirisKlientFel):
            andra_masterdata(klient, "kund", "cus-1", {"pris": 100})

        assert klient.uppdaterat == []

    def test_okand_objekttyp_vagras(self):
        from spiris_adapter import SpirisKlientFel, andra_masterdata

        with pytest.raises(SpirisKlientFel):
            andra_masterdata(
                _MasterdataKlient(), "verifikat", "v-1", {"namn": "X"}
            )

    def test_tomma_andringar_vagras(self):
        from spiris_adapter import andra_masterdata

        with pytest.raises(ValueError):
            andra_masterdata(_MasterdataKlient(), "kund", "cus-1", {})

    def test_byggmomsflaggan_gar_att_satta_nar_momsnummer_finns(self):
        """R-15: byggmoms kräver att kunden är flaggad. Utan den här nyckeln
        gick flaggan bara att sätta manuellt i Spiris."""
        from spiris_adapter import andra_masterdata

        klient = _MasterdataKlient(dict(_KUND, VatNumber="SE556677889901"))
        andra_masterdata(klient, "kund", "cus-1", {"omvand_byggmoms": True})

        payload = klient.uppdaterat[0][1]
        assert payload["ReverseChargeOnConstructionServices"] is True

    def test_byggmomsflaggan_kraver_momsregistreringsnummer(self):
        """Sandbox-mätt 2026-08-06: Spiris avvisar med "VatNumber can not be
        null or empty when using ReverseChargeOnConstructionServices".

        Kontrollen finns för att göra det svaret begripligt — utan den fick
        användaren ett naket HTTP 400 på en åtgärd som ser trivial ut."""
        from spiris_adapter import SpirisKlientFel, andra_masterdata

        klient = _MasterdataKlient()  # _KUND saknar VatNumber
        with pytest.raises(SpirisKlientFel) as fel:
            andra_masterdata(klient, "kund", "cus-1", {"omvand_byggmoms": True})

        assert klient.uppdaterat == []
        assert "momsregistreringsnummer" in str(fel.value)

    def test_vatnummer_gar_inte_att_andra(self):
        """För en enskild firma är momsregistreringsnumret härlett ur
        innehavarens personnummer. Ett AI-förslag ska inte skriva in en sådan
        identifierare — den hör hemma i Spiris egna kundformulär."""
        from spiris_adapter import SpirisKlientFel, andra_masterdata

        klient = _MasterdataKlient()
        with pytest.raises(SpirisKlientFel):
            andra_masterdata(
                klient, "kund", "cus-1", {"vatnummer": "SE556677889901"}
            )

        assert klient.uppdaterat == []


class TestBorttagning:
    def test_kund_gar_att_ta_bort(self):
        from spiris_adapter import utfor_utkast

        klient = _MasterdataKlient()
        utfor_utkast(klient, "masterdataborttagning", {
            "objekttyp": "kund", "objekt_id": "cus-1",
            "motivering": "Dubblett",
        })

        assert klient.borttaget == ["/customers/cus-1"]

    @pytest.mark.parametrize("objekttyp", ["artikel", "projekt"])
    def test_objekt_utan_delete_vagras_med_alternativ(self, objekttyp):
        """Artiklar och projekt saknar DELETE i Spiris. Beskedet ska säga vad
        användaren kan göra i stället, inte bara att det inte går."""
        from spiris_adapter import SpirisKlientFel, ta_bort_masterdata

        klient = _MasterdataKlient()
        with pytest.raises(SpirisKlientFel) as fel:
            ta_bort_masterdata(klient, objekttyp, "id-1")

        assert klient.borttaget == []
        assert "aktiv" in str(fel.value).lower()

    def test_okand_objekttyp_vagras(self):
        from spiris_adapter import SpirisKlientFel, ta_bort_masterdata

        with pytest.raises(SpirisKlientFel):
            ta_bort_masterdata(_MasterdataKlient(), "verifikat", "v-1")


class TestPayloadbyggaren:
    def test_ren_funktion_ror_inte_indatat(self):
        from spiris_adapter import bygg_masterdatauppdatering

        nuvarande = dict(_KUND)
        bygg_masterdatauppdatering(nuvarande, {"namn": "Ändrat"}, "kund")

        assert nuvarande["Name"] == "Kundbolaget AB"

    def test_artikelpris_forblir_decimal(self):
        from spiris_adapter import bygg_masterdatauppdatering

        artikel = {"Id": "art-1", "Name": "Konsult", "NetPrice": Decimal("800")}
        ut = bygg_masterdatauppdatering(
            artikel, {"pris": Decimal("900")}, "artikel"
        )

        assert ut["NetPrice"] == Decimal("900")
        assert isinstance(ut["NetPrice"], Decimal)


class TestArtikelnsId:
    def test_artikellistan_bar_id(self):
        """Fjärde gången samma felklass — efter hamta_bankkonton (Steg 3),
        hamta_offerter (sandbox) och hamta_leverantorsfakturor (Steg 6). Utan
        id går artikeln inte att adressera för en ändring."""
        from spiris_adapter import hamta_artiklar

        class _ArtikelKlient:
            def hamta_alla(self, path, params=None):
                if path == "/articles":
                    return [{"Id": "art-1", "Number": "300",
                             "Name": "Konsulttimme", "NetPrice": Decimal("900")}]
                if path == "/articleaccountcodings":
                    return []
                return []

        rader = hamta_artiklar(_ArtikelKlient())
        assert rader[0]["id"] == "art-1"


class TestTabellerIsynk:
    def test_masterdatafalten_ar_i_takt(self):
        """MCP-servern får inte importera spiris_adapter, så listan över
        ändringsbara fält är dubblerad i server.py. Det här testet är det enda
        som hindrar kopiorna från att glida isär."""
        from mcp_server.server import GILTIGA_MASTERDATAFALT
        from spiris_adapter import _MASTERDATA

        adapterns = {
            typ: frozenset(allowlist)
            for typ, (_prefix, allowlist) in _MASTERDATA.items()
        }
        assert GILTIGA_MASTERDATAFALT == adapterns

    def test_borttagbara_ar_i_takt(self):
        from mcp_server.server import BORTTAGBARA_MASTERDATA
        from spiris_adapter import _BORTTAGBARA

        assert BORTTAGBARA_MASTERDATA == _BORTTAGBARA
