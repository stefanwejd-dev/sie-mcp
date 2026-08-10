"""test_mcp_villkorssparr.py — MCP-serverns fail-closed villkorsspärr.

MCP-servern kör headless: ingen människa ser något gränssnitt när en AI-klient
anropar ett verktyg. Utan spärren kunde alltså bokföring läsas och sändas vidare
till en extern AI utan att någon någonsin tagit ställning till villkoren.

Den här sviten godkänner medvetet INTE villkoren (till skillnad från
test_mcp_server.py, som gör det för att kunna pröva verktygens sakinnehåll).
Allt som testas här är att spärren håller.
"""

from __future__ import annotations

import asyncio

import pytest

import compliance
import mcp_server.server as server_modul
from mcp_server.server import (
    spiris_kunder,
    spiris_leverantorer,
    spiris_projekt,
    spiris_kostnadsstallen,
    spiris_kontosaldo,
    spiris_referensdata,
    spiris_bankhandelser,
    spiris_avstamningslage,
    spiris_verifikatutkast,
    spiris_sie4export,
    berakna_vasentlighet,
    granska_kontotyper,
    spiris_artiklar,
    spiris_balansrapport,
    spiris_bankkonton,
    spiris_dashboard,
    spiris_foretagsinfo,
    spiris_kassaflodesanalys,
    spiris_kontoplan,
    spiris_kontosaldon,
    spiris_kontotransaktioner,
    spiris_kundbetalbeteende,
    spiris_kundreskontra,
    spiris_leverantorsfakturor,
    spiris_leverantorsreskontra,
    spiris_likviditetsprognos,
    spiris_momskoder,
    spiris_momsoversikt,
    spiris_momsrapporter,
    spiris_offerter,
    spiris_order,
    spiris_rakenskapsar,
    spiris_resultatrapport,
    spiris_sok_verifikationer,
    visa_anvandarvillkor,
    spiris_hamta_ett,
    spiris_ingaende_balans,
    spiris_kontoplan_alla,
    spiris_kundfakturor,
    spiris_verifikationer_alla,
    spiris_valutakurs,
    spiris_anlaggningstillgangar,
    spiris_kundreskontraposter,
    spiris_anvandare,
    spiris_underlag,
    spiris_hamta_underlag, spiris_offertutkast, spiris_bokforingslas,
    spiris_kvittningskandidater,
)

FILVERKTYG = [berakna_vasentlighet, granska_kontotyper]

# Namn -> giltiga argument. Varje Spiris-verktyg i registret MÅSTE finnas här;
# test_alla_spirisverktyg_ar_tackta_av_sparrsviten bevakar det. Utan den
# bevakningen räcker det att glömma en rad för att ett nytt verktyg ska sakna
# spärrtest — och därmed i praktiken vara oskyddat.
SPIRIS_ARGUMENT: dict[str, tuple] = {
    "spiris_offertutkast": (),
    "spiris_prislistor": (),
    "spiris_rabattavtal": (),
    "spiris_etiketter": ("kund",),

    "spiris_bokforingslas": (),
    "spiris_kontosaldon": ("ar-1", "2026-06-30"),
    "spiris_kontotransaktioner": ("ar-1", "1930"),
    "spiris_sok_verifikationer": ("ar-1", "hyra"),
    "spiris_resultatrapport": ("2026-01-01", "2026-06-30"),
    "spiris_balansrapport": ("2026-06-30",),
    "spiris_kassaflodesanalys": ("2026-01-01", "2026-06-30"),
    "spiris_dashboard": ("2026-01-01", "2026-06-30"),
    "spiris_rakenskapsar": (),
    "spiris_kontoplan": ("ar-1",),
    "spiris_foretagsinfo": (),
    "spiris_artiklar": (),
    "spiris_leverantorsfakturor": (),
    "spiris_order": (),
    "spiris_offerter": (),
    "spiris_bankkonton": (),
    "spiris_momskoder": (),
    "spiris_momsrapporter": (),
    "spiris_momsoversikt": ("2026-12-31",),
    "spiris_leverantorsreskontra": (),
    "spiris_kundreskontra": (),
    "spiris_kundbetalbeteende": (),
    "spiris_likviditetsprognos": ("2026-06-30",),
    "spiris_kunder": (),
    "spiris_leverantorer": (),
    "spiris_projekt": (),
    "spiris_kostnadsstallen": (),
    "spiris_kontosaldo": ("1930", "2026-12-31"),
    "spiris_referensdata": ("enheter",),
    "spiris_bankhandelser": ("bank-1",),
    "spiris_avstamningslage": (),
    "spiris_verifikatutkast": (),
    "spiris_sie4export": ("2026-01-01", "2026-12-31"),
    "spiris_hamta_ett": ("kund", "123"),
    "spiris_ingaende_balans": (),
    "spiris_kontoplan_alla": (),
    "spiris_kundfakturor": (),
    "spiris_verifikationer_alla": (),
    "spiris_valutakurs": ("2026-01-01", "SEK", "EUR"),
    "spiris_anlaggningstillgangar": (),
    "spiris_kundreskontraposter": (),
    "spiris_anvandare": (),
    "spiris_underlag": (),
    "spiris_kvittningskandidater": ("123",),
    "spiris_hamta_underlag": ("123",),
    "spiris_periodiseringar": (),
    "spiris_bokforingslas": (),
    "spiris_verifikation": ("fy-1", "v-1"),
    "spiris_bankhandelse": ("b-1", "t-1"),
}

