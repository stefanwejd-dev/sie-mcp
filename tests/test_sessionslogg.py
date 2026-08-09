"""Tester för sessionslogg.py — den läsbara loggen över vad som faktiskt
skickades till AI:t.

Loggen finns för att användaren själv ska kunna bedöma om en
personuppgiftsincident skett. Två egenskaper är därför säkerhetskrav och
testas som sådana, inte som trevliga detaljer:

1. **Den får aldrig innehålla mer än vad som skickades.** Kodnyckeln och
   blockerade meddelanden hör inte hemma i filen — det senare är anroparens
   ansvar, men loggen får inte heller uppfinna något eget.
2. **Den får aldrig fälla ett AI-anrop.** Ett fullt eller skrivskyddat filsystem
   ska ge en tyst logg, inte ett trasigt anrop.

Filen ska dessutom fungera i BÅDA riktningar: läsbar i Notepad och tolkbar av
en språkmodell. Därför testas markdown-strukturen (rubriker, tabeller,
kodblock) som ett kontrakt.

Alla tester kör mot tmp_path via SIE_MCP_DATA_ROOT — conftest isolerar redan
datarooten, men de här testerna sätter den explicit där de behöver egen mark.
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

import saker_lagring
import sessionslogg
from sessionslogg import (
    FILPREFIX,
    STANDARD_LAGRINGSTID_DAGAR,
    Sessionslogg,
    TystSessionslogg,
    Utflode,
    _kodblock,
    lista_sessioner,
    logga_sakert,
    rensa_gamla,
    sessionsfil,
    starta_session,
)


def _utflode(**overrides) -> Utflode:
    falt = {
        "forbindelse": "Anthropic",
        "modell": "claude-haiku-4-5",
        "formaga": "samtal",
        "lamnade_datorn": True,
        "systemprompt": "Du är en pedagogisk assistent.",
        "meddelanden": [{"roll": "user", "innehall": "Kontext:\nSaldo 1930: 250000\n\nFråga: Hur ligger vi till?"}],
        "svar": "Kassan ser stabil ut.",
    }
    falt.update(overrides)
    return Utflode(**falt)


class TestArkivstruktur:
    """Filnamnen ska vara begripliga i Utforskaren utan att någon förklarar
    dem, och sortera sig kronologiskt av sig själva."""

    def test_filnamnet_borjar_med_prefix_och_datum(self):
        fil = sessionsfil(datetime(2026, 8, 3, 14, 30, 52), "a1b2c3")

        assert fil.name == "AI-utflode_2026-08-03_143052_a1b2c3.md"

    def test_en_mapp_per_manad(self):
        fil = sessionsfil(datetime(2026, 8, 3, 14, 30, 52), "a1b2c3")

        assert fil.parent.name == "2026-08"

    def test_filnamnen_sorterar_kronologiskt(self):
        tidig = sessionsfil(datetime(2026, 8, 3, 9, 0, 0), "aaa").name
        sen = sessionsfil(datetime(2026, 8, 3, 17, 0, 0), "bbb").name

        assert sorted([sen, tidig]) == [tidig, sen]

    def test_ligger_under_den_guardade_loggkatalogen(self):
        # Filerna innehåller den faktiska nyttolasten och får ALDRIG hamna i
        # den molnsynkade projektmappen.
        fil = sessionsfil(datetime(2026, 8, 3, 14, 30, 52), "a1b2c3")

        assert saker_lagring.ai_utflode_dir() in fil.parents

    def test_lagringsplatsen_avvisar_projektmappen(self):
        with pytest.raises(saker_lagring.SakerLagringFel):
            saker_lagring.kontrollera_saker_plats(saker_lagring.REPO_ROOT / "logs")


class TestSessionsfilensInnehall:
    def test_filen_skapas_direkt_vid_sessionsstart(self):
        # "Varje gång appen startar" — även en session utan AI-anrop är ett
        # svar på frågan vad som skickades den dagen.
        logg = starta_session()

        assert logg.sokvag.exists()
        assert "Inga AI-anrop i den här sessionen" in logg.sokvag.read_text(encoding="utf-8")

    def test_sammanfattningen_ligger_hogst_upp(self):
        logg = starta_session()
        logg.logga(_utflode())

        text = logg.sokvag.read_text(encoding="utf-8")
        assert text.startswith("# AI-utflödeslogg")
        assert text.index("| Antal AI-anrop | 1 |") < text.index("## [1]")

    def test_sammanfattningen_skiljer_pa_lokalt_och_externt(self):
        logg = starta_session()
        logg.logga(_utflode())
        logg.logga(_utflode(forbindelse="Ollama (lokal)", lamnade_datorn=False))

        text = logg.sokvag.read_text(encoding="utf-8")
        assert "| Antal AI-anrop | 2 |" in text
        assert "| Varav skickade utanför datorn | 1 |" in text
        assert "| Mottagare | Anthropic |" in text

    def test_varje_anrop_far_ett_numrerat_avsnitt(self):
        logg = starta_session()
        logg.logga(_utflode())
        logg.logga(_utflode(formaga="agent"))

        text = logg.sokvag.read_text(encoding="utf-8")
        assert "## [1]" in text
        assert "## [2] " in text and "agent" in text

    def test_systemprompt_meddelanden_och_svar_skrivs_ut_i_klartext(self):
        # Hela poängen: användaren ska se EXAKT vad som skickades.
        logg = starta_session()
        logg.logga(_utflode())

        text = logg.sokvag.read_text(encoding="utf-8")
        assert "Du är en pedagogisk assistent." in text
        assert "Saldo 1930: 250000" in text
        assert "Kassan ser stabil ut." in text

    def test_externt_anrop_markeras_tydligt(self):
        logg = starta_session()
        logg.logga(_utflode())

        assert "Ja — skickades till en extern part" in logg.sokvag.read_text(encoding="utf-8")

    def test_lokalt_anrop_markeras_som_att_datan_stannade(self):
        logg = starta_session()
        logg.logga(_utflode(forbindelse="Ollama (lokal)", lamnade_datorn=False))

        text = logg.sokvag.read_text(encoding="utf-8")
        assert "Nej — behandlades lokalt på din dator" in text

    def test_verktygsnamn_loggas_men_inte_hela_schemana(self):
        logg = starta_session()
        logg.logga(_utflode(verktyg=["skapa_kund", "efterfraga_val"]))

        text = logg.sokvag.read_text(encoding="utf-8")
        assert "skapa_kund, efterfraga_val" in text
        assert "input_schema" not in text

    def test_fel_redovisas_utan_att_anropet_doljs(self):
        # Datan lämnade datorn även om svaret misslyckades — posten ska finnas.
        logg = starta_session()
        logg.logga(_utflode(svar=None, fel="APIConnectionError"))

        text = logg.sokvag.read_text(encoding="utf-8")
        assert "| Fel | APIConnectionError |" in text
        assert "Saldo 1930: 250000" in text

    def test_lasanvisningen_forklarar_maskering_och_gallring(self):
        # Filen ska vara begriplig för någon som öppnar den i Notepad utan
        # förkunskap om appen.
        text = starta_session().sokvag.read_text(encoding="utf-8")

        assert "[BOLAG_1]" in text
        assert "Nyckeln som översätter koderna" in text
        assert f"{STANDARD_LAGRINGSTID_DAGAR} dagar" in text

    def test_blockerade_meddelanden_namns_som_utelamnade(self):
        # Ett blockerat meddelande skickades aldrig och loggas därför inte —
        # men användaren ska förstå varför det saknas.
        text = starta_session().sokvag.read_text(encoding="utf-8")

        assert "stoppades av maskeringens säkerhetsspärr" in text


class TestKodblock:
    """Innehållet läggs i markdown-kodblock. Ett AI-svar som självt innehåller
    ``` får inte kunna bryta ut och göra resten av filen oläsbar."""

    def test_vanlig_text_far_tre_backticks(self):
        assert _kodblock("hej").startswith("```text\n")

    def test_staketet_vaxer_forbi_innehallets_backticks(self):
        block = _kodblock("se koden:\n```python\nx = 1\n```")

        assert block.startswith("````")
        assert block.endswith("````")

    def test_innehallet_bevaras_oforandrat(self):
        text = "rad 1\nrad 2 med ` och ``"

        assert text in _kodblock(text)

    def test_kodblock_i_ai_svar_sprangar_inte_filen(self):
        logg = starta_session()
        logg.logga(_utflode(svar="```\nhemlig kod\n```"))

        text = logg.sokvag.read_text(encoding="utf-8")
        # Allt efter svaret ska fortfarande vara struktur, inte kodblocksinnehåll.
        assert "hemlig kod" in text
        assert text.rstrip().endswith("````")


