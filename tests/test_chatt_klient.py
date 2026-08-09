"""Tester för chatt_klient.py — den riktiga Anthropic-integrationen bakom
den pedagogiska samtalsytan (Sektion 9, samtalsflode.py).

Separat kontrakt från haiku_klient.py: fråga+kontext in, fritext-svar ut
— inte kontomatchningens bunt-i/JSON-ut-kontrakt. Samma testdisciplin:
aldrig en riktig API-nyckel eller ett riktigt nätverksanrop — fejkad
klient injiceras alltid explicit.
"""

from __future__ import annotations

import inspect
import json

from chatt_klient import (
    AGENT_VERKTYG,
    EFTERFRAGA_VAL_VERKTYG,
    MODELL,
    PRESENTERA_STRUKTURERAT_SVAR_VERKTYG,
    SKAPA_KUNDFAKTURA_VERKTYG,
    SKAPA_KUND_VERKTYG,
    SYSTEMPROMPT,
    SYSTEMPROMPT_AGENT,
    SYSTEMPROMPT_SAMTAL,
    AgentSvar,
    Verktygsanrop,
    skapa_agentanropare,
    skapa_verklig_chattanropare,
)
from svarskontrakt import KONTRAKT_INSTRUKTION


class _FejktTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FejktSvar:
    def __init__(self, text: str) -> None:
        self.content = [_FejktTextBlock(text)]


class _FejkAnthropicKlient:
    """Minimal stand-in för anthropic.Anthropic — injiceras explicit,
    speglar bara .messages.create(...).content[0].text som
    skapa_verklig_chattanropare faktiskt läser."""

    def __init__(self, svarstext: str | None = None, fel: Exception | None = None) -> None:
        self._svarstext = svarstext
        self._fel = fel
        self.senaste_anrop: dict | None = None
        self.messages = self

    def create(self, **kwargs) -> _FejktSvar:
        self.senaste_anrop = kwargs
        if self._fel is not None:
            raise self._fel
        return _FejktSvar(self._svarstext)


class TestAnropskonfiguration:
    def test_skickar_ratt_modell_och_systemprompt(self):
        klient = _FejkAnthropicKlient(svarstext="Svar")
        anropare = skapa_verklig_chattanropare(klient=klient)

        anropare("Vad är omsättningen?", "Kontext: omsättning 100 kr")

        assert klient.senaste_anrop["model"] == MODELL
        # Samtalsläget får grundprompten PLUS svarskontraktet (fas 11).
        assert klient.senaste_anrop["system"] == SYSTEMPROMPT_SAMTAL
        assert SYSTEMPROMPT in klient.senaste_anrop["system"]

    def test_angiven_modell_overstyr_standardkonstanten(self):
        klient = _FejkAnthropicKlient(svarstext="Svar")
        anropare = skapa_verklig_chattanropare(klient=klient, modell="claude-opus-4-8")

        anropare("Fråga", "Kontext")

        assert klient.senaste_anrop["model"] == "claude-opus-4-8"

    def test_temperature_skickas_inte(self):
        """Nyare modeller har fasat ut temperature och avvisar anropet med
        HTTP 400 ('temperature is deprecated for this model'). Parametern får
        därför inte skickas — att utelämna den är giltigt för alla modeller."""
        klient = _FejkAnthropicKlient(svarstext="Svar")
        anropare = skapa_verklig_chattanropare(klient=klient)

        anropare("Fråga", "Kontext")

        assert "temperature" not in klient.senaste_anrop

    def test_fraga_och_kontext_naar_anropet(self):
        klient = _FejkAnthropicKlient(svarstext="Svar")
        anropare = skapa_verklig_chattanropare(klient=klient)

        anropare("Är bolaget lönsamt?", "Resultat: 500 000 kr")

        meddelanden = klient.senaste_anrop["messages"]
        innehall = meddelanden[0]["content"]
        assert "Är bolaget lönsamt?" in innehall
        assert "Resultat: 500 000 kr" in innehall


class _FejktThinkingBlock:
    """Speglar anthropic.ThinkingBlock: har .thinking men INGET .text."""

    def __init__(self, thinking: str) -> None:
        self.thinking = thinking


class _FejktSvarMedThinking:
    def __init__(self, thinking: str, text: str) -> None:
        self.content = [_FejktThinkingBlock(thinking), _FejktTextBlock(text)]


class _FejkThinkingKlient:
    def __init__(self, thinking: str, text: str) -> None:
        self._svar = _FejktSvarMedThinking(thinking, text)
        self.senaste_anrop: dict | None = None
        self.messages = self

    def create(self, **kwargs):
        self.senaste_anrop = kwargs
        return self._svar