_SPIRISFUNKTIONER = {
    "spiris_kontosaldon": spiris_kontosaldon,
    "spiris_kontotransaktioner": spiris_kontotransaktioner,
    "spiris_sok_verifikationer": spiris_sok_verifikationer,
    "spiris_resultatrapport": spiris_resultatrapport,
    "spiris_balansrapport": spiris_balansrapport,
    "spiris_kassaflodesanalys": spiris_kassaflodesanalys,
    "spiris_dashboard": spiris_dashboard,
    "spiris_rakenskapsar": spiris_rakenskapsar,
    "spiris_kontoplan": spiris_kontoplan,
    "spiris_foretagsinfo": spiris_foretagsinfo,
    "spiris_artiklar": spiris_artiklar,
    "spiris_leverantorsfakturor": spiris_leverantorsfakturor,
    "spiris_order": spiris_order,
    "spiris_offerter": spiris_offerter,
    "spiris_periodiseringar": server_modul.spiris_periodiseringar,
    "spiris_bokforingslas": server_modul.spiris_bokforingslas,
    "spiris_bankkonton": spiris_bankkonton,
    "spiris_momskoder": spiris_momskoder,
    "spiris_momsrapporter": spiris_momsrapporter,
    "spiris_momsoversikt": spiris_momsoversikt,
    "spiris_leverantorsreskontra": spiris_leverantorsreskontra,
    "spiris_kundreskontra": spiris_kundreskontra,
    "spiris_kundbetalbeteende": spiris_kundbetalbeteende,
    "spiris_likviditetsprognos": spiris_likviditetsprognos,
    "spiris_kunder": spiris_kunder,
    "spiris_leverantorer": spiris_leverantorer,
    "spiris_projekt": spiris_projekt,
    "spiris_kostnadsstallen": spiris_kostnadsstallen,
    "spiris_kontosaldo": spiris_kontosaldo,
    "spiris_referensdata": spiris_referensdata,
    "spiris_bankhandelser": spiris_bankhandelser,
    "spiris_avstamningslage": spiris_avstamningslage,
    "spiris_verifikatutkast": spiris_verifikatutkast,
    "spiris_sie4export": spiris_sie4export,
    "spiris_hamta_ett": spiris_hamta_ett,
    "spiris_ingaende_balans": spiris_ingaende_balans,
    "spiris_kontoplan_alla": spiris_kontoplan_alla,
    "spiris_kundfakturor": spiris_kundfakturor,
    "spiris_verifikationer_alla": spiris_verifikationer_alla,
    "spiris_valutakurs": spiris_valutakurs,
    "spiris_anlaggningstillgangar": spiris_anlaggningstillgangar,
    "spiris_kundreskontraposter": spiris_kundreskontraposter,
    "spiris_anvandare": spiris_anvandare,
    "spiris_underlag": spiris_underlag,
    "spiris_kvittningskandidater": ("123",),
    "spiris_kvittningskandidater": spiris_kvittningskandidater,
    "spiris_hamta_underlag": spiris_hamta_underlag,
    "spiris_offertutkast": spiris_offertutkast,
    "spiris_prislistor": server_modul.spiris_prislistor,
    "spiris_rabattavtal": server_modul.spiris_rabattavtal,
    "spiris_etiketter": server_modul.spiris_etiketter,
    "spiris_verifikation": server_modul.spiris_verifikation,
    "spiris_bankhandelse": server_modul.spiris_bankhandelse,
    "spiris_bokforingslas": spiris_bokforingslas,
}

