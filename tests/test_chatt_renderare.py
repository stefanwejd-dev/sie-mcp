"""Tester för chatt_renderare.py — den deterministiska renderingen av
strukturerade AI-svar (Område A, fas 2).

Modulen ritar HTML själv (st.markdown med unsafe_allow_html) för att få
zebra-randning, kantlinjer och högerställda belopp som st.dataframe inte
kan ge. Det gör två saker testvärda utöver utseendet:

1. ALLT modellgenererat innehåll måste HTML-escapas — annars vore
   unsafe_allow_html en injektionsväg rakt in i appen via ett AI-svar.
2. Renderingen måste vara fail-closed. Ett sparat svar som inte går att
   tolka ska ge False (anroparen visar vanlig text), aldrig en krasch som
   släcker hela chatten.

Streamlit-anropen fejkas: testerna kör utan UI-runtime, och det som ska
verifieras är VAD som skickas till Streamlit, inte Streamlit självt.
"""

from __future__ import annotations

import json

import pytest

import chatt_renderare
from fpa_vy import FARG_INTAKT, FARG_KOSTNAD, formatera_kr
from svarskontrakt import DiagramBlock, KolumnDef, TabellBlock, validera_svar

KOLUMNER = [
    KolumnDef(nyckel="leverantor", rubrik="Leverantör", typ="text"),
    KolumnDef(nyckel="forfaller", rubrik="Förfaller", typ="datum"),
    KolumnDef(nyckel="inkl_moms", rubrik="Inkl. moms", typ="belopp"),
]

TABELL = TabellBlock(
    rubrik="Obetalda leverantörsfakturor",
    kolumner=KOLUMNER,
    rader=[
        {"leverantor": "[BOLAG_1]", "forfaller": "2026-08-15", "inkl_moms": 24500},
        {"leverantor": "[BOLAG_2]", "forfaller": "2026-08-22", "inkl_moms": 10000},
    ],
    summa_rad={"leverantor": "Summa", "inkl_moms": 34500},
)


class _FejkSt:
    """Minimal stand-in för streamlit — spelar bara in de anrop
    chatt_renderare faktiskt gör."""

    def __init__(self, knapptryck: set[str] | None = None) -> None:
        self.session_state: dict[str, object] = {}
        self.markdown_anrop: list[tuple[str, bool]] = []
        self.diagram: list[object] = []
        self.captions: list[str] = []
        self.knappar: list[str] = []
        self.rerun_anrop = 0
        self._knapptryck = knapptryck or set()

    def markdown(self, text, unsafe_allow_html=False):
        self.markdown_anrop.append((text, unsafe_allow_html))

    def button(self, etikett, key=None):
        self.knappar.append(etikett)
        return key in self._knapptryck

    def plotly_chart(self, fig, width=None):
        self.diagram.append(fig)

    def caption(self, text):
        self.captions.append(text)

    def rerun(self):
        self.rerun_anrop += 1
        raise _Rerun()


class _Rerun(Exception):
    """Speglar Streamlits RerunException — avbryter körningen."""


@pytest.fixture
def fejk_st(monkeypatch):
    fejk = _FejkSt()
    monkeypatch.setattr(chatt_renderare, "st", fejk)
    return fejk


