"""Steg 8 — metatester för hantverksbok/UI_ATGARDER_I_VYN.md §6.

Täckningsgapet uppstod för att bindningen mellan förmåga och gränssnitt inte
testades (§1). Dessa test är en del av leveransen, inte en efterrätt — de ska
gå sönder när någon lägger till en förmåga utan gränssnitt, eller bygger en
funktion utan att låsa upp den."""

from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest

import bokslutskontroll  # noqa: F401  — fyller motor.KONTROLLER
import snabbvyer
import snabbvy_render
import utkast
import rum
from bokslutskontroll.modell import Fynd, Konteringsrad, Rattelseforslag, Regelhanvisning
from bokslutskontroll.motor import KONTROLLER
from kalla_protokoll import Formaga
from spiris_adapter import _bygg_verifikat_payload
from stil import HARKOMST_LOKAL

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _lasa(namn: str) -> str:
    return (_REPO_ROOT / namn).read_text(encoding="utf-8")


class _FakeKolumn:
    def __init__(self, st: "_FakeSt") -> None:
        self._st = st

    def button(self, etikett, **kwargs):
        self._st.button_calls.append((etikett, kwargs))
        return self._st.tryck_pa == etikett

    def metric(self, *a, **k) -> None:
        pass


class _SessionState(dict):
    """Riktig `st.session_state` stödjer både dict- och attributåtkomst
    (`st.session_state["x"]` OCH `st.session_state.x`) — koden i rum_render.py
    använder båda formerna, så fejken måste också göra det."""

    def __getattr__(self, namn):
        try:
            return self[namn]
        except KeyError as e:
            raise AttributeError(namn) from e

    def __setattr__(self, namn, värde) -> None:
        self[namn] = värde


class _FakeSt:
    """Minimal Streamlit-fejk: bara det rendera_knapprad/rendera_snabbvyfalt/
    rendera_resultat/rendera_bokslut faktiskt anropar."""

    def __init__(self) -> None:
        self.session_state = _SessionState()
        self.button_calls: list[tuple[str, dict]] = []
        self.info_calls: list[str] = []
        self.tryck_pa: str | None = None  # etikett som ska "klickas"

    def columns(self, n: int):
        return [_FakeKolumn(self) for _ in range(n)]

    def header(self, *a, **k) -> None:
        pass

    def caption(self, *a, **k) -> None:
        pass

    def markdown(self, *a, **k) -> None:
        pass

    def subheader(self, *a, **k) -> None:
        pass

    def write(self, *a, **k) -> None:
        pass

    def warning(self, *a, **k) -> None:
        pass

    def error(self, *a, **k) -> None:
        pass

    def success(self, *a, **k) -> None:
        pass

    def info(self, msg) -> None:
        self.info_calls.append(msg)

    def button(self, etikett, **kwargs):
        self.button_calls.append((etikett, kwargs))
        return self.tryck_pa == etikett

    def rerun(self) -> None:
        raise _Rerun()


class _Rerun(Exception):
    pass


def _fynd(kontroll_id: str, allvarlighet: str = "avvikelse", **kwargs) -> Fynd:
    return Fynd(
        kontroll_id=kontroll_id,
        rubrik=f"Testfynd {kontroll_id}",
        allvarlighet=allvarlighet,
        motivering="test",
        **kwargs,
    )


# --- Metatest 1: varje byggd kontroll når gränssnittet ----------------------


def test_1_varje_byggd_kontroll_nar_bokslutsrummet():
    """Ett Fynd från VARJE registrerad kontroll (KONTROLLER) ska överleva
    vägen från Vydata.fynd till Atgardsforslag, oklippt. En ny kontroll som
    ingen vy visar (t.ex. ett filter som råkar utesluta ett kontroll-id) ska
    fälla det här testet."""
    assert KONTROLLER, "inga kontroller registrerade — kan inte testa täckning"

    alla_fynd = [_fynd(kid) for kid in KONTROLLER]
    data = snabbvyer.Vydata(idag=__import__("datetime").date.today(), fynd=alla_fynd)

    resultat = snabbvyer.bygg_bokslutskontroll(data)

    visade_ider = {f.rubrik.split(" — ", 1)[0] for f in resultat.atgarder}
    assert visade_ider == set(KONTROLLER), (
        f"Kontroller som inte når gränssnittet: {set(KONTROLLER) - visade_ider}"
    )


