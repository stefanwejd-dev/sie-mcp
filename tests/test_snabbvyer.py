"""test_snabbvyer.py — P1/P2: snabbvyerna och påminnelsens två nivåer.

Snabbvyerna är deterministiska: de räknar lokalt och anropar aldrig en AI. Det
prövas här tillsammans med det som bär hela påminnelsefunktionen — att rött och
gult skiljs åt efter kundens EGET betalmönster, inte efter absoluta dagar.

Den bärande idén, med ett exempel ur skarp sandbox-data: en kund som normalt
betalar 12,7 dagar i FÖRSKOTT och nu är 65 dagar sen ligger 77,7 dagar över sitt
mönster — en större avvikelse än en kund som är 117 dagar sen men alltid är det.
En vanlig reskontralista sorterar tvärtom.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

import snabbvyer
from fpa_motor import bygg_aldersanalys, bygg_paminnelseforslag
from reskontra_tvatt import Kundpost, Leverantorspost

IDAG = date(2026, 8, 4)


def _kund(namn: str, dagar_forsent: int, belopp: str = "1000", motpart_id: str = "") -> Kundpost:
    return Kundpost(
        kund=namn,
        belopp=Decimal(belopp),
        betalstatus="obetald",
        forfallodatum=IDAG - timedelta(days=dagar_forsent),
        motpart_id=motpart_id or namn.lower(),
    )


def _lev(namn: str, dagar_forsent: int, belopp: str = "1000") -> Leverantorspost:
    return Leverantorspost(
        leverantor=namn,
        belopp=Decimal(belopp),
        betalstatus="obetald",
        forfallodatum=IDAG - timedelta(days=dagar_forsent),
    )


# --- Påminnelsens två nivåer -----------------------------------------------


def test_kund_som_brutit_sitt_monster_blir_rod():
    """Normalt 5 dagar sen, nu 20 -> 15 dagar över mönstret."""
    f = bygg_paminnelseforslag(
        [_kund("Sen Kund AB", 20, motpart_id="k1")], {"k1": Decimal("5")}, IDAG
    )
    assert len(f["rod"]) == 1 and not f["gul"]
    assert f["rod"][0]["dagar_over_monster"] == Decimal("15")


def test_kund_inom_sitt_monster_blir_gul():
    """Normalt 12 dagar sen, nu 13 -> inom marginalen, inget att larma om."""
    f = bygg_paminnelseforslag(
        [_kund("Vanligt Sen AB", 13, motpart_id="k1")], {"k1": Decimal("12")}, IDAG
    )
    assert len(f["gul"]) == 1 and not f["rod"]


def test_marginalen_hindrar_att_allt_blir_rott():
    """Utan marginal blir en kund som normalt är 12 dagar sen röd på dag 13."""
    beteende = {"k1": Decimal("12")}
    inom = bygg_paminnelseforslag([_kund("A", 15, motpart_id="k1")], beteende, IDAG)
    utanfor = bygg_paminnelseforslag([_kund("A", 16, motpart_id="k1")], beteende, IDAG)

    assert len(inom["gul"]) == 1, "3 dagars marginal ska rymma dag 15"
    assert len(utanfor["rod"]) == 1


def test_kund_utan_historik_blir_rod():
    """Arkitektbeslut B1: en ny kund som inte betalar ska synas, inte döljas."""
    f = bygg_paminnelseforslag([_kund("Ny Kund AB", 5, motpart_id="okänd")], {}, IDAG)

    assert len(f["rod"]) == 1
    assert f["rod"][0]["saknar_historik"] is True
    assert f["rod"][0]["normalt_monster_dagar"] is None


def test_kund_som_normalt_betalar_i_forskott_far_stor_avvikelse():
    """Skarpt fall ur sandboxen: −12,7 dagar normalt, 65 dagar sen nu."""
    f = bygg_paminnelseforslag(
        [_kund("Karl Svensson", 65, motpart_id="k1")],
        {"k1": Decimal("-12.7")},
        IDAG,
    )
    assert f["rod"][0]["dagar_over_monster"] == Decimal("77.7")


def test_ej_forfallen_faktura_ingar_inte():
    framtida = Kundpost(kund="Framtid AB", belopp=Decimal("500"), betalstatus="obetald",
                        forfallodatum=IDAG + timedelta(days=10), motpart_id="k1")
    f = bygg_paminnelseforslag([framtida], {}, IDAG)
    assert not f["rod"] and not f["gul"]


def test_faktura_utan_forfallodatum_hoppas_over():
    utan = Kundpost(kund="Okänd", belopp=Decimal("500"), betalstatus="obetald",
                    forfallodatum=None, motpart_id="k1")
    f = bygg_paminnelseforslag([utan], {}, IDAG)
    assert not f["rod"] and not f["gul"]


def test_rangordning_lyfter_stort_belopp_som_precis_brutit_monstret():
    """belopp × dagar över mönstret — inte bara dagar."""
    poster = [
        _kund("Liten men kroniskt sen", 60, belopp="100", motpart_id="k1"),
        _kund("Stor som precis brutit", 12, belopp="100000", motpart_id="k2"),
    ]
    f = bygg_paminnelseforslag(poster, {"k1": Decimal("55"), "k2": Decimal("0")}, IDAG)

    assert f["rod"][0]["kund"] == "Stor som precis brutit"


def test_beloppssummor_per_grupp():
    poster = [_kund("A", 30, "1000", "k1"), _kund("B", 11, "500", "k2")]
    f = bygg_paminnelseforslag(poster, {"k1": Decimal("0"), "k2": Decimal("10")}, IDAG)

    assert f["rod_belopp"] == Decimal("1000")
    assert f["gul_belopp"] == Decimal("500")


# --- Åldersanalys -----------------------------------------------------------


def test_aldersanalys_placerar_i_ratt_hink():
    poster = [_kund("A", 10), _kund("B", 45), _kund("C", 75), _kund("D", 200)]
    a = bygg_aldersanalys(poster, IDAG)

    assert a["hinkar"]["0–30"]["antal"] == 1
    assert a["hinkar"]["31–60"]["antal"] == 1
    assert a["hinkar"]["61–90"]["antal"] == 1
    assert a["hinkar"]["91+"]["antal"] == 1


def test_aldersanalys_skiljer_ej_forfallna_fran_okant():
    poster = [
        Kundpost(kund="Framtid", belopp=Decimal("1"), betalstatus="x",
                 forfallodatum=IDAG + timedelta(days=5)),
        Kundpost(kund="Utan datum", belopp=Decimal("2"), betalstatus="x",
                 forfallodatum=None),
    ]
    a = bygg_aldersanalys(poster, IDAG)

    assert a["hinkar"]["ej_forfallna"]["antal"] == 1
    assert a["hinkar"]["okant"]["antal"] == 1, "saknat datum får inte tyst bli 'ej förfallen'"


# --- Vyerna -----------------------------------------------------------------


@pytest.fixture
def data() -> snabbvyer.Vydata:
    return snabbvyer.Vydata(
        idag=IDAG,
        kundreskontra=[
            _kund("Bolaget AB", 40, "5000", "k1"),
            _kund("Anna Andersson", 5, "1200", "k2"),
            Kundpost(kund="Framtid AB", belopp=Decimal("800"), betalstatus="obetald",
                     forfallodatum=IDAG + timedelta(days=20), motpart_id="k3"),
        ],
        leverantorsreskontra=[
            _lev("Kontorsvaror AB", 10, "3000"),
            _lev("Hyresvärd AB", -3, "15000"),  # förfaller om 3 dgr
            Leverantorspost(
                leverantor="Framtid Leverantör",
                belopp=Decimal("2000"),
                betalstatus="obetald",
                forfallodatum=IDAG + timedelta(days=25),
            ),
        ],
        kundbetalbeteende={"k2": Decimal("10")},
    )


@pytest.mark.parametrize("vy", (snabbvyer.SNABBVYER_KUND + snabbvyer.SNABBVYER_LEVERANTOR), ids=lambda v: v.id)
def test_varje_vy_bygger_utan_fel(vy, data):
    resultat = vy.bygg(data)
    assert resultat.rubrik
    assert resultat.sektioner


@pytest.mark.parametrize("vy", (snabbvyer.SNABBVYER_KUND + snabbvyer.SNABBVYER_LEVERANTOR), ids=lambda v: v.id)
def test_varje_vy_tal_att_data_saknas(vy):
    """Ingen reskontra hämtad ska ge en förklaring, aldrig en tom tabell."""
    resultat = vy.bygg(snabbvyer.Vydata(idag=IDAG))
    assert "inte hämtats" in resultat.sektioner[0].beskrivning


def test_utestaende_summerar_alla_oppna(data):
    r = snabbvyer.bygg_utestaende_kundfakturor(data)
    assert r.nyckeltal[1].varde == "3"
    assert r.sektioner[0].tabell.summa_rad["belopp"] == Decimal("7000")


def test_forfallna_utesluter_framtida(data):
    r = snabbvyer.bygg_forfallna_kundfakturor(data)
    kunder = {rad["kund"] for rad in r.sektioner[0].tabell.rader}
    assert "Framtid AB" not in kunder
    assert r.sektioner[0].niva == "rod"


def test_forfallnavyn_blir_gron_nar_inget_forfallit():
    data = snabbvyer.Vydata(idag=IDAG, kundreskontra=[
        Kundpost(kund="Framtid AB", belopp=Decimal("1"), betalstatus="x",
                 forfallodatum=IDAG + timedelta(days=5))
    ])
    r = snabbvyer.bygg_forfallna_kundfakturor(data)
    assert r.sektioner[0].niva == "gron"
    assert r.sektioner[0].tabell is None


def test_paminnelsevyn_har_bada_nivaerna(data):
    r = snabbvyer.bygg_paminnelsevy(data)
    nivaer = [s.niva for s in r.sektioner]
    assert nivaer == ["rod", "gul"]


def test_paminnelsevyn_visar_riktiga_namn_lokalt(data):
    """P0: lokala vyer visar klartext. En lista där största kunden heter
    'Fiktiv Kund 3' är oanvändbar."""
    r = snabbvyer.bygg_paminnelsevy(data)
    alla = str([s.tabell.rader for s in r.sektioner if s.tabell])
    assert "Anna Andersson" in alla or "Bolaget AB" in alla
    assert "Fiktiv Kund" not in alla


def test_lev_utestaende_summerar_alla_oppna(data):
    r = snabbvyer.bygg_utestaende_leverantorsfakturor(data)
    assert r.nyckeltal[1].varde == "3"
    assert r.sektioner[0].tabell.summa_rad["belopp"] == Decimal("20000")


def test_lev_forfallna_utesluter_framtida(data):
    r = snabbvyer.bygg_forfallna_leverantorsfakturor(data)
    levs = {rad["leverantor"] for rad in r.sektioner[0].tabell.rader}
    assert "Framtid Leverantör" not in levs
    assert r.sektioner[0].niva == "rod"


def test_lev_betala_har_bada_nivaerna(data):
    r = snabbvyer.bygg_betalningsforslag_vy(data)
    nivaer = [s.niva for s in r.sektioner]
    assert nivaer == ["rod", "gul"]
    assert r.sektioner[0].tabell.rader[0]["leverantor"] == "Kontorsvaror AB"
    assert r.sektioner[1].tabell.rader[0]["leverantor"] == "Hyresvärd AB"


def test_vyerna_anropar_ingen_ai():
    """Statiskt: snabbvyerna ska vara deterministiska och fungera utan
    AI-nyckel. En import av ett AI-lager här vore ett designbrott."""
    import inspect

    kalla = inspect.getsource(snabbvyer)
    for forbjudet in ("ai_adapter", "haiku_klient", "chatt_klient", "ollama_klient"):
        assert forbjudet not in kalla


def test_hitta_vy_tal_okant_id():
    """Ett gammalt session_state efter en uppdatering får inte krascha."""
    assert snabbvyer.hitta_vy((snabbvyer.SNABBVYER_KUND + snabbvyer.SNABBVYER_LEVERANTOR), "finns_inte") is None
    assert snabbvyer.hitta_vy((snabbvyer.SNABBVYER_KUND + snabbvyer.SNABBVYER_LEVERANTOR), None) is None

# --- Tester för Uppgift 1.1 (Etapp 1) ---

def test_vydata_utan_nya_falt_gar_att_skapa():
    data = snabbvyer.Vydata(idag=date(2026, 8, 6))
    assert data.idag == date(2026, 8, 6)
    assert data.kundreskontra is None

def test_vydata_nya_falt_har_none_som_standard():
    data = snabbvyer.Vydata(idag=date(2026, 8, 6))
    assert data.kontoplan is None
    assert data.kontosaldon is None
    assert data.verifikationer is None
    assert data.verifikatutkast is None
    assert data.momsoversikt is None
    assert data.soktext == ""