class TestTabellHtml:
    def test_rubriker_och_rader_kommer_med(self):
        html = chatt_renderare._bygg_tabellhtml(TABELL)

        assert "Obetalda leverantörsfakturor" in html
        assert "<th>Leverantör</th>" in html
        assert "[BOLAG_1]" in html
        assert "[BOLAG_2]" in html

    def test_beloppskolumn_hogerstalls_och_formateras_svenskt(self):
        html = chatt_renderare._bygg_tabellhtml(TABELL)

        # formatera_kr äger avgränsaren (icke-brytande mellanslag) — testet
        # ska inte frysa den i en literal med osynliga tecken.
        assert f'<td class="sie-hoger">{formatera_kr(24500)}</td>' in html
        assert '<th class="sie-hoger">Inkl. moms</th>' in html

    def test_textkolumn_hogerstalls_inte(self):
        html = chatt_renderare._bygg_tabellhtml(TABELL)

        assert "<td>[BOLAG_1]</td>" in html

    def test_summaraden_far_egen_klass_och_fyller_tomma_celler(self):
        html = chatt_renderare._bygg_tabellhtml(TABELL)

        assert '<tr class="sie-summa-rad">' in html
        # forfaller saknas i summaraden — cellen ska vara tom, inte "None".
        assert "None" not in html

    def test_saknat_varde_visas_som_streck(self):
        tabell = TabellBlock(
            kolumner=KOLUMNER,
            rader=[{"leverantor": "[BOLAG_1]"}],
        )

        html = chatt_renderare._bygg_tabellhtml(tabell)

        assert html.count("–") == 2  # forfaller och inkl_moms

    def test_html_i_modellsvar_escapas(self):
        # unsafe_allow_html gäller HELA strängen — ett AI-svar får aldrig
        # kunna injicera markup i appen.
        tabell = TabellBlock(
            rubrik="<img src=x onerror=alert(1)>",
            kolumner=[KolumnDef(nyckel="a", rubrik="<b>A</b>")],
            rader=[{"a": "<script>alert('x')</script>"}],
        )

        html = chatt_renderare._bygg_tabellhtml(tabell)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<b>A</b>" not in html
        # Attributet finns kvar som TEXT, men taggen är stympad — inert.
        assert "<img" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html

    def test_tabellen_ligger_i_en_scrollbar_wrapper(self):
        html = chatt_renderare._bygg_tabellhtml(TABELL)

        assert html.count('<div class="sie-chatt-tabell-wrap">') == 1
        assert html.endswith("</table></div>")


class TestTalTolkning:
    @pytest.mark.parametrize(
        "ratext, forvantat",
        [
            (24500, 24500.0),
            (24500.5, 24500.5),
            ("24500", 24500.0),
            ("24 500,50 kr", 24500.5),
            ("24 500 kr", 24500.0),
            ("-1200", -1200.0),
            ("1.234", 1.234),
            ("15 %", 15.0),
        ],
    )
    def test_tolererar_modellernas_beloppsvarianter(self, ratext, forvantat):
        assert chatt_renderare._till_tal(ratext) == forvantat

    @pytest.mark.parametrize("ratext", ["", "saknas", None, True, ["1"]])
    def test_ickenumeriska_varden_ger_none(self, ratext):
        assert chatt_renderare._till_tal(ratext) is None

    def test_otolkbart_belopp_visas_som_text_i_stallet_for_att_krascha(self):
        tabell = TabellBlock(
            kolumner=[KolumnDef(nyckel="b", rubrik="Belopp", typ="belopp")],
            rader=[{"b": "cirka tiotusen"}],
        )

        html = chatt_renderare._bygg_tabellhtml(tabell)

        assert "cirka tiotusen" in html


class TestDiagramval:
    def test_datumkolumn_ger_linjediagram(self):
        assert chatt_renderare._auto_diagram_typ(TABELL) == "linje"

    def test_utan_datumkolumn_blir_det_stapel(self):
        tabell = TabellBlock(
            kolumner=[
                KolumnDef(nyckel="konto", rubrik="Konto", typ="text"),
                KolumnDef(nyckel="saldo", rubrik="Saldo", typ="belopp"),
            ],
            rader=[{"konto": "1930", "saldo": 100}],
        )

        assert chatt_renderare._auto_diagram_typ(tabell) == "stapel"

    def test_linjediagram_far_datumkolumnen_som_x_axel(self):
        # Inte första textkolumnen: en fakturalista börjar med leverantören
        # men ska ritas över förfallodatum.
        assert chatt_renderare._forsta_kategorikolumn(TABELL, "linje") == "forfaller"

    def test_stapeldiagram_tar_forsta_textkolumnen(self):
        assert chatt_renderare._forsta_kategorikolumn(TABELL, "stapel") == "leverantor"