SPIRISVERKTYG = [
    (_SPIRISFUNKTIONER[namn], argument) for namn, argument in SPIRIS_ARGUMENT.items()
]


def _kor(verktyg, argument):
    resultat = verktyg(*argument)
    if asyncio.iscoroutine(resultat):
        return asyncio.run(resultat)
    return resultat


# --- Spärren håller ---------------------------------------------------------


@pytest.mark.parametrize("verktyg", FILVERKTYG, ids=lambda v: v.__name__)
def test_filverktyg_sparras_utan_godkannande(verktyg, tmp_path, monkeypatch):
    # Sökvägsvakten öppnas medvetet, så att det som testas är villkorsspärren
    # och inte att filen råkar ligga utanför en tillåten katalog.
    monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))
    fil = tmp_path / "bok.se"
    fil.write_text("#FLAGGA 0\n", encoding="utf-8")

    svar = verktyg(str(fil))

    assert svar["fel"] == compliance.SPARRTEXT_KORT
    assert svar.get("vasentlighet") is None
    assert svar.get("avvikelser") is None


def test_utkastverktyg_sparras_utan_godkannande():
    """Utkastverktygen skriver inget mot Spiris, men de skapar filer med
    omaskerade personuppgifter på disk. De måste omfattas av spärren."""
    for anrop in (
        lambda: server_modul.forbered_kund("Anna Andersson"),
        lambda: server_modul.forbered_kundfaktura(
            "Kund AB", [{"beskrivning": "Konsult", "antal": "1", "pris": "1000"}]
        ),
        lambda: server_modul.forbered_verifikat(
            "Test", "2026-08-04",
            [{"konto": "1930", "debet": "100"}, {"konto": "3041", "kredit": "100"}],
        ),
        # Steg 5: kundfakturans livscykelåtgärder. De två första är
        # UTÅTRIKTADE — spärren måste hålla före dem också, annars kunde ett
        # utskick till en tredje man förberedas innan någon människa sett ett
        # villkor.
        lambda: server_modul.forbered_fakturautskick("101"),
        lambda: server_modul.forbered_betalningspaminnelse("101"),
        lambda: server_modul.forbered_betalningsregistrering(
            "101", "1000.0", "2026-08-06", "bank-1"
        ),
        lambda: server_modul.forbered_makulering("101", "Felaktig faktura"),
        lambda: server_modul.forbered_saljdokumentutskick("offert", "5"),
        lambda: server_modul.forbered_efakturautskick("101"),
        lambda: server_modul.forbered_saljdokumentatgard("offert", "5", "godkann"),
        lambda: server_modul.forbered_leverantorsfakturautkast(
            "lev-1", [{"konto": "4010", "debet": "100"}]
        ),
        lambda: server_modul.forbered_attest("leverantorsfaktura", "L-1"),
        lambda: server_modul.forbered_leverantorsbetalning(
            "L-1", "100.0", "2026-08-06", "bank-1"
        ),
        lambda: server_modul.forbered_masterdataandring(
            "kund", "cus-1", {"namn": "Nytt AB"}
        ),
        lambda: server_modul.forbered_masterdataborttagning(
            "kund", "cus-1", "Dubblett"
        ),
        lambda: server_modul.forbered_sie4import("/finns/ej.se"),
    ):
        svar = asyncio.run(anrop())
        assert svar["utkast_id"] is None
        assert svar["info"] == compliance.SPARRTEXT_KORT

    assert server_modul.kontrollera_utkast()["info"] == compliance.SPARRTEXT_KORT


def test_juridikverktygen_sparras_utan_godkannande():
    """Juridikverktygen läser ingen bokföring, men `sok_lagstiftning` gör ett
    UTGÅENDE anrop till data.riksdagen.se med en sökterm som kommer från
    AI-klienten och kan bära affärskontext.

    Spärrens syfte är att inget utflöde sker innan en människa godkänt
    villkoren — och ett utflöde är ett utflöde oavsett mottagare. Verktygen
    registrerades utan spärr; testet finns för att det inte ska kunna hända
    tyst igen."""
    for anrop in (
        lambda: server_modul.sok_lagstiftning("avdrag julbord"),
        lambda: server_modul.skatteverket_rattslig_vagledning("traktamente"),
    ):
        svar = asyncio.run(anrop())
        assert svar["info"] == compliance.SPARRTEXT_KORT


