"""Tester för spiris_rag.py — de tre async RAG-verktygen som låter en LLM hämta
aggregerad huvudboksdata från Spiris.

Kärnkrav (bekräftade med användaren):
- All returnerad data har gått genom befintlig maskering (maskera_siefil) — ingen
  rå personuppgift läcker.
- Strikt fail-closed: blockerade verifikationer (olösta maskeringsbehov) utesluts
  HELT, men envelopet bär en räknare + info-text så LLM:en vet att data undanhållits.
- Kontosaldon = ackumulerat utgående saldo (YTD) fram till tom_datum.

Aldrig nätverk: en fejk-SpirisKlient injiceras. Async-funktionerna körs via
asyncio.run (undviker pytest-async-pluginberoende).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from fpa_motor import (
    FINANSIERINGSKALLOR,
    bygg_balansrapport,
    bygg_kassaflodesanalys,
    bygg_nyckeltal,
    bygg_resultatrapport,
    simulera_investering,
)
from spiris_rag import (
    hamta_balansrapport,
    hamta_dashboard,
    hamta_kontosaldon,
    hamta_kontotransaktioner,
    hamta_resultatrapport,
    sok_verifikationstexter,
)

RÄKENSKAPSÅR_ID = "fy-2026"
TOM_DATUM = "2026-12-31"

COMPANYSETTINGS = {"Name": "X Sandbox", "CorporateIdentityNumber": "556677-8899", "CurrencyCode": "SEK"}

ACCOUNTS = [
    {"Number": "1910", "Name": "Kassa", "Type": 9},
    {"Number": "1510", "Name": "Kundfordringar", "Type": 5},
    {"Number": "3041", "Name": "Försäljning", "Type": 20},
    # Bart personnamn som kontonamn (inget föregående ord) — fångas VARKEN av
    # Lager 3b (kräver föregående ord) eller utan referenslista. Testar
    # omgranskningens fynd 1: MCP-vägen måste själv skicka referenslistan.
    {"Number": "2393", "Name": "Anna Andersson", "Type": 15},
]

# A2:s namn ("Torbjörn Cederkvist") finns MEDVETET INTE i referenslistan
# (namnreferens.STANDARDNAMN): det ska fortsatt gå Lager 3b-vägen och
# BLOCKERAS. A3:s namn ("Karl Svensson") FINNS i referenslistan: det ska
# auto-maskeras av Lager 3a och förbli sändningsbart — två olika utfall som
# testerna nedan skiljer på.
VOUCHERS = [
    {  # Ren text -> blir sändningsbar
        "NumberAndNumberSeries": "A1", "NumberSeries": "A", "VoucherDate": "2026-01-05",
        "VoucherText": "Kontantförsäljning", "CreatedUtc": "2026-01-05T00:00:00Z",
        "Rows": [
            {"AccountNumber": 1910, "DebitAmount": Decimal("500.00"), "CreditAmount": Decimal("0"),
             "TransactionText": "Kontantförsäljning"},
            {"AccountNumber": 3041, "DebitAmount": Decimal("0"), "CreditAmount": Decimal("500.00"),
             "TransactionText": "Kontantförsäljning"},
        ],
    },
    {  # Okänt personnamn -> olöst maskeringsbehov -> BLOCKERAD (fail-closed)
        "NumberAndNumberSeries": "A2", "NumberSeries": "A", "VoucherDate": "2026-02-10",
        "VoucherText": "Kundfaktura till Torbjörn Cederkvist", "CreatedUtc": "2026-02-10T00:00:00Z",
        "Rows": [
            {"AccountNumber": 1510, "DebitAmount": Decimal("1000.00"), "CreditAmount": Decimal("0"),
             "TransactionText": "Kundfaktura till Torbjörn Cederkvist"},
            {"AccountNumber": 3041, "DebitAmount": Decimal("0"), "CreditAmount": Decimal("1000.00"),
             "TransactionText": "Kundfaktura till Torbjörn Cederkvist"},
        ],
    },
    {  # Referenslistnamn -> Lager 3a auto-maskerar -> SÄNDNINGSBAR (fynd 1)
        "NumberAndNumberSeries": "A3", "NumberSeries": "A", "VoucherDate": "2026-03-01",
        "VoucherText": "Kundfaktura till Karl Svensson", "CreatedUtc": "2026-03-01T00:00:00Z",
        "Rows": [
            {"AccountNumber": 1510, "DebitAmount": Decimal("750.00"), "CreditAmount": Decimal("0"),
             "TransactionText": "Kundfaktura till Karl Svensson"},
        ],
    },
]

ACCOUNTBALANCES = [
    {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("500.00")},
    {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("1000.00")},
    {"AccountNumber": 3041, "AccountName": "Försäljning", "Balance": Decimal("-1500.00")},
    {"AccountNumber": 2393, "AccountName": "Anna Andersson", "Balance": Decimal("-5000.00")},
]


class _FejkKlient:
    """Injicerad stand-in för SpirisKlient — sync hamta_en/hamta_alla (körs via
    asyncio.to_thread i verktygen). Aldrig nätverk."""

    def hamta_en(self, path: str, params: dict | None = None) -> dict:
        if path == "/companysettings":
            return COMPANYSETTINGS
        raise AssertionError(f"oväntad hamta_en: {path}")

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path.startswith("/accounts/"):
            return ACCOUNTS
        if path.startswith("/vouchers/"):
            return VOUCHERS
        if path.startswith("/accountbalances/"):
            return ACCOUNTBALANCES
        raise AssertionError(f"oväntad hamta_alla: {path}")


class TestHamtaKontosaldon:
    def _kor(self) -> dict:
        return asyncio.run(hamta_kontosaldon(_FejkKlient(), RÄKENSKAPSÅR_ID, TOM_DATUM))

    def test_returnerar_saldon_per_konto(self):
        resultat = self._kor()
        rader = resultat["data"]
        kassa = next(r for r in rader if r["kontonr"] == "1910")
        assert kassa["kontonamn"] == "Kassa"
        assert kassa["saldo"] == Decimal("500.00")

    def test_innehaller_resultatkonton_ytd(self):
        rader = self._kor()["data"]
        assert any(r["kontonr"] == "3041" and r["saldo"] == Decimal("-1500.00") for r in rader)

    def test_envelope_har_info_och_raknare(self):
        resultat = self._kor()
        # Saldon är aggregat -> inget blockeras
        assert resultat["antal_exkluderade"] == 0
        assert "info" in resultat


class TestHamtaKontotransaktioner:
    def _kor(self, kontonr: str) -> dict:
        return asyncio.run(hamta_kontotransaktioner(_FejkKlient(), RÄKENSKAPSÅR_ID, kontonr))

    def test_returnerar_maskerade_rader_for_kontot(self):
        # 1910 finns bara i A1 (sändningsbar).
        resultat = self._kor("1910")
        assert len(resultat["data"]) == 1
        assert resultat["data"][0]["transtext"] == "Kontantförsäljning"

    def test_ingen_ra_pii_lacker(self):
        # 3041 finns i både A1 (ok) och A2 (blockerad). Rå "Torbjörn Cederkvist"
        # får ALDRIG nå returdatan.
        resultat = self._kor("3041")
        assert "Torbjörn Cederkvist" not in str(resultat["data"])

    def test_blockerad_verifikation_utesluts_men_raknas(self):
        resultat = self._kor("3041")
        # A2 (Torbjörn Cederkvist) är blockerad -> utesluten men räknad.
        assert resultat["antal_exkluderade"] >= 1
        assert "exkluderade" in resultat["info"].lower()


class TestSokVerifikationstexter:
    def _kor(self, sökterm: str) -> dict:
        return asyncio.run(sok_verifikationstexter(_FejkKlient(), RÄKENSKAPSÅR_ID, sökterm))

    def test_hittar_matchande_sandningsbar_verifikation(self):
        resultat = self._kor("Kontantförsäljning")
        assert any("Kontantförsäljning" in r["vertext"] for r in resultat["data"])

    def test_sokning_pa_personnamn_ger_ingen_ra_traff(self):
        # A2 är blockerad, så en sökning på personnamnet ger inga rå träffar,
        # men räknaren visar att blockerad data finns.
        resultat = self._kor("Torbjörn Cederkvist")
        assert "Torbjörn Cederkvist" not in str(resultat["data"])
        assert resultat["antal_exkluderade"] >= 1

    def test_envelope_form(self):
        resultat = self._kor("Kontantförsäljning")
        assert set(resultat) >= {"data", "antal_exkluderade", "info"}


# --- Fynd 1 (omgranskningen): referenslistan aktiv även i MCP-vägen ----------

class TestFynd1ReferenslistaIMcpVagen:
    """MCP-vägen körde förr utan referenslistan (Lager 3a): ett BART namn
    (utan föregående ord) fångas inte av Lager 3b:s regex, och utan
    referenslista passerade det därför omaskerat genom spiris_rag-verktygen.
    Nu hämtar modulen sin egen referenslista (las_namnreferens) i stället för
    att lita på att anroparen minns att skicka en."""

    def test_bart_kontonamn_maskeras_i_kontosaldon(self):
        resultat = asyncio.run(hamta_kontosaldon(_FejkKlient(), RÄKENSKAPSÅR_ID, TOM_DATUM))
        lån = next(r for r in resultat["data"] if r["kontonr"] == "2393")
        assert "Anna" not in lån["kontonamn"]
        assert "Andersson" not in lån["kontonamn"]
        assert "PERSON_" in lån["kontonamn"]

    def test_referenslistnamn_automaskeras_i_stallet_for_blockeras(self):
        # A3 ("Karl Svensson" — i referenslistan) auto-maskeras av Lager 3a och
        # är sändningsbar; A2 ("Torbjörn Cederkvist" — okänt) förblir blockerad.
        # Bägge utfallen i samma anrop: maskering ersätter inte fail-closed.
        resultat = asyncio.run(
            hamta_kontotransaktioner(_FejkKlient(), RÄKENSKAPSÅR_ID, "1510")
        )
        assert resultat["antal_exkluderade"] == 1  # bara A2
        assert len(resultat["data"]) == 1          # A3:s rad
        rad = resultat["data"][0]
        assert "Karl" not in rad["transtext"]
        assert "Svensson" not in rad["transtext"]
        assert "PERSON_" in rad["transtext"]

    def test_bart_kontonamn_maskeras_i_balansrapport(self):
        class _Klient:
            def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
                return [
                    {"AccountNumber": 1910, "AccountName": "Kassa",
                     "Balance": Decimal("5000.00")},
                    {"AccountNumber": 2393, "AccountName": "Anna Andersson",
                     "Balance": Decimal("-5000.00")},
                ]

        rapport = asyncio.run(hamta_balansrapport(_Klient(), "2026-12-31"))
        assert "Anna Andersson" not in str(rapport)
        assert "PERSON_" in str(rapport)

    def test_bart_kontonamn_maskeras_i_resultatrapport(self):
        class _Klient:
            def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
                if path == "/accountbalances/2026-01-01":
                    return []
                return [
                    {"AccountNumber": 3050, "AccountName": "Anna Andersson",
                     "Balance": Decimal("-10000.00")},
                ]

        rapport = asyncio.run(hamta_resultatrapport(_Klient(), "2026-01-01", "2026-12-31"))
        assert "Anna Andersson" not in str(rapport)
        assert "PERSON_" in str(rapport)


# --- Resultatrapport (strukturerad BAS-P&L för BI/FP&A) ---------------------

class _FejkRapportKlient:
    """Serverar kontosaldon vid periodens start och slut. Här är öppningen 0
    (periodstart) så periodresultat = utgående saldo — men verktyget beräknar
    ändå slut minus start per konto."""

    SLUT = [
        {"AccountNumber": 3041, "AccountName": "Försäljning", "Balance": Decimal("-100000.00")},
        {"AccountNumber": 4000, "AccountName": "Inköp handelsvaror", "Balance": Decimal("30000.00")},
        {"AccountNumber": 5000, "AccountName": "Lokalkostnader", "Balance": Decimal("10000.00")},
        {"AccountNumber": 7010, "AccountName": "Löner", "Balance": Decimal("25000.00")},
        {"AccountNumber": 7830, "AccountName": "Avskrivningar inventarier", "Balance": Decimal("5000.00")},
        {"AccountNumber": 8410, "AccountName": "Räntekostnader", "Balance": Decimal("2000.00")},
        {"AccountNumber": 8910, "AccountName": "Skatt på årets resultat", "Balance": Decimal("3000.00")},
        {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("800.00")},  # klass 1 -> ignoreras
    ]

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/accountbalances/2026-01-01":
            return []  # öppningssaldon = 0
        if path == "/accountbalances/2026-12-31":
            return self.SLUT
        raise AssertionError(f"oväntad path: {path}")


class TestHamtaResultatrapport:
    def _kor(self) -> dict:
        return asyncio.run(hamta_resultatrapport(_FejkRapportKlient(), "2026-01-01", "2026-12-31"))

    def test_ar_strukturerat_json_inte_text(self):
        resultat = self._kor()
        assert isinstance(resultat, dict)
        assert isinstance(resultat["poster"], dict)
        assert resultat["period"] == {"start_datum": "2026-01-01", "slut_datum": "2026-12-31"}

    def test_intakter_presenteras_positivt(self):
        # Klass 3 är kreditnormal (negativ i SIE) -> ska vändas till positivt.
        assert self._kor()["poster"]["totala_intakter"] == Decimal("100000.00")

    def test_bas_aggregat_stammer(self):
        poster = self._kor()["poster"]
        assert poster["kostnad_salda_varor"] == Decimal("30000.00")   # klass 4
        assert poster["bruttovinst"] == Decimal("70000.00")           # intäkter - KSV
        assert poster["totala_kostnader"] == Decimal("70000.00")      # klass 4-7
        assert poster["avskrivningar"] == Decimal("5000.00")          # 7700-7899
        assert poster["ebitda"] == Decimal("35000.00")               # rörelseres. + avskr.
        assert poster["rorelseresultat"] == Decimal("30000.00")       # intäkter - kostnader

    def test_klass8_ger_fullstandig_pl(self):
        poster = self._kor()["poster"]
        assert poster["finansnetto"] == Decimal("-2000.00")           # -sum(8000-8499)
        assert poster["resultat_efter_finansiella"] == Decimal("28000.00")  # EBIT + finansnetto
        assert poster["bokslutsdispositioner_skatt"] == Decimal("3000.00")  # sum(8800-8999)
        assert poster["arets_resultat"] == Decimal("25000.00")        # EBT - disp/skatt

    def test_konton_finns_for_drilldown_tabeller(self):
        konton = self._kor()["konton"]
        f3041 = next(k for k in konton if k["kontonr"] == "3041")
        assert f3041["kontonamn"] == "Försäljning"
        # Kontonivån normaliseras: intäkt (klass 3) presenteras positivt, precis
        # som poster-raden. Frontend ska aldrig behöva känna till SIE-kredittecken.
        assert f3041["saldo"] == Decimal("100000.00")
        # Varje konto bär sin P&L-grupp så drill-down-UI:t bara loopar och
        # renderar — motorn (inte frontend) äger BAS-intervall-mappningen.
        assert f3041["grupp"] == "totala_intakter"

    def test_grupper_reconcilierar_mot_poster(self):
        # "Dum frontend"-kontrakt: summan av en grupps konton == poster-raden.
        rapport = self._kor()
        poster, konton = rapport["poster"], rapport["konton"]

        def gruppsumma(grupp: str) -> Decimal:
            return sum((k["saldo"] for k in konton if k["grupp"] == grupp), Decimal("0"))

        assert gruppsumma("totala_intakter") == poster["totala_intakter"]
        assert gruppsumma("kostnad_salda_varor") == poster["kostnad_salda_varor"]
        assert gruppsumma("ovriga_rorelsekostnader") == poster["ovriga_rorelsekostnader"]
        assert gruppsumma("avskrivningar") == poster["avskrivningar"]
        assert gruppsumma("finansnetto") == poster["finansnetto"]
        assert gruppsumma("bokslutsdispositioner_skatt") == poster["bokslutsdispositioner_skatt"]
        # Övriga rörelsekostnader fyller gapet: KSV + övriga + avskrivningar =
        # totala kostnader (klass 4-7).
        assert (
            poster["kostnad_salda_varor"]
            + poster["ovriga_rorelsekostnader"]
            + poster["avskrivningar"]
            == poster["totala_kostnader"]
        )

    def test_bara_resultatkonton_klass_3_till_8(self):
        # Klass 1-2 (t.ex. 1910 Kassa) är balanskonton och ska INTE ingå.
        kontonr = {k["kontonr"] for k in self._kor()["konton"]}
        assert "1910" not in kontonr
        assert {"3041", "4000", "8410"}.issubset(kontonr)

    def test_periodresultat_ar_delta_slut_minus_start(self):
        # Öppning != 0 -> periodresultat ska vara skillnaden, inte utgående.
        class _MedÖppning(_FejkRapportKlient):
            def hamta_alla(self, path, params=None):
                if path == "/accountbalances/2026-01-01":
                    return [{"AccountNumber": 4000, "AccountName": "Inköp handelsvaror",
                             "Balance": Decimal("5000.00")}]
                return super().hamta_alla(path, params)

        resultat = asyncio.run(hamta_resultatrapport(_MedÖppning(), "2026-01-01", "2026-12-31"))
        f4000 = next(k for k in resultat["konton"] if k["kontonr"] == "4000")
        assert f4000["saldo"] == Decimal("25000.00")  # 30000 - 5000


class TestByggResultatrapport:
    """Den rena beräkningsmotorn — HELT frikopplad från datakällan (ingen
    klient, ingen fil, ingen async). Tar redan uträknade periodsaldon per konto
    och aggregerar. Datakällan (SIE-fil idag, ERP-API imorgon) byts utan att
    röra motorn."""

    KONTON = [
        {"kontonr": "3041", "kontonamn": "Försäljning", "saldo": Decimal("-100000.00")},
        {"kontonr": "4000", "kontonamn": "Inköp", "saldo": Decimal("30000.00")},
        {"kontonr": "7830", "kontonamn": "Avskrivningar", "saldo": Decimal("5000.00")},
        {"kontonr": "8410", "kontonamn": "Räntekostnader", "saldo": Decimal("2000.00")},
    ]

    def test_aggregerar_utan_klient_eller_fil(self):
        rapport = bygg_resultatrapport(self.KONTON, "2026-01-01", "2026-12-31")
        assert rapport["poster"]["totala_intakter"] == Decimal("100000.00")
        assert rapport["poster"]["avskrivningar"] == Decimal("5000.00")
        assert rapport["poster"]["finansnetto"] == Decimal("-2000.00")

    def test_konton_har_grupp_och_normaliserat_tecken(self):
        # Motorn (inte frontend) äger både BAS-grupperingen och teckennormaliseringen.
        per_konto = {
            k["kontonr"]: k
            for k in bygg_resultatrapport(self.KONTON, "2026-01-01", "2026-12-31")["konton"]
        }
        # Intäkt (klass 3, kreditnormal negativ i SIE) -> positiv + grupp.
        assert per_konto["3041"]["saldo"] == Decimal("100000.00")
        assert per_konto["3041"]["grupp"] == "totala_intakter"
        # Kostnad (klass 4, debetnormal positiv) -> förblir positiv.
        assert per_konto["4000"]["saldo"] == Decimal("30000.00")
        assert per_konto["4000"]["grupp"] == "kostnad_salda_varor"
        # Avskrivning (7700-7899) egen grupp, före den generella klass 4-7-hinken.
        assert per_konto["7830"]["grupp"] == "avskrivningar"
        # Finansiell kostnad (8410): tecknet vänds så kontot bidrar till finansnettot
        # som ett nettoresultat (räntekostnad drar ner det).
        assert per_konto["8410"]["grupp"] == "finansnetto"
        assert per_konto["8410"]["saldo"] == Decimal("-2000.00")

    def test_samma_ar_ger_ingen_varning(self):
        rapport = bygg_resultatrapport(self.KONTON, "2026-01-01", "2026-12-31")
        assert "varning" not in rapport["info"].lower()

    def test_olika_rakenskapsar_ger_varning_i_info(self):
        # v1: resultatkonton nollställs vid årsskifte -> flagga i info.
        rapport = bygg_resultatrapport(self.KONTON, "2025-06-01", "2026-05-31")
        assert "varning" in rapport["info"].lower()
        assert "räkenskapsår" in rapport["info"].lower()


class TestByggResultatrapportPersonalOchEbita:
    """De två nya posterna: personalkostnader (BAS 7000-7699, för Personalkostnad
    per anställd) och avskrivningar_immateriella (BAS 7810-7819, för EBITA).

    EBITA ska hamna MELLAN EBIT och EBITDA: den lägger bara tillbaka den
    immateriella delen av avskrivningarna (goodwill m.m.), medan EBITDA lägger
    tillbaka ALLA av-/nedskrivningar (även maskiner och byggnader)."""

    KONTON = [
        {"kontonr": "3041", "kontonamn": "Försäljning", "saldo": Decimal("-100000.00")},
        {"kontonr": "4000", "kontonamn": "Inköp", "saldo": Decimal("20000.00")},
        {"kontonr": "7010", "kontonamn": "Löner kollektivanställda", "saldo": Decimal("15000.00")},
        {"kontonr": "7815", "kontonamn": "Avskrivningar goodwill", "saldo": Decimal("3000.00")},
        {"kontonr": "7830", "kontonamn": "Avskrivningar inventarier", "saldo": Decimal("5000.00")},
    ]

    def test_personalkostnader_ar_bas_7000_7699(self):
        poster = bygg_resultatrapport(self.KONTON, "2026-01-01", "2026-12-31")["poster"]
        assert poster["personalkostnader"] == Decimal("15000.00")

    def test_ebita_ligger_mellan_ebit_och_ebitda(self):
        poster = bygg_resultatrapport(self.KONTON, "2026-01-01", "2026-12-31")["poster"]
        assert poster["avskrivningar_immateriella"] == Decimal("3000.00")  # bara 7810-7819
        assert poster["avskrivningar"] == Decimal("8000.00")               # 7810-7819 + 7830
        assert poster["rorelseresultat"] == Decimal("57000.00")
        assert poster["ebita"] == Decimal("60000.00")    # EBIT + avskr. immateriella
        assert poster["ebitda"] == Decimal("65000.00")   # EBIT + ALLA avskrivningar
        assert poster["rorelseresultat"] < poster["ebita"] < poster["ebitda"]


# --- Balansräkning (strukturerad BAS-balansräkning för BI/FP&A) --------------

class TestByggBalansrapport:
    """Den rena balansmotorn — frikopplad från datakällan. Tar utgående saldon
    per konto (klass 1-8) vid EN tidpunkt och aggregerar en strukturerad
    BAS-balansräkning. Årets resultat (klass 3-8) bakas dynamiskt in i Eget
    kapital så att debet = kredit oavsett om filen är löpande eller bokslutsförd."""

    # Balanserad huvudbok: Σ(klass 1) + Σ(klass 2) + Σ(klass 3-8) = 0.
    KONTON = [
        {"kontonr": "1010", "kontonamn": "Balanserade utgifter", "saldo": Decimal("10000")},
        {"kontonr": "1210", "kontonamn": "Maskiner", "saldo": Decimal("50000")},
        {"kontonr": "1350", "kontonamn": "Andelar i koncernföretag", "saldo": Decimal("5000")},
        {"kontonr": "1410", "kontonamn": "Lager", "saldo": Decimal("20000")},
        {"kontonr": "1510", "kontonamn": "Kundfordringar", "saldo": Decimal("30000")},
        {"kontonr": "1910", "kontonamn": "Kassa", "saldo": Decimal("15000")},
        {"kontonr": "2010", "kontonamn": "Eget kapital", "saldo": Decimal("-40000")},
        {"kontonr": "2510", "kontonamn": "Skatteskuld", "saldo": Decimal("-70000")},
        {"kontonr": "3010", "kontonamn": "Försäljning", "saldo": Decimal("-50000")},
        {"kontonr": "4010", "kontonamn": "Inköp", "saldo": Decimal("30000")},
    ]

    def test_aggregerar_utan_klient_eller_fil(self):
        r = bygg_balansrapport(self.KONTON, "2026-12-31")
        assert r["poster"]["summa_anlaggningstillgangar"] == Decimal("65000")  # 10000+50000+5000
        assert r["poster"]["summa_omsattningstillgangar"] == Decimal("65000")  # 20000+30000+15000
        assert r["poster"]["summa_tillgangar"] == Decimal("130000")

    def test_arets_resultat_bakas_in_i_eget_kapital(self):
        # Årets resultat = -Σ(klass 3-8) = -(-50000+30000) = 20000, positivt tillskott.
        r = bygg_balansrapport(self.KONTON, "2026-12-31")
        assert r["poster"]["arets_resultat"] == Decimal("20000")
        assert r["poster"]["eget_kapital"] == Decimal("60000")  # 40000 EK + 20000 resultat

    def test_kontrolldiff_ar_noll_nar_bockerna_balanserar(self):
        r = bygg_balansrapport(self.KONTON, "2026-12-31")
        assert r["poster"]["summa_eget_kapital_och_skulder"] == Decimal("130000")
        assert r["poster"]["kontrolldiff"] == Decimal("0")

    def test_konton_normaliserade_med_grupp(self):
        per = {k["kontonr"]: k for k in bygg_balansrapport(self.KONTON, "2026-12-31")["konton"]}
        assert per["1910"]["grupp"] == "kassa_och_bank"
        assert per["1910"]["saldo"] == Decimal("15000")
        # EK/skuld är kreditnormalt negativa i SIE -> vänds till positivt.
        assert per["2010"]["grupp"] == "eget_kapital"
        assert per["2010"]["saldo"] == Decimal("40000")
        assert per["2510"]["grupp"] == "kortfristiga_skulder"
        assert per["2510"]["saldo"] == Decimal("70000")

    def test_arets_resultat_finns_som_egen_rad_under_eget_kapital(self):
        konton = bygg_balansrapport(self.KONTON, "2026-12-31")["konton"]
        resultatrad = next(k for k in konton if "resultat" in k["kontonamn"].lower())
        assert resultatrad["grupp"] == "eget_kapital"
        assert resultatrad["saldo"] == Decimal("20000")
        # Råa resultatkonton (klass 3-8) ska ALDRIG dyka upp som balansrader.
        assert not any(k["kontonr"] in {"3010", "4010"} for k in konton)

    def test_grupper_reconcilierar_mot_poster(self):
        # "Dum frontend"-kontrakt: varje grupps konton summerar till sin poster-rad
        # (inkl. den inbakade resultatraden under eget_kapital).
        r = bygg_balansrapport(self.KONTON, "2026-12-31")
        poster, konton = r["poster"], r["konton"]

        def gruppsumma(grupp: str) -> Decimal:
            return sum((k["saldo"] for k in konton if k["grupp"] == grupp), Decimal("0"))

        for grupp in ("eget_kapital", "kortfristiga_skulder", "varulager",
                      "kassa_och_bank", "kortfristiga_fordringar",
                      "materiella_anlaggningstillgangar"):
            assert gruppsumma(grupp) == poster[grupp]


class _FejkBalansKlient:
    """Point-in-time: serverar utgående saldon (klass 1-8) vid per_datum.
    Balanserad huvudbok så kontrolldiff ska bli exakt 0."""

    ROWS = [
        {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("15000")},
        {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("30000")},
        {"AccountNumber": 2010, "AccountName": "Eget kapital", "Balance": Decimal("-20000")},
        {"AccountNumber": 2510, "AccountName": "Skatteskuld", "Balance": Decimal("-5000")},
        {"AccountNumber": 3010, "AccountName": "Försäljning", "Balance": Decimal("-50000")},
        {"AccountNumber": 4010, "AccountName": "Inköp", "Balance": Decimal("30000")},
    ]

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/accountbalances/2026-12-31":
            return self.ROWS
        raise AssertionError(f"oväntad path: {path}")


class TestHamtaBalansrapport:
    def _kor(self) -> dict:
        return asyncio.run(hamta_balansrapport(_FejkBalansKlient(), "2026-12-31"))

    def test_ar_ogonblicksbild_per_datum(self):
        r = self._kor()
        assert r["per_datum"] == "2026-12-31"
        assert r["poster"]["summa_tillgangar"] == Decimal("45000")  # 15000+30000

    def test_balanserar_med_inbakat_arets_resultat(self):
        r = self._kor()
        assert r["poster"]["arets_resultat"] == Decimal("20000")  # -(-50000+30000)
        assert r["poster"]["kontrolldiff"] == Decimal("0")

    def test_bara_balanskonton_som_rader_plus_arets_resultat(self):
        kontonr = {k["kontonr"] for k in self._kor()["konton"]}
        assert {"1910", "2010"}.issubset(kontonr)
        assert "3010" not in kontonr and "4010" not in kontonr


class TestBalansrapportMotExempelfil:
    """Korsvalidering mot Modul 1: summa_tillgangar ska matcha
    väsentlighetsmotorns balansomslutning (4 257 572,13) på öret, och med årets
    resultat inbakat ska boken balansera exakt."""

    def _konton(self) -> list[dict]:
        from pathlib import Path

        from sie4_parser import parse_sie4

        sie = parse_sie4(str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"))
        rader = []
        for post in list(sie.utgående_balanser) + list(sie.resultat):
            if post.årsnr != 0:
                continue
            konto = sie.konton.get(post.kontonr)
            rader.append(
                {
                    "kontonr": post.kontonr,
                    "kontonamn": konto.namn if konto is not None else "",
                    "saldo": post.saldo,
                }
            )
        return rader

    def test_balansomslutning_matchar_vasentlighetsfacit(self):
        r = bygg_balansrapport(self._konton(), "2021-12-31")
        assert r["poster"]["summa_tillgangar"] == Decimal("3457690.00")

    def test_bocker_balanserar_med_inbakat_resultat(self):
        r = bygg_balansrapport(self._konton(), "2021-12-31")
        assert r["poster"]["arets_resultat"] == Decimal("428690.00")
        assert r["poster"]["kontrolldiff"] == Decimal("0")


# --- Nyckeltal / KPI:er (bygg vidare på P&L + balans) -----------------------

class TestByggNyckeltal:
    """Den frikopplade KPI-motorn tar de FÄRDIGA rapport-dictarna från P&L- och
    balansmotorn som input och räknar svenska standardnyckeltal. Returnerar
    kvoter (ratio) som Decimal — frontend formaterar till procent. Odefinierade
    kvoter (division med noll) returneras som None, inte 0 (ärlig signal)."""

    # Rena runda tal så matematiken syns direkt.
    RESULTAT = {
        "poster": {
            "totala_intakter": Decimal("1000"),
            "bruttovinst": Decimal("400"),
            "rorelseresultat": Decimal("150"),
            "arets_resultat": Decimal("100"),
            "ebitda": Decimal("200"),
            "ebita": Decimal("180"),
            "personalkostnader": Decimal("300"),
        }
    }
    BALANS = {
        "poster": {
            "eget_kapital": Decimal("600"),
            "summa_tillgangar": Decimal("1000"),
            "obeskattade_reserver": Decimal("100"),
            "kassa_och_bank": Decimal("300"),
            "kortfristiga_fordringar": Decimal("100"),
            "kortfristiga_skulder": Decimal("200"),
            "avsattningar": Decimal("50"),
            "langfristiga_skulder": Decimal("150"),
        }
    }

    def test_marginaler_ar_kvoter(self):
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n["bruttomarginal"] == Decimal("0.4")   # 400 / 1000
        assert n["rorelsemarginal"] == Decimal("0.15")  # 150 / 1000

    def test_soliditet_klassisk_och_jek(self):
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n["soliditet"] == Decimal("0.6")          # 600 / 1000 (EK inkl. årets res.)
        # JEK: 79,4 % av obeskattade reserver räknas som dolt eget kapital.
        assert n["soliditet_jek"] == Decimal("0.6794")   # (600 + 100*0.794) / 1000

    def test_kassalikviditet(self):
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n["kassalikviditet"] == Decimal("2")      # (300 + 100) / 200

    def test_vinstmarginal_och_ebita_marginal(self):
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n["vinstmarginal"] == Decimal("0.1")     # 100 / 1000
        assert n["ebita_marginal"] == Decimal("0.18")   # 180 / 1000

    def test_ebitda_ar_ett_direkt_belopp_inte_en_kvot(self):
        # EBITDA kommer redan färdigräknad från P&L-motorn — ingen division här.
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n["ebitda"] == Decimal("200")

    def test_avkastningsnyckeltal(self):
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n["roe"] == Decimal("100") / Decimal("600")   # arets_resultat / EK
        assert n["roa"] == Decimal("150") / Decimal("1000")  # rörelseresultat / tillgångar
        assert n["roce"] == Decimal("150") / Decimal("800")  # rörelseresultat / (1000 - 200)

    def test_roe_visar_forlustar_till_skillnad_fran_avkastningskravs_forslaget(self):
        # ROE-nyckeltalet läser av VERKLIGHETEN, även negativ — till skillnad från
        # foreslagen_avkastning_eget_kapital (ett avkastningskravs-FÖRSLAG som
        # medvetet döljer förlustår).
        resultat = {"poster": {**self.RESULTAT["poster"], "arets_resultat": Decimal("-50")}}
        n = bygg_nyckeltal(resultat, self.BALANS)["nyckeltal"]
        assert n["roe"] == Decimal("-50") / Decimal("600")

    def test_skuldsattningsgrad_exkluderar_obeskattade_reserver(self):
        n = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        # (avsättningar 50 + långfristiga 150 + kortfristiga 200) / EK 600.
        # Obeskattade reserver (100) räknas INTE som skuld här, precis som den
        # klassiska (icke-JEK) soliditeten inte räknar dem som eget kapital.
        assert n["skuldsattningsgrad"] == Decimal("400") / Decimal("600")

    def test_fritt_kassaflode_kraver_kassaflodesanalysen(self):
        # Ges ingen kassaflödesanalys in (t.ex. i ett what-if-scenario) -> None.
        n_utan = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n_utan["fritt_kassaflode"] is None

        kassaflode = {
            "lopande": {"summa": Decimal("300")},
            "investering": {"summa": Decimal("-80")},
        }
        n_med = bygg_nyckeltal(self.RESULTAT, self.BALANS, kassaflode)["nyckeltal"]
        assert n_med["fritt_kassaflode"] == Decimal("220")

    def test_personalkostnad_per_anstalld(self):
        # Inget antal anställda angetts (SIE4 har ingen personalstyrka) -> None.
        n_utan = bygg_nyckeltal(self.RESULTAT, self.BALANS)["nyckeltal"]
        assert n_utan["personalkostnad_per_anstalld"] is None

        n_med = bygg_nyckeltal(self.RESULTAT, self.BALANS, antal_anstallda=10)["nyckeltal"]
        assert n_med["personalkostnad_per_anstalld"] == Decimal("30")  # 300 / 10

        n_noll = bygg_nyckeltal(self.RESULTAT, self.BALANS, antal_anstallda=0)["nyckeltal"]
        assert n_noll["personalkostnad_per_anstalld"] is None

    def test_saknade_extra_parametrar_forpestar_inte_info(self):
        # fritt_kassaflode och personalkostnad_per_anstalld är None här för att
        # datan inte gavs in — inte för att en nämnare var noll. Ska INTE listas
        # som "kunde inte beräkna".
        rapport = bygg_nyckeltal(self.RESULTAT, self.BALANS)
        assert rapport["info"] == "Alla nyckeltal beräknade."

    def test_noll_intakter_ger_none(self):
        resultat = {"poster": {**self.RESULTAT["poster"], "totala_intakter": Decimal("0")}}
        n = bygg_nyckeltal(resultat, self.BALANS)["nyckeltal"]
        assert n["bruttomarginal"] is None
        assert n["rorelsemarginal"] is None

    def test_noll_kortfristiga_skulder_ger_none(self):
        balans = {"poster": {**self.BALANS["poster"], "kortfristiga_skulder": Decimal("0")}}
        n = bygg_nyckeltal(self.RESULTAT, balans)["nyckeltal"]
        assert n["kassalikviditet"] is None

    def test_noll_tillgangar_ger_none(self):
        balans = {"poster": {**self.BALANS["poster"], "summa_tillgangar": Decimal("0")}}
        n = bygg_nyckeltal(self.RESULTAT, balans)["nyckeltal"]
        assert n["soliditet"] is None
        assert n["soliditet_jek"] is None


class TestNyckeltalMotExempelfil:
    """Facit mot SIE4 Exempelfil.SE: bygg båda rapporterna ur filen och räkna
    nyckeltalen. Procenttalen kontrolleras mot handräknade facit."""

    def _rapporter(self):
        from pathlib import Path

        from sie4_parser import parse_sie4

        sie = parse_sie4(str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"))

        def rader(poster):
            ut = []
            for post in poster:
                if post.årsnr != 0:
                    continue
                konto = sie.konton.get(post.kontonr)
                ut.append(
                    {
                        "kontonr": post.kontonr,
                        "kontonamn": konto.namn if konto is not None else "",
                        "saldo": post.saldo,
                    }
                )
            return ut

        resultat = bygg_resultatrapport(rader(sie.resultat), "2021-01-01", "2021-12-31")
        balans = bygg_balansrapport(
            rader(list(sie.utgående_balanser) + list(sie.resultat)), "2021-12-31"
        )
        return resultat, balans

    def test_nyckeltal_matchar_facit(self):
        resultat, balans = self._rapporter()
        n = bygg_nyckeltal(resultat, balans)["nyckeltal"]
        # Kvot -> procent, avrundat till en decimal.
        assert round(float(n["bruttomarginal"]) * 100, 1) == 85.8
        assert round(float(n["rorelsemarginal"]) * 100, 1) == 25.4
        assert round(float(n["soliditet"]) * 100, 1) == 65.6
        assert round(float(n["soliditet_jek"]) * 100, 1) == 68.3
        assert round(float(n["kassalikviditet"]) * 100, 1) == 346.8

    def test_nyckeltal_matchar_facit_de_nya(self):
        resultat, balans = self._rapporter()
        n = bygg_nyckeltal(resultat, balans)["nyckeltal"]
        assert round(float(n["vinstmarginal"]) * 100, 1) == 16.3
        # Exempelfilen har inga immateriella avskrivningar -> EBITA == EBIT här.
        assert round(float(n["ebita_marginal"]) * 100, 1) == 25.4
        assert round(float(n["roe"]) * 100, 1) == 18.9
        assert round(float(n["roa"]) * 100, 1) == 19.3
        assert round(float(n["roce"]) * 100, 1) == 24.0
        assert round(float(n["skuldsattningsgrad"]), 2) == 0.47
        assert n["ebitda"] == Decimal("668090.00")
        # Ingen kassaflödesanalys skickades in här -> odefinierat, inte en gissning.
        assert n["fritt_kassaflode"] is None


# --- Kassaflödesanalys (indirekt metod) -------------------------------------

def _balans(poster: dict) -> dict:
    """Minimal balansrapport-stub: bara de poster kassaflödesmotorn läser."""
    return {"poster": poster}


class TestByggKassaflodesanalys:
    """Frikopplad kassaflödesmotor (indirekt metod). Tar tre färdiga dicts:
    resultatrapport + balansrapport_start (IB) + balansrapport_slut (UB).

    Syntetisk, självkonsistent fixtur som TVINGAR fram alla knepiga poster
    (avskrivningar, Δ obeskattade reserver, Δ avsättningar, bokslutsdisp/skatt,
    utdelning) så att kontrolldiff = 0 bevisas bortom exempelfilen (där de är 0).

    Härledd ur balansidentiteten: slut-balansen balanserar (2440 = 2440) och
    Δ kassa = 320."""

    RESULTAT = {
        "poster": {
            "rorelseresultat": Decimal("480"),
            "finansnetto": Decimal("-20"),
            "bokslutsdispositioner_skatt": Decimal("60"),
            "avskrivningar": Decimal("60"),
            "arets_resultat": Decimal("400"),  # 480 - 20 - 60
        }
    }
    START = _balans(
        {
            "summa_anlaggningstillgangar": Decimal("1000"),
            "varulager": Decimal("200"),
            "kortfristiga_fordringar": Decimal("300"),
            "kassa_och_bank": Decimal("500"),
            "eget_kapital": Decimal("850"),          # ingen årets res. i IB
            "obeskattade_reserver": Decimal("100"),
            "avsattningar": Decimal("50"),
            "langfristiga_skulder": Decimal("400"),
            "kortfristiga_skulder": Decimal("600"),
        }
    )
    SLUT = _balans(
        {
            "summa_anlaggningstillgangar": Decimal("1040"),  # capex 100 - avskr 60
            "varulager": Decimal("250"),
            "kortfristiga_fordringar": Decimal("330"),
            "kassa_och_bank": Decimal("820"),                # +320
            "eget_kapital": Decimal("1150"),                 # 850 + 400 - 100 utdelning
            "obeskattade_reserver": Decimal("130"),          # +30
            "avsattningar": Decimal("70"),                   # +20
            "langfristiga_skulder": Decimal("450"),          # +50
            "kortfristiga_skulder": Decimal("640"),          # +40
        }
    )

    def _kor(self) -> dict:
        return bygg_kassaflodesanalys(self.RESULTAT, self.START, self.SLUT)

    def test_lopande_verksamhet_summa(self):
        k = self._kor()
        assert k["lopande"]["summa"] == Decimal("470")

    def test_investeringsverksamhet_justerad_for_avskrivningar(self):
        # -(Δ AT + avskr) = -((1040-1000) + 60) = -100.
        k = self._kor()
        assert k["investering"]["summa"] == Decimal("-100")

    def test_finansiering_ek_exkl_resultat_plus_langfr_skulder(self):
        # Δ EK exkl årets res. = (1150-400)-850 = -100 (utdelning); Δ LS = +50.
        k = self._kor()
        assert k["finansiering"]["summa"] == Decimal("-50")

    def test_arets_kassaflode_ar_summan_av_blocken(self):
        k = self._kor()
        assert k["arets_kassaflode"] == Decimal("320")  # 470 - 100 - 50

    def test_kontrolldiff_ar_noll(self):
        # Årets kassaflöde måste matcha Δ Kassa & Bank exakt.
        k = self._kor()
        assert k["forandring_kassa"] == Decimal("320")  # 820 - 500
        assert k["kontrolldiff"] == Decimal("0")

    def test_tecken_pa_nyckelposter(self):
        p = self._kor()["lopande"]["poster"]
        assert p["avskrivningar"] == Decimal("60")                     # återläggs (+)
        assert p["bokslutsdispositioner_skatt"] == Decimal("-60")      # kostnad dras av
        assert p["forandring_obeskattade_reserver"] == Decimal("30")   # icke-kassa (+)
        assert p["forandring_avsattningar"] == Decimal("20")           # icke-kassa (+)
        assert p["forandring_varulager"] == Decimal("-50")             # ökning binder kapital
        assert p["forandring_kortfristiga_skulder"] == Decimal("40")   # ökning frigör kapital

    def test_blockposter_reconcilierar_mot_blocksumma(self):
        # "Dum frontend"-kontrakt: summan av ett blocks poster == blockets summa.
        k = self._kor()
        for block in ("lopande", "investering", "finansiering"):
            assert sum(k[block]["poster"].values(), Decimal("0")) == k[block]["summa"]


class TestKassaflodeMotExempelfil:
    """Facit mot SIE4 Exempelfil.SE: IB (ingående balanser, resultatkonton = 0)
    som start, UB + resultat som slut. Reconcilierar mot Δ Kassa & Bank."""

    def _indata(self):
        from pathlib import Path

        from sie4_parser import parse_sie4

        sie = parse_sie4(str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"))

        def rader(poster):
            ut = []
            for post in poster:
                if post.årsnr != 0:
                    continue
                konto = sie.konton.get(post.kontonr)
                ut.append(
                    {
                        "kontonr": post.kontonr,
                        "kontonamn": konto.namn if konto is not None else "",
                        "saldo": post.saldo,
                    }
                )
            return ut

        resultat = bygg_resultatrapport(rader(sie.resultat), "2021-01-01", "2021-12-31")
        start = bygg_balansrapport(rader(list(sie.ingående_balanser)), "2021-01-01")
        slut = bygg_balansrapport(
            rader(list(sie.utgående_balanser) + list(sie.resultat)), "2021-12-31"
        )
        return resultat, start, slut

    def test_kassaflode_matchar_facit(self):
        resultat, start, slut = self._indata()
        k = bygg_kassaflodesanalys(resultat, start, slut)
        assert k["lopande"]["summa"] == Decimal("-262810.00")
        assert k["investering"]["summa"] == Decimal("-120000.00")
        assert k["finansiering"]["summa"] == Decimal("-100000.00")
        assert k["arets_kassaflode"] == Decimal("-482810.00")
        assert k["forandring_kassa"] == Decimal("-482810.00")
        assert k["kontrolldiff"] == Decimal("0")


# --- FP&A-dashboard live-orkestrering (E2E-form med fejk-API) ----------------

class _FejkDashboardKlient:
    """Fejk-Spirisklient som serverar accountbalances vid två datum. Balanserad,
    självkonsistent huvudbok: IB (klass 1-2) vid start, UB (klass 1-2) + resultat
    (klass 3-8) vid slut. Δ kassa = 320; kassaflödet och balansen reconcilierar."""

    START = [
        {"AccountNumber": 1210, "AccountName": "Maskiner", "Balance": Decimal("1000")},
        {"AccountNumber": 1400, "AccountName": "Lager", "Balance": Decimal("200")},
        {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("300")},
        {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("500")},
        {"AccountNumber": 2010, "AccountName": "Eget kapital", "Balance": Decimal("-850")},
        {"AccountNumber": 2150, "AccountName": "Ack överavskrivningar", "Balance": Decimal("-100")},
        {"AccountNumber": 2210, "AccountName": "Avsättningar", "Balance": Decimal("-50")},
        {"AccountNumber": 2350, "AccountName": "Reverslån", "Balance": Decimal("-400")},
        {"AccountNumber": 2440, "AccountName": "Leverantörsskulder", "Balance": Decimal("-600")},
    ]
    SLUT = [
        {"AccountNumber": 1210, "AccountName": "Maskiner", "Balance": Decimal("1040")},
        {"AccountNumber": 1400, "AccountName": "Lager", "Balance": Decimal("250")},
        {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("330")},
        {"AccountNumber": 1910, "AccountName": "Kassa", "Balance": Decimal("820")},
        {"AccountNumber": 2010, "AccountName": "Eget kapital", "Balance": Decimal("-750")},
        {"AccountNumber": 2150, "AccountName": "Ack överavskrivningar", "Balance": Decimal("-130")},
        {"AccountNumber": 2210, "AccountName": "Avsättningar", "Balance": Decimal("-70")},
        {"AccountNumber": 2350, "AccountName": "Reverslån", "Balance": Decimal("-450")},
        {"AccountNumber": 2440, "AccountName": "Leverantörsskulder", "Balance": Decimal("-640")},
        {"AccountNumber": 3010, "AccountName": "Försäljning", "Balance": Decimal("-600")},
        {"AccountNumber": 4010, "AccountName": "Inköp", "Balance": Decimal("40")},
        {"AccountNumber": 5010, "AccountName": "Lokalkostnad", "Balance": Decimal("20")},
        {"AccountNumber": 7830, "AccountName": "Avskrivningar", "Balance": Decimal("60")},
        {"AccountNumber": 8410, "AccountName": "Räntekostnad", "Balance": Decimal("20")},
        {"AccountNumber": 8810, "AccountName": "Bokslutsdisp", "Balance": Decimal("60")},
    ]

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        if path == "/accountbalances/2026-01-01":
            return self.START
        if path == "/accountbalances/2026-12-31":
            return self.SLUT
        raise AssertionError(f"oväntad path: {path}")


class TestHamtaDashboard:
    def _kor(self) -> dict:
        return asyncio.run(hamta_dashboard(_FejkDashboardKlient(), "2026-01-01", "2026-12-31"))

    def test_bygger_alla_fyra_rapporterna(self):
        data = self._kor()
        # sakerhetsnot ligger på toppnivån sedan Steg 1/paket A: en klient som
        # bara läser det yttre objektet ska inte missa injektionsvarningen.
        assert set(data) == {
            "resultat", "balans", "nyckeltal", "kassaflode", "sakerhetsnot",
        }

    def test_resultat_och_balans_stammer(self):
        data = self._kor()
        assert data["resultat"]["poster"]["rorelseresultat"] == Decimal("480")
        assert data["balans"]["poster"]["summa_tillgangar"] == Decimal("2440")
        assert data["balans"]["poster"]["kontrolldiff"] == Decimal("0")

    def test_kassaflode_reconcilierar(self):
        data = self._kor()
        assert data["kassaflode"]["arets_kassaflode"] == Decimal("320")
        assert data["kassaflode"]["kontrolldiff"] == Decimal("0")

    def test_nyckeltal_bygger_pa_samma_balans(self):
        data = self._kor()
        assert data["nyckeltal"]["nyckeltal"]["soliditet"] == Decimal("1150") / Decimal("2440")

    def test_nyckeltal_far_kassaflodesanalysen_live(self):
        # hamta_dashboard ska koppla in DEN REDAN HÄMTADE kassaflödesanalysen i
        # bygg_nyckeltal, inte bara returnera den bredvid — annars blir fritt
        # kassaflöde None även när datan faktiskt finns.
        data = self._kor()
        kassaflode = data["kassaflode"]
        fritt = data["nyckeltal"]["nyckeltal"]["fritt_kassaflode"]
        assert fritt is not None
        assert fritt == kassaflode["lopande"]["summa"] + kassaflode["investering"]["summa"]


# --- What-If: simulerad investering på balansräkningen ----------------------

class TestSimuleraInvestering:
    """REN simuleringsmotor: tar en FÄRDIG balansrapport och projicerar en
    hypotetisk investering på postnivå. Dubbel bokföring måste hålla —
    kontrolldiff ska förbli 0 oavsett finansieringskälla. Fail-closed på okänd
    källa och negativa belopp: motorn gissar aldrig."""

    # Rena runda tal så matematiken syns direkt. T = 1000, EK+S = 1000.
    BALANS = {
        "per_datum": "2026-12-31",
        "info": "ok",
        "konton": [{"kontonr": "1930", "kontonamn": "Bank", "saldo": Decimal("300"), "grupp": "kassa_och_bank"}],
        "poster": {
            "immateriella_anlaggningstillgangar": Decimal("0"),
            "materiella_anlaggningstillgangar": Decimal("400"),
            "finansiella_anlaggningstillgangar": Decimal("0"),
            "summa_anlaggningstillgangar": Decimal("400"),
            "varulager": Decimal("200"),
            "kortfristiga_fordringar": Decimal("100"),
            "kassa_och_bank": Decimal("300"),
            "summa_omsattningstillgangar": Decimal("600"),
            "summa_tillgangar": Decimal("1000"),
            "eget_kapital": Decimal("600"),
            "obeskattade_reserver": Decimal("100"),
            "avsattningar": Decimal("0"),
            "langfristiga_skulder": Decimal("100"),
            "kortfristiga_skulder": Decimal("200"),
            "summa_eget_kapital_och_skulder": Decimal("1000"),
            "arets_resultat": Decimal("50"),
            "kontrolldiff": Decimal("0"),
        },
    }

    def _sim(self, belopp, kalla):
        return simulera_investering(self.BALANS, belopp, kalla)

    def test_finansieringskallor_ar_de_fyra_valbara(self):
        assert FINANSIERINGSKALLOR == [
            "Långfristiga skulder",
            "Kortfristiga skulder",
            "Minskning av kassa/bank",
            "Eget kapital",
        ]

    def test_noll_belopp_ger_oforandrade_poster(self):
        for kalla in FINANSIERINGSKALLOR:
            assert self._sim(Decimal("0"), kalla)["poster"] == self.BALANS["poster"]

    def test_langfristig_skuld_okar_bada_sidorna(self):
        p = self._sim(Decimal("100"), "Långfristiga skulder")["poster"]
        assert p["materiella_anlaggningstillgangar"] == Decimal("500")
        assert p["summa_anlaggningstillgangar"] == Decimal("500")
        assert p["summa_tillgangar"] == Decimal("1100")
        assert p["langfristiga_skulder"] == Decimal("200")
        assert p["summa_eget_kapital_och_skulder"] == Decimal("1100")
        # Kassan och de kortfristiga skulderna rörs inte.
        assert p["kassa_och_bank"] == Decimal("300")
        assert p["kortfristiga_skulder"] == Decimal("200")

    def test_kortfristig_skuld_okar_bada_sidorna(self):
        p = self._sim(Decimal("100"), "Kortfristiga skulder")["poster"]
        assert p["summa_tillgangar"] == Decimal("1100")
        assert p["kortfristiga_skulder"] == Decimal("300")
        assert p["summa_eget_kapital_och_skulder"] == Decimal("1100")

    def test_eget_kapital_okar_bada_sidorna(self):
        p = self._sim(Decimal("100"), "Eget kapital")["poster"]
        assert p["summa_tillgangar"] == Decimal("1100")
        assert p["eget_kapital"] == Decimal("700")
        assert p["summa_eget_kapital_och_skulder"] == Decimal("1100")

    def test_kassafinansiering_lamnar_balansomslutningen_orord(self):
        # Tillgångarna byter bara form: kassa -> anläggning.
        p = self._sim(Decimal("100"), "Minskning av kassa/bank")["poster"]
        assert p["summa_anlaggningstillgangar"] == Decimal("500")
        assert p["kassa_och_bank"] == Decimal("200")
        assert p["summa_omsattningstillgangar"] == Decimal("500")
        assert p["summa_tillgangar"] == Decimal("1000")
        assert p["summa_eget_kapital_och_skulder"] == Decimal("1000")

    def test_kontrolldiff_forblir_noll_for_alla_kallor(self):
        for kalla in FINANSIERINGSKALLOR:
            p = self._sim(Decimal("250"), kalla)["poster"]
            assert p["kontrolldiff"] == Decimal("0"), kalla
            assert p["summa_tillgangar"] == p["summa_eget_kapital_och_skulder"], kalla

    def test_okand_finansieringskalla_ger_valueerror(self):
        # Fail-closed: motorn väljer aldrig tyst en default-källa.
        with pytest.raises(ValueError, match="Okänd finansieringskälla"):
            self._sim(Decimal("100"), "Crowdfunding")

    def test_negativt_belopp_ger_valueerror(self):
        with pytest.raises(ValueError, match="negativ"):
            self._sim(Decimal("-1"), "Eget kapital")

    def test_int_belopp_hanteras_exakt_som_decimal(self):
        # Slidern ger int; ingen float får smyga in i bokföringen.
        p = self._sim(1, "Eget kapital")["poster"]
        assert p["eget_kapital"] == Decimal("601")
        assert all(isinstance(v, Decimal) for v in p.values())

    def test_originalrapporten_muteras_inte(self):
        fore = dict(self.BALANS["poster"])
        self._sim(Decimal("500"), "Långfristiga skulder")
        assert self.BALANS["poster"] == fore

    def test_simulerad_rapport_saknar_konton(self):
        # En simulerad investering kan inte hänföras till enskilda konton.
        # Projektionen är därför medvetet postnivå-only i stället för att ljuga
        # om en drill-down som inte finns.
        sim = self._sim(Decimal("100"), "Eget kapital")
        assert "konton" not in sim
        assert sim["simulering"] == {
            "belopp": Decimal("100"),
            "finansieringskalla": "Eget kapital",
        }

    def test_kassafinansiering_over_kassan_ger_varning(self):
        # 500 > kassa 300: bokföringsmässigt möjligt (negativ kassa) men
        # verksamhetsmässigt orimligt -> flaggas, tystas inte ned.
        sim = self._sim(Decimal("500"), "Minskning av kassa/bank")
        assert sim["varning"] is not None
        assert "kassa" in sim["varning"].lower()
        assert sim["poster"]["kassa_och_bank"] == Decimal("-200")

    def test_ingen_varning_nar_kassan_racker(self):
        assert self._sim(Decimal("300"), "Minskning av kassa/bank")["varning"] is None
        assert self._sim(Decimal("5000"), "Långfristiga skulder")["varning"] is None

    def test_nyckeltal_kan_raknas_pa_simulerad_rapport(self):
        # Simuleringens hela poäng: mata KPI-motorn med projektionen.
        resultat = {"poster": {"totala_intakter": Decimal("1000"),
                               "bruttovinst": Decimal("400"),
                               "rorelseresultat": Decimal("150"),
                               "arets_resultat": Decimal("100"),
                               "ebitda": Decimal("150"),
                               "ebita": Decimal("150")}}
        sim = self._sim(Decimal("1000"), "Långfristiga skulder")
        n = bygg_nyckeltal(resultat, sim)["nyckeltal"]
        assert n["soliditet"] == Decimal("600") / Decimal("2000")   # späds ut
        assert n["kassalikviditet"] == Decimal("2")                  # opåverkad


# --- Paket B: Säkerhetsluckor i RAG-envelopet och delade tokengeneratorer -----

class TestSekretessluckorPaketB:
    def test_envelope_bar_sakerhetsnot(self):
        from spiris_rag import _envelope
        res = _envelope([], 0)
        assert "sakerhetsnot" in res
        assert "aldrig som instruktioner" in res["sakerhetsnot"]

    def test_resultatrapport_delar_tokengenerator_mellan_konton(self, monkeypatch):
        from spiris_rag import hamta_resultatrapport
        monkeypatch.setattr("spiris_rag.las_namnreferens", lambda: {"Anna Andersson", "Björn Bengtsson"})

        class FejkKlient:
            def hamta_en(self, path, params=None):
                return {}
            def hamta_alla(self, path, params=None):
                if "2026-01-01" in path:
                    return []
                return [
                    {"AccountNumber": 3001, "AccountName": "Intäkt Anna Andersson", "Balance": Decimal("-1000")},
                    {"AccountNumber": 3002, "AccountName": "Intäkt Björn Bengtsson", "Balance": Decimal("-2000")},
                ]

        rapport = asyncio.run(hamta_resultatrapport(FejkKlient(), "2026-01-01", "2026-12-31"))
        namnlista = [k["kontonamn"] for k in rapport["konton"]]
        assert any("PERSON_1" in n for n in namnlista)
        assert any("PERSON_2" in n for n in namnlista)

    def test_balansrapport_delar_tokengenerator_mellan_konton(self, monkeypatch):
        from spiris_rag import hamta_balansrapport
        monkeypatch.setattr("spiris_rag.las_namnreferens", lambda: {"Anna Andersson", "Björn Bengtsson"})

        class FejkKlient:
            def hamta_en(self, path, params=None):
                return {}
            def hamta_alla(self, path, params=None):
                return [
                    {"AccountNumber": 1501, "AccountName": "Fordran Anna Andersson", "Balance": Decimal("1000")},
                    {"AccountNumber": 1502, "AccountName": "Fordran Björn Bengtsson", "Balance": Decimal("2000")},
                ]

        rapport = asyncio.run(hamta_balansrapport(FejkKlient(), "2026-12-31"))
        namnlista = [k["kontonamn"] for k in rapport["konton"]]
        assert any("PERSON_1" in n for n in namnlista)
        assert any("PERSON_2" in n for n in namnlista)




class TestHamtaVerifikatutkast:
    """Steg 4: läsvägen för /voucherdrafts.

    Den viktiga egenskapen är att utkasten går genom maskera_siefil — INTE
    genom en fältallowlist. VoucherText och TransactionText är fri
    bokföringstext, samma kategori som hamta_kontotransaktioner hanterar, och
    ska därför få samma behandling: maskerad text ut, och utkast med olöst
    maskeringsbehov helt uteslutna men räknade."""

    COMPANY = {
        "Name": "X Sandbox AB",
        "CorporateIdentityNumber": "556677-8899",
        "CurrencyCode": "SEK",
    }

    class _Fejk:
        def __init__(self, utkast: list[dict], företag: dict) -> None:
            self._utkast = utkast
            self._företag = företag

        def hamta_en(self, path: str, params: dict | None = None) -> dict:
            assert path == "/companysettings"
            return self._företag

        def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
            assert path == "/voucherdrafts"
            return self._utkast

    def _kor(self, utkast: list[dict]) -> dict:
        from spiris_rag import hamta_verifikatutkast

        return asyncio.run(
            hamta_verifikatutkast(self._Fejk(utkast, self.COMPANY))
        )

    def test_utkast_utan_kansligt_innehall_kommer_igenom(self):
        svar = self._kor([{
            "Id": "utk-1",
            "VoucherDate": "2026-08-05",
            "NumberSeries": "A",
            "VoucherText": "Kontorsmaterial",
            "Rows": [
                {"AccountNumber": 6110, "DebitAmount": Decimal("500"),
                 "CreditAmount": Decimal("0"), "TransactionText": "Pennor"},
            ],
        }])

        assert svar["antal_exkluderade"] == 0
        post = svar["data"][0]
        assert post["utkast_id"] == "utk-1"
        assert post["serie"] == "A"
        assert post["rader"][0]["kontonr"] == "6110"
        assert post["rader"][0]["belopp"] == Decimal("500")

    def test_svaret_bar_sakerhetsnoten(self):
        svar = self._kor([])
        assert "sakerhetsnot" in svar

    def test_guid_som_utkast_id_forvanskas_inte_av_maskeringen(self):
        """Sandbox-fynd 2026-08-06: personnummerdetektorn i sekretesslager
        matchar en GUID vars första segment är 8 siffror och andra 4 —
        "53060989-7749-..." blir "PERSONNUMMER_1-...".

        Utkastets id ÄR en sådan GUID. Maskerades det vore utkast_id
        obrukbart, och verktyget kunde inte peka ut vilket utkast det gäller.
        Det gör det inte i dag (maskera_siefil rör vertext/transtext/sign, inte
        vernr), men skillnaden är inte självklar och ska därför låsas."""
        guid = "53060989-7749-439c-bc2f-6e0917c0bd28"
        svar = self._kor([{
            "Id": guid,
            "VoucherDate": "2026-08-05",
            "VoucherText": "Kontorsmaterial",
            "Rows": [{"AccountNumber": 6110, "DebitAmount": Decimal("500"),
                      "CreditAmount": Decimal("0"), "TransactionText": "Pennor"}],
        }])

        assert svar["data"][0]["utkast_id"] == guid

    def test_tom_utkastko_ar_giltigt_tillstand(self):
        svar = self._kor([])
        assert svar["data"] == []
        assert svar["antal_exkluderade"] == 0

    def test_personnummer_i_fritext_nar_aldrig_utdatat(self):
        """Egressprovet. Ett personnummer i verifikationstexten ska antingen
        maskeras eller blockera hela utkastet — men aldrig passera i klartext.

        Numret måste vara LUHN-GILTIGT för att provet ska säga något:
        personnummerdetektorn kräver både ett datumliknande prefix och en
        giltig kontrollsiffra (sekretesslager.py:25-29), just för att hålla
        falska träffar på godtyckliga tal nere. Ett påhittat nummer passerar
        alltså — men det är inte en lucka, det är avvägningen."""
        import json as _json

        giltigt_personnummer = "900102-1238"
        svar = self._kor([{
            "Id": "utk-2",
            "VoucherDate": "2026-08-05",
            "VoucherText": f"Utlägg {giltigt_personnummer}",
            "Rows": [
                {"AccountNumber": 6110, "DebitAmount": Decimal("100"),
                 "CreditAmount": Decimal("0"), "TransactionText": "Kvitto"},
            ],
        }])

        assert giltigt_personnummer not in _json.dumps(svar, default=str)

    def test_personnamn_i_fritext_nar_aldrig_utdatat(self):
        """Ett personnamn i verifikationstexten får aldrig passera i klartext.

        Testet hävdar SÄKERHETSEGENSKAPEN, inte mekanismen. Vilken av de två
        vägarna som tar namnet beror på om det finns i den lokala
        namnreferenslistan: ett KÄNT namn auto-maskeras (lager 3a), ett OKÄNT
        blockerar hela utkastet (lager 3b). Båda utfallen är godtagbara och
        båda ska hålla — att låsa vilket av dem som inträffar hade gjort
        testet beroende av referenslistans innehåll, som är lokal data."""
        import json as _json

        svar = self._kor([{
            "Id": "utk-3",
            "VoucherDate": "2026-08-05",
            "VoucherText": "Betalning Anna Andersson",
            "Rows": [
                {"AccountNumber": 6110, "DebitAmount": Decimal("100"),
                 "CreditAmount": Decimal("0"), "TransactionText": "Kvitto"},
            ],
        }])

        assert "Anna Andersson" not in _json.dumps(svar, default=str)
        # Antingen maskerad och kvar, eller blockerad och räknad — aldrig
        # tyst borttappad.
        assert len(svar["data"]) + svar["antal_exkluderade"] == 1
