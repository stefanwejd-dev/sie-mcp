"""spiris_klient — tunt HTTP/auth-lager mot Spiris/Visma eAccounting API v2.

Strikt HTTP och tokenhantering: ingen domänlogik och ingen mappning här
(det är spiris_adapter.py:s ansvar). Klienten levererar rå JSON som redan
listor av dict:ar — spiris_adapter översätter sedan till domänmodellen.

Två medvetna val, låsta av testerna:
- JSON parsas med json.loads(..., parse_float=Decimal), ALDRIG httpx .json()
  (som ger float). Decimal aldrig float — hela vägen från deserialiseringen.
- Fail-closed: allt som går fel (HTTP-fel, timeout, nätverksfel, ogiltig
  JSON, misslyckad refresh) blir vårt eget SpirisKlientFel. Inget
  httpx-specifikt undantag läcker någonsin ut ur modulen. Samma httpx-mönster
  som ai_konfiguration.py.

OAuth2 Authorization Code + refresh_token. Ett 401 tolkas som utgånget
access_token: klienten gör EN refresh och EXAKT ETT retry — sedan fail-closed.

skicka() (POST), uppdatera() (PUT) och ta_bort() (DELETE) delar EXAKT samma
refresh/fail-closed-mekanik som hamta_en/hamta_alla — alla fyra verben går
genom _anrop_med_refresh. Se _DecimalJSONEncoder för den ENDA platsen i hela
klienten där Decimal->float är godtagbart (tråd-formatet in mot Spiris, aldrig
en beräkning). De tre skrivande metoderna träffar ett LIVE affärssystem —
anroparen äger att bara kalla dem efter ett explicit mänskligt godkännande,
inte klienten själv. ta_bort() är den enda oåterkalleliga."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx

TOKEN_URL = "https://identity.vismaonline.com/connect/token"
API_BAS = "https://eaccountingapi.vismaonline.com/v2"
_TIMEOUT_SEKUNDER = 30.0


class SpirisKlientFel(Exception):
    """Fail-closed-fel för allt som går fel mot Spiris-API:t — HTTP-fel,
    timeout, nätverksfel, ogiltig JSON eller misslyckad token-refresh. Ett
    httpx-specifikt undantag når aldrig ut ur den här modulen."""


class _DecimalJSONEncoder(json.JSONEncoder):
    """Konverterar Decimal -> float ENDAST här, vid serialisering av en
    POST-kropp till HTTP-tråden. Det är det ENDA stället i hela klienten där
    Decimal->float är godtagbart: det är wire-formatet Spiris förväntar (ett
    JSON-tal), inte en beräkning — alla belopp förblir Decimal överallt i
    Python-koden fram till precis den här kanten."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