class TestThinkingModell:
    def test_hoppar_over_thinking_block_och_returnerar_textblocket(self):
        """Extended-thinking-modeller returnerar ett ThinkingBlock (utan
        .text) före det riktiga TextBlocket. content[0].text kraschar då med
        AttributeError — svaret ska istället plockas från första blocket som
        faktiskt har text."""
        klient = _FejkThinkingKlient(thinking="Låt mig tänka...", text="Bolaget går bra.")
        anropare = skapa_verklig_chattanropare(klient=klient)

        svar = anropare("Går bolaget bra?", "Resultat: positivt")

        assert svar == "Bolaget går bra."


class TestSvarstolkning:
    def test_returnerar_haikus_svarstext(self):
        klient = _FejkAnthropicKlient(svarstext="Bolaget verkar gå bra.")
        anropare = skapa_verklig_chattanropare(klient=klient)

        svar = anropare("Går bolaget bra?", "Resultat: positivt")

        assert svar == "Bolaget verkar gå bra."

    def test_api_fel_ger_fast_felmeddelande_inte_krasch(self):
        """Ingen rad försvinner tyst: går anropet fel ska ett tydligt,
        statiskt svar komma tillbaka — aldrig en okontrollerad krasch,
        aldrig rå exception-text."""
        klient = _FejkAnthropicKlient(fel=ConnectionError("nätverksfel"))
        anropare = skapa_verklig_chattanropare(klient=klient)

        svar = anropare("Fråga", "Kontext")

        assert svar == "Kunde inte få ett svar just nu. Försök igen om en stund."
        assert "nätverksfel" not in svar


class TestKontrakt:
    def test_funktionssignatur_matchar_kontraktet(self):
        klient = _FejkAnthropicKlient(svarstext="Svar")
        anropare = skapa_verklig_chattanropare(klient=klient)

        parametrar = list(inspect.signature(anropare).parameters.values())

        assert len(parametrar) == 2
        assert all(
            p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD for p in parametrar
        )


# ---------------------------------------------------------------------------
# Agentläge: Tool Calling (Fas 9) — EGET kontrakt (AgentSvar, inte str).
# chatt_klient.py känner aldrig till Spiris/kontering: den bara speglar
# Anthropics tool_use-block rakt av i ett Verktygsanrop.
# ---------------------------------------------------------------------------

class _FejktToolUseBlock:
    def __init__(self, name: str, input: dict) -> None:
        self.type = "tool_use"
        self.name = name
        self.input = input


class _FejktAgentSvar:
    def __init__(self, blocks: list) -> None:
        self.content = blocks


class _FejkAgentKlient:
    def __init__(self, blocks: list, fel: Exception | None = None) -> None:
        self._blocks = blocks
        self._fel = fel
        self.senaste_anrop: dict | None = None
        self.messages = self

    def create(self, **kwargs) -> _FejktAgentSvar:
        self.senaste_anrop = kwargs
        if self._fel is not None:
            raise self._fel
        return _FejktAgentSvar(self._blocks)


def _fraga(text: str) -> list[dict[str, str]]:
    """Hjälpare: en enda ny fråga, som en Fas 10-konversationshistorik med
    bara ETT (det första) meddelandet."""
    return [{"roll": "user", "text": text}]