def test_ingen_utgaende_trafik_fran_juridikverktyget_utan_godkannande(monkeypatch):
    """Spärren måste ligga FÖRE nätverksanropet, inte efter."""
    import juridik_api

    def _far_inte_anropas(*a, **k):
        raise AssertionError("nätverksanrop gjordes trots spärrat läge")

    monkeypatch.setattr(juridik_api, "sok_svensk_lagstiftning", _far_inte_anropas)
    asyncio.run(server_modul.sok_lagstiftning("avdrag julbord"))


def test_inget_utkast_skrivs_till_disk_utan_godkannande(monkeypatch):
    """Spärren måste ligga FÖRE filskrivningen, inte efter."""
    import utkast as utkast_modul

    def _far_inte_anropas(*a, **k):
        raise AssertionError("utkast skrevs trots att villkoren inte godkänts")

    monkeypatch.setattr(utkast_modul, "skapa", _far_inte_anropas)
    asyncio.run(server_modul.forbered_kund("Anna Andersson"))


def test_alla_registrerade_verktyg_har_ett_sparrtest():
    """Metatest över HELA registret, inte bara Spiris-verktygen.

    `visa_anvandarvillkor` är det enda undantaget — det måste vara anropbart i
    spärrat läge, annars kan användaren inte få veta hur hon godkänner."""
    registrerade = {t.name for t in asyncio.run(server_modul.mcp.list_tools())}
    # Fas 6-aliaser: rena en-rads-delegerare till spiris_*-verktygen. Täcks
    # implicit av respektive spiris_*-test ovan — behöver inga egna sparrtester.
    alias_verktyg = {
        "kontosaldon", "kontotransaktioner", "sok_verifikationer",
        "resultatrapport", "balansrapport", "rakenskapsar", "kontoplan",
        "foretagsinfo", "artiklar", "leverantorsfakturor", "order",
        "offerter", "bankkonton", "momskoder", "momsrapporter",
        "momsoversikt", "kassaflodesanalys", "dashboard", "verifikatutkast",
        "leverantorsreskontra", "kundreskontra", "kundbetalbeteende",
        "likviditetsprognos", "kunder", "leverantorer", "projekt",
        "kostnadsstallen", "kontosaldo", "referensdata", "bankhandelser",
        "avstamningslage",
        "hamta_ett", "ingaende_balans", "kontoplan_alla", "kundfakturor", "verifikationer_alla", "valutakurs", "anlaggningstillgangar", "kundreskontraposter", "anvandare", "periodiseringar"}
    tackta = (
        set(SPIRIS_ARGUMENT)
        | {"berakna_vasentlighet", "granska_kontotyper"}
        | {"forbered_kund", "forbered_kundfaktura", "forbered_verifikat",
           "kontrollera_utkast"}
        | {"forbered_fakturautskick", "forbered_betalningspaminnelse",
           "forbered_betalningsregistrering", "forbered_makulering"}
        | {"forbered_saljdokumentutskick", "forbered_efakturautskick",
           "forbered_saljdokumentatgard"}
        | {"sok_lagstiftning", "skatteverket_rattslig_vagledning"}
        | {"forbered_leverantorsfakturautkast", "forbered_attest",
           "forbered_leverantorsbetalning"}
        | {"forbered_masterdataandring", "forbered_masterdataborttagning"}
        | {"forbered_utkastandring", "forbered_utkastborttagning", "forbered_utkastbokforing"}
        | {"forbered_periodisering", "forbered_periodiseringsandring", "forbered_periodiseringsborttagning", "forbered_betalningsverifikat", "forbered_underlagskoppling", "forbered_konto", "forbered_kontoandring", "forbered_bokforingslas", "forbered_rotrut"}
        | {"forbered_sie4import", "forbered_offertutkast", "forbered_kvittning"}
        | {"visa_anvandarvillkor"}
        | alias_verktyg
    )
    saknas = registrerade - tackta
    assert not saknas, f"verktyg utan spärrtest: {sorted(saknas)}"


def test_alla_spirisverktyg_ar_tackta_av_sparrsviten():
    """Metatest: varje registrerat Spiris-verktyg måste ha argument i
    SPIRIS_ARGUMENT, annars saknar det spärrtest.

    Detta är sviten som gör att ett framtida verktyg inte kan glömmas bort. Blir
    testet rött är åtgärden att lägga till raden — aldrig att lätta på kravet."""
    registrerade = {
        t.name
        for t in asyncio.run(server_modul.mcp.list_tools())
        if t.name.startswith("spiris_")
    }
    saknas = registrerade - set(SPIRIS_ARGUMENT)
    assert not saknas, f"Spiris-verktyg utan spärrtest: {sorted(saknas)}"