# --- Metatest 2: statusen är sann i båda riktningarna -----------------------


def test_2_byggd_knapp_kor_utan_att_kasta():
    tom_data = snabbvyer.Vydata(idag=__import__("datetime").date.today())
    for vy in snabbvyer.SNABBVYER_BOKSLUT:
        if vy.status != "byggd":
            continue
        resultat = vy.bygg(tom_data)
        assert isinstance(resultat, snabbvyer.Snabbvyresultat)


def test_2_kommande_knapp_ar_platshallaren_inte_en_fardig_funktion():
    """Den andra halvan — den som är lätt att glömma: en funktion som byggts
    men vars knapp lämnats som 'kommande' är osynlig trots att den finns.
    Testar därför att en 'kommande'-vy INTE av misstag pekar på en riktig,
    färdig bygg-funktion."""
    for vy in snabbvyer.SNABBVYER_BOKSLUT:
        if vy.status != "kommande":
            continue
        assert vy.bygg is snabbvyer._kommande_platshallare, (
            f"{vy.id} är märkt 'kommande' men bygg är en annan (riktig?) "
            "funktion — status och verklighet har glidit isär."
        )
        with pytest.raises(NotImplementedError):
            vy.bygg(snabbvyer.Vydata(idag=__import__("datetime").date.today()))


# --- Metatest 3 & 4: utkasttyp och nyttolast ---------------------------------


def _syntetiskt_fynd_med_forslag() -> Fynd:
    return Fynd(
        kontroll_id="K-01",
        rubrik="Testfynd med förslag",
        allvarlighet="avvikelse",
        motivering="test",
        regel=Regelhanvisning(
            kalla="SFS 1999:1078", beteckning="5 kap. 1 §",
            lank_manniska="https://example.invalid/",
        ),
        forslag=Rattelseforslag(
            beskrivning="Rätta felkonteringen",
            rader=(
                Konteringsrad(kontonr="1930", debet=Decimal("100")),
                Konteringsrad(kontonr="3010", kredit=Decimal("100")),
            ),
        ),
    )


def test_3_atgardsknappens_utkasttyp_finns_i_giltiga_typer():
    forslag = snabbvyer._fynd_till_atgardsforslag(
        _syntetiskt_fynd_med_forslag(), snabbvyer.Formateringsval()
    )
    assert forslag.knapp is not None
    assert forslag.knapp.utkasttyp in utkast.GILTIGA_TYPER


def test_4_nyttolasten_validerar_mot_bygg_verifikat_payload():
    forslag = snabbvyer._fynd_till_atgardsforslag(
        _syntetiskt_fynd_med_forslag(), snabbvyer.Formateringsval()
    )
    payload = _bygg_verifikat_payload(forslag.knapp.nyttolast)
    assert payload["Rows"]


def test_atgardsforslag_utan_forslag_saknar_knapp():
    """Ett fynd utan Rattelseforslag (I-2 — vanligast i praktiken idag) blir
    ett förslag UTAN knapp. Fullt giltigt, se §3.2."""
    forslag = snabbvyer._fynd_till_atgardsforslag(_fynd("K-13"), snabbvyer.Formateringsval())
    assert forslag.knapp is None


# --- Metatest 5: rendera_resultat tål Snabbvyresultat utan atgarder --------


def test_5_rendera_resultat_tal_resultat_utan_atgarder_attribut():
    from types import SimpleNamespace

    resultat_utan_atgarder = SimpleNamespace(
        rubrik="Test", harkomst=HARKOMST_LOKAL, nyckeltal=[], sektioner=[], fotnot=None,
    )
    st = _FakeSt()
    snabbvy_render.rendera_resultat(st, resultat_utan_atgarder)  # ska inte kasta