class TestAgentAnropskonfiguration:
    def test_skickar_verktyg_och_agent_systemprompt(self):
        klient = _FejkAgentKlient(blocks=[_FejktTextBlock("Visst.")])
        anropare = skapa_agentanropare(klient=klient)

        anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        assert klient.senaste_anrop["tools"] == AGENT_VERKTYG
        assert klient.senaste_anrop["system"] == SYSTEMPROMPT_AGENT

    def test_agent_systemprompt_innehaller_hela_grundprompten(self):
        # Agentläget ska aldrig tappa de vanliga reglerna (hitta aldrig på
        # siffror etc.) bara för att verktyg lagts till.
        assert SYSTEMPROMPT in SYSTEMPROMPT_AGENT

    def test_angiven_modell_overstyr_standardkonstanten(self):
        klient = _FejkAgentKlient(blocks=[_FejktTextBlock("Svar")])
        anropare = skapa_agentanropare(klient=klient, modell="claude-opus-4-8")

        anropare(_fraga("Fråga"), "Kontext")

        assert klient.senaste_anrop["model"] == "claude-opus-4-8"

    def test_hela_historiken_skickas_med_kontext_bara_i_forsta(self):
        # Fas 10: assistenten måste minnas en tidigare efterfraga_val-fråga
        # och användarens knapptryckssvar på den — annars "glömmer" den vad
        # den frågade om, vilket var precis det som gjorde att den
        # fastnade i textbaserade frågeloopar.
        klient = _FejkAgentKlient(blocks=[_FejktTextBlock("Klart, fakturan skapas.")])
        anropare = skapa_agentanropare(klient=klient)
        historik = [
            {"roll": "user", "text": "Skapa en kundfaktura för Lisa Andersson."},
            {"roll": "assistant", "text": "Vilken fakturatyp gäller?"},
            {"roll": "user", "text": "Byggmoms"},
        ]

        anropare(historik, "Kontext: en rad")

        meddelanden = klient.senaste_anrop["messages"]
        assert [m["role"] for m in meddelanden] == ["user", "assistant", "user"]
        assert "Kontext: en rad" in meddelanden[0]["content"]
        assert "Skapa en kundfaktura för Lisa Andersson." in meddelanden[0]["content"]
        assert meddelanden[1]["content"] == "Vilken fakturatyp gäller?"
        assert meddelanden[2]["content"] == "Byggmoms"
        # kontext ska INTE upprepas i senare varv — bara i det första.
        assert "Kontext: en rad" not in meddelanden[1]["content"]
        assert "Kontext: en rad" not in meddelanden[2]["content"]

    def test_tom_historik_ger_fail_closed_agentsvar(self):
        klient = _FejkAgentKlient(blocks=[_FejktTextBlock("Ska inte nås.")])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare([], "Kontext")

        assert svar.text == "Kunde inte få ett svar just nu. Försök igen om en stund."
        assert svar.verktygsanrop is None
        assert klient.senaste_anrop is None


class TestVerktygsschema:
    def test_alla_verktygen_finns_i_listan(self):
        namn = {v["name"] for v in AGENT_VERKTYG}
        assert namn == {
            "skapa_kund", "skapa_kundfaktura", "efterfraga_val",
            "presentera_strukturerat_svar",
        }

    def test_skapa_kund_kraver_kundnamn_och_ar_privatperson(self):
        assert set(SKAPA_KUND_VERKTYG["input_schema"]["required"]) == {
            "kundnamn", "ar_privatperson",
        }

    def test_skapa_kundfaktura_kraver_kundnamn_och_fakturatyp(self):
        assert set(SKAPA_KUNDFAKTURA_VERKTYG["input_schema"]["required"]) == {
            "kundnamn", "fakturatyp",
        }

    def test_efterfraga_val_kraver_fraga_och_alternativ(self):
        assert set(EFTERFRAGA_VAL_VERKTYG["input_schema"]["required"]) == {
            "fraga", "alternativ",
        }

    def test_skapa_kundfaktura_exponerar_aldrig_personnummer(self):
        # Fynd B: fastighetsägarens personnummer (och övriga ROT-uppgifter) får
        # ALDRIG samlas in via AI-verktyget — de tas i ett lokalt formulär.
        properties = SKAPA_KUNDFAKTURA_VERKTYG["input_schema"]["properties"]
        assert "personnummer_fastighetsagare" not in properties
        assert "personnummer" not in properties

    def test_systemprompt_agent_forbjuder_personnummer_i_chatt(self):
        assert "personnummer" in SYSTEMPROMPT_AGENT.lower()

    def test_presentera_strukturerat_svar_kraver_block(self):
        schema = PRESENTERA_STRUKTURERAT_SVAR_VERKTYG["input_schema"]
        assert schema["required"] == ["block"]
        assert schema["properties"]["block"]["type"] == "array"

    def test_presentera_strukturerat_svar_saknar_ref_och_defs(self):
        # Anthropics tool use och (särskilt) Ollamas mindre modeller har
        # ojämnt stöd för $ref/$defs — schemat ska vara helt inlinat.
        rått = json.dumps(PRESENTERA_STRUKTURERAT_SVAR_VERKTYG["input_schema"])
        assert "$ref" not in rått
        assert "$defs" not in rått

    def test_agentprompten_namnger_presentationsverktyget(self):
        # Verktyget hjälper inte om prompten aldrig nämner när det ska
        # användas — och den gamla regeln ("vilka kunder är obetalda ska
        # ALDRIG utlösa ett verktygsanrop") får inte längre gälla generellt.
        assert "presentera_strukturerat_svar" in SYSTEMPROMPT_AGENT

    def test_samtalsprompten_har_kontraktet_men_inte_agentprompten(self):
        # Två parallella instruktioner om hur strukturerade svar levereras
        # (JSON i text OCH verktyg) skulle ställa modellen mot sig själv.
        assert KONTRAKT_INSTRUKTION in SYSTEMPROMPT_SAMTAL
        assert SYSTEMPROMPT in SYSTEMPROMPT_SAMTAL
        assert KONTRAKT_INSTRUKTION not in SYSTEMPROMPT_AGENT

    def test_fakturatyp_enum_matchar_spiris_adapterns_konstanter(self):
        from spiris_adapter import FAKTURATYP_BYGGMOMS, FAKTURATYP_FYSISK_PERSON_MED_ROT
        from spiris_adapter import FAKTURATYP_FYSISK_PERSON_UTAN_ROT, FAKTURATYP_JURIDISK_PERSON

        enum = SKAPA_KUNDFAKTURA_VERKTYG["input_schema"]["properties"]["fakturatyp"]["enum"]
        assert set(enum) == {
            FAKTURATYP_JURIDISK_PERSON, FAKTURATYP_FYSISK_PERSON_UTAN_ROT,
            FAKTURATYP_FYSISK_PERSON_MED_ROT, FAKTURATYP_BYGGMOMS,
        }