class TestFailSafe:
    """Loggningen får ALDRIG vara anledningen till att ett AI-anrop går fel."""

    def test_logga_sakert_utan_logg_gor_inget(self):
        logga_sakert(None, forbindelse="Anthropic", modell="m", formaga="samtal",
                     lamnade_datorn=True)  # ska inte kasta

    def test_logga_sakert_sväljer_trasig_logg(self):
        class Trasig:
            def logga(self, post):
                raise RuntimeError("disken är full")

        logga_sakert(Trasig(), forbindelse="Anthropic", modell="m",
                     formaga="samtal", lamnade_datorn=True)  # ska inte kasta

    def test_logga_sakert_sväljer_ogiltiga_falt(self):
        logga_sakert(TystSessionslogg(), det_har_faltet_finns_inte=True)  # ska inte kasta

    def test_osaker_lagringsplats_ger_tyst_logg_i_stallet_for_krasch(self, monkeypatch):
        monkeypatch.setenv(saker_lagring.DATA_ROOT_ENV, str(saker_lagring.REPO_ROOT / "loggar"))

        logg = starta_session()

        assert isinstance(logg, TystSessionslogg)
        assert logg.sokvag is None

    def test_tyst_logg_sväljer_poster(self):
        TystSessionslogg().logga(_utflode())  # ska inte kasta

    def test_skrivfel_stoppar_inte_loggningen(self, monkeypatch):
        logg = starta_session()

        def vagra(*a, **kw):
            raise OSError("skrivskyddad")

        monkeypatch.setattr(Path, "write_text", vagra)
        logg.logga(_utflode())  # ska inte kasta

        assert len(logg.poster) == 1


