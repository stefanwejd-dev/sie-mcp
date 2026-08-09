"""Tester för ollama_klient.py:s agentläge (Tool Calling) mot en lokal
Ollama-server. Speglar test_chatt_klient.py:s agenttester, men mot rena
JSON-dictar (httpx) i stället för Anthropics content-block. Inga riktiga
nätverksanrop: en fejkad httpx-klient injiceras alltid explicit."""

from __future__ import annotations

import inspect
import json

import httpx

from chatt_klient import AGENT_VERKTYG, AgentSvar, Verktygsanrop

from ollama_klient import skapa_agentanropare


class _FejktHttpxSvar:
    def __init__(self, json_data: dict) -> None:
        self._json = json_data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json


class _FejkHttpxKlient:
    """Minimal stand-in för httpx.Client — injiceras explicit, speglar bara
    .post(url, json=...) som skapa_agentanropare faktiskt anropar."""

    def __init__(self, svar_json: dict | None = None, fel: Exception | None = None) -> None:
        self._svar_json = svar_json
        self._fel = fel
        self.senaste_anrop: dict | None = None

    def post(self, url: str, *, json: dict) -> _FejktHttpxSvar:
        self.senaste_anrop = {"url": url, "json": json}
        if self._fel is not None:
            raise self._fel
        return _FejktHttpxSvar(self._svar_json)


def _fraga(text: str) -> list[dict[str, str]]:
    return [{"roll": "user", "text": text}]


def _meddelande(content: str | None = None, tool_calls: list | None = None) -> dict:
    m: dict = {"content": content}
    if tool_calls is not None:
        m["tool_calls"] = tool_calls
    return {"message": m}


class TestAgentAnropskonfiguration:
    def test_skickar_konverterade_verktyg_och_agent_systemprompt(self):
        from ollama_klient import SYSTEMPROMPT, SYSTEMPROMPT_AGENT

        klient = _FejkHttpxKlient(svar_json=_meddelande(content="Visst."))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        skickade_verktyg = klient.senaste_anrop["json"]["tools"]
        assert {v["function"]["name"] for v in skickade_verktyg} == {
            v["name"] for v in AGENT_VERKTYG
        }
        assert all(v["type"] == "function" for v in skickade_verktyg)

        meddelanden = klient.senaste_anrop["json"]["messages"]
        assert meddelanden[0] == {"role": "system", "content": SYSTEMPROMPT_AGENT}
        assert SYSTEMPROMPT in SYSTEMPROMPT_AGENT

    def test_hela_historiken_skickas_med_kontext_bara_i_forsta(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(content="Klart, fakturan skapas."))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)
        historik = [
            {"roll": "user", "text": "Skapa en kundfaktura för Lisa Andersson."},
            {"roll": "assistant", "text": "Vilken fakturatyp gäller?"},
            {"roll": "user", "text": "Byggmoms"},
        ]

        anropare(historik, "Kontext: en rad")

        meddelanden = klient.senaste_anrop["json"]["messages"]
        assert [m["role"] for m in meddelanden] == ["system", "user", "assistant", "user"]
        assert "Kontext: en rad" in meddelanden[1]["content"]
        assert "Skapa en kundfaktura för Lisa Andersson." in meddelanden[1]["content"]
        assert meddelanden[2]["content"] == "Vilken fakturatyp gäller?"
        assert meddelanden[3]["content"] == "Byggmoms"
        assert "Kontext: en rad" not in meddelanden[2]["content"]
        assert "Kontext: en rad" not in meddelanden[3]["content"]


class TestAgentSvarstolkning:
    def test_rent_textsvar_utan_verktygsanrop(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(content="Omsättningen är 100 000 kr."))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Vad är omsättningen?"), "Kontext")

        assert svar == AgentSvar(text="Omsättningen är 100 000 kr.", verktygsanrop=None)

    def test_verktygsanrop_med_dict_arguments(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(tool_calls=[{
            "function": {
                "name": "skapa_kund",
                "arguments": {"kundnamn": "Lisa Andersson", "ar_privatperson": True},
            },
        }]))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        assert svar.verktygsanrop == Verktygsanrop(
            namn="skapa_kund", indata={"kundnamn": "Lisa Andersson", "ar_privatperson": True},
        )

    def test_verktygsanrop_med_json_strang_arguments(self):
        # Vissa Ollama-modeller lägger arguments som en redan-serialiserad
        # JSON-sträng i stället för en dict — båda ska hanteras.
        klient = _FejkHttpxKlient(svar_json=_meddelande(tool_calls=[{
            "function": {
                "name": "skapa_kund",
                "arguments": json.dumps({"kundnamn": "Lisa Andersson", "ar_privatperson": True}),
            },
        }]))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        assert svar.verktygsanrop == Verktygsanrop(
            namn="skapa_kund", indata={"kundnamn": "Lisa Andersson", "ar_privatperson": True},
        )

    def test_text_och_verktygsanrop_samtidigt(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(
            content="Visst, jag förbereder det åt dig.",
            tool_calls=[{
                "function": {
                    "name": "skapa_kund",
                    "arguments": {"kundnamn": "Lisa Andersson", "ar_privatperson": True},
                },
            }],
        ))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        assert svar.text == "Visst, jag förbereder det åt dig."
        assert svar.verktygsanrop.namn == "skapa_kund"

    def test_bara_forsta_verktygsanropet_plockas(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(tool_calls=[
            {"function": {"name": "skapa_kund", "arguments": {"kundnamn": "A", "ar_privatperson": True}}},
            {"function": {"name": "skapa_kundfaktura", "arguments": {"kundnamn": "B", "fakturatyp": "juridisk_person"}}},
        ]))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.verktygsanrop.namn == "skapa_kund"


class TestFailClosed:
    def test_natverksfel_ger_fast_agentsvar_inget_verktygsanrop(self):
        klient = _FejkHttpxKlient(fel=httpx.ConnectError("nätverksfel"))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.text == (
            "Ollama-servern svarar inte. Kontrollera att den körs på http://localhost:11434."
        )
        assert svar.verktygsanrop is None
        assert "nätverksfel" not in svar.text

    def test_konstigt_svarsformat_ger_generiskt_fail_closed_svar(self):
        # 'message' saknas helt -> KeyError vid tolkning, ska ge det
        # generiska fail-closed-svaret, inte en krasch.
        klient = _FejkHttpxKlient(svar_json={"nagot_annat": True})
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.text == "Kunde inte få ett svar just nu. Försök igen om en stund."
        assert svar.verktygsanrop is None

    def test_trasig_json_strang_i_arguments_ger_fail_closed_inget_pahittat_anrop(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(
            tool_calls=[{"function": {"name": "skapa_kund", "arguments": "{inte giltig json"}}],
        ))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.text == "Kunde inte få ett svar just nu. Försök igen om en stund."
        assert svar.verktygsanrop is None

    def test_tom_historik_ger_fail_closed_agentsvar(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(content="Ska inte nås."))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        svar = anropare([], "Kontext")

        assert svar.text == "Kunde inte få ett svar just nu. Försök igen om en stund."
        assert svar.verktygsanrop is None
        assert klient.senaste_anrop is None


class TestKontrakt:
    def test_funktionssignatur_matchar_kontraktet(self):
        klient = _FejkHttpxKlient(svar_json=_meddelande(content="Svar"))
        anropare = skapa_agentanropare("llama3.1:8b", klient=klient)

        parametrar = list(inspect.signature(anropare).parameters.values())

        assert len(parametrar) == 2
