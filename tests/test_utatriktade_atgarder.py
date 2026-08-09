"""test_utatriktade_atgarder.py — Steg 5: kundfakturans livscykelåtgärder.

Två av de fyra åtgärderna (mejla faktura, skicka betalningspåminnelse) är
UTÅTRIKTADE: de når en tredje man och kan inte kallas tillbaka. Steg 4:s
lösning — att låta skrivningen landa i en återkallelig utkastkö i Spiris —
finns inte här. Det finns ingen utkastform för "mejla".

Grinden är i stället MOTTAGARVISNING: `utfor_utkast` vägrar utföra en
utåtriktad åtgärd utan den mottagare en MÄNNISKA sett på skärmen.

Det är inte kosmetiskt. `EmailApi.Email` är VALFRITT i Spiris, och utelämnas
det mejlar Spiris till kundens registrerade adress — alltså till någon ingen
granskat. AI:n kan dessutom per konstruktion inte se adressen, eftersom
`hamta_kunder` (Steg 2) aldrig hämtar `EmailAddress`. Utan grinden hade
människan godkänt blint i fråga om mottagaren.

Ingen HTTP här: klienten injiceras som en fejk som fångar det som skulle
POSTas i stället för att skicka det.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

_FAKTURA = {
    "Id": "fak-1",
    "InvoiceNumber": 101,
    "CustomerId": "cus-1",
    "CustomerEmail": "faktura@kundbolaget.se",
    "CustomerName": "Kundbolaget AB",
    "TotalAmount": Decimal("1250.00"),
    "RemainingAmount": Decimal("1250.00"),
    "DueDate": "2026-08-31",
    "CurrencyCode": "SEK",
}


class _FakturaKlient:
    """Fångar POST:ar och svarar med kundfakturor på /customerinvoices."""

    def __init__(self, fakturor: list[dict] | None = None) -> None:
        self.skickat: list[tuple[str, dict]] = []
        self._fakturor = [dict(_FAKTURA)] if fakturor is None else fakturor

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/customerinvoices":
            return self._fakturor
        return []

    def skicka(self, path: str, data: dict) -> dict:
        self.skickat.append((path, data))
        return {"Id": "resultat-1"}


class TestMottagargrinden:
    """Grindens hela poäng: en utåtriktad åtgärd kan inte utföras utan en
    granskad mottagare, och ingenting lämnar datorn när den saknas."""

    def test_fakturautskick_utan_mottagare_skickar_ingenting(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _FakturaKlient()
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(klient, "fakturautskick", {"fakturanummer": "101"})

        assert klient.skickat == []

    def test_betalningspaminnelse_utan_mottagare_skickar_ingenting(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _FakturaKlient()
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(klient, "betalningspaminnelse", {"fakturanummer": "101"})

        assert klient.skickat == []

    @pytest.mark.parametrize("tom", ["", "   ", None])
    def test_tom_mottagare_raknas_som_ingen(self, tom):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _FakturaKlient()
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(
                klient, "fakturautskick", {"fakturanummer": "101"},
                granskad_mottagare=tom,
            )

        assert klient.skickat == []

    def test_mottagaren_satts_explicit_i_payloaden(self):
        """Det avgörande testet. Email får ALDRIG utelämnas och överlåtas åt
        Spiris standardvärde — då hade "det som visades" och "det som
        skickades" varit två oberoende uppslag mot ett register som kan ha
        ändrats däremellan."""
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient()
        utfor_utkast(
            klient, "fakturautskick", {"fakturanummer": "101"},
            granskad_mottagare="granskad@example.com",
        )

        path, payload = klient.skickat[0]
        assert path == "/customerinvoices/fak-1/email"
        assert payload["Email"] == "granskad@example.com"

    def test_paminnelsens_mottagare_ligger_i_emaildetails(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient()
        utfor_utkast(
            klient, "betalningspaminnelse", {"fakturanummer": "101"},
            granskad_mottagare="granskad@example.com",
        )

        path, payload = klient.skickat[0]
        assert path == "/customerinvoices/fak-1/paymentreminders"
        assert payload["EmailDetails"]["Email"] == "granskad@example.com"

    def test_grinden_galler_inte_icke_utatriktade_atgarder(self):
        """Makulering är oåterkallelig men når INGEN tredje man. Grinden ska
        inte gälla den — annars blir den en formalitet man lär sig kringgå."""
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient()
        utfor_utkast(klient, "makulering", {"fakturanummer": "101"})

        assert klient.skickat[0][0] == "/customerinvoices/fak-1/void"

    def test_betalningsregistrering_kraver_ingen_mottagare(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient()
        utfor_utkast(klient, "betalningsregistrering", {
            "fakturanummer": "101", "belopp": 1250.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][0] == "/customerinvoices/fak-1/payments"


class TestDrojsmalsavgift:
    def test_avgift_utelamnas_helt_nar_den_inte_angetts(self):
        """Noll och "ingen avgift" är olika saker mot Spiris. En avgift som
        smyger in i en påminnelse är ett anspråk mot kunden ingen bett om."""
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient()
        utfor_utkast(
            klient, "betalningspaminnelse", {"fakturanummer": "101"},
            granskad_mottagare="granskad@example.com",
        )

        assert "LatePaymentFee" not in klient.skickat[0][1]

    def test_angiven_avgift_foljer_med_som_decimal(self):
        from spiris_adapter import utfor_utkast

        klient = _FakturaKlient()
        utfor_utkast(
            klient, "betalningspaminnelse",
            {"fakturanummer": "101", "drojsmalsavgift": 60},
            granskad_mottagare="granskad@example.com",
        )

        avgift = klient.skickat[0][1]["LatePaymentFee"]
        assert avgift == Decimal("60")
        assert isinstance(avgift, Decimal)


class TestBetalningspayload:
    def test_full_betalning_nar_beloppet_tacker_kvarvarande(self):
        from spiris_adapter import BETALNING_FULLBETALNING, bygg_betalningspayload

        payload = bygg_betalningspayload(
            "bank-1", "2026-08-06", Decimal("1250"), "SEK", Decimal("1250")
        )
        assert payload["PaymentType"] == BETALNING_FULLBETALNING

    def test_delbetalning_nar_beloppet_ar_lagre(self):
        from spiris_adapter import BETALNING_DELBETALNING, bygg_betalningspayload

        payload = bygg_betalningspayload(
            "bank-1", "2026-08-06", Decimal("500"), "SEK", Decimal("1250")
        )
        assert payload["PaymentType"] == BETALNING_DELBETALNING

    def test_okant_kvarvarande_hojer_fel_i_stallet_for_att_gissa(self):
        """En delbetalning som felaktigt bokförs som fullbetalning stänger en
        fordran som fortfarande finns."""
        from spiris_adapter import bygg_betalningspayload

        with pytest.raises(ValueError):
            bygg_betalningspayload(
                "bank-1", "2026-08-06", Decimal("500"), "SEK", None
            )

    def test_beloppet_forblir_decimal(self):
        from spiris_adapter import bygg_betalningspayload

        payload = bygg_betalningspayload(
            "bank-1", "2026-08-06", Decimal("1250.50"), "SEK", Decimal("2000")
        )
        assert isinstance(payload["PaymentAmount"], Decimal)

    def test_kreditfaktura_med_negativt_restbelopp(self):
        """En kundKREDITfaktura har negativt RemainingAmount (sandbox-mätt
        2026-08-06: faktura 1005, Remaining −10 940). Jämförelsen sker därför
        på beloppens STORLEK, inte på deras tecken."""
        from spiris_adapter import BETALNING_DELBETALNING, bygg_betalningspayload

        payload = bygg_betalningspayload(
            "bank-1", "2026-08-06", Decimal("5000"), "SEK", Decimal("-10940")
        )
        assert payload["PaymentType"] == BETALNING_DELBETALNING


class TestFakturauppslag:
    def test_okant_fakturanummer_hojer_fel(self):
        from spiris_adapter import SpirisKlientFel, hamta_utskicksgranskning

        with pytest.raises(SpirisKlientFel):
            hamta_utskicksgranskning(_FakturaKlient(fakturor=[]), "999")

    def test_flera_traffar_hojer_fel_i_stallet_for_att_valja(self):
        """Att mejla eller makulera FEL faktura är värre än att inte göra
        något alls."""
        from spiris_adapter import SpirisKlientFel, hamta_utskicksgranskning

        dubbletter = [dict(_FAKTURA), dict(_FAKTURA, Id="fak-2")]
        with pytest.raises(SpirisKlientFel):
            hamta_utskicksgranskning(_FakturaKlient(fakturor=dubbletter), "101")

    def test_saknad_epostadress_ar_tom_strang_inte_fel(self):
        """Ett giltigt tillstånd som godkännandevyn ska visa — och som grinden
        sedan vägrar skicka på."""
        from spiris_adapter import hamta_utskicksgranskning

        utan = [dict(_FAKTURA, CustomerEmail=None)]
        granskning = hamta_utskicksgranskning(_FakturaKlient(fakturor=utan), "101")
        assert granskning["mottagare"] == ""


class TestSkrivfunktionerNarAldrigEgressvagen:
    """RISKREGISTER R-13 påstår att MCP-servern "inte ens refererar
    skrivfunktionerna". Fram till Steg 5 fanns inget test som bevakade det.

    Steg 5 gör bevakningen viktigare: `hamta_utskicksgranskning` returnerar
    MEDVETET en e-postadress och ett omaskerat kundnamn, och finns bara för
    den lokala godkännandevyn i Streamlit. Nås den från MCP-servern eller
    egressomslaget läcker precis det som `hamta_kunder` är byggd för att
    aldrig hämta.

    Testet läser modulernas IMPORTER via AST i stället för att söka i texten:
    docstrings och kommentarer får nämna funktionerna (det gör de, med flit),
    men ingen av dem får vara importerad och därmed anropbar."""

    FORBJUDNA = frozenset({
        "hamta_utskicksgranskning",
        "skicka_faktura_epost",
        "skicka_betalningspaminnelse",
        "registrera_betalning",
        "makulera_faktura",
        "bygg_betalningspayload",
        "utfor_utkast",
        "skapa_kund",
        "skapa_kundfaktura",
        "skapa_verifikat",
        "skapa_verifikatutkast",
        "skapa_kundfakturautkast",
    })

    @staticmethod
    def _importerade_namn(sokvag: Path) -> set[str]:
        trad = ast.parse(sokvag.read_text(encoding="utf-8"))
        namn: set[str] = set()
        for nod in ast.walk(trad):
            if isinstance(nod, ast.ImportFrom):
                namn.update(alias.name for alias in nod.names)
            elif isinstance(nod, ast.Import):
                namn.update(alias.name for alias in nod.names)
        return namn

    @pytest.mark.parametrize(
        "modul", ["mcp_server/server.py", "parser/spiris_rag.py"]
    )
    def test_ingen_skrivfunktion_ar_importerad(self, modul):
        rot = Path(__file__).resolve().parent.parent
        importerade = self._importerade_namn(rot / modul)

        overtramp = importerade & self.FORBJUDNA
        assert not overtramp, (
            f"{modul} importerar skrivfunktioner: {sorted(overtramp)}"
        )

    def test_testet_skulle_faktiskt_faila(self):
        """Metatest: kontrollerar att detektorn hittar en import när den finns.
        Utan detta kunde AST-vandringen tyst sluta fungera och testet ovan bli
        grönt av fel skäl."""
        rot = Path(__file__).resolve().parent.parent
        importerade = self._importerade_namn(rot / "parser/rum_render.py")

        # rum_render ÄR den lokala godkännandevyn och SKA importera dem.
        assert "utfor_utkast" in importerade
        assert "hamta_granskad_mottagare" in importerade


# --- Steg 5b: offert- och orderkedjan --------------------------------------

_OFFERT = {"Id": "off-1", "Number": 5, "CustomerId": "cus-1",
           "CustomerName": "Kundbolaget AB", "Status": 1}
_ORDER = {"Id": "ord-1", "Number": 7, "CustomerId": "cus-1",
          "CustomerName": "Kundbolaget AB", "Status": 2}


class _SaljKlient:
    """Fejk som svarar för offerter, ordrar, kunder och e-fakturamottagare.
    Registrerar både POST och PUT, så testerna kan skilja verben åt."""

    def __init__(self, kund=None, efakturamottagare=None) -> None:
        self.skickat: list[tuple[str, dict]] = []
        self.uppdaterat: list[tuple[str, dict]] = []
        self._kund = {"EmailAddress": "offert@kundbolaget.se"} if kund is None else kund
        self._efaktura = efakturamottagare

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/quotes":
            return [dict(_OFFERT)]
        if path == "/orders":
            return [dict(_ORDER)]
        if path == "/customerinvoices":
            return [dict(_FAKTURA)]
        if path.endswith("/autoinvoicerecipients"):
            return self._efaktura or []
        return []

    def hamta_en(self, path: str, params: dict | None = None) -> dict:
        if path.startswith("/customers/"):
            return self._kund
        raise AssertionError(f"oväntad hamta_en: {path}")

    def skicka(self, path: str, data: dict) -> dict:
        self.skickat.append((path, data))
        return {"Id": "resultat-1"}

    def uppdatera(self, path: str, data: dict) -> dict:
        self.uppdaterat.append((path, data))
        return {"Id": "resultat-1"}


class TestSaljdokumentutskick:
    """Offert och order bär INGEN e-postadress i Spiris (till skillnad från en
    kundfaktura, som har CustomerEmail). Mottagaren måste därför slås upp via
    dokumentets CustomerId mot /customers — men grinden är densamma."""

    def test_utskick_utan_mottagare_skickar_ingenting(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _SaljKlient()
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(
                klient, "saljdokumentutskick",
                {"dokumenttyp": "offert", "nummer": "5"},
            )

        assert klient.skickat == []

    def test_mottagaren_hamtas_via_kunden(self):
        from spiris_adapter import hamta_saljdokumentgranskning

        granskning = hamta_saljdokumentgranskning(_SaljKlient(), "offert", "5")

        assert granskning["mottagare"] == "offert@kundbolaget.se"
        assert granskning["dokument_id"] == "off-1"

    def test_kund_utan_epost_ger_tom_mottagare(self):
        from spiris_adapter import hamta_saljdokumentgranskning

        klient = _SaljKlient(kund={"EmailAddress": None})
        assert hamta_saljdokumentgranskning(klient, "offert", "5")["mottagare"] == ""

    @pytest.mark.parametrize(
        "dokumenttyp,vantad_path",
        [("offert", "/quotes/off-1/email"), ("order", "/orders/ord-1/email")],
    )
    def test_mottagaren_satts_explicit(self, dokumenttyp, vantad_path):
        from spiris_adapter import utfor_utkast

        klient = _SaljKlient()
        utfor_utkast(
            klient, "saljdokumentutskick",
            {"dokumenttyp": dokumenttyp, "nummer": "5" if dokumenttyp == "offert" else "7"},
            granskad_mottagare="granskad@example.com",
        )

        path, payload = klient.skickat[0]
        assert path == vantad_path
        assert payload["Email"] == "granskad@example.com"

    def test_okand_dokumenttyp_hojer_fel(self):
        from spiris_adapter import SpirisKlientFel, hamta_saljdokumentgranskning

        with pytest.raises(SpirisKlientFel):
            hamta_saljdokumentgranskning(_SaljKlient(), "fakturaunderlag", "5")


class TestOnumreradeSaljdokument:
    """Sandbox-fynd 2026-08-06: `Number` är None på 3 av 5 offerter/ordrar i
    ett riktigt bolag — Spiris tilldelar numret först i ett senare skede.

    Slog uppslaget bara på nummer var ett onumrerat dokument omöjligt att
    adressera, och Steg 5b:s åtgärder oåtkomliga för just de dokument som
    oftast behöver dem: en offert som ännu inte skickats."""

    class _OnumreradKlient(_SaljKlient):
        def hamta_alla(self, path, params=None):
            if path == "/quotes":
                return [
                    {"Id": "off-utan-nr", "Number": None, "CustomerId": "cus-1",
                     "CustomerName": "Kundbolaget AB", "Status": 0},
                    {"Id": "off-2", "Number": 2, "CustomerId": "cus-1",
                     "CustomerName": "Kundbolaget AB", "Status": 1},
                ]
            return super().hamta_alla(path, params)

    def test_onumrerad_offert_gar_att_adressera_med_id(self):
        from spiris_adapter import hamta_saljdokumentgranskning

        granskning = hamta_saljdokumentgranskning(
            self._OnumreradKlient(), "offert", "off-utan-nr"
        )
        assert granskning["dokument_id"] == "off-utan-nr"
        assert granskning["nummer"] == ""

    def test_nummer_fungerar_fortfarande(self):
        from spiris_adapter import hamta_saljdokumentgranskning

        granskning = hamta_saljdokumentgranskning(
            self._OnumreradKlient(), "offert", "2"
        )
        assert granskning["dokument_id"] == "off-2"

    def test_tom_sokstrang_matchar_ingenting(self):
        """Utan den här kontrollen hade en tom sträng matchat VARJE onumrerat
        dokument, och tvetydighetskontrollen varit enda skyddet."""
        from spiris_adapter import SpirisKlientFel, hamta_saljdokumentgranskning

        with pytest.raises(SpirisKlientFel):
            hamta_saljdokumentgranskning(self._OnumreradKlient(), "offert", "  ")

    def test_saljdokumentlistan_bar_id(self):
        """hamta_offerter/hamta_order måste exponera `id`, annars har en
        AI-klient ingen väg att få tag i det värde som krävs ovan."""
        from spiris_adapter import hamta_offerter

        rader = hamta_offerter(self._OnumreradKlient())
        assert all("id" in rad for rad in rader)
        assert rader[0]["id"] == "off-utan-nr"


class TestEfakturautskick:
    """En e-faktura går inte till en e-postadress utan till en registrerad
    AutoInvoice-mottagare. Grinden är densamma — det som visas är "Namn
    (elektronisk adress)"."""

    def test_utan_registrerad_mottagare_skickas_ingenting(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _SaljKlient(efakturamottagare=[])
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(klient, "efakturautskick", {"fakturanummer": "101"})

        assert klient.skickat == []

    def test_mottagaren_bygger_pa_namn_och_elektronisk_adress(self):
        from spiris_adapter import hamta_efakturagranskning

        klient = _SaljKlient(efakturamottagare=[
            {"Name": "Kundbolaget AB", "ElectronicAddress": "7365567778899"}
        ])
        granskning = hamta_efakturagranskning(klient, "101")

        assert granskning["mottagare"] == "Kundbolaget AB (7365567778899)"

    def test_sandtyp_ar_elektronisk(self):
        from spiris_adapter import EFAKTURA_ELEKTRONISK, utfor_utkast

        klient = _SaljKlient(efakturamottagare=[
            {"Name": "Kundbolaget AB", "ElectronicAddress": "7365567778899"}
        ])
        utfor_utkast(
            klient, "efakturautskick", {"fakturanummer": "101"},
            granskad_mottagare="Kundbolaget AB (7365567778899)",
        )

        path, payload = klient.skickat[0]
        assert path == "/customerinvoices/fak-1/einvoice"
        assert payload["SendType"] == EFAKTURA_ELEKTRONISK


class TestSaljdokumentatgarder:
    """Kedjeåtgärderna når ingen tredje man, men ändrar dokumentens tillstånd
    oåterkalleligt — en konverterad offert kan inte konverteras tillbaka."""

    def test_godkann_anvander_put_inte_post(self):
        """/quotes/{id}/accept är PUT. Det är också det första stället i
        kodbasen som faktiskt använder klientens PUT, som tillkom i Steg 1 och
        varit oanvänd sedan dess."""
        from spiris_adapter import utfor_utkast

        klient = _SaljKlient()
        utfor_utkast(klient, "saljdokumentatgard", {
            "dokumenttyp": "offert", "nummer": "5", "atgard": "godkann",
        })

        assert klient.uppdaterat[0][0] == "/quotes/off-1/accept"
        assert klient.skickat == []  # ingen POST

    def test_till_order_begar_riktig_order_inte_orderutkast(self):
        """QuoteConversionApi.Type: 0 = OrderDraft, 1 = Order. Vi skapar en
        riktig order — annars vore åtgärdens namn missvisande."""
        from spiris_adapter import utfor_utkast

        klient = _SaljKlient()
        utfor_utkast(klient, "saljdokumentatgard", {
            "dokumenttyp": "offert", "nummer": "5", "atgard": "till_order",
        })

        path, payload = klient.skickat[0]
        assert path == "/quotes/off-1/converttoorder"
        assert payload["Type"] == 1

    @pytest.mark.parametrize(
        "dokumenttyp,nummer,atgard,vantad_path",
        [
            ("offert", "5", "till_faktura", "/quotes/off-1/converttocustomerinvoice"),
            ("order", "7", "till_faktura", "/orders/ord-1/convert"),
            ("order", "7", "slutford", "/orders/ord-1/completed"),
            ("order", "7", "makulerad", "/orders/ord-1/voided"),
        ],
    )
    def test_atgard_gar_till_ratt_sokvag(
        self, dokumenttyp, nummer, atgard, vantad_path
    ):
        from spiris_adapter import utfor_utkast

        klient = _SaljKlient()
        utfor_utkast(klient, "saljdokumentatgard", {
            "dokumenttyp": dokumenttyp, "nummer": nummer, "atgard": atgard,
        })

        assert klient.skickat[0][0] == vantad_path

    def test_okand_kombination_gissas_aldrig(self):
        """Att slutföra en OFFERT finns inte. Kombinationen ska höja fel, inte
        falla tillbaka på närmaste träff."""
        from spiris_adapter import SpirisKlientFel, utfor_saljdokumentatgard

        with pytest.raises(SpirisKlientFel):
            utfor_saljdokumentatgard(_SaljKlient(), "offert", "off-1", "slutford")

    def test_ingen_atgard_skickas_vid_okand_kombination(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _SaljKlient()
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(klient, "saljdokumentatgard", {
                "dokumenttyp": "order", "nummer": "7", "atgard": "godkann",
            })

        assert klient.skickat == [] and klient.uppdaterat == []


class TestGranskadMottagareDirigering:
    def test_varje_utatriktad_typ_har_en_granskningsvag(self):
        """Metatest: läggs en ny typ i UTATRIKTADE_TYPER utan att
        hamta_granskad_mottagare kan hantera den, blir det rött här i stället
        för ett fel först vid ett verkligt godkännande."""
        from spiris_adapter import UTATRIKTADE_TYPER, hamta_granskad_mottagare

        nyttolaster = {
            "fakturautskick": {"fakturanummer": "101"},
            "betalningspaminnelse": {"fakturanummer": "101"},
            "saljdokumentutskick": {"dokumenttyp": "offert", "nummer": "5"},
            "efakturautskick": {"fakturanummer": "101"},
        }
        assert set(nyttolaster) == set(UTATRIKTADE_TYPER)

        klient = _SaljKlient(efakturamottagare=[
            {"Name": "K", "ElectronicAddress": "1"}
        ])
        for typ, nyttolast in nyttolaster.items():
            assert isinstance(hamta_granskad_mottagare(klient, typ, nyttolast), str)

    def test_icke_utatriktad_typ_hojer_fel(self):
        from spiris_adapter import SpirisKlientFel, hamta_granskad_mottagare

        with pytest.raises(SpirisKlientFel):
            hamta_granskad_mottagare(_SaljKlient(), "makulering", {})


class TestAtgardstabellerIsynk:
    def test_saljdokumentatgarder_ar_i_takt(self):
        """MCP-servern får inte importera spiris_adapter (arkitekturregel), så
        listan över giltiga kombinationer är dubblerad i server.py. Det här
        testet är det enda som hindrar kopiorna från att glida isär."""
        from mcp_server.server import GILTIGA_SALJDOKUMENTATGARDER
        from spiris_adapter import _SALJDOKUMENTATGARDER

        assert GILTIGA_SALJDOKUMENTATGARDER == set(_SALJDOKUMENTATGARDER)