class TestAtomiskSkrivning:
    def test_ingen_temporarfil_lamnas_kvar(self):
        logg = starta_session()
        logg.logga(_utflode())

        assert list(logg.sokvag.parent.glob("*.tmp")) == []

    def test_filen_skrivs_om_i_sin_helhet_vid_varje_post(self):
        logg = starta_session()
        logg.logga(_utflode())
        forsta = logg.sokvag.read_text(encoding="utf-8")
        logg.logga(_utflode(formaga="agent"))
        andra = logg.sokvag.read_text(encoding="utf-8")

        # Sammanfattningen högst upp måste ha uppdaterats, inte bara appenderats.
        assert "| Antal AI-anrop | 1 |" in forsta
        assert "| Antal AI-anrop | 2 |" in andra


class TestRensning:
    """Dataminimering (art. 5.1 e): loggarna sparas så länge de kan behövas,
    inte för alltid."""

    def _skapa(self, namn: str, alder_dagar: float) -> Path:
        mapp = saker_lagring.ai_utflode_dir() / "2026-05"
        mapp.mkdir(parents=True, exist_ok=True)
        fil = mapp / namn
        fil.write_text("x", encoding="utf-8")
        gammal = time.time() - alder_dagar * 86400
        import os
        os.utime(fil, (gammal, gammal))
        return fil

    def test_filer_aldre_an_gransen_raderas(self):
        gammal = self._skapa(f"{FILPREFIX}_2026-05-01_120000_aaa.md", 120)

        assert rensa_gamla(90) == 1
        assert not gammal.exists()

    def test_farska_filer_lamnas_kvar(self):
        farsk = self._skapa(f"{FILPREFIX}_2026-05-01_120000_bbb.md", 10)

        rensa_gamla(90)

        assert farsk.exists()

    def test_bara_vara_egna_filer_ror_vi(self):
        # Något annat som råkat hamna i katalogen ska inte raderas.
        frammande = self._skapa("anteckningar.md", 500)
        aven_frammande = self._skapa(f"{FILPREFIX}_2026-05-01_120000_ccc.txt", 500)

        rensa_gamla(90)

        assert frammande.exists()
        assert aven_frammande.exists()

    def test_tomma_manadsmappar_stadas_bort(self):
        self._skapa(f"{FILPREFIX}_2026-05-01_120000_ddd.md", 500)

        rensa_gamla(90)

        assert not (saker_lagring.ai_utflode_dir() / "2026-05").exists()

    def test_noll_dagar_rensar_inget(self):
        # Skyddsnät mot en felkonfiguration som annars raderat allt direkt.
        fil = self._skapa(f"{FILPREFIX}_2026-05-01_120000_eee.md", 500)

        assert rensa_gamla(0) == 0
        assert fil.exists()

    def test_saknad_katalog_ar_inget_fel(self):
        assert rensa_gamla(90) == 0


