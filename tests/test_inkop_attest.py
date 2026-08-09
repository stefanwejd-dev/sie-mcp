"""test_inkop_attest.py — Steg 6: inköp och attest.

Tre åtgärder, ingen av dem utåtriktad — med ETT undantag som därför prövas
särskilt: `ApprovalApi` bär `RejectionMessage` och
`RejectionMessageReceivers`, så ett avslag KAN skicka ett meddelande till
namngivna mottagare. Adaptern fyller aldrig i de fälten. Ett avslag härifrån
är en statusändring, inte ett utskick.

Leverantörsfakturor går till `/supplierinvoicedrafts` av samma skäl som
kundfakturor sedan Steg 4: utkastet är ändringsbart och borttagbart, och
befordras av människan. `/convert` anropas aldrig.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

_LEVFAKTURA = {
    "Id": "levfak-1",
    "InvoiceNumber": "L-1001",
    "SupplierId": "lev-1",
    "SupplierName": "Byggvaruhuset AB",
    "TotalAmount": Decimal("2500.00"),
    "RemainingAmount": Decimal("2500.00"),
    "CurrencyCode": "SEK",
    "DueDate": "2026-09-01",
}


class _LevKlient:
    """Fångar POST och PUT var för sig, så testerna kan skilja verben åt."""

    def __init__(self, fakturor: list[dict] | None = None) -> None:
        self.skickat: list[tuple[str, dict]] = []
        self.uppdaterat: list[tuple[str, dict]] = []
        self._fakturor = [dict(_LEVFAKTURA)] if fakturor is None else fakturor

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/supplierinvoices":
            return self._fakturor
        if path == "/suppliers":
            return [{"Id": "lev-1", "Name": "Byggvaruhuset AB",
                     "CorporateIdentityNumber": "556677-8899"}]
        return []

    def skicka(self, path: str, data: dict) -> dict:
        self.skickat.append((path, data))
        return {"Id": "skapad-1"}

    def uppdatera(self, path: str, data: dict) -> dict:
        self.uppdaterat.append((path, data))
        return {"Id": "uppdaterad-1"}


class TestLeverantorsfakturautkast:
    def test_gar_till_utkastkon_inte_till_skarp_faktura(self):
        from spiris_adapter import utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "leverantorsfakturautkast", {
            "leverantor_id": "lev-1",
            "rader": [{"konto": "4010", "debet": 2000, "kredit": 0, "text": "Virke"},
                      {"konto": "2440", "debet": 0, "kredit": 2000, "text": ""}],
            "fakturanummer": "L-1001",
            "totalbelopp": 2000,
        })

        path, payload = klient.skickat[0]
        assert path == "/supplierinvoicedrafts"
        assert payload["SupplierId"] == "lev-1"
        assert payload["IsCreditInvoice"] is False
        assert len(payload["Rows"]) == 2

    def test_raderna_konteras_mot_konton_inte_artiklar(self):
        """En leverantörsfaktura konteras rad för rad — till skillnad från en
        kundfaktura, som konteras via artikelns kodning."""
        from spiris_adapter import bygg_leverantorsfakturautkast_payload

        payload = bygg_leverantorsfakturautkast_payload(
            "lev-1", [{"konto": "4010", "debet": 2000, "kredit": 0}],
            totalbelopp=Decimal("2000"),
        )
        rad = payload["Rows"][0]
        assert rad["AccountNumber"] == 4010
        assert "ArticleId" not in rad
        assert isinstance(rad["DebitAmount"], Decimal)

    def test_ocr_nummer_skickas_aldrig(self):
        """OCR är en betalningsidentifierare — samma resonemang som bankgiro
        i hamta_bankkonton."""
        from spiris_adapter import bygg_leverantorsfakturautkast_payload

        payload = bygg_leverantorsfakturautkast_payload(
            "lev-1", [{"konto": "4010", "debet": 100}],
            fakturanummer="L-1", fakturadatum="2026-08-06",
            totalbelopp=Decimal("100"),
        )
        assert "OcrNumber" not in payload

    def test_utan_rader_hojer_fel(self):
        from spiris_adapter import bygg_leverantorsfakturautkast_payload

        with pytest.raises(ValueError):
            bygg_leverantorsfakturautkast_payload(
                "lev-1", [], totalbelopp=Decimal("100")
            )

    def test_utan_totalbelopp_hojer_fel(self):
        """Sandbox-mätt 2026-08-06: Spiris avvisar med "The amount on standard
        account 2440, recievables is not equal with TotalAmountBaseCurrency".
        Schemat påstår att fältet är valfritt; verkligheten säger annat."""
        from spiris_adapter import bygg_leverantorsfakturautkast_payload

        with pytest.raises(ValueError) as fel:
            bygg_leverantorsfakturautkast_payload(
                "lev-1", [{"konto": "4010", "debet": 100}]
            )
        assert "totalbelopp" in str(fel.value)

    def test_radnumren_ar_explicita_och_borjar_pa_ett(self):
        """Utan LineNumber numrerar Spiris raderna 0,1; med det behålls 1,2."""
        from spiris_adapter import bygg_leverantorsfakturautkast_payload

        payload = bygg_leverantorsfakturautkast_payload(
            "lev-1",
            [{"konto": "4010", "debet": 100}, {"konto": "2440", "kredit": 100}],
            totalbelopp=Decimal("100"),
        )
        assert [r["LineNumber"] for r in payload["Rows"]] == [1, 2]

    def test_utan_leverantor_hojer_fel(self):
        from spiris_adapter import bygg_leverantorsfakturautkast_payload

        with pytest.raises(ValueError):
            bygg_leverantorsfakturautkast_payload(
                "", [{"konto": "4010", "debet": 100}]
            )


class TestAttest:
    """Attest är ett ansvarstagande, inte en gissning — därför fail-closed på
    både okänd objekttyp och okänt beslut."""

    def test_godkannande_av_leverantorsfaktura(self):
        from spiris_adapter import ATTEST_GODKANN, utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "attest", {
            "objekttyp": "leverantorsfaktura", "objekt": "L-1001",
            "beslut": "godkann",
        })

        path, payload = klient.uppdaterat[0]
        assert path == "/approval/supplierinvoice/levfak-1"
        assert payload["DocumentApprovalStatus"] == ATTEST_GODKANN

    def test_attest_anvander_put_inte_post(self):
        from spiris_adapter import utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "attest", {
            "objekttyp": "leverantorsfaktura", "objekt": "L-1001",
            "beslut": "godkann",
        })

        assert klient.skickat == []  # ingen POST

    def test_momsrapport_adresseras_med_id_direkt(self):
        from spiris_adapter import utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "attest", {
            "objekttyp": "momsrapport", "objekt": "moms-42", "beslut": "godkann",
        })

        assert klient.uppdaterat[0][0] == "/approval/vatreport/moms-42"

    def test_avslag_komponerar_aldrig_ett_meddelande(self):
        """ApprovalApi kan skicka RejectionMessage till
        RejectionMessageReceivers. Ett avslag härifrån är en statusändring,
        inte ett utskick — den här modulen skriver aldrig ett meddelande till
        en människa."""
        from spiris_adapter import ATTEST_AVSLA, utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "attest", {
            "objekttyp": "leverantorsfaktura", "objekt": "L-1001",
            "beslut": "avsla",
        })

        payload = klient.uppdaterat[0][1]
        assert payload["DocumentApprovalStatus"] == ATTEST_AVSLA
        assert "RejectionMessage" not in payload
        assert "RejectionMessageReceivers" not in payload
        assert set(payload) == {"DocumentApprovalStatus"}

    def test_okand_objekttyp_gissas_aldrig(self):
        from spiris_adapter import SpirisKlientFel, attestera

        with pytest.raises(SpirisKlientFel):
            attestera(_LevKlient(), "kundfaktura", "id-1", "godkann")

    def test_okant_beslut_gissas_aldrig(self):
        from spiris_adapter import SpirisKlientFel, attestera

        with pytest.raises(SpirisKlientFel):
            attestera(_LevKlient(), "leverantorsfaktura", "id-1", "kanske")

    def test_inget_skickas_vid_okant_beslut(self):
        from spiris_adapter import SpirisKlientFel, attestera

        klient = _LevKlient()
        with pytest.raises(SpirisKlientFel):
            attestera(klient, "leverantorsfaktura", "id-1", "godkänn")

        assert klient.uppdaterat == [] and klient.skickat == []


class TestLeverantorsbetalning:
    def test_betalning_gar_till_ratt_faktura(self):
        from spiris_adapter import utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "leverantorsbetalning", {
            "faktura": "L-1001", "belopp": 2500.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][0] == "/supplierinvoices/levfak-1/payments"

    def test_full_betalning_nar_beloppet_tacker_restskulden(self):
        from spiris_adapter import BETALNING_FULLBETALNING, utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "leverantorsbetalning", {
            "faktura": "L-1001", "belopp": 2500.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][1]["PaymentType"] == BETALNING_FULLBETALNING

    def test_delbetalning_nar_beloppet_ar_lagre(self):
        from spiris_adapter import BETALNING_DELBETALNING, utfor_utkast

        klient = _LevKlient()
        utfor_utkast(klient, "leverantorsbetalning", {
            "faktura": "L-1001", "belopp": 1000.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][1]["PaymentType"] == BETALNING_DELBETALNING

    def test_delbetalning_av_skuld_med_negativt_restbelopp(self):
        """Sandbox-mätt 2026-08-06: `RemainingAmount` är NEGATIVT på
        leverantörsfakturor. En rak `belopp >= kvarvarande` gjorde varje
        delbetalning till en fullbetalning — 500 kr mot en skuld på 1 000 kr
        räknades som fullt betald, eftersom 500 > −1 000."""
        from spiris_adapter import BETALNING_DELBETALNING, utfor_utkast

        skuld = [dict(_LEVFAKTURA, RemainingAmount=Decimal("-2500.00"))]
        klient = _LevKlient(fakturor=skuld)
        utfor_utkast(klient, "leverantorsbetalning", {
            "faktura": "L-1001", "belopp": 1000.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][1]["PaymentType"] == BETALNING_DELBETALNING

    def test_fullbetalning_av_skuld_med_negativt_restbelopp(self):
        from spiris_adapter import BETALNING_FULLBETALNING, utfor_utkast

        skuld = [dict(_LEVFAKTURA, RemainingAmount=Decimal("-2500.00"))]
        klient = _LevKlient(fakturor=skuld)
        utfor_utkast(klient, "leverantorsbetalning", {
            "faktura": "L-1001", "belopp": 2500.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][1]["PaymentType"] == BETALNING_FULLBETALNING

    def test_valutan_tas_fran_fakturan_inte_fran_ett_antagande(self):
        from spiris_adapter import utfor_utkast

        eur = [dict(_LEVFAKTURA, CurrencyCode="EUR")]
        klient = _LevKlient(fakturor=eur)
        utfor_utkast(klient, "leverantorsbetalning", {
            "faktura": "L-1001", "belopp": 100.00,
            "betaldatum": "2026-08-06", "bankkonto_id": "bank-1",
        })

        assert klient.skickat[0][1]["PaymentCurrency"] == "EUR"


class TestFakturauppslag:
    def test_id_fungerar_nar_nummer_kolliderar(self):
        """Leverantörens fakturanummer sätts av LEVERANTÖREN och kan kollidera
        mellan olika leverantörer — till skillnad från våra egna
        kundfakturanummer. Då är id:t den enda entydiga vägen."""
        from spiris_adapter import _hitta_leverantorsfaktura

        kollision = [
            dict(_LEVFAKTURA, Id="a", SupplierId="lev-1"),
            dict(_LEVFAKTURA, Id="b", SupplierId="lev-2"),
        ]
        klient = _LevKlient(fakturor=kollision)
        assert _hitta_leverantorsfaktura(klient, "b")["Id"] == "b"

    def test_kolliderande_nummer_hojer_fel_med_atgardsbesked(self):
        from spiris_adapter import SpirisKlientFel, _hitta_leverantorsfaktura

        kollision = [dict(_LEVFAKTURA, Id="a"), dict(_LEVFAKTURA, Id="b")]
        with pytest.raises(SpirisKlientFel) as fel:
            _hitta_leverantorsfaktura(_LevKlient(fakturor=kollision), "L-1001")

        assert "id" in str(fel.value).lower()

    def test_okant_nummer_hojer_fel(self):
        from spiris_adapter import SpirisKlientFel, _hitta_leverantorsfaktura

        with pytest.raises(SpirisKlientFel):
            _hitta_leverantorsfaktura(_LevKlient(fakturor=[]), "L-9999")

    def test_leverantorsfakturalistan_bar_id(self):
        """Utan id i listan har en AI-klient ingen väg att peka ut fakturan
        för attest eller betalning. Tredje gången samma felklass — se
        hamta_bankkonton (Steg 3) och hamta_offerter (sandbox 2026-08-06)."""
        from spiris_adapter import hamta_leverantorsfakturor

        rader = hamta_leverantorsfakturor(_LevKlient())
        assert all("id" in rad for rad in rader)
        assert rader[0]["id"] == "levfak-1"


class TestIngenBefordranHarifran:
    """Att befordra ett utkast till en bokförd post är bokföringsakten och hör
    hemma hos människan i Spiris. Regeln sattes i Steg 4 för /voucherdrafts
    och gäller lika för leverantörsfakturautkasten.

    Testet läser källkoden i stället för att köra kod: det som ska bevisas är
    att vägen inte FINNS, inte att den råkar vara oanvänd i ett visst flöde.
    Kedjeåtgärderna i Steg 5b (offert→order→faktura) använder mycket riktigt
    /convert, så en svepande "ordet convert får inte förekomma" hade varit
    falsk — därför prövas de tre utkastköerna specifikt.

    Granskningen går via AST och inte via textsökning. Första versionen
    använde en regex och blev röd på en KOMMENTAR som förklarade att vägen
    aldrig anropas. AST:t ser bara faktiska strängar i koden."""

    FORBJUDNA_VAGAR = (
        "/supplierinvoicedrafts/",
        "/voucherdrafts/",
        "/customerinvoicedrafts/",
    )

    @staticmethod
    def _strangar_i_koden(kalla: str) -> list[str]:
        """Alla stränguttryck i modulen, med f-stränghål ersatta av {}.
        Docstrings hoppas över — de är dokumentation, inte anrop."""
        import ast

        trad = ast.parse(kalla)
        docstrings = {
            nod.body[0].value
            for nod in ast.walk(trad)
            if isinstance(nod, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and nod.body
            and isinstance(nod.body[0], ast.Expr)
            and isinstance(nod.body[0].value, ast.Constant)
            and isinstance(nod.body[0].value.value, str)
        }
        strangar: list[str] = []
        for nod in ast.walk(trad):
            if isinstance(nod, ast.JoinedStr):
                strangar.append("".join(
                    del_.value if isinstance(del_, ast.Constant) else "{}"
                    for del_ in nod.values
                ))
            elif (
                isinstance(nod, ast.Constant)
                and isinstance(nod.value, str)
                and nod not in docstrings
            ):
                strangar.append(nod.value)
        return strangar

    def _adapterstrangar(self) -> list[str]:
        import pathlib

        kalla = (
            pathlib.Path(__file__).resolve().parent.parent
            / "parser" / "spiris_adapter.py"
        ).read_text(encoding="utf-8")
        return self._strangar_i_koden(kalla)

    def test_ingen_utkastko_befordras_fran_koden(self):
        for strang in self._adapterstrangar():
            for prefix in self.FORBJUDNA_VAGAR:
                assert not (prefix in strang and strang.endswith("/convert")), (
                    f"koden befordrar ett utkast: {strang!r}"
                )

    def test_detektorn_ser_ett_verkligt_anrop(self):
        """Metatest: utan detta kunde AST-vandringen tyst sluta hitta
        f-strängar och testet ovan bli grönt av fel skäl."""
        falsk_kalla = 'klient.skicka(f"/voucherdrafts/{ident}/convert", {})'
        strangar = self._strangar_i_koden(falsk_kalla)

        assert any(
            "/voucherdrafts/" in s and s.endswith("/convert") for s in strangar
        )

    def test_detektorn_faller_inte_pa_en_kommentar(self):
        """Och den ska INTE reagera på dokumentation som nämner vägen — det
        var precis vad den första, textbaserade versionen gjorde."""
        kommenterad = '# /voucherdrafts/{id}/convert exponeras aldrig\nx = 1\n'
        strangar = self._strangar_i_koden(kommenterad)

        assert not any("/convert" in s for s in strangar)