class SpirisKlient:
    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        klient: httpx.Client | None = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._klient = klient if klient is not None else httpx.Client(timeout=_TIMEOUT_SEKUNDER)
        self._äger_klient = klient is None

    # -- publikt ---------------------------------------------------------------

    def hamta_alla(self, path: str, params: dict | None = None) -> list[dict]:
        """Hämtar alla sidor för en paginerad endpoint och konkatenerar
        Data. Följer Meta.CurrentPage/TotalNumberOfPages tills sista sidan.
        Fail-closed vid varje fel."""
        rader: list[dict] = []
        sida = 1
        while True:
            sidparametrar = {**(params or {}), "$page": sida}
            svar = self._hamta_json(f"{API_BAS}{path}", sidparametrar)
            rader.extend(svar.get("Data", []))
            meta = svar.get("Meta") or {}
            total = meta.get("TotalNumberOfPages", sida)
            if sida >= total:
                return rader
            sida += 1

    def hamta_en(self, path: str, params: dict | None = None) -> dict:
        """Hämtar ett enskilt (icke-paginerat) objekt, t.ex.
        /companysettings — samma parse_float=Decimal, refresh och fail-closed
        som hamta_alla, men returnerar objektet rakt av (ingen Data/Meta)."""
        return self._hamta_json(f"{API_BAS}{path}", params or {})

    def skicka(self, path: str, data: dict) -> dict:
        """POSTar data (t.ex. en ny kund eller kundfaktura) och returnerar
        det skapade objektet — samma parse_float=Decimal, refresh-och-EN-
        retry och fail-closed-felmappning som hamta_en/hamta_alla.

        Decimal-belopp i data serialiseras via _DecimalJSONEncoder (float
        ENDAST på tråden, aldrig i beräkningen). Ett tomt svar (t.ex. 201
        utan kropp, vanligt för en lyckad POST) tolkas som {} — INTE ett
        JSON-fel. Skiljer sig medvetet från hamta_en/hamta_alla, som alltid
        förväntar en kropp: en tom POST-respons är normalt, en tom GET-
        respons vore oväntat och ska fortsatt fail-closed:a."""
        return self._tolka_kropp(self._anrop_med_refresh(
            "POST", f"{API_BAS}{path}",
            kropp=json.dumps(data, cls=_DecimalJSONEncoder),
        ))

    def uppdatera(self, path: str, data: dict) -> dict:
        """PUTar en ändring av ett BEFINTLIGT objekt och returnerar det
        uppdaterade objektet. Samma mekanik och samma fail-closed-kontrakt
        som skicka() — enda tekniska skillnaden är verbet.

        Skillnaden i RISK är däremot verklig: en PUT ÖVERSKRIVER något som
        redan finns, och Visma tolkar ett utelämnat fält som "sätt till null"
        på flera resurser. Anroparen äger därför att skicka ett FULLSTÄNDIGT
        objekt, inte bara de fält som ändrats — klienten fyller aldrig i
        något åt den, eftersom den inte kan veta vad som är avsiktligt
        borttaget och vad som bara glömts.

        Postar ALDRIG av sig själv: samma mänskliga godkännande krävs som för
        skicka() (se utkast.bekrafta_for_sandning)."""
        return self._tolka_kropp(self._anrop_med_refresh(
            "PUT", f"{API_BAS}{path}",
            kropp=json.dumps(data, cls=_DecimalJSONEncoder),
        ))

    def ta_bort(self, path: str) -> None:
        """DELETEar ett objekt. Returnerar inget: en lyckad borttagning
        svarar normalt 204 utan kropp, och det finns inget att returnera.

        Klientens enda oåterkalleliga operation — det som tas bort i Spiris
        kan inte återskapas härifrån. Anropas bara efter ett explicit
        mänskligt godkännande, aldrig som följd av en analys eller ett
        AI-förslag."""
        self._anrop_med_refresh("DELETE", f"{API_BAS}{path}")

    # -- internt ---------------------------------------------------------------

    def _hamta_json(self, url: str, params: dict) -> dict:
        svar = self._anrop_med_refresh("GET", url, params=params)
        try:
            return json.loads(svar.text, parse_float=Decimal)
        except (json.JSONDecodeError, ValueError) as e:
            raise SpirisKlientFel("Ogiltigt JSON-svar från Spiris.") from e

    def _tolka_kropp(self, svar: httpx.Response) -> dict:
        """Delad svarstolkning för skicka/uppdatera. Ett TOMT svar tolkas som
        {} — INTE ett JSON-fel: en lyckad POST/PUT utan kropp (201/204) är
        normalt, medan en tom GET-respons vore oväntad och fortsatt ska
        fail-closed:a (se _hamta_json)."""
        text = svar.text.strip()
        if not text:
            return {}
        try:
            return json.loads(text, parse_float=Decimal)
        except (json.JSONDecodeError, ValueError) as e:
            raise SpirisKlientFel("Ogiltigt JSON-svar från Spiris.") from e

    def _anrop_med_refresh(
        self, metod: str, url: str, *,
        params: dict | None = None, kropp: str | None = None,
    ) -> httpx.Response:
        """EN väg ut för alla fyra verben. Ett 401 tolkas som utgånget
        access_token: EN refresh, EXAKT ETT retry, sedan fail-closed.

        Ersätter de tidigare parvisa _get_med_refresh/_post_med_refresh med
        oförändrat beteende. Skälet är inte estetik: refresh-och-exakt-ett-
        retry är ett SÄKERHETSKONTRAKT (låst av test_spiris_klient.py), och
        med fyra verb hade det kontraktet funnits i fyra kopior som kunde
        glida isär."""
        svar = self._anrop(metod, url, params=params, kropp=kropp)
        if svar.status_code == 401:
            self._refresh()
            svar = self._anrop(metod, url, params=params, kropp=kropp)
        try:
            svar.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise SpirisKlientFel(f"Spiris avvisade förfrågan (HTTP {svar.status_code}).") from e
        return svar

    def _anrop(
        self, metod: str, url: str, *,
        params: dict | None = None, kropp: str | None = None,
    ) -> httpx.Response:
        """Content-Type sätts BARA när det finns en kropp — en GET eller
        DELETE utan kropp ska inte påstå att den skickar JSON."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if kropp is not None:
            headers["Content-Type"] = "application/json"
        try:
            return self._klient.request(
                metod, url, params=params, content=kropp, headers=headers
            )
        except httpx.TimeoutException as e:
            raise SpirisKlientFel("Tidsgräns överskreds vid anrop mot Spiris.") from e
        except httpx.HTTPError as e:
            raise SpirisKlientFel("Nätverksfel vid anrop mot Spiris.") from e

    def _refresh(self) -> None:
        try:
            svar = self._klient.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            svar.raise_for_status()
            data: Any = json.loads(svar.text)
        except httpx.HTTPError as e:
            raise SpirisKlientFel("Kunde inte förnya Spiris-token.") from e
        except (json.JSONDecodeError, ValueError) as e:
            raise SpirisKlientFel("Ogiltigt svar vid token-förnyelse.") from e

        nytt_at = data.get("access_token")
        if not nytt_at:
            raise SpirisKlientFel("Token-förnyelsen gav inget access_token.")
        self.access_token = nytt_at
        self.refresh_token = data.get("refresh_token", self.refresh_token)

    def stäng(self) -> None:
        if self._äger_klient:
            self._klient.close()
