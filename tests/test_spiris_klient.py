"""Tester för spiris_klient.py — det tunna HTTP/auth-lagret mot Spiris/Visma
eAccounting API v2.

Aldrig riktigt nätverk i testsviten: en fejk-transport injiceras via
httpx.MockTransport, som kör den RIKTIGA httpx.Client-koden (request-bygge,
statuskoder, undantag) men svarar lokalt. Routar på värdnamn — identity.* är
token-endpointen, eaccountingapi.* är API:t.

Kontrakt som låses här:
- JSON parsas med parse_float=Decimal DIREKT vid deserialisering (aldrig
  httpx .json(), som ger float) — Decimal aldrig float.
- Paginering: alla sidor hämtas och Data konkateneras.
- 401 -> exakt EN token-refresh + EXAKT ETT retry. Fortsatt fel, timeout,
  500 eller ogiltig JSON -> vårt eget SpirisKlientFel. Inget httpx-specifikt
  undantag får någonsin läcka ut ur modulen.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from spiris_klient import SpirisKlient, SpirisKlientFel


def _sida(data: list[dict], current: int, total_pages: int) -> str:
    """Bygger en paginerad API-svarskropp som RÅ JSON-sträng (inte via
    httpx json=) så vi kontrollerar den exakta talformateringen."""
    return json.dumps(
        {
            "Meta": {
                "CurrentPage": current,
                "TotalNumberOfPages": total_pages,
                "PageSize": 50,
                "TotalNumberOfResults": len(data),
            },
            "Data": data,
        }
    )


_TOKENSVAR_OK = (200, {"access_token": "NY_AT", "refresh_token": "NY_RT", "expires_in": 3600})


class _FejkSpiris:
    """Skriptbar fejk-transport. api_svar konsumeras i tur och ordning per
    API-anrop; varje post är antingen (status, kropp) eller ett Exception som
    ska kastas (för timeout/nätverksfel). token_svar besvarar varje anrop mot
    identity-endpointen."""

    def __init__(self, api_svar: list, token_svar=None) -> None:
        self._api_svar = list(api_svar)
        self._token_svar = token_svar
        self.api_anrop: list[httpx.Request] = []
        self.token_anrop: list[httpx.Request] = []

    def klient(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handler))

    def _handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "identity.vismaonline.com":
            self.token_anrop.append(request)
            return self._svara(self._token_svar)
        self.api_anrop.append(request)
        return self._svara(self._api_svar.pop(0))

    @staticmethod
    def _svara(spec) -> httpx.Response:
        if isinstance(spec, Exception):
            raise spec
        status, kropp = spec
        if isinstance(kropp, str):
            return httpx.Response(status, text=kropp)
        return httpx.Response(status, text=json.dumps(kropp))


def _klient(fejk: _FejkSpiris, access_token: str = "AT1") -> SpirisKlient:
    return SpirisKlient(
        access_token=access_token,
        refresh_token="RT1",
        client_id="xsandbox",
        client_secret="hemlis",
        klient=fejk.klient(),
    )


class TestHamtning:
    def test_hamtar_och_konkatenerar_alla_sidor(self):
        fejk = _FejkSpiris(
            api_svar=[
                (200, _sida([{"Id": "a"}, {"Id": "b"}], current=1, total_pages=2)),
                (200, _sida([{"Id": "c"}], current=2, total_pages=2)),
            ]
        )
        data = _klient(fejk).hamta_alla("/vouchers/år-id")

        assert [rad["Id"] for rad in data] == ["a", "b", "c"]
        assert len(fejk.api_anrop) == 2  # exakt två sidor, stannar vid total_pages

    def test_en_sida_ger_inget_extra_anrop(self):
        fejk = _FejkSpiris(api_svar=[(200, _sida([{"Id": "a"}], current=1, total_pages=1))])
        data = _klient(fejk).hamta_alla("/accounts/år-id")

        assert [rad["Id"] for rad in data] == ["a"]
        assert len(fejk.api_anrop) == 1

    def test_belopp_parsas_som_decimal_inte_float(self):
        # RÅ JSON med decimaltal. Använder klienten httpx .json() blir det
        # float; kravet är parse_float=Decimal vid deserialiseringen.
        kropp = (
            '{"Meta":{"CurrentPage":1,"TotalNumberOfPages":1,"PageSize":50,'
            '"TotalNumberOfResults":1},'
            '"Data":[{"AccountNumber":3041,"DebitAmount":9000.50,"CreditAmount":0.00}]}'
        )
        fejk = _FejkSpiris(api_svar=[(200, kropp)])
        data = _klient(fejk).hamta_alla("/vouchers/år-id")

        belopp = data[0]["DebitAmount"]
        assert isinstance(belopp, Decimal)
        assert belopp == Decimal("9000.50")

    def test_access_token_skickas_som_bearer(self):
        fejk = _FejkSpiris(api_svar=[(200, _sida([], current=1, total_pages=1))])
        _klient(fejk, access_token="AT1").hamta_alla("/vouchers/år-id")

        assert fejk.api_anrop[0].headers["Authorization"] == "Bearer AT1"


class TestTokenRefresh:
    def test_401_utloser_exakt_en_refresh_och_ett_retry(self):
        fejk = _FejkSpiris(
            api_svar=[
                (401, {"ErrorCode": 9000}),
                (200, _sida([{"Id": "a"}], current=1, total_pages=1)),
            ],
            token_svar=_TOKENSVAR_OK,
        )
        klient = _klient(fejk)
        data = klient.hamta_alla("/vouchers/år-id")

        assert [rad["Id"] for rad in data] == ["a"]
        assert len(fejk.token_anrop) == 1  # exakt EN refresh
        assert len(fejk.api_anrop) == 2  # original + exakt ETT retry

    def test_retry_anvander_det_nya_access_tokenet(self):
        fejk = _FejkSpiris(
            api_svar=[
                (401, {"ErrorCode": 9000}),
                (200, _sida([], current=1, total_pages=1)),
            ],
            token_svar=_TOKENSVAR_OK,
        )
        klient = _klient(fejk, access_token="AT1")
        klient.hamta_alla("/vouchers/år-id")

        assert fejk.api_anrop[0].headers["Authorization"] == "Bearer AT1"
        assert fejk.api_anrop[1].headers["Authorization"] == "Bearer NY_AT"
        assert klient.access_token == "NY_AT"  # klienten uppdaterar sitt token

    def test_refresh_skickar_grant_type_refresh_token(self):
        fejk = _FejkSpiris(
            api_svar=[
                (401, {"ErrorCode": 9000}),
                (200, _sida([], current=1, total_pages=1)),
            ],
            token_svar=_TOKENSVAR_OK,
        )
        _klient(fejk).hamta_alla("/vouchers/år-id")

        kropp = fejk.token_anrop[0].content
        assert b"grant_type=refresh_token" in kropp
        assert b"RT1" in kropp  # det lagrade refresh-tokenet skickas med

    def test_fortsatt_401_efter_retry_ger_spirisklientfel_ingen_oandlig_loop(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (401, {"ErrorCode": 9000})],
            token_svar=_TOKENSVAR_OK,
        )
        klient = _klient(fejk)

        with pytest.raises(SpirisKlientFel):
            klient.hamta_alla("/vouchers/år-id")

        assert len(fejk.token_anrop) == 1  # inte fler refresh-försök
        assert len(fejk.api_anrop) == 2  # exakt ETT retry, inte en loop

    def test_misslyckad_refresh_ger_spirisklientfel(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000})],
            token_svar=(400, {"error": "invalid_grant"}),
        )
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).hamta_alla("/vouchers/år-id")


class TestFailClosed:
    def test_500_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[(500, {"error": "internt"})])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).hamta_alla("/vouchers/år-id")

    def test_timeout_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[httpx.TimeoutException("tidsgräns")])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).hamta_alla("/vouchers/år-id")

    def test_natverksfel_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[httpx.ConnectError("kunde inte ansluta")])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).hamta_alla("/vouchers/år-id")

    def test_ogiltig_json_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[(200, "<html>inte json</html>")])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).hamta_alla("/vouchers/år-id")

    def test_inget_httpx_undantag_lacker_ut(self):
        # Uttryckligt: det som lämnar modulen får ALDRIG vara ett
        # httpx-specifikt undantag, bara vårt eget domänfel.
        fejk = _FejkSpiris(api_svar=[httpx.ConnectError("nere")])
        try:
            _klient(fejk).hamta_alla("/vouchers/år-id")
        except SpirisKlientFel:
            pass
        except httpx.HTTPError as e:
            pytest.fail(f"httpx-undantag läckte ut ur modulen: {type(e).__name__}")


class TestHamtaEn:
    """hamta_en för enskilda (icke-paginerade) objekt, t.ex.
    /companysettings — samma parse_float=Decimal, refresh och fail-closed
    som hamta_alla, men returnerar objektet rakt av (ingen Data/Meta)."""

    def test_returnerar_objektet_rakt_av(self):
        kropp = '{"Name":"X Sandbox","CorporateIdentityNumber":"143917-3855"}'
        fejk = _FejkSpiris(api_svar=[(200, kropp)])
        data = _klient(fejk).hamta_en("/companysettings")

        assert data["Name"] == "X Sandbox"
        assert data["CorporateIdentityNumber"] == "143917-3855"

    def test_tal_parsas_som_decimal(self):
        fejk = _FejkSpiris(api_svar=[(200, '{"Saldo":123.45}')])
        data = _klient(fejk).hamta_en("/companysettings")

        assert isinstance(data["Saldo"], Decimal)
        assert data["Saldo"] == Decimal("123.45")

    def test_401_utloser_refresh_och_retry(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (200, '{"Name":"X Sandbox"}')],
            token_svar=_TOKENSVAR_OK,
        )
        data = _klient(fejk).hamta_en("/companysettings")

        assert data["Name"] == "X Sandbox"
        assert len(fejk.token_anrop) == 1
        assert len(fejk.api_anrop) == 2

    def test_500_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[(500, {"error": "internt"})])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).hamta_en("/companysettings")


class TestSkicka:
    """skicka() (POST) — samma refresh/fail-closed-mekanik som hamta_alla/
    hamta_en, plus två egna kontrakt: Decimal serialiseras till JSON-tal
    (aldrig en sträng), och ett tomt svar tolkas som {} i stället för ett fel
    (en lyckad POST utan kropp är normalt, till skillnad från en tom GET)."""

    def test_postar_till_ratt_url_och_returnerar_skapat_objekt(self):
        fejk = _FejkSpiris(api_svar=[(201, '{"Id":"ny-kund-1","Name":"Ny Kund AB"}')])
        data = _klient(fejk).skicka("/customers", {"Name": "Ny Kund AB"})

        assert data["Id"] == "ny-kund-1"
        assert fejk.api_anrop[0].url == "https://eaccountingapi.vismaonline.com/v2/customers"
        assert fejk.api_anrop[0].method == "POST"

    def test_decimal_serialiseras_som_jsontal_inte_strang(self):
        fejk = _FejkSpiris(api_svar=[(201, '{"Id":"f1"}')])
        _klient(fejk).skicka("/customerinvoices", {"Rows": [{"UnitPrice": Decimal("1234.50")}]})

        kropp = json.loads(fejk.api_anrop[0].content)
        assert kropp["Rows"][0]["UnitPrice"] == 1234.50
        assert isinstance(kropp["Rows"][0]["UnitPrice"], float)  # JSON-tal, inte sträng

    def test_access_token_skickas_som_bearer(self):
        fejk = _FejkSpiris(api_svar=[(201, '{"Id":"f1"}')])
        _klient(fejk, access_token="AT1").skicka("/customers", {"Name": "X"})

        assert fejk.api_anrop[0].headers["Authorization"] == "Bearer AT1"

    def test_content_type_ar_json(self):
        fejk = _FejkSpiris(api_svar=[(201, '{"Id":"f1"}')])
        _klient(fejk).skicka("/customers", {"Name": "X"})

        assert fejk.api_anrop[0].headers["Content-Type"] == "application/json"

    def test_tomt_svar_ger_tom_dict_inte_fel(self):
        fejk = _FejkSpiris(api_svar=[(201, "")])
        data = _klient(fejk).skicka("/customers", {"Name": "X"})

        assert data == {}

    def test_401_utloser_exakt_en_refresh_och_ett_retry(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (201, '{"Id":"f1"}')],
            token_svar=_TOKENSVAR_OK,
        )
        data = _klient(fejk).skicka("/customers", {"Name": "X"})

        assert data["Id"] == "f1"
        assert len(fejk.token_anrop) == 1
        assert len(fejk.api_anrop) == 2

    def test_retry_skickar_om_samma_kropp(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (201, '{"Id":"f1"}')],
            token_svar=_TOKENSVAR_OK,
        )
        _klient(fejk).skicka("/customers", {"Name": "Samma Kropp AB"})

        första = json.loads(fejk.api_anrop[0].content)
        andra = json.loads(fejk.api_anrop[1].content)
        assert första == andra == {"Name": "Samma Kropp AB"}

    def test_400_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[(400, {"error": "ogiltig faktura"})])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).skicka("/customerinvoices", {"Rows": []})

    def test_natverksfel_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[httpx.ConnectError("nere")])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).skicka("/customers", {"Name": "X"})

    def test_inget_httpx_undantag_lacker_ut(self):
        fejk = _FejkSpiris(api_svar=[httpx.ConnectError("nere")])
        try:
            _klient(fejk).skicka("/customers", {"Name": "X"})
        except SpirisKlientFel:
            pass
        except httpx.HTTPError as e:
            pytest.fail(f"httpx-undantag läckte ut ur modulen: {type(e).__name__}")


class TestUppdatera:
    """uppdatera() (PUT) — speglar TestSkicka rakt av. Samma refresh- och
    fail-closed-kontrakt, samma Decimal-serialisering, samma tolerans för ett
    tomt svar. Enda tekniska skillnaden mot skicka() är verbet; skillnaden i
    risk (en PUT överskriver något som redan finns) ligger hos anroparen, inte
    hos klienten."""

    def test_putar_till_ratt_url_och_returnerar_uppdaterat_objekt(self):
        fejk = _FejkSpiris(api_svar=[(200, '{"Id":"kund-id-1","Name":"Ändrat Namn AB"}')])
        data = _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": "Ändrat Namn AB"})

        assert data["Name"] == "Ändrat Namn AB"
        assert fejk.api_anrop[0].url == (
            "https://eaccountingapi.vismaonline.com/v2/customers/kund-id-1"
        )
        assert fejk.api_anrop[0].method == "PUT"

    def test_decimal_serialiseras_som_jsontal_inte_strang(self):
        fejk = _FejkSpiris(api_svar=[(200, '{"Id":"f1"}')])
        _klient(fejk).uppdatera(
            "/customerinvoices/f1", {"Rows": [{"UnitPrice": Decimal("1234.50")}]}
        )

        kropp = json.loads(fejk.api_anrop[0].content)
        assert kropp["Rows"][0]["UnitPrice"] == 1234.50
        assert isinstance(kropp["Rows"][0]["UnitPrice"], float)  # JSON-tal, inte sträng

    def test_access_token_skickas_som_bearer(self):
        fejk = _FejkSpiris(api_svar=[(200, '{"Id":"f1"}')])
        _klient(fejk, access_token="AT1").uppdatera("/customers/kund-id-1", {"Name": "X"})

        assert fejk.api_anrop[0].headers["Authorization"] == "Bearer AT1"

    def test_content_type_ar_json(self):
        fejk = _FejkSpiris(api_svar=[(200, '{"Id":"f1"}')])
        _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": "X"})

        assert fejk.api_anrop[0].headers["Content-Type"] == "application/json"

    def test_tomt_svar_ger_tom_dict_inte_fel(self):
        # 204 utan kropp är ett normalt svar på en lyckad PUT.
        fejk = _FejkSpiris(api_svar=[(204, "")])
        data = _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": "X"})

        assert data == {}

    def test_401_utloser_exakt_en_refresh_och_ett_retry(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (200, '{"Id":"f1"}')],
            token_svar=_TOKENSVAR_OK,
        )
        data = _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": "X"})

        assert data["Id"] == "f1"
        assert len(fejk.token_anrop) == 1
        assert len(fejk.api_anrop) == 2

    def test_retry_skickar_om_samma_kropp(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (200, '{"Id":"f1"}')],
            token_svar=_TOKENSVAR_OK,
        )
        _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": "Samma Kropp AB"})

        första = json.loads(fejk.api_anrop[0].content)
        andra = json.loads(fejk.api_anrop[1].content)
        assert första == andra == {"Name": "Samma Kropp AB"}

    def test_400_ger_spirisklientfel(self):
        fejk = _FejkSpiris(api_svar=[(400, {"error": "ogiltig kund"})])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": ""})

    def test_inget_httpx_undantag_lacker_ut(self):
        fejk = _FejkSpiris(api_svar=[httpx.ConnectError("nere")])
        try:
            _klient(fejk).uppdatera("/customers/kund-id-1", {"Name": "X"})
        except SpirisKlientFel:
            pass
        except httpx.HTTPError as e:
            pytest.fail(f"httpx-undantag läckte ut ur modulen: {type(e).__name__}")


class TestTaBort:
    """ta_bort() (DELETE) — klientens enda oåterkalleliga operation. Skickar
    ingen kropp och returnerar inget: en lyckad borttagning svarar normalt 204
    utan innehåll. Samma refresh- och fail-closed-kontrakt som övriga verb."""

    def test_deletar_ratt_url_och_metod(self):
        fejk = _FejkSpiris(api_svar=[(204, "")])
        _klient(fejk).ta_bort("/customers/kund-id-1")

        assert fejk.api_anrop[0].url == (
            "https://eaccountingapi.vismaonline.com/v2/customers/kund-id-1"
        )
        assert fejk.api_anrop[0].method == "DELETE"

    def test_access_token_skickas_som_bearer(self):
        fejk = _FejkSpiris(api_svar=[(204, "")])
        _klient(fejk, access_token="AT1").ta_bort("/customers/kund-id-1")

        assert fejk.api_anrop[0].headers["Authorization"] == "Bearer AT1"

    def test_204_utan_kropp_ger_none(self):
        fejk = _FejkSpiris(api_svar=[(204, "")])
        assert _klient(fejk).ta_bort("/customers/kund-id-1") is None

    def test_401_utloser_exakt_en_refresh_och_ett_retry(self):
        fejk = _FejkSpiris(
            api_svar=[(401, {"ErrorCode": 9000}), (204, "")],
            token_svar=_TOKENSVAR_OK,
        )
        _klient(fejk).ta_bort("/customers/kund-id-1")

        assert len(fejk.token_anrop) == 1
        assert len(fejk.api_anrop) == 2

    def test_404_ger_spirisklientfel(self):
        # Fail-closed: en borttagning av något som inte finns ska höras, inte
        # sväljas som "redan borta".
        fejk = _FejkSpiris(api_svar=[(404, {"error": "finns inte"})])
        with pytest.raises(SpirisKlientFel):
            _klient(fejk).ta_bort("/customers/finns-inte")

    def test_inget_httpx_undantag_lacker_ut(self):
        fejk = _FejkSpiris(api_svar=[httpx.ConnectError("nere")])
        try:
            _klient(fejk).ta_bort("/customers/kund-id-1")
        except SpirisKlientFel:
            pass
        except httpx.HTTPError as e:
            pytest.fail(f"httpx-undantag läckte ut ur modulen: {type(e).__name__}")


class TestVerbHygien:
    """Låser den ENDA avsiktliga beteendeskillnaden i _anrop: Content-Type
    sätts bara när det faktiskt finns en kropp att beskriva.

    Testet finns för att skillnaden är lätt att bygga bort av misstag. Samlas
    headern i en delad konstant "för att det är samma överallt" börjar varje
    GET och DELETE påstå att den skickar JSON — vilket är osant, och vilket
    inget annat test i sviten hade märkt."""

    def test_get_satter_inte_content_type(self):
        fejk = _FejkSpiris(api_svar=[(200, _sida([], current=1, total_pages=1))])
        _klient(fejk).hamta_alla("/customers")

        assert "Content-Type" not in fejk.api_anrop[0].headers

    def test_delete_satter_inte_content_type(self):
        fejk = _FejkSpiris(api_svar=[(204, "")])
        _klient(fejk).ta_bort("/customers/kund-id-1")

        assert "Content-Type" not in fejk.api_anrop[0].headers