def test_5_rendera_resultat_ritar_forslag_utan_knapp_utan_att_kasta():
    forslag = snabbvyer._fynd_till_atgardsforslag(_fynd("K-13"), snabbvyer.Formateringsval())
    resultat = snabbvyer.Snabbvyresultat(rubrik="Test", atgarder=(forslag,))
    st = _FakeSt()
    snabbvy_render.rendera_resultat(st, resultat)


def test_5_rendera_resultat_ritar_forslag_med_knapp_och_bekraftelsetext():
    forslag = snabbvyer._fynd_till_atgardsforslag(
        _syntetiskt_fynd_med_forslag(), snabbvyer.Formateringsval()
    )
    resultat = snabbvyer.Snabbvyresultat(rubrik="Test", atgarder=(forslag,))
    st = _FakeSt()
    snabbvy_render.rendera_resultat(st, resultat)
    etiketter = [e for e, _ in st.button_calls]
    assert forslag.knapp.etikett in etiketter


# --- Metatest 6: en kommande-knapp går inte att trycka på -------------------


def test_6_kommande_knapp_ar_disabled_och_laksmarkt():
    st = _FakeSt()
    snabbvy_render.rendera_knapprad(st, snabbvyer.SNABBVYER_BOKSLUT, "test_bokslut_knapprad")

    kommande_ider = {v.id for v in snabbvyer.SNABBVYER_BOKSLUT if v.status == "kommande"}
    assert kommande_ider, "inga kommande-knappar att pröva mot"

    for etikett, kwargs in st.button_calls:
        if "🔒" in etikett:
            assert kwargs.get("disabled") is True

    laste_etiketter = [e for e, k in st.button_calls if k.get("disabled")]
    assert len(laste_etiketter) == len(kommande_ider)
    assert all(e.startswith("🔒 ") for e in laste_etiketter)


def test_6_byggd_knapp_ar_inte_disabled():
    st = _FakeSt()
    snabbvy_render.rendera_knapprad(st, snabbvyer.SNABBVYER_BOKSLUT, "test_bokslut_knapprad2")
    byggda = {v.id for v in snabbvyer.SNABBVYER_BOKSLUT if v.status == "byggd"}
    for etikett, kwargs in st.button_calls:
        if not kwargs.get("disabled"):
            assert "🔒" not in etikett


# --- Metatest 7: kraver_data och kommande skiljs åt -------------------------


class _FejkKallaUtanFormaga:
    visningsnamn = "Fejkkälla"

    def formagor(self):
        return frozenset()


def test_7_kraver_data_ger_stinfo_inte_laksmarkning():
    vy = snabbvyer.Snabbvy(
        "kraver_test", "Kräver test", "🧪",
        lambda data: snabbvyer.Snabbvyresultat(rubrik="Ska aldrig nås"),
        kraver=frozenset([Formaga.LASA_HUVUDBOK]),
    )
    st = _FakeSt()
    nyckel = "test_kraver_data"
    st.session_state[nyckel] = vy.id  # simulerar att knappen redan är vald

    visad = snabbvy_render.rendera_snabbvyfalt(
        st, (vy,), nyckel, snabbvyer.Vydata(idag=__import__("datetime").date.today()),
        kalla=_FejkKallaUtanFormaga(),
    )

    assert visad is True
    assert st.info_calls, "kraver_data-vägen (st.info) användes aldrig"
    assert not any("🔒" in e for e, _ in st.button_calls), (
        "kraver_data fick låsmarkering — de två spärrlägena har blandats ihop (§4.2)"
    )


def test_7_kommande_ar_inte_samma_som_kraver_data():
    """En 'kommande'-vy ska INTE trigga kraver_data-vägen (st.info) — den ska
    vara icke-klickbar redan i knappraden, utan att ens nå
    rendera_snabbvyfalt:s kraver-kontroll."""
    st = _FakeSt()
    nyckel = "test_kommande_ej_kraver_data"
    kommande_vy = next(v for v in snabbvyer.SNABBVYER_BOKSLUT if v.status == "kommande")
    st.session_state[nyckel] = kommande_vy.id

    snabbvy_render.rendera_snabbvyfalt(
        st, snabbvyer.SNABBVYER_BOKSLUT, nyckel,
        snabbvyer.Vydata(idag=__import__("datetime").date.today()),
    )
    assert not st.info_calls