class TestListaSessioner:
    def test_nyast_forst(self):
        Sessionslogg(sessionsfil(datetime(2026, 8, 1, 10, 0, 0), "aaa"),
                     datetime(2026, 8, 1, 10, 0, 0), "aaa")
        Sessionslogg(sessionsfil(datetime(2026, 8, 3, 10, 0, 0), "bbb"),
                     datetime(2026, 8, 3, 10, 0, 0), "bbb")

        namn = [s["namn"] for s in lista_sessioner()]

        assert namn[0].startswith(f"{FILPREFIX}_2026-08-03")

    def test_tom_katalog_ger_tom_lista(self):
        assert lista_sessioner() == []

    def test_posterna_bar_det_ui_behover(self):
        starta_session()

        post = lista_sessioner()[0]

        assert set(post) == {"sokvag", "namn", "storlek_kb", "andrad"}


class _FejkSamlare:
    """Loggmottagare som bara sparar posterna, utan I/O."""

    def __init__(self) -> None:
        self.poster: list[Utflode] = []

    def logga(self, post: Utflode) -> None:
        self.poster.append(post)


class _FejktTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FejkAnthropic:
    def __init__(self, svarstext: str = "Svar", fel: Exception | None = None) -> None:
        self._svarstext = svarstext
        self._fel = fel
        self.senaste_anrop: dict | None = None
        self.messages = self

    def create(self, **kwargs):
        self.senaste_anrop = kwargs
        if self._fel is not None:
            raise self._fel
        return type("Svar", (), {"content": [_FejktTextBlock(self._svarstext)]})()


