"""test_compliance.py — villkorsspärren: lagring, fail-closed och Streamlit-UI.

Spärren är en juridisk kontroll, inte en kosmetisk ruta. Det som testas är
därför att den faktiskt SPÄRRAR: att inget godkännande registreras av misstag,
att ett ofullständigt eller föråldrat godkännande inte räknas, och att
Streamlit-spärren anropar st.stop() innan någon annan del av appen hinner
rita något.

Streamlit fejkas (samma mönster som test_chatt_renderare.py) — det som ska
verifieras är VAD spärren gör, inte Streamlit självt.
"""

from __future__ import annotations

import json

import pytest

import compliance
import saker_lagring


class _FejkSt:
    """Minimal stand-in för streamlit — spelar in anropen spärren gör."""

    def __init__(self, kryssade: set[str] | None = None, knapp_tryckt: bool = False) -> None:
        self.session_state: dict[str, object] = {}
        self.errors: list[str] = []
        self.markdown_anrop: list[str] = []
        self.captions: list[str] = []
        self.checkboxar: list[tuple[str, str]] = []
        self.knappar: list[dict] = []
        self.stop_anrop = 0
        self.rerun_anrop = 0
        self._kryssade = kryssade or set()
        self._knapp_tryckt = knapp_tryckt

    def error(self, text):
        self.errors.append(text)

    def markdown(self, text, **_):
        self.markdown_anrop.append(text)

    def caption(self, text):
        self.captions.append(text)

    def checkbox(self, etikett, key=None, **_):
        self.checkboxar.append((etikett, key))
        return key in self._kryssade

    def button(self, etikett, **kwargs):
        self.knappar.append({"etikett": etikett, **kwargs})
        return self._knapp_tryckt and not kwargs.get("disabled", False)

    def stop(self):
        self.stop_anrop += 1

    def rerun(self):
        self.rerun_anrop += 1


def _alla_nycklar() -> set[str]:
    return {f"{compliance._KRYSSPREFIX}{p.nyckel}" for p in compliance.VILLKORSPUNKTER}


# --- Lagring och fail-closed ------------------------------------------------


def test_ej_godkand_fran_start():
    assert not compliance.ar_compliance_godkand()


def test_godkann_och_verifiera(tmp_path, monkeypatch):
    compliance.godkann_compliance()
    assert compliance.ar_compliance_godkand()

    fil = saker_lagring.state_dir() / "compliance_accepted.json"
    data = json.loads(fil.read_text(encoding="utf-8"))
    assert data["version"] == compliance.COMPLIANCE_VERSION
    assert data["godkand"] is True
    assert data["roll"] == "slutanvandare_byok"
    # Varje enskild ansvarspunkt ska vara spårbart godkänd, inte bara "ja".
    assert set(data["godkanda_punkter"]) == {p.nyckel for p in compliance.VILLKORSPUNKTER}


def test_aterkallat_godkannande_sparrar_igen():
    compliance.godkann_compliance()
    assert compliance.ar_compliance_godkand()
    compliance.aterkalla_compliance()
    assert not compliance.ar_compliance_godkand()


def test_foraldrad_version_ar_ogiltig():
    """Höjs COMPLIANCE_VERSION måste användaren ta ställning på nytt."""
    compliance.godkann_compliance()
    fil = saker_lagring.state_dir() / "compliance_accepted.json"
    data = json.loads(fil.read_text(encoding="utf-8"))
    data["version"] = "1900-01-01"
    fil.write_text(json.dumps(data), encoding="utf-8")

    assert not compliance.ar_compliance_godkand()


def test_saknad_punkt_ar_ogiltig():
    """Ett godkännande som inte täcker alla nuvarande punkter räknas inte."""
    compliance.godkann_compliance()
    fil = saker_lagring.state_dir() / "compliance_accepted.json"
    data = json.loads(fil.read_text(encoding="utf-8"))
    data["godkanda_punkter"] = data["godkanda_punkter"][:-1]
    fil.write_text(json.dumps(data), encoding="utf-8")

    assert not compliance.ar_compliance_godkand()


@pytest.mark.parametrize(
    "innehall",
    ["inte json alls", "[]", '{"godkand": true}', '{"version": "x", "godkand": true}'],
)
def test_trasig_fil_sparrar_istallet_for_att_oppna(innehall):
    fil = saker_lagring.state_dir() / "compliance_accepted.json"
    fil.parent.mkdir(parents=True, exist_ok=True)
    fil.write_text(innehall, encoding="utf-8")

    assert not compliance.ar_compliance_godkand()


def test_lagringsfel_sparrar(monkeypatch):
    def _fel():
        raise saker_lagring.SakerLagringFel("otillåten sökväg")

    monkeypatch.setattr(compliance, "state_dir", _fel)
    assert not compliance.ar_compliance_godkand()


# --- Villkorstexten ---------------------------------------------------------


def test_villkorstext_innehaller_varje_punkt():
    text = compliance.villkorstext()
    for punkt in compliance.VILLKORSPUNKTER:
        assert punkt.rubrik in text
        assert punkt.text in text


