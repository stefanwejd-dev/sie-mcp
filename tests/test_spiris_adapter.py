"""Tester för spiris_adapter.py — ren mappning av rå Spiris/Visma
eAccounting-JSON till projektets domänmodell (SIEFil/Konto/Verifikation/
Transaktion/Saldopost).

Ingen HTTP här: adaptern är ett rent transformationslager, fullt testbart
utan nätverk eller fejk-klient. Fixturerna nedan är INTE påhittade — de är
fältexakt fångade från användarens Spiris-sandbox (räkenskapsår 2026,
testbolaget "X Sandbox") och korsverifierade mot samma bolags SIE4-export.
Belopp anges som Decimal eftersom spiris_klient.py:s kontrakt är att JSON
parsas med parse_float=Decimal (Decimal aldrig float) — adaptern tar alltså
emot Decimal och ska aldrig introducera en float.

"DueDate" på FAKTUROR/KUNDFAKTUROR nedan ÄR sandbox-verifierat (live-probe,
2026-07-19): fältet finns på både /customerinvoices och /supplierinvoices,
format "YYYY-MM-DD" (ingen tidskomponent) på båda. Lagt till för
fpa_motor.bygg_likviditetsprognos, som kräver ett förfallodatum per faktura.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain_model import Konto, Saldopost, Transaktion, Verifikation

from reskontra_tvatt import Kundpost, Leverantorspost

from reskontra_tvatt import maskera_for_egress
from spiris_adapter import (
    ARBETSTYP_ROT_BYGGARBETE,
    FAKTURATYP_BYGGMOMS,
    FAKTURATYP_FYSISK_PERSON_MED_ROT,
    FAKTURATYP_FYSISK_PERSON_UTAN_ROT,
    FAKTURATYP_JURIDISK_PERSON,
    KONTOKATEGORI_ARBETE,
    KONTOKATEGORI_MATERIEL,
    bygg_kundbetalhistorik_rader,
    bygg_kundfaktura_payload,
    bygg_kundreskontra_rader,
    bygg_reskontra_rader,
    bygg_rot_uppgifter,
    filtrera_aktiva_konton,
    foreslå_konto,
    hamta_kundbetalhistorik,
    hamta_kundreskontra,
    hamta_reskontra,
    hitta_artikel_for_konto,
    kraver_rot_flaggning,
    losa_artikel_ider_for_fakturarader,
    mappa_konto,
    mappa_saldon,
    mappa_transaktion,
    mappa_verifikation,
    skapa_kund,
    skapa_kundfaktura,
    spiris_typ_till_ktyp,
)
from spiris_klient import SpirisKlientFel

# --- Fältexakt sandbox-data (räkenskapsår 2026) ------------------------------

# Verifikat A12 (kundfaktura). SIE-facit: #TRANS 3041 -9000.00 / 2611 -2250.00
# / 1510 11250.00. En rad har en objektreferens i SIE (#TRANS 3041 {"6" "A-100"})
# men i REST kommer den som ProjectId=GUID — mappas medvetet INTE (beslut f).
VER_A12 = {
    "Id": "d49232b0-ae1f-477b-abc2-58c431a11af8",
    "NumberAndNumberSeries": "A12",
    "NumberSeries": "A",
    "VoucherDate": "2026-03-30",
    "VoucherText": "Kundfaktura till 6 Sparlivs, 1011",
    "VoucherType": 14,
    "CreatedUtc": "2026-06-27T17:34:17.672816Z",
    "ModifiedUtc": "2026-06-27T17:34:17.6730217Z",
    "Rows": [
        {
            "AccountNumber": 3041,
            "AccountDescription": "Försäljn tjänst 25% sv",
            "DebitAmount": Decimal("0.00"),
            "CreditAmount": Decimal("9000.00"),
            "TransactionText": "Kundfaktura till 6 Sparlivs, 1011",
            "ProjectId": "b99422f2-9ca0-4785-992c-c14d9285a04b",
        },
        {
            "AccountNumber": 2611,
            "AccountDescription": "Utgående moms på försäljning inom Sverige, 25%",
            "DebitAmount": Decimal("0.00"),
            "CreditAmount": Decimal("2250.00"),
            "TransactionText": "Kundfaktura till 6 Sparlivs, 1011",
            "ProjectId": None,
        },
        {
            "AccountNumber": 1510,
            "AccountDescription": "Kundfordringar",
            "DebitAmount": Decimal("11250.00"),
            "CreditAmount": Decimal("0.00"),
            "TransactionText": "Kundfaktura till 6 Sparlivs, 1011",
            "ProjectId": None,
        },
    ],
}

# Verifikat A1 (leverantörsfaktura). SIE-facit: #TRANS 2440 -800.00 / 4000
# 800.00. Här är TransactionText null på raderna — precis som i SIE saknas
# transtext; fallback till vertext är bygg_bunts ansvar, inte adapterns.
VER_A1 = {
    "Id": "aaaa1111-0000-0000-0000-000000000001",
    "NumberAndNumberSeries": "A1",
    "NumberSeries": "A",
    "VoucherDate": "2026-06-27",
    "VoucherText": "Leverantörsfaktura från 1 KA Data & Elektronik, 9999",
    "VoucherType": 12,
    "CreatedUtc": "2026-06-27T17:34:10.000000Z",
    "Rows": [
        {
            "AccountNumber": 2440,
            "AccountDescription": "Leverantörsskulder",
            "DebitAmount": Decimal("0.00"),
            "CreditAmount": Decimal("800.00"),
            "TransactionText": None,
            "ProjectId": None,
        },
        {
            "AccountNumber": 4000,
            "AccountDescription": "Inköp av handelsvaror (gruppkonto)",
            "DebitAmount": Decimal("800.00"),
            "CreditAmount": Decimal("0.00"),
            "TransactionText": None,
            "ProjectId": None,
        },
    ],
}


class TestTypmappning:
    """spiris_typ_till_ktyp: Visma-typnummer -> SIE #KTYP (T/S/K/I).
    Beslut a: 0-9->T, 10-19->S, 20-23->I, 24-27->K, 28-30 (finansiella/
    dispositioner/resultat) -> None. Fail-closed: okänd/None -> None, aldrig
    en gissad typ som kontotyp_vakt sedan skulle granska mot sig själv."""

    def test_tillgangstyper_blir_T(self):
        # 0=Immateriella ... 9=Kassa och bank — alla balanstillgångar
        for typ in range(0, 10):
            assert spiris_typ_till_ktyp(typ) == "T", typ

    def test_skuld_och_kapitaltyper_blir_S(self):
        # 10=Eget kapital ... 19=Upplupna kostnader — kredit/skuldsidan
        for typ in range(10, 20):
            assert spiris_typ_till_ktyp(typ) == "S", typ

    def test_intaktstyper_blir_I(self):
        # 20=Nettoomsättning ... 23=Övriga rörelseintäkter
        for typ in range(20, 24):
            assert spiris_typ_till_ktyp(typ) == "I", typ

    def test_kostnadstyper_blir_K(self):
        # 24=Varor/material ... 27=Övriga kostnader inkl avskrivningar
        for typ in range(24, 28):
            assert spiris_typ_till_ktyp(typ) == "K", typ

    def test_tvetydiga_typer_blir_None(self):
        # 28=Finansiella intäkter OCH kostnader, 29=Dispositioner/skatteposter,
        # 30=Resultat — kan inte entydigt bli K eller I. Fail-closed -> None.
        for typ in (28, 29, 30):
            assert spiris_typ_till_ktyp(typ) is None, typ

    def test_none_ger_none(self):
        assert spiris_typ_till_ktyp(None) is None

    def test_okant_typnummer_ger_none_inte_krasch(self):
        # Framtida/oväntat typnummer får aldrig gissas till en giltig typ.
        for typ in (-1, 31, 99, 1000):
            assert spiris_typ_till_ktyp(typ) is None, typ


class TestMappaKonto:
    def test_intaktskonto_3041_blir_typ_I(self):
        rå = {"Number": "3041", "Name": "Försäljn tjänst 25% sv", "Type": 20}
        konto = mappa_konto(rå)
        assert isinstance(konto, Konto)
        assert konto.kontonr == "3041"
        assert konto.namn == "Försäljn tjänst 25% sv"
        assert konto.typ == "I"

    def test_egetkapitalkonto_2099_blir_typ_S(self):
        rå = {"Number": "2099", "Name": "Årets resultat", "Type": 10}
        assert mappa_konto(rå).typ == "S"

    def test_tillgangskonto_1510_blir_typ_T(self):
        rå = {"Number": "1510", "Name": "Kundfordringar", "Type": 5}
        assert mappa_konto(rå).typ == "T"

    def test_kostnadskonto_4000_blir_typ_K(self):
        rå = {"Number": "4000", "Name": "Inköp av handelsvaror (gruppkonto)", "Type": 24}
        assert mappa_konto(rå).typ == "K"

    def test_kontonr_ar_alltid_strang(self):
        # Number kommer redan som str från API:t, men får aldrig bli int.
        assert isinstance(mappa_konto({"Number": "1930", "Name": "Företagskonto", "Type": 9}).kontonr, str)


class TestMappaTransaktion:
    def test_belopp_ar_debit_minus_kredit_och_decimal(self):
        # A12 rad 1: 3041, Debit 0, Kredit 9000 -> -9000.00 (SIE-facit: -9000.00)
        t = mappa_transaktion(VER_A12["Rows"][0])
        assert isinstance(t, Transaktion)
        assert t.kontonr == "3041"
        assert t.belopp == Decimal("-9000.00")
        assert isinstance(t.belopp, Decimal)

    def test_debetrad_ger_positivt_belopp(self):
        # A12 rad 3: 1510, Debit 11250, Kredit 0 -> 11250.00
        t = mappa_transaktion(VER_A12["Rows"][2])
        assert t.belopp == Decimal("11250.00")

    def test_transtext_bevaras_nar_den_finns(self):
        t = mappa_transaktion(VER_A12["Rows"][0])
        assert t.transtext == "Kundfaktura till 6 Sparlivs, 1011"

    def test_transtext_none_bevaras_som_none(self):
        # Leverantörsfakturarad: TransactionText är null -> None, inte "".
        # bygg_bunts transtext-or-vertext-fallback hanterar tomheten, inte adaptern.
        t = mappa_transaktion(VER_A1["Rows"][0])
        assert t.transtext is None

    def test_objektreferenser_mappas_inte(self):
        # ProjectId är ett GUID, inte ett SIE-objektnr (beslut f) -> tom dict.
        t = mappa_transaktion(VER_A12["Rows"][0])
        assert t.objektreferenser == {}


class TestMappaVerifikation:
    def test_serie_och_vernr_harleds(self):
        v = mappa_verifikation(VER_A12)
        assert isinstance(v, Verifikation)
        assert v.serie == "A"
        assert v.vernr == "12"  # "A12" minus serieprefixet "A"

    def test_verdatum_blir_date(self):
        v = mappa_verifikation(VER_A12)
        assert v.verdatum == date(2026, 3, 30)
        assert isinstance(v.verdatum, date)

    def test_regdatum_harleds_fran_created_utc(self):
        v = mappa_verifikation(VER_A12)
        assert v.regdatum == date(2026, 6, 27)

    def test_vertext_bevaras(self):
        assert mappa_verifikation(VER_A12).vertext == "Kundfaktura till 6 Sparlivs, 1011"

    def test_alla_rader_blir_transaktioner(self):
        v = mappa_verifikation(VER_A12)
        assert len(v.transaktioner) == 3
        assert [t.kontonr for t in v.transaktioner] == ["3041", "2611", "1510"]

    def test_verifikationen_balanserar(self):
        # Grundläggande sundhetskoll: en korrekt verifikation summerar till 0.
        v = mappa_verifikation(VER_A12)
        assert sum(t.belopp for t in v.transaktioner) == Decimal("0.00")

    def test_saknad_numberseries_faller_tillbaka_till_hela_numret(self):
        # Fail-safe: går serieprefixet inte att skala av, tappa inte numret.
        rå = dict(VER_A12, NumberSeries=None, NumberAndNumberSeries="123")
        v = mappa_verifikation(rå)
        assert v.vernr == "123"


class TestMappaSaldon:
    """Delar kontosaldon i (utgående_balanser, resultat) på kontoklass
    (beslut b): klass 1-2 -> UB, klass 3-8 -> RES. Nollsaldon filtreras.
    Splitten görs på kontonummer, inte på Type-fältet — saldovägen är
    oberoende av typmappningen."""

    SALDON = [
        {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("50733.08")},
        {"AccountNumber": 1930, "AccountName": "Företagskonto", "Balance": Decimal("-381.03")},
        {"AccountNumber": 3041, "AccountName": "Försäljn tjänst 25% sv", "Balance": Decimal("-27900.00")},
        {"AccountNumber": 4000, "AccountName": "Inköp", "Balance": Decimal("4142.68")},
        {"AccountNumber": 1010, "AccountName": "Utvecklingsutgifter", "Balance": Decimal("0.00")},
    ]

    def test_balanskonton_hamnar_i_utgaende_balanser(self):
        ub, _ = mappa_saldon(self.SALDON)
        kontonr = {p.kontonr for p in ub}
        assert kontonr == {"1510", "1930"}
        assert all(isinstance(p, Saldopost) for p in ub)

    def test_resultatkonton_hamnar_i_resultat(self):
        _, res = mappa_saldon(self.SALDON)
        assert {p.kontonr for p in res} == {"3041", "4000"}

    def test_nollsaldon_filtreras_bort(self):
        ub, res = mappa_saldon(self.SALDON)
        alla = {p.kontonr for p in ub} | {p.kontonr for p in res}
        assert "1010" not in alla  # Balance 0.00

    def test_saldo_ar_decimal_och_bevarar_tecken(self):
        ub, _ = mappa_saldon(self.SALDON)
        företagskonto = next(p for p in ub if p.kontonr == "1930")
        assert företagskonto.saldo == Decimal("-381.03")
        assert isinstance(företagskonto.saldo, Decimal)

    def test_arsnr_satts(self):
        ub, _ = mappa_saldon(self.SALDON, årsnr=0)
        assert all(p.årsnr == 0 for p in ub)


class TestFiltreraAktivaKonton:
    """Spiris /accounts returnerar HELA standardkontoplanen (1400+ konton),
    varav de flesta oanvända. filtrera_aktiva_konton behåller bara konton som
    faktiskt har aktivitet — ett saldo (i UB eller RES) eller minst en
    transaktion — så Modul 2 slipper brusflagga inaktiva nollsaldo-konton."""

    def _konton(self) -> dict[str, Konto]:
        return {
            "1930": Konto(kontonr="1930", namn="Företagskonto"),
            "1510": Konto(kontonr="1510", namn="Kundfordringar"),
            "3041": Konto(kontonr="3041", namn="Försäljning"),
            "9999": Konto(kontonr="9999", namn="OBS-konto (oanvänt)"),
        }

    def _verifikation(self, kontonr: str) -> Verifikation:
        return Verifikation(
            serie="A",
            vernr="1",
            verdatum=date(2026, 1, 1),
            transaktioner=[Transaktion(kontonr=kontonr, belopp=Decimal("100"))],
        )

    def test_konto_med_utgaende_saldo_behalls(self):
        ub = [Saldopost(årsnr=0, kontonr="1930", objektreferenser={}, saldo=Decimal("-381.03"))]
        ut = filtrera_aktiva_konton(self._konton(), [], ub, [])
        assert "1930" in ut

    def test_konto_med_resultatsaldo_behalls(self):
        res = [Saldopost(årsnr=0, kontonr="3041", objektreferenser={}, saldo=Decimal("-27900"))]
        ut = filtrera_aktiva_konton(self._konton(), [], [], res)
        assert "3041" in ut

    def test_konto_med_transaktion_behalls(self):
        ut = filtrera_aktiva_konton(self._konton(), [self._verifikation("1510")], [], [])
        assert "1510" in ut

    def test_konto_utan_aktivitet_filtreras_bort(self):
        ub = [Saldopost(årsnr=0, kontonr="1930", objektreferenser={}, saldo=Decimal("-381.03"))]
        ut = filtrera_aktiva_konton(self._konton(), [self._verifikation("1510")], ub, [])
        assert "9999" not in ut  # varken saldo eller transaktion

    def test_behaller_konto_objekten_intakta(self):
        ub = [Saldopost(årsnr=0, kontonr="1930", objektreferenser={}, saldo=Decimal("-381.03"))]
        ut = filtrera_aktiva_konton(self._konton(), [], ub, [])
        assert ut["1930"].namn == "Företagskonto"


# --- Leverantörsreskontra (Fas C): fältexakta sandbox-fixtures ---------------

SUPPLIERS = [
    {"Id": "s1", "Name": "3M Sverige AB", "CorporateIdentityNumber": "5578451212"},
    {"Id": "s2", "Name": "Bachbinder GmbH", "CorporateIdentityNumber": ""},
]
FAKTUROR = [
    {"SupplierId": "s1", "SupplierName": "3M Sverige AB", "TotalAmount": Decimal("-1275.00"),
     "RemainingAmount": Decimal("-1275.00"), "PaymentStatus": 7, "DueDate": "2026-08-15"},
    {"SupplierId": "s1", "SupplierName": "3M Sverige AB", "TotalAmount": Decimal("-456.00"),
     "RemainingAmount": Decimal("0"), "PaymentStatus": 6,  # betald -> filtreras bort
     "DueDate": "2026-07-01"},
    {"SupplierId": "s2", "SupplierName": "Bachbinder GmbH", "TotalAmount": Decimal("-241.00"),
     "RemainingAmount": Decimal("-241.00"), "PaymentStatus": 7,
     "DueDate": "2026-08-20T00:00:00"},  # datetime-sträng — [:10]-slicen ska klippa tiden
]


class TestByggReskontraRader:
    """Beslut B: bara öppna poster (RemainingAmount != 0), joinat med orgnr från
    /suppliers. belopp = RemainingAmount (matchar huvudbok 2440)."""

    def test_betalda_poster_filtreras_bort(self):
        rader = bygg_reskontra_rader(SUPPLIERS, FAKTUROR)
        assert len(rader) == 2  # den betalda (Remaining 0) exkluderas

    def test_orgnr_joinas_in_fran_suppliers(self):
        rader = bygg_reskontra_rader(SUPPLIERS, FAKTUROR)
        r_3m = next(r for r in rader if r["namn"] == "3M Sverige AB")
        assert r_3m["orgnr"] == "5578451212"

    def test_belopp_ar_remaining_amount_decimal(self):
        rader = bygg_reskontra_rader(SUPPLIERS, FAKTUROR)
        assert all(isinstance(r["belopp"], Decimal) for r in rader)
        assert any(r["belopp"] == Decimal("-1275.00") for r in rader)

    def test_betalstatus_oversatts_till_text(self):
        rader = bygg_reskontra_rader(SUPPLIERS, FAKTUROR)
        assert all(isinstance(r["betalstatus"], str) and r["betalstatus"] for r in rader)

    def test_forfallodatum_blir_date_objekt(self):
        rader = bygg_reskontra_rader(SUPPLIERS, FAKTUROR)
        r_3m = next(r for r in rader if r["namn"] == "3M Sverige AB")
        assert r_3m["forfallodatum"] == date(2026, 8, 15)

    def test_forfallodatum_klipper_datetime_strang(self):
        # DueDate med tidskomponent (samma försvar som CreatedUtc redan har).
        rader = bygg_reskontra_rader(SUPPLIERS, FAKTUROR)
        r_gmbh = next(r for r in rader if r["namn"] == "Bachbinder GmbH")
        assert r_gmbh["forfallodatum"] == date(2026, 8, 20)

    def test_saknat_duedate_hojer_keyerror(self):
        # Fail-closed: förfallodatum är lika grundläggande som VoucherDate —
        # en trasig/ofullständig faktura ska INTE tyst ge en likviditets-
        # prognos med hål i.
        trasig_faktura = [{"SupplierId": "s1", "SupplierName": "3M Sverige AB",
                            "RemainingAmount": Decimal("-100.00"), "PaymentStatus": 7}]
        with pytest.raises(KeyError):
            bygg_reskontra_rader(SUPPLIERS, trasig_faktura)


class TestHamtaReskontra:
    """Orkestreringen: hämtar /suppliers + /supplierinvoices, joinar/filtrerar
    och kör genom tvättmaskinen -> färdigtvättade Leverantorspost."""

    class _FejkKlient:
        def hamta_alla(self, path, params=None, **kwargs):
            if path == "/suppliers":
                return SUPPLIERS
            if path == "/supplierinvoices":
                return FAKTUROR
            raise AssertionError(f"oväntad path: {path}")

    def test_hamtar_joinar_filtrerar_och_tvattar(self):
        ut = maskera_for_egress(hamta_reskontra(self._FejkKlient()))
        assert all(isinstance(p, Leverantorspost) for p in ut)
        assert len(ut) == 2  # bara öppna poster

    def test_gmbh_slapper_igenom_via_suffix_ab_via_orgnr(self):
        ut = maskera_for_egress(hamta_reskontra(self._FejkKlient()))
        namn = {p.leverantor for p in ut}
        assert "3M Sverige AB" in namn         # via org.nr
        assert "Bachbinder GmbH" in namn       # via bolagsform-suffix (tomt orgnr)
        assert all(p.maskerad is False for p in ut)

    def test_forfallodatum_gar_hela_vagen_till_leverantorspost(self):
        # fpa_motor.bygg_likviditetsprognos behöver kunna läsa förfallodatum
        # direkt av vad hamta_reskontra() returnerar, inte bara av de råa
        # dict-raderna — annars är kopplingen till Spiris ofullständig.
        ut = maskera_for_egress(hamta_reskontra(self._FejkKlient()))
        p_3m = next(p for p in ut if p.leverantor == "3M Sverige AB")
        assert p_3m.forfallodatum == date(2026, 8, 15)


# --- Kundreskontra (Fas D) --------------------------------------------------

CUSTOMERS = [
    {"Id": "c1", "Name": "Redovisningsbyrån AB", "CorporateIdentityNumber": "5561234567",
     "IsPrivatePerson": False},
    {"Id": "c2", "Name": "Karl Svensson", "CorporateIdentityNumber": "", "IsPrivatePerson": True},
]
KUNDFAKTUROR = [
    {"CustomerId": "c1", "CustomerName": "Redovisningsbyrån AB", "CustomerIsPrivatePerson": False,
     "RemainingAmount": Decimal("5000.00"), "PaymentStatus": 2, "DueDate": "2026-08-10"},
    {"CustomerId": "c1", "CustomerName": "Redovisningsbyrån AB", "CustomerIsPrivatePerson": False,
     "RemainingAmount": Decimal("0"), "PaymentStatus": 0,  # betald -> filtreras bort
     "DueDate": "2026-06-01"},
    {"CustomerId": "c2", "CustomerName": "Karl Svensson", "CustomerIsPrivatePerson": True,
     "RemainingAmount": Decimal("1200.00"), "PaymentStatus": 1, "DueDate": "2026-08-25"},
]


class TestByggKundreskontraRader:
    def test_betalda_poster_filtreras_bort(self):
        rader = bygg_kundreskontra_rader(CUSTOMERS, KUNDFAKTUROR)
        assert len(rader) == 2

    def test_orgnr_joinas_in(self):
        rader = bygg_kundreskontra_rader(CUSTOMERS, KUNDFAKTUROR)
        r = next(r for r in rader if r["namn"] == "Redovisningsbyrån AB")
        assert r["orgnr"] == "5561234567"

    def test_privatperson_flagga_foljer_med(self):
        rader = bygg_kundreskontra_rader(CUSTOMERS, KUNDFAKTUROR)
        r = next(r for r in rader if r["namn"] == "Karl Svensson")
        assert r["privatperson"] is True

    def test_belopp_ar_decimal(self):
        rader = bygg_kundreskontra_rader(CUSTOMERS, KUNDFAKTUROR)
        assert all(isinstance(r["belopp"], Decimal) for r in rader)

    def test_forfallodatum_blir_date_objekt(self):
        rader = bygg_kundreskontra_rader(CUSTOMERS, KUNDFAKTUROR)
        r = next(r for r in rader if r["namn"] == "Redovisningsbyrån AB")
        assert r["forfallodatum"] == date(2026, 8, 10)

    def test_motpart_id_ar_customer_id(self):
        rader = bygg_kundreskontra_rader(CUSTOMERS, KUNDFAKTUROR)
        r = next(r for r in rader if r["namn"] == "Karl Svensson")
        assert r["motpart_id"] == "c2"

    def test_saknat_duedate_hojer_keyerror(self):
        trasig_faktura = [{"CustomerId": "c1", "CustomerName": "Redovisningsbyrån AB",
                            "RemainingAmount": Decimal("100.00"), "PaymentStatus": 1}]
        with pytest.raises(KeyError):
            bygg_kundreskontra_rader(CUSTOMERS, trasig_faktura)


class TestHamtaKundreskontra:
    class _FejkKlient:
        def hamta_alla(self, path, params=None, **kwargs):
            if path == "/customers":
                return CUSTOMERS
            if path == "/customerinvoices":
                return KUNDFAKTUROR
            raise AssertionError(f"oväntad path: {path}")

    def test_hamtar_och_tvattar(self):
        ut = maskera_for_egress(hamta_kundreskontra(self._FejkKlient()))
        assert all(isinstance(p, Kundpost) for p in ut)
        assert len(ut) == 2

    def test_privatperson_maskeras_juridisk_slapper(self):
        ut = maskera_for_egress(hamta_kundreskontra(self._FejkKlient()))
        ab = next(p for p in ut if p.kund == "Redovisningsbyrån AB")
        assert ab.maskerad is False
        privat = next(p for p in ut if p.maskerad)
        assert "Karl Svensson" not in privat.kund
        assert privat.kund.startswith("Fiktiv Kund")

    def test_forfallodatum_och_motpart_id_gar_hela_vagen_till_kundpost(self):
        # motpart_id förs igenom FASTÄN namnet maskeras — det är ett opakt
        # internt ID (Spiris CustomerId), inte en personuppgift, och
        # fpa_motor.bygg_likviditetsprognos behöver det för betalbeteende-
        # slagningen oavsett om kunden visas maskerad eller ej.
        ut = maskera_for_egress(hamta_kundreskontra(self._FejkKlient()))
        ab = next(p for p in ut if p.kund == "Redovisningsbyrån AB")
        assert ab.forfallodatum == date(2026, 8, 10)
        assert ab.motpart_id == "c1"
        privat = next(p for p in ut if p.maskerad)
        assert privat.motpart_id == "c2"


# --- Kundbetalhistorik (Fas 6b): PaymentDate -> berakna_kundbetalbeteende ----

BETALHISTORIK_FAKTUROR = [
    # Fullt betald, PaymentDate som RENT datum (leverantörsformatet, men på
    # kundendpointen — sandboxen visade att formatet varierar friare än bara
    # "per endpoint", så normaliseringen måste tåla båda oavsett sida).
    {"CustomerId": "c1", "DueDate": "2026-05-22", "PaymentDate": "2026-05-25",
     "PaymentStatus": 0, "RemainingAmount": Decimal("0")},
    # Fullt betald, PaymentDate som FULL ISO-datetime (det faktiskt vanliga
    # kundformatet enligt sandbox-proben).
    {"CustomerId": "c1", "DueDate": "2026-06-01", "PaymentDate": "2026-06-10T00:00:00Z",
     "PaymentStatus": 0, "RemainingAmount": Decimal("0")},
    # Förfallen (PaymentStatus=2) MEN med ett PaymentDate satt — sandbox-fyndet:
    # en delbetalning, inte en fullbetalning. Ska INTE räknas.
    {"CustomerId": "c2", "DueDate": "2026-05-01", "PaymentDate": "2026-05-20T00:00:00Z",
     "PaymentStatus": 2, "RemainingAmount": Decimal("500.00")},
    # Obetald (PaymentStatus=1), inget PaymentDate. Ska INTE räknas.
    {"CustomerId": "c3", "DueDate": "2026-06-15", "PaymentDate": None,
     "PaymentStatus": 1, "RemainingAmount": Decimal("1000.00")},
    # Betald men utan registrerat PaymentDate (skulle inte hända i praktiken,
    # men fail-safe: går inte att räkna ett snitt utan ett datum).
    {"CustomerId": "c4", "DueDate": "2026-06-20", "PaymentDate": None,
     "PaymentStatus": 0, "RemainingAmount": Decimal("0")},
]


class TestByggKundbetalhistorikRader:
    """PaymentStatus == 'Betald' är INTE kosmetiskt: sandbox-proben visade att
    PaymentDate kan vara satt på en fortfarande öppen (delbetald) faktura —
    ett sådant datum får inte smyga in i betalbeteende-profilen."""

    def test_bara_betalda_poster_med_paymentdate_tas_med(self):
        rader = bygg_kundbetalhistorik_rader(BETALHISTORIK_FAKTUROR)
        assert len(rader) == 2  # de två c1-raderna

    def test_forfallen_med_delbetalningsdatum_exkluderas(self):
        rader = bygg_kundbetalhistorik_rader(BETALHISTORIK_FAKTUROR)
        assert all(r["motpart_id"] != "c2" for r in rader)

    def test_obetald_exkluderas(self):
        rader = bygg_kundbetalhistorik_rader(BETALHISTORIK_FAKTUROR)
        assert all(r["motpart_id"] != "c3" for r in rader)

    def test_betald_utan_paymentdate_exkluderas(self):
        rader = bygg_kundbetalhistorik_rader(BETALHISTORIK_FAKTUROR)
        assert all(r["motpart_id"] != "c4" for r in rader)

    def test_bada_datumformaten_normaliseras_till_date(self):
        rader = bygg_kundbetalhistorik_rader(BETALHISTORIK_FAKTUROR)
        for rad in rader:
            assert isinstance(rad["forfallodatum"], date)
            assert isinstance(rad["betaldatum"], date)
        rent_datum = next(r for r in rader if r["forfallodatum"] == date(2026, 5, 22))
        assert rent_datum["betaldatum"] == date(2026, 5, 25)
        iso_datetime = next(r for r in rader if r["forfallodatum"] == date(2026, 6, 1))
        assert iso_datetime["betaldatum"] == date(2026, 6, 10)

    def test_motpart_id_foljer_med(self):
        rader = bygg_kundbetalhistorik_rader(BETALHISTORIK_FAKTUROR)
        assert all(r["motpart_id"] == "c1" for r in rader)

    def test_tom_indata_ger_tom_lista(self):
        assert bygg_kundbetalhistorik_rader([]) == []

    def test_saknat_duedate_pa_en_giltig_betald_post_hojer_keyerror(self):
        trasig = [{"CustomerId": "c1", "PaymentDate": "2026-05-25", "PaymentStatus": 0,
                   "RemainingAmount": Decimal("0")}]
        with pytest.raises(KeyError):
            bygg_kundbetalhistorik_rader(trasig)


class TestHamtaKundbetalhistorik:
    class _FejkKlient:
        def hamta_alla(self, path, params=None, **kwargs):
            if path == "/customerinvoices":
                return BETALHISTORIK_FAKTUROR
            raise AssertionError(f"oväntad path: {path}")

    def test_hamtar_och_filtrerar(self):
        historik = hamta_kundbetalhistorik(self._FejkKlient())
        assert len(historik) == 2
        assert all(post["motpart_id"] == "c1" for post in historik)

    def test_redo_som_indata_till_berakna_kundbetalbeteende(self):
        from fpa_motor import berakna_kundbetalbeteende

        historik = hamta_kundbetalhistorik(self._FejkKlient())
        profil = berakna_kundbetalbeteende(historik)
        # c1: (2026-05-25 - 2026-05-22)=3 dagar, (2026-06-10 - 2026-06-01)=9 dagar -> snitt 6.
        assert profil["c1"] == 6


# --- Konteringsmotor + skriv-funktioner (Fas 7) ------------------------------

class TestForeslaKonto:
    """Fail-closed konteringsmotor — regler beslutade av Arkitekten, ingen
    AI-gissning: en okänd fakturatyp/kategori-kombination höjer ValueError."""

    def test_byggmoms_lagger_bade_arbete_och_material_pa_3231(self):
        assert foreslå_konto(FAKTURATYP_BYGGMOMS, KONTOKATEGORI_ARBETE) == "3231"
        assert foreslå_konto(FAKTURATYP_BYGGMOMS, KONTOKATEGORI_MATERIEL) == "3231"

    def test_juridisk_person_delar_arbete_och_material(self):
        assert foreslå_konto(FAKTURATYP_JURIDISK_PERSON, KONTOKATEGORI_ARBETE) == "3041"
        assert foreslå_konto(FAKTURATYP_JURIDISK_PERSON, KONTOKATEGORI_MATERIEL) == "3051"

    def test_fysisk_person_utan_rot_samma_konton_som_juridisk_person(self):
        assert foreslå_konto(FAKTURATYP_FYSISK_PERSON_UTAN_ROT, KONTOKATEGORI_ARBETE) == "3041"
        assert foreslå_konto(FAKTURATYP_FYSISK_PERSON_UTAN_ROT, KONTOKATEGORI_MATERIEL) == "3051"

    def test_fysisk_person_med_rot_samma_konton_som_utan_rot(self):
        # ROT skiljer sig INTE i kontonr, bara i flaggning (kraver_rot_flaggning).
        assert foreslå_konto(FAKTURATYP_FYSISK_PERSON_MED_ROT, KONTOKATEGORI_ARBETE) == "3041"
        assert foreslå_konto(FAKTURATYP_FYSISK_PERSON_MED_ROT, KONTOKATEGORI_MATERIEL) == "3051"

    def test_okand_fakturatyp_hojer_valueerror(self):
        with pytest.raises(ValueError):
            foreslå_konto("okand_typ", KONTOKATEGORI_ARBETE)

    def test_okand_kategori_hojer_valueerror(self):
        with pytest.raises(ValueError):
            foreslå_konto(FAKTURATYP_JURIDISK_PERSON, "transport")


class TestKraverRotFlaggning:
    def test_bara_fysisk_person_med_rot_kraver_flaggning(self):
        assert kraver_rot_flaggning(FAKTURATYP_FYSISK_PERSON_MED_ROT) is True

    def test_ovriga_typer_kraver_inte_flaggning(self):
        assert kraver_rot_flaggning(FAKTURATYP_BYGGMOMS) is False
        assert kraver_rot_flaggning(FAKTURATYP_JURIDISK_PERSON) is False
        assert kraver_rot_flaggning(FAKTURATYP_FYSISK_PERSON_UTAN_ROT) is False

    def test_okand_fakturatyp_hojer_valueerror(self):
        with pytest.raises(ValueError):
            kraver_rot_flaggning("okand_typ")


class TestByggRotUppgifter:
    """Sandbox-BEKRÄFTADE (live POST, inte bara schemaläsning) värden och
    krav — se modulkommentaren ovanför ROT_TYP_*/bygg_rot_uppgifter."""

    def test_defaultvarden_ar_rot_pa_fastighet(self):
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="Solberga 1:23",
            personnummer_fastighetsagare="800101-1234",
            personer=[{"Ssn": "800101-1234", "Amount": Decimal("1500.00")}],
        )
        assert rot["RotReducedInvoicingType"] == 1  # Rot
        assert rot["RotPropertyType"] == 2  # Fastighet

    def test_faltnamnen_matchar_bekraftat_schema(self):
        # Regression: EXAKT de fält Spiris faktiskt accepterade i en lyckad
        # (icke-ROT) och en delvis lyckad (ROT, stoppad på personnummer-
        # validering) live-POST — RotReducedInvoicingPercent/
        # AutomaticDistribution FINNS INTE med (bekräftat read-only).
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="X", personnummer_fastighetsagare="Y",
            personer=[{"Ssn": "Y", "Amount": Decimal("100")}],
        )
        assert set(rot.keys()) == {
            "RotReducedInvoicingType", "RotPropertyType",
            "RotReducedInvoicingPropertyName", "RotReducedInvoicingOrgNumber", "Persons",
        }

    def test_rot_belopp_utelamnas_om_ej_angett(self):
        # Bekräftat: Spiris räknar ut avdraget automatiskt om det utelämnas.
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="X", personnummer_fastighetsagare="Y",
            personer=[{"Ssn": "Y", "Amount": Decimal("100")}],
        )
        assert "RotReducedInvoicingAmount" not in rot

    def test_rot_belopp_kan_anges_manuellt(self):
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="X", personnummer_fastighetsagare="Y",
            personer=[{"Ssn": "Y", "Amount": Decimal("100")}],
            rot_belopp=Decimal("1500.00"),
        )
        assert rot["RotReducedInvoicingAmount"] == Decimal("1500.00")

    def test_langt_personnummer_hojer_valueerror(self):
        # Bekräftat via ett faktiskt 400-svar: max 11 tecken, kort format.
        with pytest.raises(ValueError):
            bygg_rot_uppgifter(
                fastighetsbeteckning="X", personnummer_fastighetsagare="19800101-1234",
                personer=[{"Ssn": "19800101-1234", "Amount": Decimal("100")}],
            )

    def test_kort_personnummer_accepteras(self):
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="X", personnummer_fastighetsagare="800101-1234",
            personer=[{"Ssn": "800101-1234", "Amount": Decimal("100")}],
        )
        assert rot["RotReducedInvoicingOrgNumber"] == "800101-1234"

    def test_persons_fors_igenom_oforandrat(self):
        # Bekräftat via ett faktiskt 400-svar: "Persons are required..."
        # innan detta fält fanns med — det är obligatoriskt, inte kosmetiskt.
        personer = [{"Ssn": "800101-1234", "Amount": Decimal("1500.00")}]
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="X", personnummer_fastighetsagare="800101-1234",
            personer=personer,
        )
        assert rot["Persons"] == personer


class TestHittaArtikelForKonto:
    """En kundfakturarad saknar HELT ett kontofält (bekräftat i Vismas
    OpenAPI-schema OCH via en riktig POST) — kontering sker via ArticleId,
    vars Article i sin tur pekar på en ArticleAccountCoding med kontonumret."""

    class _FejkKlient:
        def __init__(self, kodningar, artiklar):
            self._kodningar = kodningar
            self._artiklar = artiklar

        def hamta_alla(self, path, params=None, **kwargs):
            if path == "/articleaccountcodings":
                return self._kodningar
            if path == "/articles":
                return self._artiklar
            raise AssertionError(f"oväntad path: {path}")

    def test_hittar_artikel_via_normal_moms_konto(self):
        klient = self._FejkKlient(
            kodningar=[{"Id": "kod-1", "DomesticSalesSubjectToVatAccountNumber": 3041}],
            artiklar=[{"Id": "artikel-1", "CodingId": "kod-1"}],
        )
        assert hitta_artikel_for_konto(klient, "3041") == "artikel-1"

    def test_hittar_artikel_via_byggmoms_konto(self):
        klient = self._FejkKlient(
            kodningar=[{
                "Id": "kod-1",
                "DomesticSalesSubjectToVatAccountNumber": 3041,
                "DomesticSalesSubjectToReversedConstructionVatAccountNumber": 3231,
            }],
            artiklar=[{"Id": "artikel-1", "CodingId": "kod-1"}],
        )
        assert hitta_artikel_for_konto(klient, "3231") == "artikel-1"

    def test_ingen_matchande_kodning_hojer_valueerror(self):
        klient = self._FejkKlient(kodningar=[], artiklar=[])
        with pytest.raises(ValueError):
            hitta_artikel_for_konto(klient, "9999")

    def test_kodning_utan_ansluten_artikel_hojer_valueerror(self):
        klient = self._FejkKlient(
            kodningar=[{"Id": "kod-1", "DomesticSalesSubjectToVatAccountNumber": 3041}],
            artiklar=[{"Id": "artikel-x", "CodingId": "annan-kodning"}],
        )
        with pytest.raises(ValueError):
            hitta_artikel_for_konto(klient, "3041")


class TestLosaArtikelIderForFakturarader:
    class _FejkKlient:
        def __init__(self):
            self.uppslag = 0

        def hamta_alla(self, path, params=None, **kwargs):
            self.uppslag += 1
            if path == "/articleaccountcodings":
                return [
                    {"Id": "kod-arbete", "DomesticSalesSubjectToVatAccountNumber": 3041},
                    {"Id": "kod-material", "DomesticSalesSubjectToVatAccountNumber": 3051},
                ]
            return [
                {"Id": "artikel-arbete", "CodingId": "kod-arbete"},
                {"Id": "artikel-material", "CodingId": "kod-material"},
            ]

    def test_loser_artikel_id_per_rad(self):
        klient = self._FejkKlient()
        rader = [
            {"beskrivning": "Arbete", "belopp": Decimal("5000"), "kontonr": "3041"},
            {"beskrivning": "Material", "belopp": Decimal("2000"), "kontonr": "3051"},
        ]
        lösta = losa_artikel_ider_for_fakturarader(klient, rader)
        assert lösta[0]["artikel_id"] == "artikel-arbete"
        assert lösta[1]["artikel_id"] == "artikel-material"

    def test_cachear_upprepade_uppslag_mot_samma_konto(self):
        klient = self._FejkKlient()
        rader = [
            {"beskrivning": "Arbete 1", "belopp": Decimal("100"), "kontonr": "3041"},
            {"beskrivning": "Arbete 2", "belopp": Decimal("200"), "kontonr": "3041"},
        ]
        losa_artikel_ider_for_fakturarader(klient, rader)
        # 2 endpoints (codings + articles) x 1 (bara ETT unikt kontonr, cachead)
        assert klient.uppslag == 2

    def test_ovriga_faltvarden_bevaras(self):
        klient = self._FejkKlient()
        rader = [{"beskrivning": "Arbete", "belopp": Decimal("5000"), "kontonr": "3041"}]
        lösta = losa_artikel_ider_for_fakturarader(klient, rader)
        assert lösta[0]["beskrivning"] == "Arbete"
        assert lösta[0]["belopp"] == Decimal("5000")


class TestByggKundfakturaPayload:
    def _rader(self):
        return [
            {"beskrivning": "Snickeriarbete",
             "belopp": Decimal("5000.00"), "artikel_id": "artikel-arbete"},
            {"beskrivning": "Virke",
             "belopp": Decimal("2000.00"), "antal": Decimal("1"), "artikel_id": "artikel-material"},
        ]

    def test_bygger_giltig_payload(self):
        payload = bygg_kundfaktura_payload(
            "kund-id-1", self._rader(), "2026-07-19", "2026-08-18"
        )
        assert payload["CustomerId"] == "kund-id-1"
        assert payload["InvoiceDate"] == "2026-07-19"
        assert payload["DueDate"] == "2026-08-18"
        assert len(payload["Rows"]) == 2

    def test_radernas_artikel_id_hamnar_pa_raden(self):
        payload = bygg_kundfaktura_payload("k1", self._rader(), "2026-07-19", "2026-08-18")
        artikel_ider = {rad["ArticleId"] for rad in payload["Rows"]}
        assert artikel_ider == {"artikel-arbete", "artikel-material"}

    def test_beskrivning_hamnar_i_text_faltet(self):
        # Bekräftat fältnamn: "Text", inte "Description".
        payload = bygg_kundfaktura_payload("k1", self._rader(), "2026-07-19", "2026-08-18")
        texter = {rad["Text"] for rad in payload["Rows"]}
        assert texter == {"Snickeriarbete", "Virke"}

    def test_olost_rad_utan_artikel_id_hojer_valueerror(self):
        rader = [{"beskrivning": "Okänd rad", "belopp": Decimal("100"), "kontonr": "3041"}]
        with pytest.raises(ValueError):
            bygg_kundfaktura_payload("k1", rader, "2026-07-19", "2026-08-18")

    def test_rot_uppgifter_vavs_in_i_payloaden(self):
        rot = bygg_rot_uppgifter(
            fastighetsbeteckning="Solberga 1:23", personnummer_fastighetsagare="800101-1234",
            personer=[{"Ssn": "800101-1234", "Amount": Decimal("1500.00")}],
        )
        payload = bygg_kundfaktura_payload(
            "k1", self._rader(), "2026-07-19", "2026-08-18", rot_uppgifter=rot
        )
        assert payload["RotReducedInvoicingPropertyName"] == "Solberga 1:23"

    def test_utan_rot_uppgifter_finns_inga_rot_falt(self):
        payload = bygg_kundfaktura_payload("k1", self._rader(), "2026-07-19", "2026-08-18")
        assert not any(key.startswith("Rot") for key in payload)

    def test_antal_defaultar_till_1(self):
        payload = bygg_kundfaktura_payload("k1", self._rader(), "2026-07-19", "2026-08-18")
        arbetsrad = next(r for r in payload["Rows"] if r["ArticleId"] == "artikel-arbete")
        assert arbetsrad["Quantity"] == Decimal("1")

    def test_arbetstyp_kraver_arbetstimmar(self):
        # Bekräftat via ett faktiskt 400-svar: "work hours < 1.00 or without
        # work hours" — en ROT-flaggad rad utan timmar avvisas.
        rader = [{"beskrivning": "Arbete", "belopp": Decimal("5000"),
                   "artikel_id": "a1", "arbetstyp": ARBETSTYP_ROT_BYGGARBETE}]
        with pytest.raises(ValueError):
            bygg_kundfaktura_payload("k1", rader, "2026-07-19", "2026-08-18")

    def test_arbetstyp_och_arbetstimmar_hamnar_pa_raden(self):
        rader = [{"beskrivning": "Arbete", "belopp": Decimal("5000"), "artikel_id": "a1",
                   "arbetstyp": ARBETSTYP_ROT_BYGGARBETE, "arbetstimmar": Decimal("10")}]
        payload = bygg_kundfaktura_payload("k1", rader, "2026-07-19", "2026-08-18")
        rad = payload["Rows"][0]
        assert rad["WorkCostType"] == ARBETSTYP_ROT_BYGGARBETE == 1
        assert rad["WorkHours"] == Decimal("10")


class TestSkapaKund:
    class _FejkKlient:
        def __init__(self, svar=None, fel=None):
            self._svar = svar
            self._fel = fel
            self.anrop: list[tuple[str, dict]] = []

        def skicka(self, path, data):
            self.anrop.append((path, data))
            if self._fel:
                raise self._fel
            return self._svar

    def test_postar_till_customers_och_returnerar_svaret(self):
        klient = self._FejkKlient(svar={"Id": "ny-kund-1", "Name": "Ny Kund AB"})
        resultat = skapa_kund(klient, {"Name": "Ny Kund AB"})

        assert resultat["Id"] == "ny-kund-1"
        assert klient.anrop == [("/customers", {"Name": "Ny Kund AB"})]

    def test_fel_fors_vidare_efter_loggning(self):
        klient = self._FejkKlient(fel=SpirisKlientFel("nere"))
        with pytest.raises(SpirisKlientFel):
            skapa_kund(klient, {"Name": "X"})


class TestSkapaKundfaktura:
    class _FejkKlient:
        def __init__(self, svar=None, fel=None):
            self._svar = svar
            self._fel = fel
            self.anrop: list[tuple[str, dict]] = []

        def skicka(self, path, data):
            self.anrop.append((path, data))
            if self._fel:
                raise self._fel
            return self._svar

    def test_postar_till_customerinvoices_och_returnerar_svaret(self):
        payload = {"CustomerId": "k1", "Rows": [{"AccountNumber": "3041"}]}
        klient = self._FejkKlient(svar={"Id": "faktura-1"})
        resultat = skapa_kundfaktura(klient, payload)

        assert resultat["Id"] == "faktura-1"
        assert klient.anrop == [("/customerinvoices", payload)]

    def test_fel_fors_vidare_efter_loggning(self):
        klient = self._FejkKlient(fel=SpirisKlientFel("avvisad"))
        payload = {"Rows": [{"AccountNumber": "3041"}]}
        with pytest.raises(SpirisKlientFel):
            skapa_kundfaktura(klient, payload)


# --- Paket B: Säkerhetsluckor i Reskontrans namnvakt ------------------------

class TestSekretessluckorReskontraPaketB:
    class _FejkKlient:
        def __init__(self, kunder=None, kundfakturor=None, lev=None, levfakturor=None):
            self._kunder = kunder or []
            self._kundfakturor = kundfakturor or []
            self._lev = lev or []
            self._levfakturor = levfakturor or []

        def hamta_alla(self, path, params=None, **kwargs):
            if path == "/customers":
                return self._kunder
            if path == "/customerinvoices":
                return self._kundfakturor
            if path == "/suppliers":
                return self._lev
            if path == "/supplierinvoices":
                return self._levfakturor
            return []

    def test_kundreskontra_maskerar_personnamn_med_bolagssuffix(self, monkeypatch):
        from spiris_adapter import hamta_kundreskontra
        monkeypatch.setattr("namnreferens.las_namnreferens", lambda: {"Anna Andersson"})
        kunder = [{"Id": "c1", "Name": "Anna Andersson AB", "CorporateIdentityNumber": ""}]
        fakturor = [{"Id": "f1", "CustomerId": "c1", "RemainingAmount": Decimal("100"), "PaymentStatus": 1, "DueDate": "2026-10-10"}]
        ut = maskera_for_egress(hamta_kundreskontra(self._FejkKlient(kunder=kunder, kundfakturor=fakturor)))
        assert len(ut) == 1
        assert "Anna Andersson" not in ut[0].kund
        assert ut[0].maskerad is True

    def test_kundreskontra_slapper_igenom_vanligt_bolagsnamn(self, monkeypatch):
        from spiris_adapter import hamta_kundreskontra
        monkeypatch.setattr("namnreferens.las_namnreferens", lambda: {"Anna Andersson"})
        kunder = [{"Id": "c1", "Name": "Scandinavian Photo AB", "CorporateIdentityNumber": ""}]
        fakturor = [{"Id": "f1", "CustomerId": "c1", "RemainingAmount": Decimal("100"), "PaymentStatus": 1, "DueDate": "2026-10-10"}]
        ut = maskera_for_egress(hamta_kundreskontra(self._FejkKlient(kunder=kunder, kundfakturor=fakturor)))
        assert len(ut) == 1
        assert ut[0].kund == "Scandinavian Photo AB"
        assert ut[0].maskerad is False

    def test_leverantorsreskontra_anvander_namnvakten(self, monkeypatch):
        from spiris_adapter import hamta_reskontra
        monkeypatch.setattr("namnreferens.las_namnreferens", lambda: {"Björn Bengtsson"})
        lev = [{"Id": "s1", "Name": "Björn Bengtsson AB", "CorporateIdentityNumber": ""}]
        fakturor = [{"Id": "f1", "SupplierId": "s1", "RemainingAmount": Decimal("-100"), "PaymentStatus": 1, "DueDate": "2026-10-10"}]
        ut = maskera_for_egress(hamta_reskontra(self._FejkKlient(lev=lev, levfakturor=fakturor)))
        assert len(ut) == 1
        assert "Björn" not in ut[0].leverantor
        assert ut[0].maskerad is True

    def test_obedombart_motpartsnamn_maskeras(self, monkeypatch):
        from spiris_adapter import hamta_reskontra
        monkeypatch.setattr("namnreferens.las_namnreferens", lambda: set())
        lev = [{"Id": "s1", "Name": "王小明", "CorporateIdentityNumber": ""}]
        fakturor = [{"Id": "f1", "SupplierId": "s1", "RemainingAmount": Decimal("-100"), "PaymentStatus": 1, "DueDate": "2026-10-10"}]
        ut = maskera_for_egress(hamta_reskontra(self._FejkKlient(lev=lev, levfakturor=fakturor)))
        assert len(ut) == 1
        assert "王小明" not in ut[0].leverantor
        assert ut[0].maskerad is True


import json

class TestHamtaKunder:
    class _FejkKlient:
        def __init__(self, kunder_svar):
            self.kunder_svar = kunder_svar
        def hamta_alla(self, path, **kwargs):
            if path == "/customers":
                return self.kunder_svar
            raise AssertionError(f"oväntad path: {path}")

    def test_juridisk_person_star_i_klartext(self):
        from spiris_adapter import hamta_kunder
        klient = self._FejkKlient([{"Name": "Testbolag AB", "CorporateIdentityNumber": "556677-8899"}])
        res = hamta_kunder(klient)
        assert res[0]["namn"] == "Testbolag AB"
        assert res[0]["maskerad"] is False

    def test_privatperson_maskeras(self):
        from spiris_adapter import hamta_kunder
        klient = self._FejkKlient([{"Name": "Anna Andersson", "IsPrivatePerson": True}])
        res = hamta_kunder(klient)
        assert res[0]["namn"] == "[Maskerad motpart]"
        assert res[0]["maskerad"] is True
        assert "Anna" not in json.dumps(res)

    def test_organisationsnummer_returneras_aldrig(self):
        from spiris_adapter import hamta_kunder
        orgnr = "556677-8899"
        klient = self._FejkKlient([{"Name": "Testbolag AB", "CorporateIdentityNumber": orgnr}])
        res = hamta_kunder(klient)
        assert orgnr not in json.dumps(res)

    def test_kontaktuppgifter_och_adress_returneras_aldrig(self):
        from spiris_adapter import hamta_kunder
        klient = self._FejkKlient([{
            "Name": "Testbolag AB",
            "CorporateIdentityNumber": "556677-8899",
            "ContactPersonName": "Anna Andersson",
            "MobilePhone": "0701234567",
            "InvoiceAddress1": "Hemliga vägen 1",
            "Iban": "SE1234567890",
            "PropertyReference": "FASTIGHET 1:1"
        }])
        res = hamta_kunder(klient)
        dump = json.dumps(res)
        assert "Anna" not in dump
        assert "070" not in dump
        assert "Hemliga" not in dump
        assert "SE123" not in dump
        assert "FASTIGHET" not in dump

    def test_belopp_forblir_decimal(self):
        from spiris_adapter import hamta_kunder
        from decimal import Decimal
        klient = self._FejkKlient([{
            "Name": "Testbolag AB",
            "UnpaidInvoicesAmount": Decimal("1234.50")
        }])
        res = hamta_kunder(klient)
        assert isinstance(res[0]["obetalt_belopp"], Decimal)
        assert res[0]["obetalt_belopp"] == Decimal("1234.50")


class TestHamtaLeverantorer:
    class _FejkKlient:
        def __init__(self, lev_svar):
            self.lev_svar = lev_svar
        def hamta_alla(self, path, **kwargs):
            if path == "/suppliers":
                return self.lev_svar
            raise AssertionError(f"oväntad path: {path}")

    def test_juridisk_person_star_i_klartext(self):
        from spiris_adapter import hamta_leverantorer
        klient = self._FejkKlient([{"Name": "Testbolag AB", "CorporateIdentityNumber": "556677-8899"}])
        res = hamta_leverantorer(klient)
        assert res[0]["namn"] == "Testbolag AB"
        assert res[0]["maskerad"] is False

    def test_betalidentifierare_returneras_aldrig(self):
        from spiris_adapter import hamta_leverantorer
        klient = self._FejkKlient([{
            "Name": "Testbolag AB",
            "CorporateIdentityNumber": "556677-8899",
            "BankAccountNumber": "1234-5678",
            "BankIban": "SE1234567890",
            "BankgiroNumber": "123-4567",
            "PlusgiroNumber": "12-3456"
        }])
        res = hamta_leverantorer(klient)
        dump = json.dumps(res)
        assert "1234-5678" not in dump
        assert "SE1234" not in dump
        assert "123-4567" not in dump
        assert "12-3456" not in dump

    def test_approvers_returneras_aldrig(self):
        from spiris_adapter import hamta_leverantorer
        klient = self._FejkKlient([{
            "Name": "Testbolag AB",
            "CorporateIdentityNumber": "556677-8899",
            "Approvers": ["Anna Andersson"]
        }])
        res = hamta_leverantorer(klient)
        dump = json.dumps(res)
        assert "Anna" not in dump

    def test_organisationsnummer_returneras_aldrig(self):
        from spiris_adapter import hamta_leverantorer
        orgnr = "556677-8899"
        klient = self._FejkKlient([{"Name": "Testbolag AB", "CorporateIdentityNumber": orgnr}])
        res = hamta_leverantorer(klient)
        assert orgnr not in json.dumps(res)


class TestHamtaProjekt:
    class _FejkKlient:
        def __init__(self, proj_svar):
            self.proj_svar = proj_svar
        def hamta_alla(self, path, **kwargs):
            if path == "/projects":
                return self.proj_svar
            raise AssertionError(f"oväntad path: {path}")

    def test_projektnamn_maskeras_med_etikettmaskeraren(self):
        from spiris_adapter import hamta_projekt
        klient = self._FejkKlient([{"Name": "Villa Anna Andersson", "Status": 1}])
        res = hamta_projekt(klient)
        assert res[0]["namn"] != "Villa Anna Andersson"
        assert "Anna" not in res[0]["namn"]

    def test_okand_status_gissas_inte(self):
        from spiris_adapter import hamta_projekt
        klient = self._FejkKlient([{"Name": "Projekt 1", "Status": 7}])
        res = hamta_projekt(klient)
        assert res[0]["status"] == "Status 7"

    def test_notes_returneras_aldrig(self):
        from spiris_adapter import hamta_projekt
        klient = self._FejkKlient([{"Name": "Projekt 1", "Notes": "Hemliga anteckningar"}])
        res = hamta_projekt(klient)
        assert "Hemliga" not in json.dumps(res)


class TestHamtaKostnadsstallen:
    class _FejkKlient:
        def __init__(self, ks_svar):
            self.ks_svar = ks_svar
        def hamta_alla(self, path, **kwargs):
            if path == "/costcenters":
                return self.ks_svar
            raise AssertionError(f"oväntad path: {path}")

    def test_poster_foljer_med_kostnadsstallet(self):
        from spiris_adapter import hamta_kostnadsstallen
        klient = self._FejkKlient([{
            "Name": "KST1",
            "Items": [{"Name": "Post 1", "ShortName": "P1"}]
        }])
        res = hamta_kostnadsstallen(klient)
        assert len(res[0]["poster"]) == 1
        assert res[0]["poster"][0]["namn"] == "Post 1"

    def test_saknade_poster_ger_tom_lista_inte_fel(self):
        from spiris_adapter import hamta_kostnadsstallen
        klient = self._FejkKlient([{"Name": "KST1"}])
        res = hamta_kostnadsstallen(klient)
        assert res[0]["poster"] == []

    def test_en_delad_maskerare_for_hela_hamtningen(self):
        from spiris_adapter import hamta_kostnadsstallen
        klient = self._FejkKlient([
            {"Name": "Anna Andersson"},
            {"Name": "Karin Karlsson"}
        ])
        res = hamta_kostnadsstallen(klient)
        assert res[0]["namn"] != "Anna Andersson"
        assert res[1]["namn"] != "Karin Karlsson"
        assert res[0]["namn"] != res[1]["namn"]


class TestHamtaKontosaldo:
    class _FejkKlient:
        def __init__(self, saldo_svar):
            self.saldo_svar = saldo_svar
            self.anropad_metod = None
        def hamta_en(self, path, params=None, **kwargs):
            self.anropad_metod = "hamta_en"
            return self.saldo_svar
        def hamta_alla(self, path, **kwargs):
            self.anropad_metod = "hamta_alla"
            return [self.saldo_svar]

    def test_anvander_hamta_en_inte_hamta_alla(self):
        from spiris_adapter import hamta_kontosaldo
        klient = self._FejkKlient({"AccountNumber": "1930", "AccountName": "Bank", "Balance": 0})
        hamta_kontosaldo(klient, "1930", "2026-12-31")
        assert klient.anropad_metod == "hamta_en"

    def test_kontonamn_maskeras(self):
        from spiris_adapter import hamta_kontosaldo
        klient = self._FejkKlient({"AccountNumber": "1930", "AccountName": "Konto för Anna Andersson"})
        res = hamta_kontosaldo(klient, "1930", "2026-12-31")
        assert res["kontonamn"] != "Konto för Anna Andersson"
        assert "Anna" not in res["kontonamn"]

    def test_tvetydig_kontotyp_ger_none_inte_gissning(self):
        from spiris_adapter import hamta_kontosaldo
        klient = self._FejkKlient({"AccountNumber": "1930", "AccountType": 29})
        res = hamta_kontosaldo(klient, "1930", "2026-12-31")
        assert res["kontotyp"] is None


class TestHamtaReferensdata:
    class _FejkKlient:
        def __init__(self, ref_svar):
            self.ref_svar = ref_svar
        def hamta_alla(self, path, **kwargs):
            return self.ref_svar

    def test_okand_typ_hojer_valueerror_med_giltiga_alternativ(self):
        from spiris_adapter import hamta_referensdata
        klient = self._FejkKlient([])
        with pytest.raises(ValueError, match="Giltiga är:"):
            hamta_referensdata(klient, "hittepa")

    @pytest.mark.parametrize("typ", [
        "enheter", "valutor", "betalningsvillkor", "leveranssatt", 
        "leveransvillkor", "lander", "kontotyper"
    ])
    def test_alla_typer_i_tabellen_gar_att_hamta(self, typ):
        from spiris_adapter import hamta_referensdata
        klient = self._FejkKlient([{}])
        res = hamta_referensdata(klient, typ)
        assert len(res) == 1

    def test_momssatser_plattar_ut_nastlad_lista(self):
        from spiris_adapter import hamta_referensdata
        klient = self._FejkKlient([{
            "Id": "1", "Code": "25", "Description": "Moms 25",
            "VatRates": [{"VatRateDate": "2020-01-01", "VatRate": 25.0}]
        }])
        res = hamta_referensdata(klient, "momssatser")
        assert res[0]["id"] == "1"
        assert len(res[0]["satser"]) == 1
        assert res[0]["satser"][0]["datum"] == "2020-01-01"
        assert res[0]["satser"][0]["momssats"] == 25.0

    def test_bara_allowlistade_nycklar_returneras(self):
        from spiris_adapter import hamta_referensdata
        klient = self._FejkKlient([{
            "Id": "1", "Code": "SEK", "Hemligt": "SynsInte"
        }])
        res = hamta_referensdata(klient, "valutor")
        assert "kod" in res[0]
        assert "Id" not in res[0]
        assert "Hemligt" not in res[0]
        assert "SynsInte" not in json.dumps(res)


FORVANTADE_NYCKLAR: dict[str, set[str]] = {
    "kunder": {"id","kundnummer","namn","maskerad","privatperson","valuta",
               "aktiv","land","betalningsvillkor_id","obetalt_belopp"},
    "leverantorer": {"id","leverantorsnummer","namn","maskerad","valuta",
                     "aktiv","land","betalningsvillkor_id","obetalt_belopp"},
    "projekt": {"id","nummer","namn","startdatum","slutdatum","kund",
                "maskerad","status"},
    "bankhandelser": {"id","datum","avstamd","belopp","originalbelopp",
                      "avgift","valuta","antal_konteringsrader","konteringar"},
    "konteringar": {"verifikat_id","verifikatnummer","belopp","kalla"},
}

class TestNycklarMotSpirio:
    """Detta test finns för att regel R1 (allowlist) annars är den enda regeln
    som en grön svit inte säger något om, eftersom det inte finns något test 
    för fält som *inte* ska finnas. Ett tillagt fält i utdatat gör detta test rött.
    
    Notera: Testet fångar inte fält som hämtas från Spiris men aldrig läggs
    i utdatat, utan endast de fält som faktiskt exponeras utåt."""
    
    class _FejkKlient:
        def __init__(self, data):
            self.data = data
        def hamta_alla(self, path, params=None, **kwargs):
            return self.data
    
    def test_kunder_nycklar_frysta(self):
        from spiris_adapter import hamta_kunder
        klient = self._FejkKlient([{
            "Id": "1", "CustomerNumber": "100", "Name": "Test", 
            "IsPrivatePerson": False, "CurrencyCode": "SEK",
            "IsActive": True, "InvoiceCountryCode": "SE", 
            "TermsOfPaymentId": "1", "UnpaidInvoicesAmount": 0,
            "CorporateIdentityNumber": "556677-8899",
            "ContactPersonName": "Hemlig Person",
            "MobilePhone": "0701234567"
        }])
        res = hamta_kunder(klient)
        assert set(res[0].keys()) == FORVANTADE_NYCKLAR["kunder"]

    def test_leverantorer_nycklar_frysta(self):
        from spiris_adapter import hamta_leverantorer
        klient = self._FejkKlient([{
            "Id": "1", "SupplierNumber": "100", "Name": "Test", 
            "CurrencyCode": "SEK", "IsActive": True, 
            "CountryCode": "SE", "TermsOfPaymentId": "1", 
            "UnpaidInvoicesAmount": 0,
            "CorporateIdentityNumber": "556677-8899",
            "BankAccountNumber": "1234",
            "BankIban": "SE000"
        }])
        res = hamta_leverantorer(klient)
        assert set(res[0].keys()) == FORVANTADE_NYCKLAR["leverantorer"]

    def test_projekt_nycklar_frysta(self):
        from spiris_adapter import hamta_projekt
        klient = self._FejkKlient([{
            "Id": "1", "Number": "100", "Name": "Test", 
            "StartDate": "2026-01-01", "EndDate": "2026-12-31", 
            "CustomerName": "Kund", "Status": 1,
            "Notes": "Hemliga anteckningar"
        }])
        res = hamta_projekt(klient)
        assert set(res[0].keys()) == FORVANTADE_NYCKLAR["projekt"]

    def test_bankhandelser_nycklar_frysta(self):
        from spiris_adapter import hamta_bankhandelser
        klient = self._FejkKlient([{
            "Id": "1", "TransactionDate": "2026-01-01", 
            "IsReconciled": False, "TransactionAmount": Decimal("100"),
            "OriginalAmount": Decimal("100"), "ChargeAmount": Decimal("0"),
            "TransactionAmountCurrency": "SEK", 
            "Rows": []
        }])
        res = hamta_bankhandelser(klient, "bank-1")
        assert set(res[0].keys()) == FORVANTADE_NYCKLAR["bankhandelser"]

    def test_konteringsrader_nycklar_frysta(self):
        from spiris_adapter import hamta_bankhandelser
        klient = self._FejkKlient([{
            "Id": "1", "Rows": [{
                "VoucherId": "v1", "PaymentVoucherNumber": "A123",
                "AmountTransactionCurrency": Decimal("100"), "Source": 1,
                "Name": "Kundnamnet", "Reference": "12345", 
                "Number": "Faktura1", "SourceId": "111", 
                "PaymentVoucherId": "v1"
            }]
        }])
        res = hamta_bankhandelser(klient, "bank-1")
        assert set(res[0]["konteringar"][0].keys()) == FORVANTADE_NYCKLAR["konteringar"]


class TestHamtaBankkonton:
    class _FejkKlient:
        def __init__(self, data):
            self.data = data
        def hamta_alla(self, path, params=None, **kwargs):
            return self.data

    def test_bankkonto_bar_id(self):
        from spiris_adapter import hamta_bankkonton
        klient = self._FejkKlient([{"Id": "bank-1", "Name": "Konto", "LedgerAccountNumber": "1930"}])
        res = hamta_bankkonton(klient)
        assert "id" in res[0]
        assert res[0]["id"] == "bank-1"

    def test_kontoinnehavare_och_iban_returneras_aldrig(self):
        from spiris_adapter import hamta_bankkonton
        import json
        klient = self._FejkKlient([{
            "Id": "bank-1", 
            "Name": "Konto",
            "LedgerAccountNumber": "1930",
            "BankAccountHolderName": "Hemlig Person",
            "Iban": "SE123",
            "Bban": "456",
            "DirectDebitCreditorId": "789"
        }])
        res = hamta_bankkonton(klient)
        str_res = json.dumps(res)
        assert "Hemlig Person" not in str_res
        assert "SE123" not in str_res
        assert "456" not in str_res
        assert "789" not in str_res


class TestHamtaBankhandelser:
    class _FejkKlient:
        def __init__(self, data):
            self.data = data
            self.anropad_path = None
            self.anropade_params = None
        def hamta_alla(self, path, params=None, **kwargs):
            self.anropad_path = path
            self.anropade_params = params
            return self.data

    def test_omatchade_ar_standard(self):
        from spiris_adapter import hamta_bankhandelser
        klient = self._FejkKlient([])
        hamta_bankhandelser(klient, "bank-1")
        assert klient.anropad_path == "/banktransactions/bank-1/unmatched"

    def test_matchade_gar_till_ratt_path(self):
        from spiris_adapter import hamta_bankhandelser
        klient = self._FejkKlient([])
        hamta_bankhandelser(klient, "bank-1", status="matchade")
        assert klient.anropad_path == "/banktransactions/bank-1/matched"

    def test_okand_status_hojer_valueerror_med_giltiga_alternativ(self):
        from spiris_adapter import hamta_bankhandelser
        klient = self._FejkKlient([])
        with pytest.raises(ValueError, match="Giltiga är:"):
            hamta_bankhandelser(klient, "bank-1", status="okand")

    def test_datumfilter_skickas_som_fromdate_och_todate(self):
        from spiris_adapter import hamta_bankhandelser
        klient = self._FejkKlient([])
        hamta_bankhandelser(klient, "bank-1", fran_datum="2026-01-01", till_datum="2026-12-31")
        assert klient.anropade_params == {"fromDate": "2026-01-01", "toDate": "2026-12-31"}

    def test_kundnamn_i_rows_returneras_aldrig(self):
        from spiris_adapter import hamta_bankhandelser
        import json
        klient = self._FejkKlient([{
            "Id": "1", "Rows": [{
                "Name": "Anna Andersson",
                "Reference": "12345678"
            }]
        }])
        res = hamta_bankhandelser(klient, "bank-1")
        str_res = json.dumps(res)
        assert "Anna Andersson" not in str_res
        assert "12345678" not in str_res

    def test_belopp_forblir_decimal(self):
        from spiris_adapter import hamta_bankhandelser
        from decimal import Decimal
        klient = self._FejkKlient([{"Id": "1", "TransactionAmount": Decimal("10.5")}])
        res = hamta_bankhandelser(klient, "bank-1")
        assert isinstance(res[0]["belopp"], Decimal)


class TestHamtaAvstamningslage:
    class _FejkKlient:
        def __init__(self, konton, handelser):
            self.konton = konton
            self.handelser = handelser
        def hamta_alla(self, path, params=None, **kwargs):
            if "bankaccounts" in path:
                return self.konton
            return self.handelser

    def test_summerar_omatchade_per_bankkonto(self):
        from spiris_adapter import hamta_avstamningslage
        from decimal import Decimal
        klient = self._FejkKlient(
            [{"Id": "bank-1", "Name": "Konto", "LedgerAccountNumber": "1930"}],
            [
                {"Id": "1", "TransactionAmount": Decimal("100"), "TransactionDate": "2026-02-01"},
                {"Id": "2", "TransactionAmount": Decimal("50"), "TransactionDate": "2026-01-01"}
            ]
        )
        res = hamta_avstamningslage(klient)
        assert len(res) == 1
        assert res[0]["antal_omatchade"] == 2
        assert res[0]["summa_omatchade"] == Decimal("150")
        assert res[0]["aldsta_omatchad"] == "2026-01-01"

    def test_konto_utan_omatchade_ger_noll_och_none(self):
        from spiris_adapter import hamta_avstamningslage
        from decimal import Decimal
        klient = self._FejkKlient(
            [{"Id": "bank-1", "Name": "Konto", "LedgerAccountNumber": "1930"}],
            []
        )
        res = hamta_avstamningslage(klient)
        assert res[0]["antal_omatchade"] == 0
        assert res[0]["summa_omatchade"] == Decimal("0")
        assert res[0]["aldsta_omatchad"] is None

    def test_summan_ar_decimal_inte_float(self):
        from spiris_adapter import hamta_avstamningslage
        from decimal import Decimal
        klient = self._FejkKlient(
            [{"Id": "bank-1", "Name": "Konto", "LedgerAccountNumber": "1930"}],
            [{"Id": "1", "TransactionAmount": Decimal("100")}]
        )
        res = hamta_avstamningslage(klient)
        assert isinstance(res[0]["summa_omatchade"], Decimal)



class TestUtkastvagen:
    """Steg 4: Spiris utkastendpoints (/voucherdrafts, /customerinvoicedrafts).

    Skillnaden mot de skarpa vägarna är återkallelighet, inte form. Testerna
    nedan låser dels att formen bevaras (så att allt som är sandbox-verifierat
    om kontering, ROT och artikelrader fortsatt gäller), dels att den nästlade
    utkastvägen inte fäller på fält som är valfria i utkastschemat men
    obligatoriska i det skarpa."""

    def test_kundfakturautkast_lagger_till_de_obligatoriska_faltten(self):
        from spiris_adapter import ROT_TYP_NORMAL, bygg_kundfakturautkast_payload

        payload = bygg_kundfakturautkast_payload({
            "CustomerId": "cus-1",
            "InvoiceDate": "2026-08-05",
            "Rows": [{"ArticleId": "art-1", "UnitPrice": Decimal("1000")}],
        })

        assert payload["EuThirdParty"] is False
        assert payload["RotReducedInvoicingType"] == ROT_TYP_NORMAL
        rad = payload["Rows"][0]
        assert rad["IsTextRow"] is False
        assert rad["ReversedConstructionServicesVatFree"] is False
        # Ursprungsfälten är orörda — transformationen lägger bara till.
        assert rad["ArticleId"] == "art-1"
        assert rad["UnitPrice"] == Decimal("1000")

    def test_rot_typ_skrivs_aldrig_over(self):
        """Bär payloaden redan ROT-uppgifter har bygg_rot_uppgifter satt
        RotReducedInvoicingType, och DET värdet gäller — inte standardvärdet."""
        from spiris_adapter import ROT_TYP_ROT, bygg_kundfakturautkast_payload

        payload = bygg_kundfakturautkast_payload({
            "CustomerId": "cus-1",
            "RotReducedInvoicingType": ROT_TYP_ROT,
            "Rows": [],
        })

        assert payload["RotReducedInvoicingType"] == ROT_TYP_ROT

    def test_kundfaktura_gar_till_utkast_som_standard(self):
        from spiris_adapter import utfor_utkast

        class _Fangare:
            def __init__(self):
                self.skickat = []

            def hamta_alla(self, path, params=None, **kwargs):
                if path == "/customers":
                    return [{"Id": "cus-1", "Name": "Kundbolaget AB"}]
                if path == "/articleaccountcodings":
                    return [{"Id": "kod-1", "DomesticSalesSubjectToVatAccountNumber": 3041}]
                if path == "/articles":
                    return [{"Id": "art-1", "CodingId": "kod-1"}]
                return []

            def skicka(self, path, data):
                self.skickat.append((path, data))
                return {"Id": "nytt-id"}

        klient = _Fangare()
        utfor_utkast(klient, "kundfaktura", {
            "kundnamn": "Kundbolaget AB",
            "rader": [{"beskrivning": "Arbete", "pris": 1000, "antal": 1, "konto": "3041"}],
        })

        assert klient.skickat[0][0] == "/customerinvoicedrafts"

    def test_verifikatutkast_utan_kreditbelopp_fyller_inte_pa_fel(self):
        """DebitAmount/CreditAmount är VALFRIA på VoucherDraftRowApi — ett
        halvfärdigt utkast är ett normalt tillstånd och får inte fälla
        listningen med KeyError."""
        from spiris_adapter import mappa_verifikatutkast

        verifikation = mappa_verifikatutkast({
            "Id": "utk-1",
            "VoucherDate": "2026-08-05",
            "VoucherText": "Halvfärdigt",
            "Rows": [{"AccountNumber": 1930, "DebitAmount": Decimal("125")}],
        })

        assert verifikation.transaktioner[0].belopp == Decimal("125")
        assert isinstance(verifikation.transaktioner[0].belopp, Decimal)

    def test_utkastets_id_blir_vernr(self):
        """Ett utkast har ännu inget verifikationsnummer — Spiris tilldelar
        det först vid /convert. Id används som vernr, och det är opakt."""
        from spiris_adapter import mappa_verifikatutkast

        verifikation = mappa_verifikatutkast({
            "Id": "utk-1", "VoucherDate": "2026-08-05", "NumberSeries": "A", "Rows": [],
        })

        assert verifikation.vernr == "utk-1"
        assert verifikation.serie == "A"


class TestEtapp1ODataParametrar:
    class _FangarKlient:
        def __init__(self):
            self.anrop = []

        def hamta_alla(self, path, params=None, filter=None, select=None, orderby=None, pagesize=None):
            self.anrop.append((path, filter, select, orderby, pagesize))
            return []

        def hamta_en(self, path, params=None, **kwargs):
            self.anrop.append((path, params))
            return {}

        def skicka(self, path, data):
            pass

    def test_kunder_skickar_odata(self):
        from spiris_adapter import hamta_kunder
        klient = self._FangarKlient()
        hamta_kunder(klient, filter="Namn", select=["Id"], orderby="Namn", pagesize=10)
        assert klient.anrop[0] == ("/customers", "Namn", ["Id"], "Namn", 10)

    def test_leverantorer_skickar_odata(self):
        from spiris_adapter import hamta_leverantorer
        klient = self._FangarKlient()
        hamta_leverantorer(klient, filter="Namn", select=["Id"], orderby="Namn", pagesize=10)
        assert klient.anrop[0] == ("/suppliers", "Namn", ["Id"], "Namn", 10)

    def test_projekt_skickar_odata(self):
        from spiris_adapter import hamta_projekt
        klient = self._FangarKlient()
        hamta_projekt(klient, filter="Namn", select=["Id"], orderby="Namn", pagesize=10)
        assert klient.anrop[0] == ("/projects", "Namn", ["Id"], "Namn", 10)

    def test_kostnadsstallen_skickar_odata(self):
        from spiris_adapter import hamta_kostnadsstallen
        klient = self._FangarKlient()
        hamta_kostnadsstallen(klient, filter="Namn", select=["Id"], orderby="Namn", pagesize=10)
        assert klient.anrop[0] == ("/costcenters", "Namn", ["Id"], "Namn", 10)

    def test_kontosaldo_skickar_odata_som_params(self):
        from spiris_adapter import hamta_kontosaldo
        klient = self._FangarKlient()
        hamta_kontosaldo(klient, "1930", "2026-12-31", filter="Namn", select=["Id"], orderby="Namn", pagesize=10)
        path, params = klient.anrop[0]
        assert path == "/accountbalances/1930/2026-12-31"
        assert params["$filter"] == "Namn"
        assert params["$select"] == "Id"
        assert params["$orderby"] == "Namn"
        assert params["$pagesize"] == "10"

    def test_referensdata_skickar_odata(self):
        from spiris_adapter import hamta_referensdata
        klient = self._FangarKlient()
        hamta_referensdata(klient, "valutor", filter="Namn", select=["Id"], orderby="Namn", pagesize=10)
        assert klient.anrop[0] == ("/currencies", "Namn", ["Id"], "Namn", 10)

class TestU15_Enkeluppslag:
    class _FejkKlient:
        def hamta_en(self, path, **kwargs):
            return {"Id": "123", "Name": "Test"}
        def hamta_alla(self, path, **kwargs):
            return [{"Id": "123", "Name": "Test"}]

    def test_hamta_ett_kunder(self):
        from spiris_adapter import hamta_ett
        res = hamta_ett(self._FejkKlient(), "kund", "123")
        assert "namn" in res

    def test_hamta_ett_verifikatutkast(self):
        from spiris_adapter import hamta_ett
        kl = self._FejkKlient()
        def hamta_en_mock(p, **kw): return {"Id": "123", "VoucherDate": "2026-08-01", "NumberAndNumberSeries": "A1"}
        kl.hamta_en = hamta_en_mock
        res = hamta_ett(kl, "verifikatutkast", "123")
        assert "verifikat" in res

class TestU61_Lasfunktioner_Bockerna:
    def test_hamta_kontotransaktioner(self):
        from unittest.mock import MagicMock
        mock_spiris_klient = MagicMock()
        from parser.spiris_adapter import hamta_kontotransaktioner
        from decimal import Decimal
        
        mock_spiris_klient.hamta_alla.return_value = [
            {
                "NumberSeries": "A",
                "NumberAndNumberSeries": "A 1",
                "VoucherDate": "2026-01-01",
                "VoucherText": "Test 1",
                "Rows": [
                    {"AccountNumber": 1930, "Debit": 100, "Credit": 0, "TransactionText": "TR1"},
                    {"AccountNumber": 3010, "Debit": 0, "Credit": 100, "TransactionText": "TR2"}
                ]
            }
        ]
        
        res = hamta_kontotransaktioner(mock_spiris_klient, "FY1", "1930")
        assert len(res) == 1
        assert res[0]["belopp"] == Decimal("100")
        assert res[0]["transtext"] == "TR1"
        assert res[0]["plats"] == "serie=A vernr=1"

    def test_hamta_kontosaldon(self):
        from unittest.mock import MagicMock
        mock_spiris_klient = MagicMock()
        from parser.spiris_adapter import hamta_kontosaldon
        from decimal import Decimal
        
        def _mock_hamta_alla(url, **kwargs):
            if "accounts" in url:
                return [{"Number": 1930, "Name": "Bank", "FiscalYearId": 1, "IsActive": True}]
            if "accountbalances" in url:
                return [{"AccountNumber": 1930, "Balance": 100}]
            return []
            
        mock_spiris_klient.hamta_alla.side_effect = _mock_hamta_alla
        
        res = hamta_kontosaldon(mock_spiris_klient, "FY1", "2026-12-31")
        assert len(res) == 1
        assert res[0]["kontonr"] == "1930"
        assert res[0]["kontonamn"] == "Bank"
        assert res[0]["saldo"] == Decimal("100")

    def test_hamta_momsoversikt(self):
        from unittest.mock import MagicMock
        mock_spiris_klient = MagicMock()
        from parser.spiris_adapter import hamta_momsoversikt
        
        mock_spiris_klient.hamta_alla.return_value = [
            {"AccountNumber": 2611, "AccountName": "Moms", "Balance": -1000},
            {"AccountNumber": 3000, "AccountName": "Intäkt", "Balance": -4000}
        ]
        
        res = hamta_momsoversikt(mock_spiris_klient, "2026-12-31")
        assert isinstance(res, dict)
        assert "period" in res