class TestAgentSvarstolkning:
    def test_rent_verktygsanrop_utan_text(self):
        klient = _FejkAgentKlient(blocks=[
            _FejktToolUseBlock("skapa_kund", {"kundnamn": "Lisa Andersson", "ar_privatperson": True}),
        ])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        assert svar.text is None
        assert svar.verktygsanrop == Verktygsanrop(
            namn="skapa_kund", indata={"kundnamn": "Lisa Andersson", "ar_privatperson": True},
        )

    def test_text_och_verktygsanrop_samtidigt(self):
        klient = _FejkAgentKlient(blocks=[
            _FejktTextBlock("Visst, jag förbereder det åt dig."),
            _FejktToolUseBlock("skapa_kund", {"kundnamn": "Lisa Andersson", "ar_privatperson": True}),
        ])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Skapa kunden Lisa Andersson"), "Kontext")

        assert svar.text == "Visst, jag förbereder det åt dig."
        assert svar.verktygsanrop.namn == "skapa_kund"

    def test_rent_textsvar_utan_verktygsanrop(self):
        klient = _FejkAgentKlient(blocks=[_FejktTextBlock("Omsättningen är 100 000 kr.")])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Vad är omsättningen?"), "Kontext")

        assert svar.text == "Omsättningen är 100 000 kr."
        assert svar.verktygsanrop is None

    def test_efterfraga_val_verktygsanrop_tolkas(self):
        klient = _FejkAgentKlient(blocks=[
            _FejktToolUseBlock(
                "efterfraga_val",
                {"fraga": "Vilken fakturatyp gäller?", "alternativ": ["Byggmoms", "Juridisk person"]},
            ),
        ])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Skapa en kundfaktura för Lisa Andersson."), "Kontext")

        assert svar.verktygsanrop == Verktygsanrop(
            namn="efterfraga_val",
            indata={"fraga": "Vilken fakturatyp gäller?", "alternativ": ["Byggmoms", "Juridisk person"]},
        )

    def test_bara_forsta_verktygsanropet_plockas(self):
        # v1: ett verktyg åt gången, konsekvent med SYSTEMPROMPT_AGENT:s regel.
        klient = _FejkAgentKlient(blocks=[
            _FejktToolUseBlock("skapa_kund", {"kundnamn": "A", "ar_privatperson": True}),
            _FejktToolUseBlock("skapa_kundfaktura", {"kundnamn": "B", "fakturatyp": "juridisk_person"}),
        ])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.verktygsanrop.namn == "skapa_kund"

    def test_api_fel_ger_fast_felmeddelande_i_text_inget_verktygsanrop(self):
        klient = _FejkAgentKlient(blocks=[], fel=ConnectionError("nätverksfel"))
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.text == "Kunde inte få ett svar just nu. Försök igen om en stund."
        assert svar.verktygsanrop is None
        assert "nätverksfel" not in svar.text

    def test_hoppar_over_thinking_block(self):
        thinking_block = _FejktThinkingBlock("Låt mig tänka...")
        klient = _FejkAgentKlient(blocks=[thinking_block, _FejktTextBlock("Klart.")])
        anropare = skapa_agentanropare(klient=klient)

        svar = anropare(_fraga("Fråga"), "Kontext")

        assert svar.text == "Klart."
