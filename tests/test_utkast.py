"""test_utkast.py — Steg 2: grinden mellan AI-förslag och verklig skrivning.

Det som prövas här är inte funktionalitet utan att grinden HÅLLER. Fyra
egenskaper bär hela säkerhetsmodellen, och blir något av dem rött är åtgärden
aldrig att lätta på kravet:

1. **MCP kan föreslå men aldrig utföra.** Statiskt test på att MCP-servern inte
   ens känner till skrivfunktionerna.
2. **Hashbindning.** En nyttolast som ändrats mellan förslag och godkännande
   skickas inte. Det människan såg är det som skickas.
3. **Livslängd.** Ett dygn gammalt utkast kan inte godkännas — underlaget kan ha
   ändrats i Spiris under tiden.
4. **Sökvägsvakt.** utkast_id kommer från en MCP-klient, alltså från en AI.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import compliance
import mcp_server.server as server_modul
import saker_lagring
import utkast


@pytest.fixture(autouse=True)
def _godkanda_villkor():
    compliance.godkann_compliance()


NYTTOLAST = {"Name": "Anna Andersson", "Email": "anna@example.com"}
SAMMANFATTNING = [["Kundnamn", "Anna Andersson"]]


# --- 1. Grunderna ----------------------------------------------------------


def test_skapat_utkast_vantar_och_ar_inte_utfort():
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    assert u.status == utkast.VANTAR
    assert utkast.las(u.utkast_id).nyttolast == NYTTOLAST


def test_utkast_lagras_utanfor_repot():
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    fil = saker_lagring.state_dir() / utkast.KATALOG / f"{u.utkast_id}.json"
    assert fil.exists()
    assert saker_lagring.REPO_ROOT not in fil.parents


@pytest.mark.parametrize("typ", ["", "faktura", "voucher", "kund; DROP"])
def test_okand_typ_avvisas(typ):
    with pytest.raises(utkast.UtkastFel):
        utkast.skapa(typ, NYTTOLAST, [])


def test_tom_nyttolast_avvisas():
    with pytest.raises(utkast.UtkastFel):
        utkast.skapa("kund", {}, [])


def test_lista_ger_bara_vantande_nar_status_anges():
    a = utkast.skapa("kund", NYTTOLAST, [])
    b = utkast.skapa("kund", {"Name": "B"}, [])
    utkast.avvisa(b.utkast_id)

    vantande = [u.utkast_id for u in utkast.lista(status=utkast.VANTAR)]
    assert vantande == [a.utkast_id]


# --- 2. Hashbindningen -----------------------------------------------------


def test_bekraftelse_ger_nyttolasten_for_ororat_utkast():
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    assert utkast.bekrafta_for_sandning(u.utkast_id) == NYTTOLAST


def test_andrad_nyttolast_avvisas():
    """Kärntestet: det människan såg är det som skickas.

    Utkastet ligger på disk mellan förslag och godkännande. Ändras filen — av en
    bugg, en annan process eller någon med lokal åtkomst — ska godkännandet
    vägras, inte tyst skicka något annat än det som granskades."""
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    fil = saker_lagring.state_dir() / utkast.KATALOG / f"{u.utkast_id}.json"

    data = json.loads(fil.read_text(encoding="utf-8"))
    data["nyttolast"]["Name"] = "Någon Annan"
    fil.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(utkast.UtkastFel, match="ändrats"):
        utkast.bekrafta_for_sandning(u.utkast_id)


def test_hash_ar_oberoende_av_nyckelordning():
    """En omordnad men identisk dict får inte se ut som en manipulation."""
    a = utkast.berakna_hash({"x": 1, "y": 2})
    b = utkast.berakna_hash({"y": 2, "x": 1})
    assert a == b


def test_hash_andras_av_belopp():
    assert utkast.berakna_hash({"belopp": 100}) != utkast.berakna_hash({"belopp": 101})


# --- 3. Livslängd och status ----------------------------------------------


def _aldra(utkast_id: str, timmar: int) -> None:
    fil = saker_lagring.state_dir() / utkast.KATALOG / f"{utkast_id}.json"
    data = json.loads(fil.read_text(encoding="utf-8"))
    data["skapad"] = (datetime.now() - timedelta(hours=timmar)).isoformat(timespec="seconds")
    fil.write_text(json.dumps(data), encoding="utf-8")


def test_utganget_utkast_kan_inte_skickas():
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    _aldra(u.utkast_id, utkast.STANDARD_LIVSLANGD_TIMMAR + 1)

    with pytest.raises(utkast.UtkastFel, match="timmar"):
        utkast.bekrafta_for_sandning(u.utkast_id)


def test_utkast_precis_inom_livslangden_gar_bra():
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    _aldra(u.utkast_id, utkast.STANDARD_LIVSLANGD_TIMMAR - 1)
    assert utkast.bekrafta_for_sandning(u.utkast_id) == NYTTOLAST


def test_otolkbart_datum_behandlas_som_utganget():
    """Fail-closed: hellre ett vägrat godkännande än ett på okänt underlag."""
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    fil = saker_lagring.state_dir() / utkast.KATALOG / f"{u.utkast_id}.json"
    data = json.loads(fil.read_text(encoding="utf-8"))
    data["skapad"] = "inte ett datum"
    fil.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(utkast.UtkastFel):
        utkast.bekrafta_for_sandning(u.utkast_id)


@pytest.mark.parametrize("atgard", [utkast.avvisa, utkast.markera_skickat])
def test_redan_hanterat_utkast_kan_inte_skickas_igen(atgard):
    """Dubbelsändningsskydd: en faktura ska inte kunna skickas två gånger."""
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    atgard(u.utkast_id)

    with pytest.raises(utkast.UtkastFel, match="redan"):
        utkast.bekrafta_for_sandning(u.utkast_id)


def test_misslyckat_bar_bara_kort_orsak():
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    utkast.markera_misslyckat(u.utkast_id, "Spiris avvisade posten")
    assert utkast.las(u.utkast_id).resultat == {"orsak": "Spiris avvisade posten"}


def test_rensa_gamla_tar_aven_skickade():
    """Även ett skickat utkast bär omaskerade personuppgifter."""
    u = utkast.skapa("kund", NYTTOLAST, SAMMANFATTNING)
    utkast.markera_skickat(u.utkast_id, {"Id": "1"})
    fil = saker_lagring.state_dir() / utkast.KATALOG / f"{u.utkast_id}.json"
    import os
    gammalt = datetime.now().timestamp() - 48 * 3600
    os.utime(fil, (gammalt, gammalt))

    assert utkast.rensa_gamla() == 1
    assert utkast.las(u.utkast_id) is None


# --- 3b. Payloadens fältnamn (sandbox-verifierade) -------------------------
# Den här sviten finns för att fältnamnen i verifikat-payloaden VAR FEL i
# första versionen — `Description` i stället för `VoucherText`, `VoucherSeries`
# i stället för `NumberSeries` — och samtliga 1651 tester var gröna ändå.
# Ingenting påstod något om vad som faktiskt skickas. Felet upptäcktes först
# vid en riktig GET mot Visma-sandboxen (2026-08-04), och POST:en är därefter
# verifierad skarpt (verifikat A31 i testbolaget "X Sandbox").
#
# Ändras något här ska det ske mot ett verkligt API-svar, inte mot en gissning.


class _FangarKlient:
    """Fångar det som skulle POSTas i stället för att skicka det."""

    def __init__(self) -> None:
        self.skickat: list[tuple[str, dict]] = []
        self.access_token = self.refresh_token = "T"

    def skicka(self, path, data):
        self.skickat.append((path, data))
        return {"Id": "nytt-id", "NumberAndNumberSeries": "A99"}

    def hamta_alla(self, path, params=None):
        if path == "/customers":
            return [{"Id": "cus-1", "Name": "Kundbolaget AB"}]
        return []


_VERIFIKAT_NYTTOLAST = {
    "beskrivning": "Kontant försäljning",
    "transaktionsdatum": "2026-08-04",
    "verifikationsserie": "A",
    "rader": [
        {"konto": "1930", "debet": 125, "kredit": 0, "text": "Insättning"},
        {"konto": "3041", "debet": 0, "kredit": 125, "text": ""},
    ],
}


def test_verifikatets_faltnamn_ar_de_sandboxverifierade():
    """Låser FÄLTNAMNEN, inte destinationen. `mal` anges därför uttryckligen:
    testet ska pröva payloadens form, inte vilken väg den standardmässigt
    tar — det senare prövas i test_verifikat_gar_till_utkast_som_standard."""
    from spiris_adapter import MAL_BOKFOR, utfor_utkast

    klient = _FangarKlient()
    utfor_utkast(klient, "verifikat", dict(_VERIFIKAT_NYTTOLAST), MAL_BOKFOR)

    path, payload = klient.skickat[0]
    assert path == "/vouchers"
    # Verifierat mot ett riktigt /vouchers-svar: VoucherText, inte Description.
    assert payload["VoucherText"] == "Kontant försäljning"
    assert payload["NumberSeries"] == "A"
    assert payload["VoucherDate"] == "2026-08-04"
    assert "Description" not in payload and "VoucherSeries" not in payload

    rad = payload["Rows"][0]
    assert rad["AccountNumber"] == 1930  # int, inte sträng
    assert rad["DebitAmount"] == Decimal("125")
    assert rad["CreditAmount"] == Decimal("0")
    assert rad["TransactionText"] == "Insättning"


class TestMalDirigering:
    """Steg 4: ett godkänt utkast går som STANDARD till Spiris utkastkö, inte
    rakt in i räkenskaperna.

    Skälet är oåterkallelighet. Ett bokfört verifikat kan enligt
    bokföringslagen 5 kap. inte tas bort, bara rättas med ett nytt; en bokförd
    kundfaktura kan dessutom mejlas till en riktig mottagare. Spiris
    utkastendpoints går att ändra (PUT) och ta bort (DELETE), och befordras
    till den skarpa posten först av människan i Spiris eget gränssnitt.

    Testerna låser att STANDARDVÄGEN är den återkalleliga — en framtida
    ändring som råkar vända på defaulten ska bli röd här, inte upptäckas av
    en användare med ett felaktigt bokfört verifikat."""

    def test_verifikat_gar_till_utkast_som_standard(self):
        from spiris_adapter import utfor_utkast

        klient = _FangarKlient()
        utfor_utkast(klient, "verifikat", dict(_VERIFIKAT_NYTTOLAST))

        path, _ = klient.skickat[0]
        assert path == "/voucherdrafts"

    def test_utkastvagen_har_samma_faltnamn_som_den_skarpa(self):
        from spiris_adapter import MAL_BOKFOR, utfor_utkast

        skarp, utkast_ = _FangarKlient(), _FangarKlient()
        utfor_utkast(skarp, "verifikat", dict(_VERIFIKAT_NYTTOLAST), MAL_BOKFOR)
        utfor_utkast(utkast_, "verifikat", dict(_VERIFIKAT_NYTTOLAST))

        assert skarp.skickat[0][1] == utkast_.skickat[0][1]

    def test_okant_mal_hojer_fel_och_skickar_ingenting(self):
        from spiris_adapter import SpirisKlientFel, utfor_utkast

        klient = _FangarKlient()
        with pytest.raises(SpirisKlientFel):
            utfor_utkast(klient, "verifikat", dict(_VERIFIKAT_NYTTOLAST), "bokför")

        assert klient.skickat == []  # fail-closed: inget lämnade datorn

    def test_kund_paverkas_inte_av_mal(self):
        """En kundpost har ingen utkastmotsvarighet i Spiris — den är varken
        en bokföringshändelse eller oåterkallelig (PUT och DELETE finns)."""
        from spiris_adapter import MAL_BOKFOR, utfor_utkast

        for mal in (None, MAL_BOKFOR):
            klient = _FangarKlient()
            nyttolast = {"Name": "Nytt Bolag AB"}
            if mal is None:
                utfor_utkast(klient, "kund", nyttolast)
            else:
                utfor_utkast(klient, "kund", nyttolast, mal)
            assert klient.skickat[0][0] == "/customers"


def test_kundutkast_postar_till_customers():
    from spiris_adapter import utfor_utkast

    klient = _FangarKlient()
    utfor_utkast(klient, "kund", {"Name": "Nytt Bolag AB"})
    assert klient.skickat[0][0] == "/customers"


def test_okand_utkasttyp_avvisas_av_utforaren():
    from spiris_adapter import utfor_utkast
    from spiris_klient import SpirisKlientFel

    with pytest.raises(SpirisKlientFel):
        utfor_utkast(_FangarKlient(), "betalning", {})


def test_kundfaktura_kraver_entydig_kund():
    """Fail-closed: hellre ingen faktura än en till fel mottagare."""
    from spiris_adapter import utfor_utkast
    from spiris_klient import SpirisKlientFel

    klient = _FangarKlient()
    with pytest.raises(SpirisKlientFel, match="Ingen kund"):
        utfor_utkast(klient, "kundfaktura", {
            "kundnamn": "Finns Inte AB", "rader": [],
            "fakturadatum": None, "forfallodatum": None,
        })
    assert klient.skickat == []


# --- 3c. Tidig sammanfattning via elicitation (S2-D) -----------------------
# Elicitation visar förslaget för användaren redan när det läggs, men är INTE
# grinden: MCP-specen tillåter en agentklient att besvara den automatiskt.
# Den bärande egenskapen är asymmetrisk och testas därför i båda riktningar:
#
#   avböjt  -> inget utkast skapas          (elicitation kan STOPPA)
#   accepterat -> utkast skapas, utfort=False (elicitation kan INTE godkänna)


class _FejkElicitSvar:
    def __init__(self, action, skapa_utkast=True):
        self.action = action
        self.data = type("D", (), {"skapa_utkast": skapa_utkast})()


class _FejkCtx:
    """Minimal Context-stand-in. Spelar in meddelandet och svarar som instruerat."""

    def __init__(self, svar=None, kastar=False):
        self.meddelanden: list[str] = []
        self._svar = svar or _FejkElicitSvar("accept")
        self._kastar = kastar

    async def elicit(self, message, schema):
        self.meddelanden.append(message)
        if self._kastar:
            raise RuntimeError("klienten stödjer inte elicitation")
        return self._svar


def test_accepterad_elicitation_godkanner_INTE_bara_skapar_utkast():
    """Kärnasymmetrin. Ett ja i dialogrutan får aldrig betyda 'skicka'."""
    ctx = _FejkCtx(_FejkElicitSvar("accept", skapa_utkast=True))

    svar = asyncio.run(server_modul.forbered_kund("Anna Andersson", ctx=ctx))

    assert svar["utfort"] is False
    assert utkast.las(svar["utkast_id"]).status == utkast.VANTAR
    assert "INGENTING HAR SKICKATS" in svar["info"]


@pytest.mark.parametrize(
    "svar_fran_klient",
    [
        _FejkElicitSvar("decline"),
        _FejkElicitSvar("cancel"),
        _FejkElicitSvar("accept", skapa_utkast=False),
    ],
)
def test_avbojd_elicitation_skapar_inget_utkast(svar_fran_klient):
    ctx = _FejkCtx(svar_fran_klient)

    svar = asyncio.run(server_modul.forbered_kund("Anna Andersson", ctx=ctx))

    assert svar["utkast_id"] is None
    assert svar["utfort"] is False
    assert utkast.lista(status=utkast.VANTAR) == []


def test_saknat_klientstod_stoppar_ingenting():
    """Fail-OPEN med avsikt: elicitation är inte ett säkerhetssteg, så en
    klient utan stöd får inte tysta funktionen."""
    ctx = _FejkCtx(kastar=True)

    svar = asyncio.run(server_modul.forbered_kund("Anna Andersson", ctx=ctx))

    assert svar["utkast_id"] is not None


def test_utan_ctx_fungerar_som_forut():
    svar = asyncio.run(server_modul.forbered_kund("Anna Andersson"))
    assert svar["utkast_id"] is not None


def test_meddelandet_visar_beloppen_och_sager_att_inget_skickas():
    ctx = _FejkCtx()

    asyncio.run(server_modul.forbered_kundfaktura(
        "Kundbolaget AB",
        [{"beskrivning": "Konsult", "antal": 10, "pris": 1500}],
        ctx=ctx,
    ))

    text = ctx.meddelanden[0]
    assert "Kundbolaget AB" in text
    assert "15,000.00" in text
    assert "SKICKAS INTE" in text
    assert "Åtgärder" in text


def test_obalanserat_verifikat_fragar_inte_alls():
    """Att fråga om något som ändå ska avvisas vore bara förvirrande."""
    ctx = _FejkCtx()

    svar = asyncio.run(server_modul.forbered_verifikat(
        "Skev post", "2026-08-04",
        [{"konto": "1930", "debet": 100}, {"konto": "3041", "kredit": 90}],
        ctx=ctx,
    ))

    assert ctx.meddelanden == []
    assert svar["utkast_id"] is None


def test_sammanfattningen_ar_densamma_tidigt_och_i_utkastet():
    """Det användaren ser i dialogrutan måste vara exakt det hon senare
    godkänner i appen — annars är den tidiga rutan vilseledande."""
    ctx = _FejkCtx()

    svar = asyncio.run(server_modul.forbered_verifikat(
        "Kontant försäljning", "2026-08-04",
        [{"konto": "1930", "debet": 1250}, {"konto": "3041", "kredit": 1250}],
        ctx=ctx,
    ))

    lagrad = utkast.las(svar["utkast_id"]).sammanfattning
    for etikett, varde in lagrad:
        assert f"{etikett}: {varde}" in ctx.meddelanden[0]


def test_ctx_ar_inte_ett_verktygsargument():
    """ctx injiceras av FastMCP och får inte dyka upp i verktygets schema —
    en klientmodell ska varken se eller kunna sätta det."""
    verktyg = {t.name: t for t in asyncio.run(server_modul.mcp.list_tools())}
    for namn in ("forbered_kund", "forbered_kundfaktura", "forbered_verifikat"):
        assert "ctx" not in verktyg[namn].inputSchema.get("properties", {})


# --- 4. Sökvägsvakten ------------------------------------------------------


@pytest.mark.parametrize(
    "elakt_id",
    ["../../secrets/.env", "..\\..\\secrets\\.env", "a" * 200, "", "utkast/../x",
     "nyckel.enc"],
)
def test_utkast_id_fran_ai_kan_inte_bli_en_filprimitiv(elakt_id):
    """utkast_id kommer från MCP-klienten, alltså från en AI."""
    assert utkast.las(elakt_id) is None


# --- 5. MCP-verktygen föreslår men utför aldrig ---------------------------


def test_mcp_servern_kan_inte_skriva_till_spiris():
    """Statiskt: MCP-servern får inte ens känna till skrivfunktionerna.

    Samma klass av test som test_mcp_servern_gar_aldrig_forbi_spiris_rag — ett
    verktyg som POSTar direkt skulle se helt rimligt ut i ett funktionstest."""
    from pathlib import Path

    källa = Path(server_modul.__file__).read_text(encoding="utf-8")
    for förbjudet in ("skapa_kund", "skapa_kundfaktura", "bekrafta_for_sandning",
                      "markera_skickat"):
        assert förbjudet not in källa, f"MCP-servern refererar {förbjudet}"


def test_forbered_kund_skapar_utkast_utan_att_utfora():
    svar = asyncio.run(server_modul.forbered_kund("Anna Andersson", epost="anna@example.com"))

    assert svar["utfort"] is False
    assert "INGENTING HAR SKICKATS" in svar["info"]
    u = utkast.las(svar["utkast_id"])
    assert u.typ == "kund" and u.nyttolast["Name"] == "Anna Andersson"


def test_forbered_kundfaktura_summerar_raderna():
    svar = asyncio.run(server_modul.forbered_kundfaktura(
        "Kundbolaget AB",
        [{"beskrivning": "Konsult", "antal": 10, "pris": 1500},
         {"beskrivning": "Resa", "antal": 1, "pris": 500}],
    ))
    assert svar["utfort"] is False
    text = str(svar["sammanfattning"])
    assert "15,500.00" in text or "15500" in text.replace(",", "")


def test_forbered_verifikat_kraver_balans():
    """Ett obalanserat verifikat ska aldrig ens bli ett utkast."""
    svar = asyncio.run(server_modul.forbered_verifikat(
        "Skev post", "2026-08-04",
        [{"konto": "1930", "debet": 100}, {"konto": "3041", "kredit": 90}],
    ))
    assert svar["utkast_id"] is None
    assert utkast.lista(status=utkast.VANTAR) == []


def test_forbered_verifikat_accepterar_balanserat():
    svar = asyncio.run(server_modul.forbered_verifikat(
        "Kontant försäljning", "2026-08-04",
        [{"konto": "1930", "debet": 1250, "text": "Insättning"},
         {"konto": "3041", "kredit": 1000},
         {"konto": "2611", "kredit": 250}],
    ))
    assert svar["utfort"] is False
    assert utkast.las(svar["utkast_id"]).typ == "verifikat"


def test_kontrollera_utkast_listar_vantande():
    asyncio.run(server_modul.forbered_kund("Anna Andersson"))
    asyncio.run(server_modul.forbered_kund("Bertil Bertilsson"))

    svar = server_modul.kontrollera_utkast()
    assert len(svar["utkast"]) == 2
    assert "2 utkast" in svar["info"]


def test_kontrollera_utkast_pa_okant_id():
    assert server_modul.kontrollera_utkast("0123456789abcdef")["utkast"] is None


def test_utkastsvaret_bar_sakerhetsnot():
    svar = asyncio.run(server_modul.forbered_kund("Anna Andersson"))
    assert "sakerhetsnot" in svar
