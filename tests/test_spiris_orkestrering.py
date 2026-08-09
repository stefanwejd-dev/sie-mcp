"""Tester för hamta_siefil_fran_spiris — limmet som väver ihop spiris_klient
(HTTP) och spiris_adapter (mappning) till en komplett SIEFil.

Ingen HTTP och inget nätverk: en fejk-klient injiceras som returnerar våra
verifierade sandbox-fixtures och registrerar exakt vilka endpoints som
efterfrågas. Orkestreringen gör ingen egen HTTP — den anropar bara klientens
hamta_en/hamta_alla och matar resultatet genom adaptern.

Det avgörande beviset (krav 3): den byggda SIEFil:en ska glida rakt genom
den befintliga domänkärnan — berakna_vasentlighet (Modul 1) och
maskera_siefil (sekretesslagret) — utan att något behövt ändras där.
"""

from __future__ import annotations

from decimal import Decimal

from domain_model import Konto, SIEFil, Verifikation
from sekretesslager import maskera_siefil
from vasentlighet import Vasentlighetstal, berakna_vasentlighet

from spiris_adapter import hamta_siefil_fran_spiris

RÄKENSKAPSÅR_ID = "1342e232-4275-42b1-b702-124d3a2d87d5"
TOM_DATUM = "2026-12-31"

# --- Verifierade sandbox-fixtures (räkenskapsår 2026, "X Sandbox") -----------

COMPANYSETTINGS = {
    "Name": "X Sandbox",
    "CorporateIdentityNumber": "143917-3855",
    "CurrencyCode": "SEK",
}

ACCOUNTS = [
    {"Number": "3041", "Name": "Försäljn tjänst 25% sv", "Type": 20},  # -> I
    {"Number": "3231", "Name": "Försäljning inom byggsektorn", "Type": 20},  # -> I
    {"Number": "2611", "Name": "Utgående moms 25%", "Type": 16},  # -> S
    {"Number": "1510", "Name": "Kundfordringar", "Type": 5},  # -> T
    {"Number": "1930", "Name": "Företagskonto", "Type": 9},  # -> T
    {"Number": "4000", "Name": "Inköp av handelsvaror (gruppkonto)", "Type": 24},  # -> K
]

# Verifikat A4 innehåller ett personnamn i vertext — sekretesslagret ska
# fånga det (regex_fallback), precis som mot den riktiga sandbox-datan.
VOUCHERS = [
    {
        "NumberAndNumberSeries": "A4",
        "NumberSeries": "A",
        "VoucherDate": "2026-05-21",
        "VoucherText": "Kundfaktura till 1 Karl Svensson, 1003",
        "VoucherType": 14,
        "CreatedUtc": "2026-06-27T17:34:00.000000Z",
        "Rows": [
            {
                "AccountNumber": 3231,
                "DebitAmount": Decimal("0.00"),
                "CreditAmount": Decimal("4000.00"),
                "TransactionText": "Kundfaktura till 1 Karl Svensson, 1003",
            },
            {
                "AccountNumber": 1510,
                "DebitAmount": Decimal("4000.00"),
                "CreditAmount": Decimal("0.00"),
                "TransactionText": "Kundfaktura till 1 Karl Svensson, 1003",
            },
        ],
    },
]

BALANCES = [
    {"AccountNumber": 1510, "AccountName": "Kundfordringar", "Balance": Decimal("50733.08")},
    {"AccountNumber": 1930, "AccountName": "Företagskonto", "Balance": Decimal("-381.03")},
    {"AccountNumber": 3041, "AccountName": "Försäljn tjänst 25% sv", "Balance": Decimal("-27900.00")},
    {"AccountNumber": 4000, "AccountName": "Inköp", "Balance": Decimal("4142.68")},
]