class TestDiagramgenerering:
    def test_bygger_linjediagram_med_appens_intaktsfarg(self):
        fig = chatt_renderare._bygg_diagram_fran_tabell(TABELL)

        assert fig.data[0].type == "scatter"
        assert fig.data[0].line.color == FARG_INTAKT
        assert list(fig.data[0].x) == ["2026-08-15", "2026-08-22"]
        assert list(fig.data[0].y) == [24500.0, 10000.0]

    def test_negativa_staplar_far_kostnadsfargen(self):
        tabell = TabellBlock(
            kolumner=[
                KolumnDef(nyckel="konto", rubrik="Konto", typ="text"),
                KolumnDef(nyckel="saldo", rubrik="Saldo", typ="belopp"),
            ],
            rader=[{"konto": "1930", "saldo": 5000}, {"konto": "2440", "saldo": -3000}],
        )

        fig = chatt_renderare._bygg_diagram_fran_tabell(tabell)

        assert fig.data[0].type == "bar"
        assert list(fig.data[0].marker.color) == [FARG_INTAKT, FARG_KOSTNAD]

    def test_summaraden_ritas_inte_med(self):
        # Summan är ingen egen kategori — den skulle dominera diagrammet.
        fig = chatt_renderare._bygg_diagram_fran_tabell(TABELL)

        assert len(fig.data[0].x) == 2

    def test_tabell_utan_beloppskolumn_ger_inget_diagram(self):
        tabell = TabellBlock(
            kolumner=[KolumnDef(nyckel="a", rubrik="A", typ="text")],
            rader=[{"a": "x"}],
        )

        assert chatt_renderare._bygg_diagram_fran_tabell(tabell) is None

    def test_tabell_utan_rader_ger_inget_diagram(self):
        tabell = TabellBlock(kolumner=KOLUMNER, rader=[])

        assert chatt_renderare._bygg_diagram_fran_tabell(tabell) is None

    def test_tabell_utan_tolkbara_tal_ger_inget_diagram(self):
        tabell = TabellBlock(
            kolumner=[
                KolumnDef(nyckel="a", rubrik="A", typ="text"),
                KolumnDef(nyckel="b", rubrik="B", typ="belopp"),
            ],
            rader=[{"a": "x", "b": "vet ej"}],
        )

        assert chatt_renderare._bygg_diagram_fran_tabell(tabell) is None

    def test_cirkeldiagram_far_legend_och_appens_kategorifarger(self):
        block = DiagramBlock(
            diagram_typ="cirkel", rubrik="Fördelning",
            kategori_falt="k", varde_falt="v",
            data=[{"k": "A", "v": 60}, {"k": "B", "v": 40}],
        )

        fig = chatt_renderare._bygg_diagram_fran_block(block)

        assert fig.data[0].type == "pie"
        assert fig.layout.showlegend is True
        assert tuple(fig.data[0].marker.colors) == chatt_renderare._KATEGORIFARGER[:2]

    def test_diagramblock_respekterar_modellens_typval(self):
        block = DiagramBlock(
            diagram_typ="stapel", rubrik="Saldon", kategori_falt="k",
            varde_falt="v", data=[{"k": "A", "v": "1 200 kr"}],
        )

        fig = chatt_renderare._bygg_diagram_fran_block(block)

        assert fig.data[0].type == "bar"
        assert list(fig.data[0].y) == [1200.0]