def test_villkoren_tacker_de_fyra_bararande_friskrivningarna():
    """Regressionsskydd: dessa fyra får aldrig tas bort ur spärren."""
    nycklar = {p.nyckel for p in compliance.VILLKORSPUNKTER}
    assert "fullt_eget_ansvar" in nycklar
    assert "inga_garantier" in nycklar
    assert "resultat_ej_verklighet" in nycklar
    assert "ingen_professionell_radgivning" in nycklar


def test_sparrtext_hanvisar_till_manuellt_godkannande():
    assert "compliance.py --godkann" in compliance.SPARRTEXT_KORT
    assert "MCP" in compliance.SPARRTEXT_KORT


# --- Streamlit-spärren ------------------------------------------------------


def test_sparren_stoppar_appen_nar_villkor_saknas():
    st = _FejkSt()
    compliance.krav_godkannande(st)

    assert st.stop_anrop == 1, "appen måste stoppas när villkoren inte är godkända"
    assert st.errors, "användaren måste få veta varför appen är spärrad"


def test_sparren_visar_en_kryssruta_per_punkt():
    st = _FejkSt()
    compliance.krav_godkannande(st)

    assert len(st.checkboxar) == len(compliance.VILLKORSPUNKTER)
    assert {key for _, key in st.checkboxar} == _alla_nycklar()


def test_knappen_ar_last_tills_alla_punkter_kryssats():
    delvis = set(list(_alla_nycklar())[:-1])
    st = _FejkSt(kryssade=delvis)
    compliance.krav_godkannande(st)

    assert st.knappar[0]["disabled"] is True
    assert not compliance.ar_compliance_godkand()


def test_knappen_lases_upp_nar_allt_kryssats():
    st = _FejkSt(kryssade=_alla_nycklar())
    compliance.krav_godkannande(st)

    assert st.knappar[0]["disabled"] is False


def test_tryck_pa_knappen_registrerar_godkannandet():
    st = _FejkSt(kryssade=_alla_nycklar(), knapp_tryckt=True)
    compliance.krav_godkannande(st)

    assert compliance.ar_compliance_godkand()
    assert st.rerun_anrop == 1


def test_tryck_utan_alla_kryss_registrerar_ingenting():
    """Knappen är disabled — ett klick får inte kunna smita förbi."""
    st = _FejkSt(kryssade=set(), knapp_tryckt=True)
    compliance.krav_godkannande(st)

    assert not compliance.ar_compliance_godkand()
    assert st.stop_anrop == 1


def test_sparren_slapper_igenom_nar_villkoren_ar_godkanda():
    compliance.godkann_compliance()
    st = _FejkSt()
    compliance.krav_godkannande(st)

    assert st.stop_anrop == 0
    assert st.checkboxar == [], "inget villkors-UI ska ritas för en godkänd användare"


# --- CLI --------------------------------------------------------------------


@pytest.mark.parametrize("svar", ["JAG GODKÄNNER", "JAG GODKANNER", "  JAG GODKÄNNER  "])
def test_cli_godkanner_vid_exakt_fras(monkeypatch, svar):
    """Den ä-lösa varianten accepteras för konsoler som inte kan skriva Ä —
    båda är otvetydiga, versaliserade viljeyttringar."""
    monkeypatch.setattr("builtins.input", lambda *_: svar)
    assert compliance._cli(["--godkann"]) == 0
    assert compliance.ar_compliance_godkand()


@pytest.mark.parametrize(
    "svar", ["ja", "j", "jag godkänner", "JAG GODKÃ\x84NNER", "godkänner", "y", ""]
)
def test_cli_godkanner_inte_vid_nagot_annat(monkeypatch, svar):
    monkeypatch.setattr("builtins.input", lambda *_: svar)
    assert compliance._cli(["--godkann"]) == 1
    assert not compliance.ar_compliance_godkand()


def test_cli_avbrott_godkanner_inte(monkeypatch):
    def _avbryt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _avbryt)
    assert compliance._cli(["--godkann"]) == 1
    assert not compliance.ar_compliance_godkand()


def test_cli_skriver_ut_villkoren_fore_fragan(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *_: "nej")
    compliance._cli(["--godkann"])
    utskrift = capsys.readouterr().out
    for punkt in compliance.VILLKORSPUNKTER:
        assert punkt.rubrik in utskrift


def test_cli_status_och_aterkalla(monkeypatch, capsys):
    assert compliance._cli(["--status"]) == 0
    assert "INTE godkänt" in capsys.readouterr().out

    compliance.godkann_compliance()
    assert compliance._cli(["--status"]) == 0
    assert "Godkänt" in capsys.readouterr().out

    assert compliance._cli(["--aterkalla"]) == 0
    assert not compliance.ar_compliance_godkand()


def test_cli_utan_flagga_godkanner_ingenting(capsys):
    assert compliance._cli([]) == 1
    assert not compliance.ar_compliance_godkand()