class TestKlienternaLoggarVidTraden:
    """Det som loggas MÅSTE vara det som skickades — inte en rekonstruktion
    gjord i app.py, som kan glida isär från verkligheten. Testerna jämför
    därför loggposten mot vad fejkklienten faktiskt tog emot."""

    def test_samtalet_loggar_exakt_den_skickade_payloaden(self):
        from chatt_klient import skapa_verklig_chattanropare

        samlare = _FejkSamlare()
        klient = _FejkAnthropic(svarstext="Kassan ser stabil ut.")
        anropare = skapa_verklig_chattanropare(klient=klient, modell="m", logg=samlare)

        anropare("Hur ligger vi till?", "Saldo 1930: 250000")

        post = samlare.poster[0]
        skickat = klient.senaste_anrop
        assert post.systemprompt == skickat["system"]
        assert post.meddelanden[0]["innehall"] == skickat["messages"][0]["content"]
        assert post.svar == "Kassan ser stabil ut."
        assert post.lamnade_datorn is True
        assert post.formaga == "samtal"

    def test_agentlaget_loggar_hela_historiken_och_verktygsnamnen(self):
        from chatt_klient import AGENT_VERKTYG, skapa_agentanropare

        samlare = _FejkSamlare()
        klient = _FejkAnthropic(svarstext="Visst.")
        anropare = skapa_agentanropare(klient=klient, modell="m", logg=samlare)

        anropare([{"roll": "user", "text": "Vilka fakturor är obetalda?"}], "Kontextdata")

        post = samlare.poster[0]
        skickat = klient.senaste_anrop
        assert [m["innehall"] for m in post.meddelanden] == [
            m["content"] for m in skickat["messages"]
        ]
        assert post.verktyg == [v["name"] for v in AGENT_VERKTYG]

    def test_analysen_loggar_bunten_som_skickades(self):
        from domain_model import Konto
        from haiku_klient import skapa_verklig_haiku_anropare

        samlare = _FejkSamlare()
        klient = _FejkAnthropic(svarstext="[]")
        anropare = skapa_verklig_haiku_anropare(
            {"1930": Konto(kontonr="1930", namn="Bank")},
            klient=klient, modell="m", logg=samlare,
        )

        anropare([{"kontonr": "1930", "belopp": Decimal("250000")}], None)

        post = samlare.poster[0]
        assert post.formaga == "analys"
        assert post.meddelanden[0]["innehall"] == klient.senaste_anrop["messages"][0]["content"]

    def test_misslyckat_anrop_loggas_med_feltyp_men_utan_exceptiontext(self):
        # Datan lämnade datorn även om svaret kom bort — posten måste finnas.
        # Men exceptionens TEXT loggas inte: den kan bära nyckel eller payload.
        from chatt_klient import skapa_verklig_chattanropare

        samlare = _FejkSamlare()
        klient = _FejkAnthropic(fel=RuntimeError("sk-hemlig-nyckel i felmeddelandet"))
        anropare = skapa_verklig_chattanropare(klient=klient, modell="m", logg=samlare)

        anropare("Fråga", "Kontext")

        post = samlare.poster[0]
        assert post.fel == "RuntimeError"
        assert "sk-hemlig-nyckel" not in str(post.fel)
        assert post.svar is None

    def test_ollama_markeras_som_att_datan_stannade_pa_datorn(self):
        import httpx

        from ollama_klient import skapa_verklig_chattanropare as ollama_chatt

        class _FejkHttpx:
            def post(self, url, json=None, **kw):
                self.senaste = json
                return httpx.Response(
                    200, json={"message": {"content": "Hej!"}},
                    request=httpx.Request("POST", url),
                )

        samlare = _FejkSamlare()
        klient = _FejkHttpx()
        anropare = ollama_chatt("llama3", klient=klient, logg=samlare)

        anropare("Fråga", "Kontext")

        post = samlare.poster[0]
        assert post.lamnade_datorn is False
        assert post.forbindelse == "Ollama (lokal)"
        assert [m["innehall"] for m in post.meddelanden] == [
            m["content"] for m in klient.senaste["messages"]
        ]

    def test_utan_logg_fungerar_anroparna_som_forut(self):
        from chatt_klient import skapa_verklig_chattanropare

        anropare = skapa_verklig_chattanropare(klient=_FejkAnthropic("Svar"), modell="m")

        assert anropare("Fråga", "Kontext") == "Svar"


class TestTeckenrakning:
    """Sammanfattningen ska ge en känsla för omfattningen utan att man läser
    varje post."""

    def test_raknar_systemprompt_och_meddelanden(self):
        post = Utflode(
            forbindelse="Anthropic", modell="m", formaga="samtal", lamnade_datorn=True,
            systemprompt="12345", meddelanden=[{"roll": "user", "innehall": "abc"}],
        )

        assert post.tecken_ut() == 8

    def test_svaret_raknas_inte_som_utflode(self):
        # Svaret kom TILL datorn; det lämnade den inte.
        post = Utflode(
            forbindelse="Anthropic", modell="m", formaga="samtal", lamnade_datorn=True,
            systemprompt="12345", svar="ett långt svar som inte ska räknas",
        )

        assert post.tecken_ut() == 5