# --- Metatest 8: hela kedjan, knapptupel -> sida -----------------------------


def test_8_varje_snabbvyer_tupel_refereras_i_rum_render():
    källa_snabbvyer = _lasa("parser/snabbvyer.py")
    källa_rum_render = _lasa("parser/rum_render.py")

    namn = set(re.findall(r"^(SNABBVYER_\w+)\s*[:=]", källa_snabbvyer, flags=re.MULTILINE))
    assert namn, "hittade inga SNABBVYER_*-tupler att pröva"

    ej_refererade = {n for n in namn if f"snabbvyer.{n}" not in källa_rum_render}
    assert not ej_refererade, f"SNABBVYER_*-tupler som aldrig ritas: {sorted(ej_refererade)}"


def _knapprads_funktioner_i_rum_render() -> set[str]:
    """Varje `rendera_*`-funktion i rum_render.py vars kropp anropar
    rendera_snabbvyfalt eller rendera_knapprad."""
    träd = ast.parse(_lasa("parser/rum_render.py"))
    funktioner = set()
    for node in ast.walk(träd):
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("rendera_")):
            continue
        for barn in ast.walk(node):
            if isinstance(barn, ast.Call) and isinstance(barn.func, ast.Attribute):
                if barn.func.attr in ("rendera_snabbvyfalt", "rendera_knapprad"):
                    funktioner.add(node.name)
                    break
    return funktioner


def _st_page_funktioner_i_app() -> set[str]:
    träd = ast.parse(_lasa("app.py"))
    funktioner = set()
    for node in ast.walk(träd):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Page"):
            continue
        if not node.args:
            continue
        förstaargument = node.args[0]
        if isinstance(förstaargument, ast.Attribute):
            funktioner.add(förstaargument.attr)
        elif isinstance(förstaargument, ast.Name):
            funktioner.add(förstaargument.id)
    return funktioner


def test_8_varje_knapprads_funktion_ar_en_riktig_sida():
    """Det testet som saknades (§6, punkt 8): kedjan SNABBVYER_* ->
    rendera_* -> st.Page i app.py ska vara hel för ALLA rum, inte bara
    bokslutsrummet. Skrivet generellt: fäller om något befintligt rum också
    har ett hål, i stället för att undanta det."""
    knapprad_funktioner = _knapprads_funktioner_i_rum_render()
    sid_funktioner = _st_page_funktioner_i_app()

    saknar_sida = knapprad_funktioner - sid_funktioner
    assert not saknar_sida, (
        f"rendera_*-funktioner som ritar en knapprad men aldrig blir en "
        f"st.Page i app.py (onåbara i den körande appen): {sorted(saknar_sida)}"
    )


def test_8_bokslutsrummet_ar_med_i_bada_leden():
    assert "rendera_bokslut" in _knapprads_funktioner_i_rum_render()
    assert "rendera_bokslut" in _st_page_funktioner_i_app()
    assert "bokslut" in {r.id for r in rum.RUM}


# --- Invarianter (§7) — ett namngivet test per U-1 … U-7 --------------------


def test_u1_ingen_streamlit_import_i_vy_modell_snabbvyer_eller_vymoduler():
    granskade = ["parser/vy_modell.py", "parser/snabbvyer.py"] + [
        f"parser/rum/{p.name}"
        for p in (_REPO_ROOT / "parser" / "rum").glob("*.py")
        if p.name != "__pycache__"
    ]
    for filnamn in granskade:
        källa = _lasa(filnamn)
        assert "import streamlit" not in källa, f"{filnamn} importerar streamlit"