@pytest.mark.parametrize("verktyg,argument", SPIRISVERKTYG, ids=lambda v: getattr(v, "__name__", ""))
def test_spirisverktyg_sparras_utan_godkannande(verktyg, argument, monkeypatch):
    def _far_inte_anropas(*a, **k):
        raise AssertionError("Spiris-klienten byggdes trots att villkoren inte godkänts")

    monkeypatch.setattr(server_modul, "bygg_klient", _far_inte_anropas)

    svar = _kor(verktyg, argument)

    assert svar["info"] == compliance.SPARRTEXT_KORT
    assert svar["data"] == []
    assert svar["antal_exkluderade"] == 0


def test_filverktyg_laser_ingen_fil_nar_villkor_saknas(tmp_path, monkeypatch):
    """Spärren ska ligga FÖRE filåtkomsten, inte efter."""
    monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))

    def _far_inte_anropas(*a, **k):
        raise AssertionError("SIE-filen lästes trots att villkoren inte godkänts")

    monkeypatch.setattr(server_modul, "parse_sie4", _far_inte_anropas)
    fil = tmp_path / "bok.se"
    fil.write_text("#FLAGGA 0\n", encoding="utf-8")

    assert berakna_vasentlighet(str(fil))["fel"] == compliance.SPARRTEXT_KORT
    assert granska_kontotyper(str(fil))["fel"] == compliance.SPARRTEXT_KORT


def test_fel_i_vakten_sparrar_istallet_for_att_oppna(monkeypatch, tmp_path):
    """Fail-closed: ett undantag i kontrollen får aldrig tolkas som godkänt."""
    compliance.godkann_compliance()

    def _kraschar():
        raise RuntimeError("oväntat")

    monkeypatch.setattr(compliance, "ar_compliance_godkand", _kraschar)
    monkeypatch.setenv("SIE_MCP_SIE_KATALOGER", str(tmp_path))

    assert server_modul._villkor_godkanda() is False
    assert berakna_vasentlighet(str(tmp_path / "bok.se"))["fel"] == compliance.SPARRTEXT_KORT


# --- Godkännandet öppnar, och kan inte ske via MCP --------------------------


def test_godkannande_slapper_igenom_spirisvakten(monkeypatch):
    """Efter godkännande ska spärren inte längre stoppa — då tar den
    ordinarie fail-closed-logiken (saknad session) över."""
    compliance.godkann_compliance()

    def _ingen_session(*a, **k):
        raise server_modul.SpirisSessionFel("ingen session")

    monkeypatch.setattr(server_modul, "bygg_klient", _ingen_session)

    svar = asyncio.run(spiris_kontosaldon("ar-1", "2026-06-30"))

    assert svar["info"] != compliance.SPARRTEXT_KORT
    assert "session" in svar["info"].lower()


def test_villkorsverktyget_kan_inte_godkanna_nagot():
    """Det läsande verktyget får aldrig ha en sidoeffekt — en AI ska inte
    kunna acceptera juridiskt ansvar för människan som kör den."""
    svar = visa_anvandarvillkor()

    assert svar["godkant"] is False
    assert not compliance.ar_compliance_godkand()
    assert compliance.villkorstext() in svar["villkor"]


def test_villkorsverktyget_visar_godkant_lage():
    compliance.godkann_compliance()
    assert visa_anvandarvillkor()["godkant"] is True


def test_ingen_mcp_vag_kan_skriva_godkannandet():
    """Regressionsskydd: inget exporterat MCP-verktyg får anropa
    godkann_compliance eller aterkalla_compliance."""
    import inspect

    for namn, objekt in vars(server_modul).items():
        if not callable(objekt) or namn.startswith("_"):
            continue
        try:
            kalla = inspect.getsource(objekt)
        except (OSError, TypeError):
            continue
        assert "godkann_compliance" not in kalla, f"{namn} får inte godkänna villkor"
        assert "aterkalla_compliance" not in kalla, f"{namn} får inte återkalla villkor"

def test_mcp_verktyg_forbered_underlagskoppling_sparrat():
    """Låser att forbered_underlagskoppling avvisas om villkoren inte är godkända."""
    import compliance
    import asyncio
    import mcp_server.server as server_modul
    compliance._VILLKOR_GODKANDA = False
    res = asyncio.run(server_modul.forbered_underlagskoppling("123", "456"))
    assert compliance.SPARRTEXT_KORT in res.get("info", "")