class _FejkKlient:
    """Injicerad stand-in för SpirisKlient. Aldrig nätverk — svarar med
    fixtures och registrerar varje efterfrågad path så testet kan verifiera
    att rätt endpoints anropas."""

    def __init__(self) -> None:
        self.anropade_paths: list[str] = []

    def hamta_en(self, path: str) -> dict:
        self.anropade_paths.append(path)
        if path == "/companysettings":
            return COMPANYSETTINGS
        raise AssertionError(f"oväntad hamta_en-path: {path}")

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        self.anropade_paths.append(path)
        if path.startswith("/accounts/"):
            return ACCOUNTS
        if path.startswith("/vouchers/"):
            return VOUCHERS
        if path.startswith("/accountbalances/"):
            return BALANCES
        raise AssertionError(f"oväntad hamta_alla-path: {path}")


def _bygg() -> tuple[SIEFil, _FejkKlient]:
    klient = _FejkKlient()
    sie = hamta_siefil_fran_spiris(klient, RÄKENSKAPSÅR_ID, TOM_DATUM)
    return sie, klient


class TestRättEndpointsAnropas:
    def test_alla_fyra_endpoints_efterfragas(self):
        _, klient = _bygg()
        paths = klient.anropade_paths
        assert "/companysettings" in paths
        assert f"/accounts/{RÄKENSKAPSÅR_ID}" in paths
        assert f"/vouchers/{RÄKENSKAPSÅR_ID}" in paths
        assert f"/accountbalances/{TOM_DATUM}" in paths


class TestKomplettSIEFil:
    def test_resultatet_ar_en_siefil(self):
        sie, _ = _bygg()
        assert isinstance(sie, SIEFil)

    def test_foretagsnamn_och_orgnr_fran_companysettings(self):
        sie, _ = _bygg()
        assert sie.företagsnamn == "X Sandbox"
        assert sie.orgnr == "143917-3855"

    def test_kontoplan_byggs_med_typ(self):
        sie, _ = _bygg()
        # 2611 saknar både saldo och transaktion i fixturen och filtreras bort
        # (inaktivt konto); övriga fem är aktiva.
        assert len(sie.konton) == 5
        assert isinstance(sie.konton["3041"], Konto)
        assert sie.konton["3041"].typ == "I"
        assert sie.konton["1510"].typ == "T"
        assert sie.konton["4000"].typ == "K"

    def test_inaktiva_konton_filtreras_bort(self):
        sie, _ = _bygg()
        # 2611 finns i ACCOUNTS men refereras varken av saldo eller transaktion.
        assert "2611" not in sie.konton
        # Aktiva konton (saldo eller transaktion) finns kvar.
        assert "1510" in sie.konton  # både saldo och transaktion
        assert "1930" in sie.konton  # saldo
        assert "3231" in sie.konton  # transaktion i verifikatet

    def test_verifikationer_byggs_med_transaktioner(self):
        sie, _ = _bygg()
        assert len(sie.verifikationer) == 1
        ver = sie.verifikationer[0]
        assert isinstance(ver, Verifikation)
        assert ver.serie == "A"
        assert ver.vernr == "4"
        assert len(ver.transaktioner) == 2

    def test_saldon_delas_i_ub_och_res(self):
        sie, _ = _bygg()
        ub = {p.kontonr for p in sie.utgående_balanser}
        res = {p.kontonr for p in sie.resultat}
        assert ub == {"1510", "1930"}
        assert res == {"3041", "4000"}


class TestGliderGenomDomänkärnan:
    def test_modul1_vasentlighet_kors_pa_resultatet(self):
        sie, _ = _bygg()
        tal = berakna_vasentlighet(sie)
        assert isinstance(tal, Vasentlighetstal)
        # Icke-noll och Decimal — beviset att saldona nådde fram rätt.
        assert tal.omsattning == Decimal("27900.00")
        assert tal.balansomslutning == Decimal("50352.05")
        assert isinstance(tal.resultat, Decimal)

    def test_sekretesslagret_fangar_personnamn_i_vertext(self):
        sie, _ = _bygg()
        m = maskera_siefil(sie)
        assert any("Karl Svensson" in b.misstänkt_text for b in m.maskeringsbehov)