def test_u2_bokslutsrummet_kor_motorn_pa_den_raa_siefilen(monkeypatch):
    """Appriktningen. MCP-riktningen (masken sker FÖRE motorn) täcks av
    tests/test_bokslutskontroll_mcp.py::TestI3MaskeradDataPåMCPVägen — samma
    invariant, testad från andra hållet."""
    import rum_render
    from domain_model import SIEFil

    rå_sie = SIEFil(företagsnamn="Rå — omaskerad")
    sedd_sie = {}

    def _spionerande_kor_kontroller(sie, *, idag, arsnr=0, endast=None):
        sedd_sie["sie"] = sie
        return []

    monkeypatch.setattr(bokslutskontroll, "kor_kontroller", _spionerande_kor_kontroller)

    st = _FakeSt()
    st.session_state["sie"] = rå_sie
    monkeypatch.setattr(rum_render, "st", st)

    rum_render.rendera_bokslut()

    assert sedd_sie["sie"] is rå_sie, "motorn körde inte på den råa SIEFil:en"


def test_u3_ingen_vymodul_anropar_skrivfunktioner():
    """Sök efter ANROP (namn + öppningsparentes), inte bara förekomst av
    namnet — modulernas egna kommentarer om VARFÖR de inte får kalla dessa
    funktioner nämner dem annars i klartext och ger falska träffar."""
    forbjudna = ("bekrafta_for_sandning(", "utfor_utkast(")
    for filnamn in ("parser/snabbvyer.py", "parser/snabbvy_render.py", "parser/vy_modell.py"):
        källa = _lasa(filnamn)
        for namn in forbjudna:
            assert namn not in källa, f"{filnamn} anropar {namn.rstrip('(')}"
        assert re.search(r"spiris_adapter\.(skapa|utfor|bekrafta)_\w+\(", källa) is None, (
            f"{filnamn} verkar anropa en skrivfunktion i spiris_adapter"
        )


def test_u4_none_och_tom_lista_betyder_olika_saker():
    idag = __import__("datetime").date.today()

    inte_kort = snabbvyer.bygg_bokslutskontroll(snabbvyer.Vydata(idag=idag, fynd=None))
    assert not inte_kort.atgarder
    assert any("saknas" in s.beskrivning.lower() or "saknas" in s.tomtext.lower() for s in inte_kort.sektioner)

    kort_inget_hittat = snabbvyer.bygg_bokslutskontroll(snabbvyer.Vydata(idag=idag, fynd=[]))
    assert not kort_inget_hittat.atgarder
    assert any("hittade inget" in (s.beskrivning or "") for s in kort_inget_hittat.sektioner)

    assert inte_kort.sektioner[0].beskrivning != kort_inget_hittat.sektioner[0].beskrivning


def test_u5_en_knapps_status_ar_sann():
    for vy in snabbvyer.SNABBVYER_BOKSLUT:
        if vy.status == "byggd":
            assert vy.bygg is not snabbvyer._kommande_platshallare
        else:
            assert vy.status == "kommande"
            assert vy.bygg is snabbvyer._kommande_platshallare


def test_u6_sparr_pa_grund_av_funktion_och_data_ar_skilda(monkeypatch):
    # Samma mekanism som metatest 6/7 ovan, fast namngivet efter invarianten.
    st = _FakeSt()
    snabbvy_render.rendera_knapprad(st, snabbvyer.SNABBVYER_BOKSLUT, "test_u6_knapprad")
    laksta = {e for e, k in st.button_calls if k.get("disabled")}
    assert all(e.startswith("🔒 ") for e in laksta)

    vy = snabbvyer.Snabbvy(
        "u6_kraver_test", "U6 kräver test", "🧪",
        lambda data: snabbvyer.Snabbvyresultat(rubrik="x"),
        kraver=frozenset([Formaga.LASA_HUVUDBOK]),
    )
    st2 = _FakeSt()
    st2.session_state["u6_nyckel"] = vy.id
    snabbvy_render.rendera_snabbvyfalt(
        st2, (vy,), "u6_nyckel", snabbvyer.Vydata(idag=__import__("datetime").date.today()),
        kalla=_FejkKallaUtanFormaga(),
    )
    assert st2.info_calls and not any("🔒" in e for e, _ in st2.button_calls)


def test_u7_en_formaga_ar_inte_byggd_forran_den_ar_nabar():
    knapprad_funktioner = _knapprads_funktioner_i_rum_render()
    sid_funktioner = _st_page_funktioner_i_app()
    assert knapprad_funktioner <= sid_funktioner