class TestRendering:
    def test_textblock_renderas_som_markdown_utan_ra_html(self, fejk_st):
        renderat = chatt_renderare.rendera_strukturerat_svar(
            {"block": [{"typ": "text", "innehall": "**Två** fakturor är obetalda."}]},
            meddelande_index=0,
        )

        assert renderat is True
        assert fejk_st.markdown_anrop == [("**Två** fakturor är obetalda.", False)]

    def test_tabellblock_renderas_som_html_med_diagramknapp(self, fejk_st):
        chatt_renderare.rendera_strukturerat_svar(
            {"block": [TABELL.model_dump()]}, meddelande_index=3
        )

        html, unsafe = fejk_st.markdown_anrop[0]
        assert unsafe is True
        assert "sie-chatt-tabell" in html
        assert fejk_st.knappar == ["📊 Visa som diagram"]
        assert fejk_st.diagram == []

    def test_diagram_visas_forst_nar_knappen_slagits_pa(self, fejk_st):
        fejk_st.session_state["visa_diagram_3_0"] = True

        chatt_renderare.rendera_strukturerat_svar(
            {"block": [TABELL.model_dump()]}, meddelande_index=3
        )

        assert len(fejk_st.diagram) == 1
        assert fejk_st.knappar == ["📊 Dölj diagram"]

    def test_knapptryck_slar_om_laget_och_kor_om(self, monkeypatch):
        fejk = _FejkSt(knapptryck={"knapp_diagram_3_0"})
        monkeypatch.setattr(chatt_renderare, "st", fejk)

        with pytest.raises(_Rerun):
            chatt_renderare.rendera_strukturerat_svar(
                {"block": [TABELL.model_dump()]}, meddelande_index=3
            )

        assert fejk.session_state["visa_diagram_3_0"] is True
        assert fejk.rerun_anrop == 1

    def test_diagramknappar_far_unika_nycklar_per_meddelande(self, fejk_st):
        chatt_renderare.rendera_strukturerat_svar(
            {"block": [TABELL.model_dump()]}, meddelande_index=1
        )
        chatt_renderare.rendera_strukturerat_svar(
            {"block": [TABELL.model_dump()]}, meddelande_index=2
        )

        fejk_st.session_state["visa_diagram_1_0"] = True
        chatt_renderare.rendera_strukturerat_svar(
            {"block": [TABELL.model_dump()]}, meddelande_index=1
        )

        # Bara meddelande 1 visar diagram — nyckeln är inte delad.
        assert "visa_diagram_2_0" not in fejk_st.session_state
        assert len(fejk_st.diagram) == 1

    def test_tabell_utan_diagramunderlag_ger_forklarande_caption(self, fejk_st):
        tabell = TabellBlock(
            kolumner=[KolumnDef(nyckel="a", rubrik="A", typ="text")],
            rader=[{"a": "x"}],
        )
        fejk_st.session_state["visa_diagram_0_0"] = True

        chatt_renderare.rendera_strukturerat_svar(
            {"block": [tabell.model_dump()]}, meddelande_index=0
        )

        assert fejk_st.diagram == []
        assert len(fejk_st.captions) == 1

    def test_blocken_renderas_i_ordning(self, fejk_st):
        chatt_renderare.rendera_strukturerat_svar(
            {
                "block": [
                    {"typ": "text", "innehall": "Kommentar"},
                    TABELL.model_dump(),
                ]
            },
            meddelande_index=0,
        )

        assert fejk_st.markdown_anrop[0] == ("Kommentar", False)
        assert fejk_st.markdown_anrop[1][1] is True

    def test_otolkbart_sparat_svar_ger_false_utan_att_rita(self, fejk_st):
        # Fail-closed: app.py visar meddelandets vanliga text i stället.
        renderat = chatt_renderare.rendera_strukturerat_svar(
            {"block": [{"typ": "tabell", "kolumner": []}]}, meddelande_index=0
        )

        assert renderat is False
        assert fejk_st.markdown_anrop == []
        assert fejk_st.knappar == []

    def test_tomt_svar_ger_false(self, fejk_st):
        assert chatt_renderare.rendera_strukturerat_svar({}, meddelande_index=0) is False

    def test_hela_vandan_fran_modellsvar_till_rendering(self, fejk_st):
        # Exakt den väg app.py tar: modellens råa JSON → validera_svar →
        # .model_dump() i session_state → rendering. Ett fel i något av
        # stegen syns bara här.
        rått = json.dumps({
            "block": [
                {"typ": "text", "innehall": "Två fakturor är obetalda."},
                TABELL.model_dump(mode="json"),
            ]
        })

        svar = validera_svar(rått)
        assert svar is not None

        renderat = chatt_renderare.rendera_strukturerat_svar(
            svar.model_dump(), meddelande_index=0
        )

        assert renderat is True
        assert fejk_st.markdown_anrop[0] == ("Två fakturor är obetalda.", False)
        # formatera_kr, inte en egen literal: avgränsaren är ett icke-brytande
        # mellanslag och ska förbli appens, inte testets, beslut.
        assert formatera_kr(24500) in fejk_st.markdown_anrop[1][0]


class TestCss:
    def test_css_ar_scopad_till_chattabellen(self, fejk_st):
        chatt_renderare.injicera_chatt_css()

        css, unsafe = fejk_st.markdown_anrop[0]
        assert unsafe is True
        # Varje regel ska vara scopad — annars skulle appens övriga tabeller
        # (rapporter, reskontra) dras med.
        for rad in css.splitlines():
            if rad.strip().endswith("{") and not rad.strip().startswith(("@", "/*")):
                assert ".sie-" in rad

    def test_zebrarandningen_ar_temaneutral(self, fejk_st):
        # Grå rgba fungerar i både ljust och mörkt tema; vitt gör det inte.
        chatt_renderare.injicera_chatt_css()

        css = fejk_st.markdown_anrop[0][0]
        assert "rgba(255, 255, 255" not in css
        assert "rgba(128, 128, 128, 0.08)" in css
