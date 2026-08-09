"""Tester för fpa_vy.py — adaptern SIEFil -> strukturerad P&L/balans-rapport
och FP&A-dashboardens uppställnings-config.

Kärnkrav:
- Adaptern matar de FRIKOPPLADE motorerna (bygg_resultatrapport /
  bygg_balansrapport) och ger samma siffror som E2E:t mot SIE4 Exempelfil.SE.
- "Dum frontend"-kontraktet på config-nivå: varje drill-down-grupp i
  uppställningen har en matchande poster-rad, och gruppens konton summerar
  exakt till den raden. Då kan dashboarden rendera rakt av utan egen logik.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fpa_vy import (
    BALANS_EK_SKULDER,
    FINANSIERINGSFORKLARING,
    SIMULERING_MAX,
    BALANS_TILLGANGAR,
    STAPEL_FINANSIERING,
    STAPEL_TILLGANGAR,
    BALANS_SEGMENT,
    DEFAULT_NYCKELTAL,
    FARG_EGET_KAPITAL,
    FARG_NY_INVESTERING,
    FARG_KASSA,
    FARG_OBESKATTADE_RESERVER,
    FARG_OVRIGT_SKULD,
    FARG_OVRIGT_TILLGANG,
    INLINE_TEXT_TROSKEL,
    KAPITALSTACK_FARG,
    NARRATIV_TABELL_CSS,
    NY_INVESTERING_NOD,
    TEXT_PA_LJUS_YTA,
    TEXT_PA_MORK_YTA,
    GRAFTYPER,
    KASSAFLODE_BLOCK,
    NYCKELTAL_KATALOG,
    RESULTAT_UPPSTALLNING,
    Finansieringspost,
    balansrapport_fran_sie,
    belopp_fran_procent,
    dela_uppstallning,
    foreslaget_avkastningskrav_procent,
    kapitalstack,
    kapitalstapel,
    kvot_fran_procent,
    leasing_utkopstillagg,
    narrativtabell_html,
    procent_fran_belopp,
    procentsumma,
    kontrastkvot,
    dashboard_rendering_lage,
    dashboard_saknar_data,
    default_datumintervall,
    formatera_kr,
    formatera_nyckeltal,
    innevarande_ar_intervall,
    formatera_multipel,
    formatera_procent,
    formatera_procentenheter,
    kassaflodesanalys_fran_sie,
    konton_i_grupp,
    narrativ_simulering,
    nyckeltal_fran_sie,
    nyckeltal_med_personalkostnad,
    radbryt,
    sankey_data,
    segment_med_nyckel,
    sortera_drilldown,
    stapeldata_balans,
    valda_segment_ur_punkter,
    simulering,
    konton_i_segment,
    likviditetsdagar_ur_punkter,
    likviditetsgraf_data,
    likviditetsprognos_fran_reskontra,
    likviditetsprognos_med_varningstroskel,
    momssaldo_fran_sie,
    rapporter_fran_sie,
    resultatrapport_fran_sie,
    ryms_inline_text,
    text_farg,
    resultattabell_rader,
    stapeldata_resultat,
    stapeldata_resultat_bi,
    valj_nyckeltal,
    valj_rakenskapsar_for_ar,
    vattenfall_kassaflode,
    vattenfall_resultat,
)
from sie4_parser import parse_sie4
from domain_model import SIEFil, Saldopost
from fpa_motor import (
    BOLAGSSKATT,
    berakna_wacc,
    foreslagen_avkastning_eget_kapital,
    simulera_kapitalstack,
)
from reskontra_tvatt import Kundpost, Leverantorspost

NBSP = " "  # icke-brytande mellanslag: svensk avgränsare i formaterarna

SIE4_EXEMPEL = str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE")


def _sie():
    return parse_sie4(SIE4_EXEMPEL)


class TestResultatrapportFranSie:
    def test_samma_siffror_som_e2e(self):
        r = resultatrapport_fran_sie(_sie())
        assert r["period"] == {"start_datum": "2025-01-01", "slut_datum": "2025-12-31"}
        assert r["poster"]["totala_intakter"] == Decimal("2625800.00")
        assert r["poster"]["arets_resultat"] == Decimal("428690.00")

    def test_ingen_varning_for_helt_ar(self):
        r = resultatrapport_fran_sie(_sie())
        assert "varning" not in r["info"].lower()


class TestBalansrapportFranSie:
    def test_balansomslutning_och_kontrolldiff(self):
        r = balansrapport_fran_sie(_sie())
        assert r["per_datum"] == "2025-12-31"
        assert r["poster"]["summa_tillgangar"] == Decimal("3457690.00")
        assert r["poster"]["kontrolldiff"] == Decimal("0")

    def test_arets_resultat_bakas_in(self):
        r = balansrapport_fran_sie(_sie())
        assert r["poster"]["arets_resultat"] == Decimal("428690.00")


class TestUppstallningskontrakt:
    """Varje drill-down-grupp i uppställningen ska ha en matchande poster-rad,
    och gruppens konton ska summera exakt till den (annars kan frontend inte
    vara dum)."""

    def _reconcilierar(self, rapport, uppstallning):
        for nyckel, _etikett, radtyp in uppstallning:
            assert nyckel in rapport["poster"], f"saknad poster-rad: {nyckel}"
            if radtyp == "grupp":
                gruppsumma = sum(
                    (k["saldo"] for k in konton_i_grupp(rapport, nyckel)),
                    Decimal("0"),
                )
                assert gruppsumma == rapport["poster"][nyckel], nyckel

    def test_resultat_uppstallning_reconcilierar(self):
        self._reconcilierar(resultatrapport_fran_sie(_sie()), RESULTAT_UPPSTALLNING)

    def test_balans_uppstallning_reconcilierar(self):
        rapport = balansrapport_fran_sie(_sie())
        self._reconcilierar(rapport, BALANS_TILLGANGAR)
        self._reconcilierar(rapport, BALANS_EK_SKULDER)


class TestRenderingshjalpare:
    def test_formatera_kr_svenskt_tusental(self):
        # Non-breaking space (U+00A0) som svensk tusentalsavgraensare.
        # Strippa ALLA blanksteg -> ren siffra, oberoende av mellanslagstyp.
        resultat = formatera_kr(Decimal("1690380.20"))
        assert " " in resultat
        assert resultat.replace(" ", "").replace(" ", "") == "1690380kr"
        neg = formatera_kr(Decimal("-2000.00"))
        assert neg.replace(" ", "").replace(" ", "") == "-2000kr"


    def test_konton_i_grupp_filtrerar(self):
        r = resultatrapport_fran_sie(_sie())
        intakter = konton_i_grupp(r, "totala_intakter")
        assert intakter and all(k["grupp"] == "totala_intakter" for k in intakter)

    def test_stapeldata_ar_floats(self):
        data = stapeldata_resultat(resultatrapport_fran_sie(_sie()))
        assert set(data) == {"Totala intäkter", "Totala kostnader", "Rörelseresultat"}
        assert all(isinstance(v, float) for v in data.values())


class TestBiStapelOchTabell:
    def _rapport(self):
        return resultatrapport_fran_sie(_sie())

    def test_stapeldata_bi_ordning_och_distinkta_farger(self):
        data = stapeldata_resultat_bi(self._rapport())
        # Exakt ordning: intäkter, kostnader, resultat.
        assert [etikett for etikett, _, _ in data] == [
            "Totala intäkter", "Kostnader", "Resultat"
        ]
        # Tre distinkta färger (grön/röd/blå).
        assert len({färg for _, _, färg in data}) == 3

    def test_stapeldata_bi_varden_matchar_poster(self):
        data = stapeldata_resultat_bi(self._rapport())
        belopp = {etikett: värde for etikett, värde, _ in data}
        assert belopp["Totala intäkter"] == pytest.approx(2625800.00, abs=0.01)
        assert belopp["Kostnader"] == pytest.approx(1957710.00, abs=0.01)
        assert belopp["Resultat"] == pytest.approx(668090.00, abs=0.01)
        assert all(isinstance(v, float) for v in belopp.values())

    def test_resultattabell_rader_summor_ar_feta(self):
        rader = resultattabell_rader(self._rapport())
        per_post = {r["Post"]: r for r in rader}
        # Del-/slutsummor -> feta.
        for summa in ("Bruttovinst", "EBITDA", "Rörelseresultat (EBIT)", "Årets resultat"):
            assert per_post[summa]["_summa"] is True
        # Vanliga rader (drill-down-grupper) -> ej feta.
        assert per_post["Totala intäkter"]["_summa"] is False

    def test_graftyper_ar_de_tva_valen(self):
        assert GRAFTYPER == ["Standard (Staplar)", "Vattenfallsdiagram"]

    def test_vattenfall_resultat_ordning_och_measures(self):
        steg = vattenfall_resultat(self._rapport())
        assert [etikett for etikett, _, _ in steg] == [
            "Totala intäkter", "Kostnad sålda varor", "Övriga rörelsekostnader",
            "Av- och nedskrivningar", "Resultat",
        ]
        # Alla steg 'relative' (Plotly färgar grönt/rött), sista 'total' (blå).
        assert all(m == "relative" for _, _, m in steg[:-1])
        assert steg[-1][2] == "total"

    def test_nollkostnad_ger_positiv_nolla_inte_minus_noll(self):
        # -0.0 skulle renderas som "-0 kr" i grafen.
        per_etikett = {e: b for e, b, _ in vattenfall_resultat(self._rapport())}
        assert str(per_etikett["Av- och nedskrivningar"]) == "0.0"

    def test_vattenfall_resultat_kostnader_ar_negativa(self):
        per_etikett = {e: b for e, b, _ in vattenfall_resultat(self._rapport())}
        assert per_etikett["Totala intäkter"] > 0
        assert per_etikett["Kostnad sålda varor"] < 0
        assert per_etikett["Övriga rörelsekostnader"] < 0

    def test_vattenfall_resultat_reconcilierar_till_resultat(self):
        # Intäkter − KSV − Övriga − Avskrivningar == Resultat (samma som staplarna).
        steg = vattenfall_resultat(self._rapport())
        summa_steg = sum(belopp for _, belopp, measure in steg if measure != "total")
        total = next(belopp for _, belopp, measure in steg if measure == "total")
        assert round(summa_steg, 2) == round(total, 2)
        assert total == pytest.approx(668090.00, abs=0.01)

    def test_resultattabell_belopp_ar_numeriskt(self):
        # Numeriskt så st.dataframe högerjusterar + column_config tusentalsformaterar.
        rader = resultattabell_rader(self._rapport())
        assert len(rader) == len(RESULTAT_UPPSTALLNING)
        assert all(isinstance(r["Belopp"], float) for r in rader)
        per_post = {r["Post"]: r for r in rader}
        assert per_post["Totala intäkter"]["Belopp"] == 2625800  # hela kronor


class TestNyckeltalVy:
    def test_nyckeltal_fran_sie_facit(self):
        n = nyckeltal_fran_sie(_sie())["nyckeltal"]
        assert round(float(n["soliditet"]) * 100, 1) == 65.6
        assert round(float(n["soliditet_jek"]) * 100, 1) == 68.3
        assert round(float(n["bruttomarginal"]) * 100, 1) == 85.8

    def test_nyckeltal_fran_sie_facit_de_nya(self):
        # Samma exempelfil, nu även de nio tidigare platshållarna. nyckeltal_fran_sie
        # bygger kassaflödet internt, så fritt_kassaflode ska vara med här också.
        n = nyckeltal_fran_sie(_sie())["nyckeltal"]
        assert round(float(n["vinstmarginal"]) * 100, 1) == 16.3
        assert round(float(n["ebita_marginal"]) * 100, 1) == 25.4
        assert round(float(n["roe"]) * 100, 1) == 18.9
        assert round(float(n["roa"]) * 100, 1) == 19.3
        assert round(float(n["roce"]) * 100, 1) == 24.0
        assert round(float(n["skuldsattningsgrad"]), 2) == 0.47
        assert n["ebitda"] == Decimal("668090.00")
        assert n["fritt_kassaflode"] == Decimal("-382810.00")
        # Ingen antal_anstallda gavs in -> odefinierat, inte en gissad nolla.
        assert n["personalkostnad_per_anstalld"] is None

    def test_formatera_procent(self):
        # Strippa blanksteg (regular/nbsp) -> deterministiskt oavsett mellanslagstyp.
        procent = formatera_procent(Decimal("0.573")).replace(NBSP, "").replace(" ", "")
        assert procent == "57,3%"


class TestNyckeltalMedPersonalkostnad:
    """Vy-lagrets omräkning av personalkostnad_per_anstalld när användaren
    fyller i antal anställda LIVE i Nyckeltal-fliken — SIE4 har ingen
    personalstyrka, så talet kan aldrig vara med i den ursprungliga rapporten."""

    def test_ursprungsrapporten_saknar_talet(self):
        n = nyckeltal_fran_sie(_sie())["nyckeltal"]
        assert n["personalkostnad_per_anstalld"] is None

    def test_raknar_om_med_antal_anstallda(self):
        sie = _sie()
        resultat = resultatrapport_fran_sie(sie)
        n = nyckeltal_fran_sie(sie)["nyckeltal"]

        omraknat = nyckeltal_med_personalkostnad(n, resultat, 10)
        assert omraknat["personalkostnad_per_anstalld"] == (
            resultat["poster"]["personalkostnader"] / 10
        )

    def test_muterar_inte_originalet(self):
        sie = _sie()
        resultat = resultatrapport_fran_sie(sie)
        n = nyckeltal_fran_sie(sie)["nyckeltal"]

        nyckeltal_med_personalkostnad(n, resultat, 10)
        assert n["personalkostnad_per_anstalld"] is None

    def test_inget_antal_anstallda_ger_none(self):
        sie = _sie()
        resultat = resultatrapport_fran_sie(sie)
        n = nyckeltal_fran_sie(sie)["nyckeltal"]

        omraknat = nyckeltal_med_personalkostnad(n, resultat, None)
        assert omraknat["personalkostnad_per_anstalld"] is None

    def test_andra_nycklar_ar_orörda(self):
        sie = _sie()
        resultat = resultatrapport_fran_sie(sie)
        n = nyckeltal_fran_sie(sie)["nyckeltal"]

        omraknat = nyckeltal_med_personalkostnad(n, resultat, 10)
        assert omraknat["soliditet"] == n["soliditet"]
        assert omraknat["ebitda"] == n["ebitda"]

    def test_formatera_multipel(self):
        assert formatera_multipel(Decimal("7.9172")).startswith("7,92")

    def test_none_renderas_som_streck_inte_noll(self):
        # Odefinierat nyckeltal -> ett streck, aldrig "0" (skulle lura läsaren).
        for saknas in (formatera_procent(None), formatera_multipel(None)):
            assert not any(c.isdigit() for c in saknas)
        assert formatera_procent(None) == formatera_multipel(None)


class TestNyckeltalskatalog:
    _PER_ETIKETT = {d.etikett: d for d in NYCKELTAL_KATALOG}

    def test_default_ar_precis_de_fyra(self):
        assert DEFAULT_NYCKELTAL == [
            "Bruttomarginal", "Rörelsemarginal (EBIT)", "Soliditet", "Kassalikviditet"
        ]

    def test_alla_nya_finns_som_valbara(self):
        for etikett in (
            "Vinstmarginal", "EBITDA", "EBITA-marginal",
            "Avkastning på eget kapital (ROE)", "Avkastning på totalt kapital (ROA)",
            "Avkastning på sysselsatt kapital (ROCE)", "Skuldsättningsgrad",
            "Fritt kassaflöde", "Personalkostnad per anställd",
        ):
            assert etikett in self._PER_ETIKETT

    def test_alla_nyckeltal_ar_nu_implementerade(self):
        # De nio var platshållare (🚧); nu har alla en färdig formel i motorn.
        assert all(d.implementerad for d in NYCKELTAL_KATALOG)


class TestFormateraNyckeltal:
    def test_procent_respekterar_toggle(self):
        som_p = formatera_nyckeltal(Decimal("0.573"), "procent", som_procent=True)
        assert "57,3" in som_p and "%" in som_p
        som_kvot = formatera_nyckeltal(Decimal("0.573"), "procent", som_procent=False)
        assert som_kvot.endswith("x")

    def test_kr_och_multipel_ignorerar_toggle(self):
        assert "kr" in formatera_nyckeltal(Decimal("1000"), "kr", som_procent=False)
        assert formatera_nyckeltal(Decimal("2.5"), "multipel", som_procent=True).endswith("x")

    def test_none_ger_streck(self):
        streck = formatera_nyckeltal(None, "procent", som_procent=True)
        assert not any(c.isdigit() for c in streck)


class TestValjNyckeltal:
    def test_foljer_multiselect_ordningen_inte_katalogen(self):
        # "Drag and drop": renderingsordningen SKA vara markeringsordningen.
        valda = valj_nyckeltal(["Soliditet", "Bruttomarginal"])
        assert [d.nyckel for d in valda] == ["soliditet", "bruttomarginal"]

    def test_ignorerar_okanda_etiketter(self):
        assert [d.nyckel for d in valj_nyckeltal(["Finns inte", "EBITDA"])] == ["ebitda"]

    def test_tom_lista(self):
        assert valj_nyckeltal([]) == []


class TestRadbryt:
    def test_delar_i_delrader(self):
        assert radbryt([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_jamnt_upp(self):
        assert radbryt([1, 2, 3, 4], 4) == [[1, 2, 3, 4]]

    def test_tom_lista(self):
        assert radbryt([], 4) == []


class TestKassaflodeVy:
    def test_kassaflodesanalys_fran_sie_facit(self):
        k = kassaflodesanalys_fran_sie(_sie())
        assert k["arets_kassaflode"] == Decimal("-482810.00")
        assert k["kontrolldiff"] == Decimal("0")
        assert k["lopande"]["summa"] == Decimal("-262810.00")

    def test_vattenfall_reconcilierar_till_arets_kassaflode(self):
        steg = vattenfall_kassaflode(kassaflodesanalys_fran_sie(_sie()))
        # Startstapel + relativa steg == total-stapeln.
        icke_total = sum(belopp for _, belopp, measure in steg if measure != "total")
        total = next(belopp for _, belopp, measure in steg if measure == "total")
        assert round(icke_total, 2) == round(total, 2)
        assert steg[0][2] == "absolute"
        assert steg[-1][2] == "total"

    def test_block_poster_finns_i_rapporten(self):
        # Uppställnings-config pekar bara på poster som motorn faktiskt levererar.
        k = kassaflodesanalys_fran_sie(_sie())
        for block_nyckel, _etikett, rader in KASSAFLODE_BLOCK:
            poster = k[block_nyckel]["poster"]
            for post_nyckel, _post_etikett in rader:
                assert post_nyckel in poster


class TestDashboardRouting:
    def test_spirislage_utan_data_ger_ingen(self):
        assert (
            dashboard_rendering_lage(
                datakälla_ar_spiris=True, sie_finns=True, spiris_data_finns=False
            )
            == "ingen"
        )

    def test_spirislage_med_data_ger_spiris(self):
        # I Spiris-läge används ENBART live-data — inte en ev. maskerad SIEFil.
        assert (
            dashboard_rendering_lage(
                datakälla_ar_spiris=True, sie_finns=True, spiris_data_finns=True
            )
            == "spiris"
        )

    def test_fillage_med_sie_ger_fil(self):
        assert (
            dashboard_rendering_lage(
                datakälla_ar_spiris=False, sie_finns=True, spiris_data_finns=False
            )
            == "fil"
        )

    def test_inget_inlast_ger_ingen(self):
        assert (
            dashboard_rendering_lage(
                datakälla_ar_spiris=False, sie_finns=False, spiris_data_finns=False
            )
            == "ingen"
        )


class TestDashboardSaknarData:
    def test_tom_period_ar_tom(self):
        # Bara den syntetiska Årets resultat-raden (8999) -> ingen riktig data.
        data = {"resultat": {"konton": []}, "balans": {"konton": [{"kontonr": "8999"}]}}
        assert dashboard_saknar_data(data) is True

    def test_med_konton_ar_inte_tom(self):
        data = {
            "resultat": {"konton": [{"kontonr": "3010"}]},
            "balans": {"konton": [{"kontonr": "1910"}, {"kontonr": "8999"}]},
        }
        assert dashboard_saknar_data(data) is False


class TestDefaultDatumintervall:
    def test_valjer_senaste_rakenskapsaret(self):
        år = [
            {"StartDate": "2025-01-01", "EndDate": "2025-12-31"},
            {"StartDate": "2026-01-01", "EndDate": "2026-12-31"},
        ]
        start, slut = default_datumintervall(år)
        assert start == date(2026, 1, 1)
        assert slut == date(2026, 12, 31)

    def test_tom_lista_ger_innevarande_kalenderar(self):
        start, slut = default_datumintervall([])
        assert start.month == 1 and start.day == 1
        assert slut.month == 12 and slut.day == 31
        assert start.year == slut.year


class TestInnevarandeArIntervall:
    def test_ger_1jan_till_31dec_for_injicerat_ar(self):
        assert innevarande_ar_intervall(date(2026, 7, 9)) == (date(2026, 1, 1), date(2026, 12, 31))


class TestValjRakenskapsarForAr:
    _ÅR = [
        {"StartDate": "2025-01-01", "EndDate": "2025-12-31", "Id": "a"},
        {"StartDate": "2026-01-01", "EndDate": "2026-12-31", "Id": "b"},
    ]

    def test_valjer_matchande_ar(self):
        assert valj_rakenskapsar_for_ar(self._ÅR, 2026)["Id"] == "b"
        assert valj_rakenskapsar_for_ar(self._ÅR, 2025)["Id"] == "a"

    def test_saknat_ar_ger_none(self):
        assert valj_rakenskapsar_for_ar(self._ÅR, 2030) is None
        assert valj_rakenskapsar_for_ar([], 2026) is None


# --- Framtidens balansräkning: Sankey-mappning + narrativt lager -------------

class TestSankeyData:
    """Mappar en FÄRDIG balansrapport till Plotly-Sankey: finansieringskällor
    till vänster, tillgångar till höger. Flödena fördelas PRO RATA — kapital är
    fungibelt, så ingen enskild krona kan hänföras till en enskild tillgång.
    Kontraktet: summan av länkarna ut ur varje källa = källans belopp, och
    summan in i varje tillgång = tillgångens belopp."""

    POSTER = {
        "summa_anlaggningstillgangar": Decimal("400"),
        "kassa_och_bank": Decimal("300"),
        "summa_omsattningstillgangar": Decimal("600"),
        "summa_tillgangar": Decimal("1000"),
        "eget_kapital": Decimal("600"),
        "obeskattade_reserver": Decimal("100"),
        "avsattningar": Decimal("0"),
        "langfristiga_skulder": Decimal("100"),
        "kortfristiga_skulder": Decimal("200"),
        "summa_eget_kapital_och_skulder": Decimal("1000"),
    }

    def _data(self, **overrides):
        return sankey_data({"poster": {**self.POSTER, **overrides}})

    def test_kallor_till_vanster_tillgangar_till_hoger(self):
        d = self._data()
        assert d["noder"] == [
            "Eget kapital",
            "Obeskattade reserver",
            "Långfristiga skulder",
            "Kortfristiga skulder",
            "Anläggningstillgångar",
            "Omsättningstillgångar (exkl. kassa)",
            "Kassa & bank",
        ]

    def test_obeskattade_reserver_ar_med_annars_forsvinner_kapital(self):
        # Regression: med bara EK + LS + KS hade 100 kr (87 500 i exempelfilen)
        # tappats bort och Sankey-flödena inte gått ihop.
        assert "Obeskattade reserver" in self._data()["noder"]

    def test_nollposter_utelamnas(self):
        # Avsättningar = 0 -> ingen nod (en nollflödesnod är bara brus).
        assert "Avsättningar" not in self._data()["noder"]
        assert "Avsättningar" in self._data(avsattningar=Decimal("50"))["noder"]

    def test_omsattningstillgangar_exkluderar_kassan(self):
        # summa_omsattningstillgangar INKLUDERAR kassan -> annars dubbelräkning.
        d = self._data()
        index = d["noder"].index("Omsättningstillgångar (exkl. kassa)")
        assert sum(länk["varde"] for länk in d["lankar"] if länk["mal"] == index) == pytest.approx(300.0)

    def test_lankarna_ut_ur_varje_kalla_summerar_till_kallans_belopp(self):
        d = self._data()
        for etikett, belopp in [("Eget kapital", 600.0), ("Obeskattade reserver", 100.0),
                                ("Långfristiga skulder", 100.0), ("Kortfristiga skulder", 200.0)]:
            i = d["noder"].index(etikett)
            ut = sum(länk["varde"] for länk in d["lankar"] if länk["kalla"] == i)
            assert ut == pytest.approx(belopp), etikett

    def test_lankarna_in_i_varje_tillgang_summerar_till_tillgangens_belopp(self):
        d = self._data()
        for etikett, belopp in [("Anläggningstillgångar", 400.0),
                                ("Omsättningstillgångar (exkl. kassa)", 300.0),
                                ("Kassa & bank", 300.0)]:
            j = d["noder"].index(etikett)
            inflöde = sum(länk["varde"] for länk in d["lankar"] if länk["mal"] == j)
            assert inflöde == pytest.approx(belopp), etikett

    def test_totalt_flode_ar_balansomslutningen(self):
        d = self._data()
        assert sum(länk["varde"] for länk in d["lankar"]) == pytest.approx(1000.0)
        assert d["varning"] is None

    def test_pro_rata_andel(self):
        # EK (600) finansierar 40 % av anläggningstillgångarna (400/1000) = 240.
        d = self._data()
        i, j = d["noder"].index("Eget kapital"), d["noder"].index("Anläggningstillgångar")
        länk = next(x for x in d["lankar"] if x["kalla"] == i and x["mal"] == j)
        assert länk["varde"] == pytest.approx(240.0)

    def test_varje_nod_har_en_farg(self):
        d = self._data()
        assert len(d["nodfarger"]) == len(d["noder"])

    def test_noll_balansomslutning_ger_inga_lankar_och_varning(self):
        d = sankey_data({"poster": dict.fromkeys(self.POSTER, Decimal("0"))})
        assert d["lankar"] == []
        assert d["varning"] is not None

    def test_negativ_post_utelamnas_och_flaggas(self):
        # Negativt EK (förlustbolag) går inte att rita som ett flöde -> flaggas.
        d = self._data(eget_kapital=Decimal("-100"))
        assert "Eget kapital" not in d["noder"]
        assert d["varning"] is not None and "negativ" in d["varning"].lower()

    def test_mot_exempelfilen(self):
        d = sankey_data(balansrapport_fran_sie(_sie()))
        assert d["varning"] is None
        assert sum(länk["varde"] for länk in d["lankar"]) == pytest.approx(3457690.00, abs=0.01)
        # 87 500 kr obeskattade reserver ska synas som ett eget flöde.
        i = d["noder"].index("Obeskattade reserver")
        assert sum(länk["varde"] for länk in d["lankar"] if länk["kalla"] == i) == pytest.approx(120000.0)


class TestNarrativSimulering:
    """Det narrativa lagret: deterministiska meningar (ingen LLM, ingen PII) som
    förklarar vad simuleringen gjorde med soliditeten och kassalikviditeten.
    Riktningen läses ur de FAKTISKA värdena — texten påstår aldrig något som
    siffrorna inte visar."""

    FORE = {"soliditet": Decimal("0.60"), "kassalikviditet": Decimal("2.00")}

    def test_noll_investering_ger_en_neutral_rad(self):
        rader = narrativ_simulering(self.FORE, self.FORE, Decimal("0"), "Eget kapital")
        assert len(rader) == 1
        assert "Ingen investering" in rader[0]

    def test_soliditet_sjunker_vid_lanefinansiering(self):
        efter = {"soliditet": Decimal("0.50"), "kassalikviditet": Decimal("2.00")}
        text = " ".join(narrativ_simulering(self.FORE, efter, Decimal("100"), "Långfristiga skulder")).replace(NBSP, " ")
        assert "Soliditeten sjunker från 60,0 % till 50,0 %" in text

    def test_oforandrat_nyckeltal_pastar_ingen_forandring(self):
        text = " ".join(narrativ_simulering(self.FORE, self.FORE, Decimal("100"), "Långfristiga skulder")).replace(NBSP, " ")
        assert "Kassalikviditeten är oförändrad på 200,0 %" in text

    def test_stigande_nyckeltal(self):
        efter = {"soliditet": Decimal("0.70"), "kassalikviditet": Decimal("2.00")}
        text = " ".join(narrativ_simulering(self.FORE, efter, Decimal("100"), "Eget kapital")).replace(NBSP, " ")
        assert "Soliditeten stiger från 60,0 % till 70,0 %" in text

    def test_odefinierat_nyckeltal_ger_arlig_text_inte_falsk_nolla(self):
        efter = {"soliditet": None, "kassalikviditet": Decimal("2.00")}
        rader = narrativ_simulering(self.FORE, efter, Decimal("100"), "Eget kapital")
        soliditetsraden = next(rad for rad in rader if rad.startswith("Soliditeten"))
        assert soliditetsraden == "Soliditeten kan inte beräknas (nämnaren är noll)."
        assert "%" not in soliditetsraden  # ingen påhittad procentsats

    def test_beloppet_och_finansieringsforklaringen_finns_med(self):
        rader = narrativ_simulering(self.FORE, self.FORE, Decimal("1000000"), "Kortfristiga skulder")
        assert formatera_kr(Decimal("1000000")) in rader[0]
        assert rader[-1] == FINANSIERINGSFORKLARING["Kortfristiga skulder"]

    def test_varje_finansieringskalla_har_en_forklaring(self):
        from fpa_motor import FINANSIERINGSKALLOR

        assert sorted(FINANSIERINGSFORKLARING) == sorted(FINANSIERINGSKALLOR)

    def test_simuleringens_maxbelopp(self):
        assert SIMULERING_MAX == 5_000_000


class TestFormateraProcentenheter:
    """st.metric-deltat: förändringen i procentenheter, med svensk decimalkomma
    och tecken. None när deltat saknar mening (odefinierat eller oförändrat) —
    Streamlit ritar då inget delta alls i stället för en falsk nolla."""

    def test_minskning(self):
        assert formatera_procentenheter(Decimal("0.825"), Decimal("0.52")) == f"-30,5{NBSP}p.e."

    def test_okning_far_plustecken(self):
        assert formatera_procentenheter(Decimal("0.60"), Decimal("0.70")) == f"+10,0{NBSP}p.e."

    def test_oforandrat_ger_none(self):
        assert formatera_procentenheter(Decimal("0.60"), Decimal("0.60")) is None

    def test_odefinierat_ger_none(self):
        assert formatera_procentenheter(None, Decimal("0.60")) is None
        assert formatera_procentenheter(Decimal("0.60"), None) is None


class TestSimuleringGlue:
    """Glue-funktionen håller dashboarden dum: den anropar SAMMA KPI-motor som
    KPI-fliken, så soliditetsformeln aldrig dubbleras i UI-koden."""

    def _rapporter(self):
        sie = _sie()
        return resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie)

    def test_noll_investering_lamnar_nyckeltalen_orörda(self):
        resultat, balans = self._rapporter()
        s = simulering(resultat, balans, Decimal("0"), "Långfristiga skulder")
        assert s["nyckeltal_fore"] == s["nyckeltal_efter"]
        assert s["balans_efter"]["poster"]["kontrolldiff"] == Decimal("0")

    def test_lanefinansiering_spader_ut_soliditeten(self):
        resultat, balans = self._rapporter()
        s = simulering(resultat, balans, Decimal("1000000"), "Långfristiga skulder")
        assert s["nyckeltal_efter"]["soliditet"] < s["nyckeltal_fore"]["soliditet"]
        # Kassan och de kortfristiga skulderna rörs inte -> kassalikviditeten står still.
        assert s["nyckeltal_efter"]["kassalikviditet"] == s["nyckeltal_fore"]["kassalikviditet"]
        assert "Soliditeten sjunker" in " ".join(s["narrativ"])

    def test_kassafinansiering_lamnar_soliditeten_men_sanker_likviditeten(self):
        resultat, balans = self._rapporter()
        s = simulering(resultat, balans, Decimal("1000000"), "Minskning av kassa/bank")
        assert s["nyckeltal_efter"]["soliditet"] == s["nyckeltal_fore"]["soliditet"]
        assert s["nyckeltal_efter"]["kassalikviditet"] < s["nyckeltal_fore"]["kassalikviditet"]

    def test_sankey_pa_den_simulerade_rapporten_gar_ihop(self):
        resultat, balans = self._rapporter()
        s = simulering(resultat, balans, Decimal("1000000"), "Eget kapital")
        d = sankey_data(s["balans_efter"])
        assert sum(länk["varde"] for länk in d["lankar"]) == pytest.approx(4457690.00, abs=0.01)

    def test_varningen_nar_ut_till_dashboarden(self):
        resultat, balans = self._rapporter()
        # Kassan är 2 381 558,42 -> 5 Mkr ur kassan ger negativ kassa.
        s = simulering(resultat, balans, Decimal("5000000"), "Minskning av kassa/bank")
        assert s["varning"] is not None
        # Motorn är display-fri; vy-lagret formaterar beloppet (aldrig en rå float).
        assert formatera_kr(Decimal("-4450810.00")) in s["varning"]
        assert "-4450810.00" not in s["varning"]


class TestRapporterFranSie:
    """Fil-vägen ska ge EXAKT samma dict-form som spiris_rag.hamta_dashboard
    ger live, så app.py kan mata båda källorna in i samma renderare."""

    def test_samma_nycklar_som_live_dashboarden(self):
        rapporter = rapporter_fran_sie(_sie())

        assert set(rapporter) == {"resultat", "balans", "nyckeltal", "kassaflode"}

    def test_delrapporterna_ar_identiska_med_de_enskilda_byggarna(self):
        sie = _sie()
        rapporter = rapporter_fran_sie(sie)

        assert rapporter["resultat"] == resultatrapport_fran_sie(sie)
        assert rapporter["balans"] == balansrapport_fran_sie(sie)
        assert rapporter["nyckeltal"] == nyckeltal_fran_sie(sie)
        assert rapporter["kassaflode"] == kassaflodesanalys_fran_sie(sie)


class TestStapeldataBalans:
    """Två staplar på BAS-kontogruppsnivå. Den bärande invarianten: varje stapels
    segment summerar EXAKT till stapelns slutsumma — annars blir staplarna olika
    höga trots att bokföringen balanserar, och hela läsningen debet = kredit dör."""

    def test_tillgangsstapeln_summerar_till_summa_tillgangar(self):
        rapport = balansrapport_fran_sie(_sie())
        segment = stapeldata_balans(rapport)["segment"]

        tillgangar = [s for s in segment if s["stapel"] == STAPEL_TILLGANGAR]
        assert sum(s["belopp"] for s in tillgangar) == pytest.approx(
            float(rapport["poster"]["summa_tillgangar"])
        )

    def test_finansieringsstapeln_summerar_till_summa_ek_och_skulder(self):
        rapport = balansrapport_fran_sie(_sie())
        segment = stapeldata_balans(rapport)["segment"]

        finansiering = [s for s in segment if s["stapel"] == STAPEL_FINANSIERING]
        assert sum(s["belopp"] for s in finansiering) == pytest.approx(
            float(rapport["poster"]["summa_eget_kapital_och_skulder"])
        )

    def test_staplarna_ar_lika_hoga_nar_bokforingen_balanserar(self):
        rapport = balansrapport_fran_sie(_sie())
        assert rapport["poster"]["kontrolldiff"] == 0
        segment = stapeldata_balans(rapport)["segment"]

        höjd: dict[str, float] = {}
        for s in segment:
            höjd[s["stapel"]] = höjd.get(s["stapel"], 0.0) + s["belopp"]
        assert höjd[STAPEL_TILLGANGAR] == pytest.approx(höjd[STAPEL_FINANSIERING])

    def test_segmenten_ligger_pa_bas_kontogruppsniva(self):
        # Kundfordringar (15) och Maskiner och inventarier (12) är egna segment,
        # inte hopslagna i "Kortfristiga fordringar"/"Materiella anläggningstillgångar".
        rapport = balansrapport_fran_sie(_sie())
        etiketter = {s["etikett"] for s in stapeldata_balans(rapport)["segment"]}

        assert "Kundfordringar" in etiketter
        assert "Maskiner och inventarier" in etiketter
        assert "Varulager" in etiketter
        assert "Kassa och bank" in etiketter

    def test_nollposter_utelamnas(self):
        # Exempelfilen saknar byggnader och mark (BAS 11) -> inget nollhögt segment.
        rapport = balansrapport_fran_sie(_sie())
        nycklar = {s["nyckel"] for s in stapeldata_balans(rapport)["segment"]}

        assert "byggnader_och_mark" not in nycklar

    def test_varje_segment_har_egen_farg_inom_sin_stapel(self):
        rapport = balansrapport_fran_sie(_sie())
        segment = stapeldata_balans(rapport)["segment"]

        for stapel in (STAPEL_TILLGANGAR, STAPEL_FINANSIERING):
            färger = [s["farg"] for s in segment if s["stapel"] == stapel]
            assert len(set(färger)) == len(färger)

    def test_tom_balansrakning_flaggas(self):
        rapport = balansrapport_fran_sie(_sie())
        for nyckel in rapport["poster"]:
            rapport["poster"][nyckel] = Decimal("0")

        data = stapeldata_balans(rapport)

        assert data["segment"] == []
        assert "noll" in data["varning"]


class TestNegativaBasgrupper:
    """En BAS-grupp kan ha negativt saldo (2510 Skatteskulder med debetsaldo i
    exempelfilen). Negativa poster går inte att stapla — de måste absorberas av
    Övrigt-hinken, aldrig utelämnas, annars blir stapeln för hög."""

    def test_exempelfilen_har_en_negativ_basgrupp(self):
        # Skyddar premissen för resten av klassen.
        rapport = balansrapport_fran_sie(_sie())
        per_undergrupp: dict[str, Decimal] = {}
        for konto in rapport["konton"]:
            per_undergrupp.setdefault(konto["undergrupp"], Decimal("0"))
            per_undergrupp[konto["undergrupp"]] += konto["saldo"]

        assert per_undergrupp["25"] < 0

    def test_totalen_bevaras_trots_negativ_grupp(self):
        rapport = balansrapport_fran_sie(_sie())
        finansiering = [
            s for s in stapeldata_balans(rapport)["segment"] if s["stapel"] == STAPEL_FINANSIERING
        ]

        assert sum(s["belopp"] for s in finansiering) == pytest.approx(
            float(rapport["poster"]["summa_eget_kapital_och_skulder"])
        )

    def test_inget_segment_ar_negativt(self):
        rapport = balansrapport_fran_sie(_sie())
        assert all(s["belopp"] > 0 for s in stapeldata_balans(rapport)["segment"])

    def test_nedflyttning_varnas(self):
        rapport = balansrapport_fran_sie(_sie())
        varning = stapeldata_balans(rapport)["varning"]

        assert varning is not None
        assert "Långfristiga skulder" in varning

    def test_hinken_offrar_sin_egen_familj_forst(self):
        # Obeskattade reserver är KAPITAL och får aldrig hamna under etiketten
        # "Övriga skulder och avsättningar" — då ljuger etiketten. Ett skuldsegment
        # offras i stället, trots att det är större.
        rapport = balansrapport_fran_sie(_sie())
        segment = stapeldata_balans(rapport)["segment"]
        nycklar = {s["nyckel"] for s in segment}

        assert "obeskattade_reserver" in nycklar
        assert "langfristiga_skulder" not in nycklar
        ovrigt = next(s for s in segment if s["nyckel"] == "ovriga_skulder")
        assert ovrigt["etikett"] == "Övriga skulder och avsättningar"

    def test_hinken_byter_till_neutral_etikett_om_annan_familj_tvingas_ned(self):
        # Konstruerat: en enorm negativ skuldgrupp tvingar ned även kapitalet.
        rapport = balansrapport_fran_sie(_sie())
        rapport["konton"].append(
            {
                "kontonr": "2510",
                "kontonamn": "Extrem skattefordran",
                "saldo": Decimal("-4000000"),
                "grupp": "kortfristiga_skulder",
                "undergrupp": "25",
            }
        )
        rapport["poster"]["summa_eget_kapital_och_skulder"] = Decimal("257572.13")

        segment = stapeldata_balans(rapport)["segment"]
        ovrigt = next(s for s in segment if s["nyckel"] == "ovriga_skulder")

        assert ovrigt["etikett"] == "Övriga poster"


class TestSegmentDrilldown:
    def test_ovrigt_hinken_drillar_ned_till_exakt_sitt_eget_belopp(self):
        # Hinken äger sina egna undergrupper PLUS de nedflyttade segmentens.
        rapport = balansrapport_fran_sie(_sie())
        ovrigt = next(
            s for s in stapeldata_balans(rapport)["segment"] if s["nyckel"] == "ovriga_skulder"
        )

        konton = konton_i_segment(rapport, ovrigt["undergrupper"])
        assert sum(float(k["saldo"]) for k in konton) == pytest.approx(ovrigt["belopp"])

    def test_alla_segment_drillar_ned_till_sitt_belopp(self):
        rapport = balansrapport_fran_sie(_sie())
        for del_ in stapeldata_balans(rapport)["segment"]:
            konton = konton_i_segment(rapport, del_["undergrupper"])
            assert sum(float(k["saldo"]) for k in konton) == pytest.approx(
                del_["belopp"]
            ), del_["nyckel"]

    def test_kundfordringar_drillar_ned_till_15xx_konton(self):
        rapport = balansrapport_fran_sie(_sie())
        konton = konton_i_segment(rapport, ("15",))

        assert konton
        assert all(k["kontonr"].startswith("15") for k in konton)

    def test_okand_undergrupp_ger_tom_lista_inte_krasch(self):
        rapport = balansrapport_fran_sie(_sie())
        assert konton_i_segment(rapport, ("99",)) == []
        assert segment_med_nyckel("finns_inte") is None


class TestSorteraDrilldown:
    """Manage by exception: stora poster överst, nollkonton undan."""

    def _konto(self, kontonr: str, saldo: str) -> dict:
        return {"kontonr": kontonr, "kontonamn": f"Konto {kontonr}", "saldo": Decimal(saldo)}

    def test_aktiva_sorteras_fallande_pa_belopp(self):
        konton = [self._konto("1510", "100"), self._konto("1930", "5000"), self._konto("1410", "900")]

        aktiva, _ = sortera_drilldown(konton)

        assert [k["kontonr"] for k in aktiva] == ["1930", "1410", "1510"]

    def test_sorteringen_gar_pa_absolut_belopp(self):
        # En stor skattefordran (-210 000) är minst lika intressant som en stor
        # positiv post och ska inte hamna längst ned.
        konton = [self._konto("2650", "119375"), self._konto("2510", "-210000")]

        aktiva, _ = sortera_drilldown(konton)

        assert [k["kontonr"] for k in aktiva] == ["2510", "2650"]

    def test_nollkonton_separeras(self):
        konton = [self._konto("1510", "0"), self._konto("1930", "5000"), self._konto("1410", "0")]

        aktiva, nollkonton = sortera_drilldown(konton)

        assert [k["kontonr"] for k in aktiva] == ["1930"]
        assert [k["kontonr"] for k in nollkonton] == ["1410", "1510"]

    def test_nollkonton_sorteras_pa_kontonummer(self):
        konton = [self._konto("2999", "0"), self._konto("1010", "0")]

        _, nollkonton = sortera_drilldown(konton)

        assert [k["kontonr"] for k in nollkonton] == ["1010", "2999"]

    def test_lika_belopp_sorteras_stabilt_pa_kontonummer(self):
        konton = [self._konto("1930", "500"), self._konto("1910", "500")]

        aktiva, _ = sortera_drilldown(konton)

        assert [k["kontonr"] for k in aktiva] == ["1910", "1930"]

    def test_inga_konton_ger_tomma_listor(self):
        assert sortera_drilldown([]) == ([], [])

    def test_inget_konto_tappas(self):
        konton = [self._konto("1510", "0"), self._konto("1930", "5000")]
        aktiva, nollkonton = sortera_drilldown(konton)

        assert len(aktiva) + len(nollkonton) == len(konton)


class TestValdaSegmentUrPunkter:
    """Klickhanteringen ska tåla allt Plotly-frontend kan skicka tillbaka."""

    def test_plockar_nyckel_ur_customdata(self):
        punkter = [{"curve_number": 3, "customdata": ["eget_kapital"]}]
        assert valda_segment_ur_punkter(punkter) == ["eget_kapital"]

    def test_flera_klick_behaller_klickordningen(self):
        punkter = [{"customdata": ["kassa_och_bank"]}, {"customdata": ["eget_kapital"]}]
        assert valda_segment_ur_punkter(punkter) == ["kassa_och_bank", "eget_kapital"]

    def test_dubbletter_filtreras_bort(self):
        punkter = [{"customdata": ["eget_kapital"]}, {"customdata": ["eget_kapital"]}]
        assert valda_segment_ur_punkter(punkter) == ["eget_kapital"]

    def test_punkt_utan_customdata_ignoreras(self):
        assert valda_segment_ur_punkter([{"curve_number": 0}]) == []

    def test_okand_nyckel_ignoreras(self):
        assert valda_segment_ur_punkter([{"customdata": ["hittepa"]}]) == []

    def test_ingen_selection_ger_tom_lista(self):
        assert valda_segment_ur_punkter([]) == []


class TestInlineEtiketter:
    """Inline-texten skrivs bara i segment som är höga nog att rymma en rad."""

    def test_andel_ar_segmentets_andel_av_stapeln(self):
        rapport = balansrapport_fran_sie(_sie())
        for stapel in (STAPEL_TILLGANGAR, STAPEL_FINANSIERING):
            segment = [s for s in stapeldata_balans(rapport)["segment"] if s["stapel"] == stapel]
            assert sum(s["andel"] for s in segment) == pytest.approx(1.0)

    def test_stort_segment_far_text(self):
        assert ryms_inline_text(0.55) is True

    def test_tunt_segment_far_ingen_text(self):
        # Obeskattade reserver (2,1 % av stapeln) skulle bli oläslig.
        assert ryms_inline_text(0.021) is False

    def test_troskeln_ar_inklusiv(self):
        assert ryms_inline_text(INLINE_TEXT_TROSKEL) is True

    def test_kassan_far_text_men_ovriga_tillgangar_inte(self):
        rapport = balansrapport_fran_sie(_sie())
        per_nyckel = {s["nyckel"]: s for s in stapeldata_balans(rapport)["segment"]}

        assert ryms_inline_text(per_nyckel["kassa_och_bank"]["andel"]) is True
        assert ryms_inline_text(per_nyckel["ovriga_tillgangar"]["andel"]) is False


class TestOvrigtHinkarnasFarger:
    def test_de_tva_hinkarna_har_olika_gra(self):
        # Annars delar två legendrader swatch och identiteten blir tvetydig.
        assert FARG_OVRIGT_TILLGANG != FARG_OVRIGT_SKULD


class TestTextFarg:
    """Textfärgen inuti ett segment räknas ut, aldrig hårdkodas till vit."""

    def test_vit_text_pa_mork_fyllning(self):
        assert text_farg(FARG_EGET_KAPITAL) == TEXT_PA_MORK_YTA

    def test_mork_text_pa_ljus_fyllning(self):
        # Vit text på kassa-blått ger 2,24:1 — långt under WCAG 4,5:1.
        assert text_farg(FARG_KASSA) == TEXT_PA_LJUS_YTA

    def test_alla_segmentfarger_nar_wcag_ag_kontrast(self):
        for segment in BALANS_SEGMENT:
            kvot = kontrastkvot(text_farg(segment.farg), segment.farg)
            assert kvot >= 4.5, f"{segment.nyckel}: {kvot:.2f}:1"

    def test_hardkodad_vit_hade_fallit_pa_ljusa_segment(self):
        # Dokumenterar VARFÖR färgen räknas ut: den naiva lösningen underkänns.
        assert kontrastkvot(TEXT_PA_MORK_YTA, FARG_KASSA) < 4.5
        assert kontrastkvot(TEXT_PA_MORK_YTA, FARG_OBESKATTADE_RESERVER) < 4.5

    def test_kontrastkvoten_ar_symmetrisk(self):
        assert kontrastkvot("#ffffff", "#000000") == pytest.approx(21.0, abs=0.1)
        assert kontrastkvot("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)

    def test_samma_farg_ger_kvot_ett(self):
        assert kontrastkvot(FARG_KASSA, FARG_KASSA) == pytest.approx(1.0)


class TestDelaUppstallning:
    """Slutsummeraden lyfts ut ur kolumnen så att de två sidornas summor kan
    renderas på EN gemensam rad — radantal och radhöjder skiljer sig åt."""

    def test_tillgangssidan_delas_i_kropp_och_summa(self):
        kropp, summa = dela_uppstallning(BALANS_TILLGANGAR)

        assert summa == ("summa_tillgangar", "SUMMA TILLGÅNGAR", "summa")
        assert len(kropp) == len(BALANS_TILLGANGAR) - 1

    def test_skuldsidan_delas_i_kropp_och_summa(self):
        kropp, summa = dela_uppstallning(BALANS_EK_SKULDER)

        assert summa[1] == "SUMMA EGET KAPITAL OCH SKULDER"
        assert len(kropp) == len(BALANS_EK_SKULDER) - 1

    def test_ingen_summarad_blir_kvar_i_kroppen(self):
        for uppstallning in (BALANS_TILLGANGAR, BALANS_EK_SKULDER):
            kropp, _ = dela_uppstallning(uppstallning)
            assert all(radtyp != "summa" for _, _, radtyp in kropp)

    def test_sidorna_har_olika_manga_kroppsrader(self):
        # Premissen för hela foten: radantalen går inte ihop, och radtyperna
        # (expander vs textrad) väger dessutom olika i höjd.
        kropp_t, _ = dela_uppstallning(BALANS_TILLGANGAR)
        kropp_s, _ = dela_uppstallning(BALANS_EK_SKULDER)

        assert len(kropp_t) != len(kropp_s)

    def test_uppstallning_utan_summarad_avvisas(self):
        with pytest.raises(ValueError):
            dela_uppstallning([("varulager", "Varulager", "grupp")])

    def test_uppstallning_med_summa_mitt_i_avvisas(self):
        with pytest.raises(ValueError):
            dela_uppstallning(
                [
                    ("summa_tillgangar", "SUMMA", "summa"),
                    ("varulager", "Varulager", "grupp"),
                    ("summa_tillgangar", "SUMMA", "summa"),
                ]
            )


def _post(typ, belopp, kostnad="0", namn=None, **extra) -> Finansieringspost:
    """Kortform för en finansieringspost i testerna. id:t härleds ur typ+belopp
    så två poster av samma typ ändå får skilda id:n."""
    return Finansieringspost(
        id=f"{typ}-{belopp}-{namn or ''}",
        namn=namn or typ,
        typ=typ,
        belopp=Decimal(str(belopp)),
        kostnad=Decimal(str(kostnad)),
        **extra,
    )


class TestFinansieringspost:
    """Posten är fail-closed redan i konstruktorn: en ogiltig post ska inte
    kunna existera och sedan tyst räknas fel längre ned i kedjan."""

    def test_okand_typ_avvisas(self):
        with pytest.raises(ValueError, match="Okänd finansieringstyp"):
            _post("guldreserv", 100)

    def test_negativt_belopp_avvisas(self):
        with pytest.raises(ValueError, match="negativt"):
            _post("lan", -1)

    def test_negativ_kostnad_avvisas(self):
        with pytest.raises(ValueError, match="negativ"):
            _post("lan", 100, kostnad="-0.01")

    def test_okand_leasingmetod_avvisas(self):
        with pytest.raises(ValueError, match="leasingmetod"):
            _post("leasing", 100, leasingmetod="kreativ")

    def test_loptid_under_ett_ar_avvisas(self):
        with pytest.raises(ValueError, match="minst ett år"):
            _post("leasing", 100, loptid_ar=0)

    def test_tva_lan_med_olika_ranta_ar_skilda_poster(self):
        # Det gick inte i den gamla dict-modellen: namnet var nyckeln.
        poster = [
            _post("lan", 100, kostnad="0.03", namn="Banklån"),
            _post("lan", 100, kostnad="0.09", namn="Säljarrevers"),
        ]

        assert len({p.id for p in poster}) == 2
        assert {p.kostnad for p in poster} == {Decimal("0.03"), Decimal("0.09")}


class TestSimuleraKapitalstack:
    """En investering, flera finansieringskällor. Den bärande invarianten: den
    dubbla bokföringen håller post för post, och posterna summerar EXAKT till
    investeringsbeloppet."""

    def _poster(self, skuld="500000", ek="300000", kassa="200000") -> list:
        return [
            _post("lan", skuld, namn="Långfristiga skulder"),
            _post("agarinsats", ek, namn="Ägarinsats"),
            _post("egna_pengar", kassa, namn="Egna pengar"),
        ]

    def test_posterna_summerar_till_investeringsbeloppet(self):
        balans = balansrapport_fran_sie(_sie())
        sim = simulera_kapitalstack(balans, Decimal("1000000"), self._poster())

        assert sum(p.belopp for p in sim["poster"]) == Decimal("1000000")

    def test_kontrolldiff_forblir_noll(self):
        balans = balansrapport_fran_sie(_sie())
        sim = simulera_kapitalstack(balans, Decimal("1000000"), self._poster())

        assert sim["balans_efter"]["poster"]["kontrolldiff"] == 0

    def test_hela_beloppet_aktiveras_som_anlaggningstillgang(self):
        balans = balansrapport_fran_sie(_sie())
        fore = balans["poster"]["materiella_anlaggningstillgangar"]
        sim = simulera_kapitalstack(balans, Decimal("1000000"), self._poster())
        efter = sim["balans_efter"]["poster"]["materiella_anlaggningstillgangar"]

        assert efter - fore == Decimal("1000000")

    def test_varje_typ_traffar_sin_egen_post(self):
        balans = balansrapport_fran_sie(_sie())
        p_fore = balans["poster"]
        sim = simulera_kapitalstack(balans, Decimal("1000000"), self._poster())
        p_efter = sim["balans_efter"]["poster"]

        assert p_efter["langfristiga_skulder"] - p_fore["langfristiga_skulder"] == Decimal("500000")
        assert p_efter["eget_kapital"] - p_fore["eget_kapital"] == Decimal("300000")
        assert p_fore["kassa_och_bank"] - p_efter["kassa_och_bank"] == Decimal("200000")

    def test_tva_lan_adderas_till_samma_balanspost(self):
        balans = balansrapport_fran_sie(_sie())
        fore = balans["poster"]["langfristiga_skulder"]
        sim = simulera_kapitalstack(balans, Decimal("300000"), [
            _post("lan", 200000, kostnad="0.03", namn="Banklån"),
            _post("lan", 100000, kostnad="0.09", namn="Säljarrevers"),
        ])

        assert sim["balans_efter"]["poster"]["langfristiga_skulder"] - fore == Decimal("300000")

    def test_orord_originalrapport(self):
        balans = balansrapport_fran_sie(_sie())
        fore = dict(balans["poster"])
        simulera_kapitalstack(balans, Decimal("1000000"), self._poster())

        assert balans["poster"] == fore

    def test_nollbelopp_ar_tillatet_och_andrar_inget(self):
        balans = balansrapport_fran_sie(_sie())
        sim = simulera_kapitalstack(balans, Decimal("0"), [])

        assert sim["balans_efter"]["poster"]["summa_tillgangar"] == balans["poster"]["summa_tillgangar"]

    def test_enkalla_ar_ett_specialfall(self):
        balans = balansrapport_fran_sie(_sie())
        sim = simulera_kapitalstack(balans, Decimal("500000"), [_post("lan", 500000)])

        assert sim["balans_efter"]["poster"]["kassa_och_bank"] == balans["poster"]["kassa_och_bank"]

    def test_kassafinansiering_over_kassan_flaggas(self):
        balans = balansrapport_fran_sie(_sie())
        sim = simulera_kapitalstack(
            balans, Decimal("99000000"), [_post("egna_pengar", 99000000)]
        )

        assert sim["varning"] is not None
        assert sim["balans_efter"]["poster"]["kassa_och_bank"] < 0

    def test_poster_som_inte_summerar_till_beloppet_avvisas(self):
        balans = balansrapport_fran_sie(_sie())
        with pytest.raises(ValueError, match="summerar"):
            simulera_kapitalstack(balans, Decimal("1000"), [_post("lan", 900)])

    def test_negativt_belopp_avvisas(self):
        balans = balansrapport_fran_sie(_sie())
        with pytest.raises(ValueError):
            simulera_kapitalstack(balans, Decimal("-1"), [])


class TestOperationellLeasingUtanforBalansrakningen:
    """K2 p. 7.10/9.4: alla leasingavtal redovisas som operationella, och
    tillgången står kvar hos leasegivaren. Den delen får därför INTE dyka upp
    som anläggningstillgång i den projicerade balansräkningen."""

    def _leasing(self, metod, belopp=400000):
        return _post("leasing", belopp, kostnad="0.04", namn="Leasing", leasingmetod=metod)

    def test_operationell_leasing_aktiveras_inte(self):
        balans = balansrapport_fran_sie(_sie())
        fore = balans["poster"]["materiella_anlaggningstillgangar"]
        sim = simulera_kapitalstack(balans, Decimal("1000000"), [
            _post("lan", 600000), self._leasing("operationell"),
        ])

        efter = sim["balans_efter"]["poster"]["materiella_anlaggningstillgangar"]
        assert efter - fore == Decimal("600000")
        assert sim["aktiverat_belopp"] == Decimal("600000")
        assert sim["ej_aktiverat_belopp"] == Decimal("400000")

    def test_operationell_leasing_ger_ingen_skuld(self):
        balans = balansrapport_fran_sie(_sie())
        fore = balans["poster"]["langfristiga_skulder"]
        sim = simulera_kapitalstack(
            balans, Decimal("400000"), [self._leasing("operationell")]
        )

        assert sim["balans_efter"]["poster"]["langfristiga_skulder"] == fore

    def test_finansiell_leasing_ger_bade_tillgang_och_skuld(self):
        # K3 p. 20.5: rättigheter och skyldigheter tas upp som tillgång OCH skuld.
        balans = balansrapport_fran_sie(_sie())
        p_fore = balans["poster"]
        sim = simulera_kapitalstack(
            balans, Decimal("400000"), [self._leasing("finansiell")]
        )
        p_efter = sim["balans_efter"]["poster"]

        assert p_efter["materiella_anlaggningstillgangar"] - p_fore[
            "materiella_anlaggningstillgangar"] == Decimal("400000")
        assert p_efter["langfristiga_skulder"] - p_fore["langfristiga_skulder"] == Decimal("400000")
        assert sim["ej_aktiverat_belopp"] == 0

    def test_kontrolldiff_haller_aven_med_operationell_leasing(self):
        balans = balansrapport_fran_sie(_sie())
        sim = simulera_kapitalstack(balans, Decimal("1000000"), [
            _post("lan", 600000), self._leasing("operationell"),
        ])

        assert sim["balans_efter"]["poster"]["kontrolldiff"] == 0


class TestBeraknaWacc:
    """WACC = Σ vikt × kapitalkostnad. Bara skuldräntan får skattesköld."""

    def _poster(self) -> list:
        return [
            _post("lan", 500000, kostnad="0.05", namn="Långfristiga skulder"),
            _post("agarinsats", 300000, kostnad="0.12", namn="Ägarinsats"),
            _post("egna_pengar", 200000, kostnad="0.02", namn="Egna pengar"),
        ]

    def test_wacc_fore_skatt_ar_viktat_snitt(self):
        wacc = berakna_wacc(self._poster())

        # 0,5×5 % + 0,3×12 % + 0,2×2 % = 6,5 %
        assert wacc["wacc_fore_skatt"] == pytest.approx(Decimal("0.065"))

    def test_skatteskolden_traffar_bara_skulden(self):
        wacc = berakna_wacc(self._poster())

        # 0,5×5 %×(1−0,206) + 0,3×12 % + 0,2×2 % = 5,985 %
        assert wacc["wacc_efter_skatt"] == pytest.approx(Decimal("0.05985"))
        assert wacc["skatteskold"] == pytest.approx(Decimal("0.00515"))

    def test_agarinsats_far_ingen_skatteskold(self):
        wacc = berakna_wacc([_post("agarinsats", 100, kostnad="0.10")])

        assert wacc["wacc_fore_skatt"] == wacc["wacc_efter_skatt"]
        assert wacc["skatteskold"] == 0

    def test_egna_pengar_far_ingen_skatteskold(self):
        wacc = berakna_wacc([_post("egna_pengar", 100, kostnad="0.03")])

        assert wacc["wacc_efter_skatt"] == pytest.approx(Decimal("0.03"))

    def test_ren_skuldfinansiering_ger_kd_gange_ett_minus_skatt(self):
        wacc = berakna_wacc([_post("lan", 100, kostnad="0.05")])

        assert wacc["wacc_efter_skatt"] == pytest.approx(Decimal("0.05") * (1 - BOLAGSSKATT))

    def test_leasingrantan_far_skatteskold(self):
        # Leasingavgiften är avdragsgill och behandlas som skuldkapital.
        wacc = berakna_wacc([_post("leasing", 100, kostnad="0.04")])

        assert wacc["wacc_efter_skatt"] == pytest.approx(Decimal("0.04") * (1 - BOLAGSSKATT))

    def test_vikterna_summerar_till_ett(self):
        wacc = berakna_wacc(self._poster())

        assert sum(post["vikt"] for post in wacc["poster"]) == pytest.approx(Decimal("1"))

    def test_bidragen_summerar_till_wacc(self):
        wacc = berakna_wacc(self._poster())

        assert sum(p["bidrag_efter_skatt"] for p in wacc["poster"]) == wacc["wacc_efter_skatt"]

    def test_nollbelopp_ger_none_inte_noll_procent(self):
        # En investering som inte görs har ingen kapitalkostnad. 0 % vore ett
        # påstående om gratis kapital.
        wacc = berakna_wacc([])

        assert wacc["wacc_fore_skatt"] is None
        assert wacc["wacc_efter_skatt"] is None
        assert wacc["poster"] == []

    def test_post_utan_belopp_utelamnas(self):
        wacc = berakna_wacc([
            _post("agarinsats", 100, kostnad="0.1", namn="Ägarinsats"),
            _post("egna_pengar", 0, kostnad="0.1", namn="Egna pengar"),
        ])

        assert [post["kalla"] for post in wacc["poster"]] == ["Ägarinsats"]

    def test_tva_lan_med_olika_ranta_vagas_var_for_sig(self):
        wacc = berakna_wacc([
            _post("lan", 100, kostnad="0.02", namn="Billigt lån"),
            _post("lan", 100, kostnad="0.10", namn="Dyrt lån"),
        ])

        assert [p["kalla"] for p in wacc["poster"]] == ["Billigt lån", "Dyrt lån"]
        assert wacc["wacc_fore_skatt"] == pytest.approx(Decimal("0.06"))


class TestLeasingUtkopstillagg:
    """Utköpspriset är en real kostnad som annars aldrig syns i WACC:en.
    Periodiseringen följer avtalets klassificering: linjärt för operationell
    leasing (K3 p. 20.13), effektivränta för finansiell (K3 p. 20.9)."""

    def _leasing(self, metod, utkop=20000, ar=5, belopp=100000):
        return _post(
            "leasing", belopp, kostnad="0.04", namn="Leasing",
            utkopspris=Decimal(str(utkop)), loptid_ar=ar, leasingmetod=metod,
        )

    def test_linjar_periodisering_ar_kvoten_delat_med_aren(self):
        # 20 000 / 100 000 = 20 %, utslaget på 5 år = 4,00 % per år.
        assert leasing_utkopstillagg(self._leasing("operationell")) == pytest.approx(
            Decimal("0.04")
        )

    def test_geometrisk_periodisering_ar_lagre_an_linjar(self):
        # (1,20)^(1/5) − 1 = 3,71 % — geometrisk tar hänsyn till att påslaget
        # i sin tur förräntas, och blir därför alltid lägre.
        geometrisk = leasing_utkopstillagg(self._leasing("finansiell"))

        assert geometrisk == pytest.approx(Decimal("0.037137"), abs=Decimal("0.000001"))
        assert geometrisk < leasing_utkopstillagg(self._leasing("operationell"))

    def test_utan_utkopspris_finns_inget_tillagg(self):
        assert leasing_utkopstillagg(
            _post("leasing", 100000, kostnad="0.04", loptid_ar=5)
        ) == 0

    def test_utan_loptid_finns_inget_tillagg(self):
        assert leasing_utkopstillagg(
            _post("leasing", 100000, kostnad="0.04", utkopspris=Decimal("20000"))
        ) == 0

    def test_icke_leasing_har_aldrig_tillagg(self):
        assert leasing_utkopstillagg(_post("lan", 100000, kostnad="0.05")) == 0

    def test_nollbelopp_ger_inget_tillagg(self):
        # Ett påslag på ingenting är inte en kostnad — och skulle dividera med noll.
        assert leasing_utkopstillagg(self._leasing("operationell", belopp=0)) == 0

    def test_tillagget_laggs_pa_rantan_i_wacc(self):
        wacc = berakna_wacc([self._leasing("operationell")])

        # 4 % leasingränta + 4 % utköpstillägg = 8 % före skatt.
        assert wacc["wacc_fore_skatt"] == pytest.approx(Decimal("0.08"))
        assert wacc["poster"][0]["utkopstillagg"] == pytest.approx(Decimal("0.04"))

    def test_utkopsdelen_far_ingen_skatteskold(self):
        # Utköpet är ett förvärv av en tillgång (K2 p. 10.12), inte en
        # avdragsgill kostnad — bara leasingräntan skyddas.
        wacc = berakna_wacc([self._leasing("operationell")])

        forvantat = Decimal("0.04") * (1 - BOLAGSSKATT) + Decimal("0.04")
        assert wacc["wacc_efter_skatt"] == pytest.approx(forvantat)

    def test_metodvalet_syns_i_wacc(self):
        linjar = berakna_wacc([self._leasing("operationell")])["wacc_fore_skatt"]
        geometrisk = berakna_wacc([self._leasing("finansiell")])["wacc_fore_skatt"]

        assert geometrisk < linjar


class TestForeslagenAvkastningEgetKapital:
    def test_arets_roe_foreslas(self):
        sie = _sie()
        resultat, balans = resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie)
        kvot = foreslagen_avkastning_eget_kapital(resultat, balans)

        assert kvot == pytest.approx(
            resultat["poster"]["arets_resultat"] / balans["poster"]["eget_kapital"]
        )

    def test_negativt_eget_kapital_ger_none(self):
        sie = _sie()
        resultat, balans = resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie)
        balans["poster"]["eget_kapital"] = Decimal("-1")

        assert foreslagen_avkastning_eget_kapital(resultat, balans) is None

    def test_negativt_resultat_ger_none(self):
        # Ett negativt avkastningskrav är inte ett krav.
        sie = _sie()
        resultat, balans = resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie)
        resultat["poster"]["arets_resultat"] = Decimal("-1000")

        assert foreslagen_avkastning_eget_kapital(resultat, balans) is None

    def test_procentformen_avrundas_till_en_decimal(self):
        sie = _sie()
        assert foreslaget_avkastningskrav_procent(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie)
        ) == pytest.approx(18.9)

    def test_procentformen_ar_none_nar_kvoten_ar_none(self):
        sie = _sie()
        resultat, balans = resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie)
        balans["poster"]["eget_kapital"] = Decimal("0")

        assert foreslaget_avkastningskrav_procent(resultat, balans) is None


class TestKapitalstapel:
    """Kapitalstacken som staplade skikt. Ersätter Sankey-diagrammet: varje
    skikt ska kunna läsas utan legend, alltså bära namn, belopp och andel."""

    def _stapel(self):
        return kapitalstapel([
            _post("lan", 100000, namn="Banklån"),
            _post("agarinsats", 60000, namn="Ägarinsats"),
            _post("egna_pengar", 40000, namn="Egna pengar"),
        ])

    def test_ett_skikt_per_kalla(self):
        assert [s["namn"] for s in self._stapel()["skikt"]] == [
            "Banklån", "Ägarinsats", "Egna pengar",
        ]

    def test_skikten_summerar_till_totalen(self):
        data = self._stapel()

        assert sum(s["belopp"] for s in data["skikt"]) == data["total"]
        assert data["total"] == Decimal("200000")

    def test_andelarna_summerar_till_ett(self):
        assert sum(s["andel"] for s in self._stapel()["skikt"]) == Decimal("1")

    def test_etiketten_bar_namn_belopp_och_andel(self):
        etikett = self._stapel()["skikt"][0]["etikett"]

        assert "Banklån" in etikett
        assert formatera_kr(Decimal("100000")) in etikett
        assert formatera_procent(Decimal("0.5")) in etikett

    def test_skikten_kommer_i_lasordning(self):
        # Renderaren vänder listan (Plotly staplar nerifrån) — ordningen här
        # ska matcha formulärets rader, inte ritordningen.
        assert self._stapel()["skikt"][0]["namn"] == "Banklån"

    def test_fargen_foljer_typen(self):
        assert self._stapel()["skikt"][1]["farg"] == KAPITALSTACK_FARG["agarinsats"]

    def test_textfargen_valjs_for_kontrast(self):
        # Samma WCAG-logik som balansstapeln — aldrig hårdkodat vitt.
        for skikt in self._stapel()["skikt"]:
            assert skikt["textfarg"] == text_farg(skikt["farg"])

    def test_tunt_skikt_far_ingen_inline_etikett(self):
        # Hellre ingen etikett än en hoptryckt, oläslig sådan.
        data = kapitalstapel([
            _post("lan", 999000, namn="Stort lån"),
            _post("egna_pengar", 1000, namn="Liten slant"),
        ])

        assert data["skikt"][0]["visa_etikett"] is True
        assert data["skikt"][1]["visa_etikett"] is False

    def test_post_utan_belopp_utelamnas(self):
        data = kapitalstapel([
            _post("egna_pengar", 100, namn="Egna pengar"),
            _post("agarinsats", 0, namn="Ägarinsats"),
        ])

        assert [s["namn"] for s in data["skikt"]] == ["Egna pengar"]

    def test_tom_stack_ger_varning_och_inga_skikt(self):
        data = kapitalstapel([])

        assert data["skikt"] == []
        assert data["varning"] is not None

    def test_tva_lan_skiljs_at_pa_namn(self):
        data = kapitalstapel([
            _post("lan", 100, namn="Banklån"),
            _post("lan", 100, namn="Säljarrevers"),
        ])

        assert [s["namn"] for s in data["skikt"]] == ["Banklån", "Säljarrevers"]


class TestNarrativtabell:
    """Narrativet renderas som HTML — postnamnen kommer från användarens egna
    inmatningar, så ingenting får nå markupen oescapat."""

    def test_varje_rad_blir_tva_celler(self):
        html = narrativtabell_html([("Investering", "200 000 kr"), ("Soliditeten", "sjunker")])

        assert html.count("<tr>") == 3  # rubrikraden i thead + två datarader
        assert html.count("<td") == 4

    def test_etikettkolumnen_far_egen_klass(self):
        html = narrativtabell_html([("Investering", "text")])

        assert '<td class="sie-narrativ-etikett">Investering</td>' in html

    def test_html_i_postnamn_escapas(self):
        html = narrativtabell_html([("<script>alert(1)</script>", "<b>text</b>")])

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<b>text</b>" not in html

    def test_tom_lista_ger_tabell_utan_rader(self):
        html = narrativtabell_html([])

        assert "<tbody></tbody>" in html

    def test_css_ar_scopad_till_narrativtabellen(self):
        for rad in NARRATIV_TABELL_CSS.splitlines():
            if rad.strip().endswith("{") and not rad.strip().startswith(("@", "/*")):
                assert ".sie-narrativ-tabell" in rad

    def test_zebrarandningen_ar_temaneutral(self):
        assert "rgba(255, 255, 255" not in NARRATIV_TABELL_CSS
        assert "rgba(128, 128, 128, 0.08)" in NARRATIV_TABELL_CSS


class TestProcentOchBelopp:
    """Formuläret kan skrivas i procent ELLER i kronor. Beloppet är sanningen;
    procenten räknas fram för display — annars hade motorn behövt två
    kodvägar för samma stack."""

    def test_procentsumma_tar_lista(self):
        assert procentsumma([50, 30, 20]) == 100

    def test_kvot_fran_procent(self):
        assert kvot_fran_procent(2.5) == Decimal("0.025")

    def test_beloppen_summerar_exakt_till_investeringen(self):
        belopp = belopp_fran_procent(Decimal("1000000"), [50, 30, 20])

        assert sum(belopp) == Decimal("1000000")

    def test_avrundningsrest_hamnar_pa_storsta_posten(self):
        # 1/3-delar går inte jämnt ut i ören; ingenting får läcka, annars
        # slår motorns summa-kontroll till på en stack användaren ser som rätt.
        belopp = belopp_fran_procent(Decimal("1000000.01"), [34, 33, 33])

        assert sum(belopp) == Decimal("1000000.01")
        assert belopp[0] == max(belopp)

    def test_procent_raknas_tillbaka_ur_beloppen(self):
        assert procent_fran_belopp(
            Decimal("200000"), [Decimal("100000"), Decimal("60000"), Decimal("40000")]
        ) == [50.0, 30.0, 20.0]

    def test_nollinvestering_ger_nollprocent_inte_division_med_noll(self):
        assert procent_fran_belopp(Decimal("0"), [Decimal("100")]) == [0.0]


def _narrativtext(kalkyl: dict) -> str:
    """Narrativet som en sammanhängande sträng. Raderna är (etikett, text)-par
    sedan tabellrenderingen infördes."""
    return " ".join(f"{etikett} {text}" for etikett, text in kalkyl["narrativ"])


class TestKapitalstackKomposition:
    def _poster(self) -> list:
        return [
            _post("lan", 500000, kostnad="0.05", namn="Långfristiga skulder"),
            _post("agarinsats", 300000, kostnad="0.12", namn="Ägarinsats"),
            _post("egna_pengar", 200000, kostnad="0.02", namn="Egna pengar"),
        ]

    def test_kalkylen_kopplar_ihop_motorns_delar(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie),
            1000000, self._poster(),
        )

        assert kalkyl["wacc"]["wacc_fore_skatt"] == pytest.approx(Decimal("0.065"))
        assert sum(p.belopp for p in kalkyl["poster"]) == Decimal("1000000")
        assert kalkyl["balans_efter"]["poster"]["kontrolldiff"] == 0

    def test_soliditeten_sjunker_nar_investeringen_lanefinansieras(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie),
            1000000, [_post("lan", 1000000, kostnad="0.05")],
        )

        assert kalkyl["nyckeltal_efter"]["soliditet"] < kalkyl["nyckeltal_fore"]["soliditet"]

    def test_narrativet_namner_wacc_och_alla_anvanda_kallor(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie),
            1000000, self._poster(),
        )
        text = _narrativtext(kalkyl)

        assert "WACC" in text
        for kalla in ("långfristiga skulder", "ägarinsats", "egna pengar"):
            assert kalla in text.lower()

    def test_narrativet_forklarar_operationell_leasing_utanfor_balansrakningen(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie), 1000000, [
                _post("lan", 600000, kostnad="0.05"),
                _post("leasing", 400000, kostnad="0.04", leasingmetod="operationell"),
            ],
        )
        text = _narrativtext(kalkyl)

        assert kalkyl["ej_aktiverat_belopp"] == Decimal("400000")
        assert "kostnadsförs" in text
        assert "aldrig i balansräkningen" in text

    def test_narrativet_redovisar_utkopets_arliga_paslag(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie), 100000, [
                _post(
                    "leasing", 100000, kostnad="0.04", namn="Leasing skåpbil",
                    utkopspris=Decimal("20000"), loptid_ar=5,
                    leasingmetod="operationell",
                ),
            ],
        )
        etiketter = [etikett for etikett, _ in kalkyl["narrativ"]]
        text = _narrativtext(kalkyl)

        assert "Utköp: Leasing skåpbil" in etiketter
        assert "linjärt" in text

    def test_samma_forklaring_upprepas_inte_for_tva_lan(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie), 200000, [
                _post("lan", 100000, kostnad="0.03", namn="Banklån"),
                _post("lan", 100000, kostnad="0.09", namn="Säljarrevers"),
            ],
        )

        assert len(kalkyl["narrativ"]) == len(set(kalkyl["narrativ"]))

    def test_nollinvestering_ger_narrativ_utan_pastaenden(self):
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie), 0, [],
        )

        assert kalkyl["narrativ"] == [(
            "Ingen simulering",
            "Siffrorna visar balansräkningen som den ser ut i bokföringen.",
        )]
        assert kalkyl["wacc"]["wacc_efter_skatt"] is None

    def test_narrativet_ar_etikett_textpar_hela_vagen(self):
        # Kontraktet narrativtabell_html litar på.
        sie = _sie()
        kalkyl = kapitalstack(
            resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie),
            1000000, self._poster(),
        )

        assert all(
            isinstance(rad, tuple) and len(rad) == 2 and all(isinstance(d, str) for d in rad)
            for rad in kalkyl["narrativ"]
        )

    def test_stack_som_inte_gar_ihop_avvisas(self):
        sie = _sie()
        with pytest.raises(ValueError):
            kapitalstack(
                resultatrapport_fran_sie(sie), balansrapport_fran_sie(sie), 1000,
                [_post("lan", 500), _post("agarinsats", 300)],
            )


# ---------------------------------------------------------------------------
# Likviditetsprognos: glue (reskontra -> fpa_motor-indata) + Plotly-redo data
# ---------------------------------------------------------------------------

def _sie_med_saldo(*par: tuple[str, str]) -> SIEFil:
    """Minimal SIEFil med bara utgående_balanser satta (årsnr 0), för
    momssaldo_fran_sie — samma minimalistiska konstruktionsmönster som
    _maskeringsresultat/_sie i test_samtalsflode.py."""
    balanser = [
        Saldopost(årsnr=0, kontonr=kontonr, objektreferenser={}, saldo=Decimal(saldo))
        for kontonr, saldo in par
    ]
    return SIEFil(utgående_balanser=balanser)


class TestMomssaldoFranSie:
    def test_foredrar_konto_2650(self):
        sie = _sie_med_saldo(("2650", "-5000"), ("2610", "-1000"))
        assert momssaldo_fran_sie(sie) == Decimal("-5000")

    def test_fallback_summerar_intervallet_2610_2649_om_2650_saknas(self):
        sie = _sie_med_saldo(("2611", "-8000"), ("2640", "3000"))
        assert momssaldo_fran_sie(sie) == Decimal("-5000")

    def test_inget_momskonto_ger_noll(self):
        sie = _sie_med_saldo(("1930", "10000"), ("2440", "-2000"))
        assert momssaldo_fran_sie(sie) == Decimal("0")

    def test_tom_sie_ger_noll(self):
        assert momssaldo_fran_sie(SIEFil()) == Decimal("0")

    def test_bara_innevarande_ar_raknas(self):
        balanser = [
            Saldopost(årsnr=0, kontonr="2650", objektreferenser={}, saldo=Decimal("-100")),
            Saldopost(årsnr=-1, kontonr="2650", objektreferenser={}, saldo=Decimal("-9999")),
        ]
        assert momssaldo_fran_sie(SIEFil(utgående_balanser=balanser)) == Decimal("-100")

    def test_positivt_saldo_ar_fordran(self):
        sie = _sie_med_saldo(("2650", "1200"))
        assert momssaldo_fran_sie(sie) == Decimal("1200")


class TestLikviditetsprognosFranReskontra:
    def test_bygger_giltig_prognos_ur_tvattade_poster(self):
        leverantorer = [
            Leverantorspost(leverantor="3M Sverige AB", belopp=Decimal("-1000.00"),
                             betalstatus="Förfallen", maskerad=False,
                             forfallodatum=date(2026, 1, 10)),
        ]
        kunder = [
            Kundpost(kund="Redovisningsbyrån AB", belopp=Decimal("2000.00"),
                     betalstatus="Obetald", maskerad=False, motpart_id="c1",
                     forfallodatum=date(2026, 1, 15)),
        ]
        prognos = likviditetsprognos_fran_reskontra(
            leverantorer, kunder, Decimal("5000"), date(2026, 1, 1), antal_dagar=30,
        )
        assert prognos["nuvarande_kassa"] == Decimal("5000")
        assert len(prognos["alla_handelser"]) == 2

    def test_motpart_namn_och_motpart_id_gar_igenom(self):
        kunder = [
            Kundpost(kund="Karl Svensson (maskerad)", belopp=Decimal("500.00"),
                     betalstatus="Obetald", maskerad=True, motpart_id="c2",
                     forfallodatum=date(2026, 1, 5)),
        ]
        prognos = likviditetsprognos_fran_reskontra(
            [], kunder, Decimal("0"), date(2026, 1, 1), antal_dagar=10,
        )
        handelse = prognos["alla_handelser"][0]
        assert handelse["motpart"] == "Karl Svensson (maskerad)"
        assert handelse["motpart_id"] == "c2"

    def test_none_listor_tolkas_som_tomma(self):
        # Saknad ea:purchase/ea:sales-behörighet -> None, inte ett fel.
        prognos = likviditetsprognos_fran_reskontra(
            None, None, Decimal("1000"), date(2026, 1, 1), antal_dagar=5,
        )
        assert prognos["alla_handelser"] == []
        assert all(d["utgaende_kassa"] == Decimal("1000") for d in prognos["dagar"])

    def test_kundbetalbeteende_och_varningstroskel_fors_vidare(self):
        kunder = [
            Kundpost(kund="Sen Kund", belopp=Decimal("100.00"), betalstatus="Obetald",
                     maskerad=False, motpart_id="sen", forfallodatum=date(2026, 1, 5)),
        ]
        prognos = likviditetsprognos_fran_reskontra(
            [], kunder, Decimal("1000"), date(2026, 1, 1),
            kundbetalbeteende={"sen": 3}, antal_dagar=10,
            varningströskel=Decimal("500"),
        )
        handelse = prognos["alla_handelser"][0]
        assert handelse["dagar_justering"] == 3
        assert handelse["har_historisk_justering"] is True

    def test_saknat_forfallodatum_ger_motorns_egen_valueerror(self):
        # Post utan forfallodatum (t.ex. handbyggd utan Spiris-adaptern) ska
        # fail-closed:a med SAMMA felmeddelande som fpa_motor redan testar —
        # ingen duplicerad kontroll i glue-funktionen.
        leverantorer = [
            Leverantorspost(leverantor="X", belopp=Decimal("-100.00"),
                             betalstatus="Obetald", maskerad=False),
        ]
        with pytest.raises(ValueError):
            likviditetsprognos_fran_reskontra(
                leverantorer, [], Decimal("1000"), date(2026, 1, 1),
            )

    def test_momssaldo_ger_en_handelse_pa_nasta_forfallodag(self):
        prognos = likviditetsprognos_fran_reskontra(
            [], [], Decimal("10000"), date(2026, 1, 1),
            antal_dagar=30, momssaldo=Decimal("-4000"),
        )
        handelse = prognos["alla_handelser"][0]
        assert handelse["typ"] == "moms"
        assert handelse["belopp_signerat"] == Decimal("-4000")
        assert handelse["forfallodatum"] == date(2026, 1, 12)

    def test_ingen_momssaldo_ger_ingen_momshandelse(self):
        prognos = likviditetsprognos_fran_reskontra(
            [], [], Decimal("1000"), date(2026, 1, 1), antal_dagar=5,
        )
        assert prognos["alla_handelser"] == []

    def test_noll_momssaldo_ger_ingen_momshandelse(self):
        # 0 betyder "inget momskonto har saldo" (se momssaldo_fran_sie) — inte
        # en momshändelse på 0 kr.
        prognos = likviditetsprognos_fran_reskontra(
            [], [], Decimal("1000"), date(2026, 1, 1),
            antal_dagar=5, momssaldo=Decimal("0"),
        )
        assert prognos["alla_handelser"] == []


class TestLikviditetsgrafData:
    def _prognos(self):
        kunder = [
            Kundpost(kund="Sen Kund", belopp=Decimal("100.00"), betalstatus="Obetald",
                     maskerad=False, motpart_id="sen", forfallodatum=date(2026, 1, 5)),
            Kundpost(kund="Punktlig Kund", belopp=Decimal("200.00"), betalstatus="Obetald",
                     maskerad=False, motpart_id="ok", forfallodatum=date(2026, 1, 8)),
        ]
        return likviditetsprognos_fran_reskontra(
            [], kunder, Decimal("1000"), date(2026, 1, 1),
            kundbetalbeteende={"sen": 4}, antal_dagar=15,
        )

    def test_serierna_har_en_post_per_dag(self):
        data = likviditetsgraf_data(self._prognos())
        assert len(data["datum"]) == len(data["kassa"]) == len(data["farg"]) == 15

    def test_farg_speglar_status(self):
        data = likviditetsgraf_data(self._prognos())
        # Ingen dag är negativ i det här scenariot -> alla gröna.
        assert all(f == "#0ca30c" for f in data["farg"])

    def test_sen_kund_overlay_innehaller_bara_den_skiftade_dagen(self):
        data = likviditetsgraf_data(self._prognos())
        # Kunden med justering hamnar dag 5+4=9; den punktliga hamnar dag 8
        # och ska INTE finnas i overlayn.
        assert data["sen_kund_dag_nr"] == [9]

    def test_ingen_sen_kund_ger_tom_overlay(self):
        prognos = likviditetsprognos_fran_reskontra(
            [], [], Decimal("1000"), date(2026, 1, 1), antal_dagar=5,
        )
        data = likviditetsgraf_data(prognos)
        assert data["sen_kund_dag_nr"] == []
        assert data["sen_kund_datum"] == []
        assert data["sen_kund_kassa"] == []

    def test_moms_overlay_innehaller_bara_momsdagen(self):
        prognos = likviditetsprognos_fran_reskontra(
            [], [], Decimal("10000"), date(2026, 1, 1),
            antal_dagar=15, momssaldo=Decimal("-3000"),
        )
        data = likviditetsgraf_data(prognos)
        assert data["moms_dag_nr"] == [12]
        assert data["moms_datum"] == [date(2026, 1, 12)]

    def test_ingen_moms_ger_tom_overlay(self):
        data = likviditetsgraf_data(self._prognos())
        assert data["moms_dag_nr"] == []
        assert data["moms_datum"] == []
        assert data["moms_kassa"] == []


class TestLikviditetsdagarUrPunkter:
    def test_plockar_dag_nr_ur_customdata(self):
        punkter = [{"customdata": [7]}, {"customdata": [12]}]
        assert likviditetsdagar_ur_punkter(punkter) == [7, 12]

    def test_dubbletter_tas_bort_ordning_bevaras(self):
        punkter = [{"customdata": [3]}, {"customdata": [3]}, {"customdata": [1]}]
        assert likviditetsdagar_ur_punkter(punkter) == [3, 1]

    def test_saknad_customdata_ignoreras(self):
        punkter = [{"customdata": None}, {}, {"customdata": [5]}]
        assert likviditetsdagar_ur_punkter(punkter) == [5]

    def test_icke_numerisk_customdata_ignoreras(self):
        punkter = [{"customdata": ["oj"]}, {"customdata": [9]}]
        assert likviditetsdagar_ur_punkter(punkter) == [9]

    def test_tom_punktlista_ger_tom_lista(self):
        assert likviditetsdagar_ur_punkter([]) == []


class TestLikviditetsprognosMedVarningstroskel:
    def _prognos(self):
        leverantorer = [
            Leverantorspost(leverantor="X", belopp=Decimal("-1400.00"),
                             betalstatus="Obetald", maskerad=False,
                             forfallodatum=date(2026, 1, 3)),
        ]
        return likviditetsprognos_fran_reskontra(
            leverantorer, [], Decimal("1000"), date(2026, 1, 1), antal_dagar=5,
        )

    def test_utan_troskel_ar_binart(self):
        prognos = self._prognos()
        # Dag 3: 1000 - 1400 = -400 -> röd. Övriga dagar: 1000 -> grön.
        statusar = {d["dag_nr"]: d["status"] for d in prognos["dagar"]}
        assert statusar[1] == "grön"
        assert statusar[3] == "röd"

    def test_med_troskel_flaggar_lag_positiv_kassa_gul(self):
        prognos = likviditetsprognos_med_varningstroskel(self._prognos(), Decimal("2000"))
        statusar = {d["dag_nr"]: d["status"] for d in prognos["dagar"]}
        assert statusar[1] == "gul"  # 1000 kr, under 2000-tröskeln
        assert statusar[3] == "röd"  # negativ kassa övertrumfar alltid tröskeln

    def test_ror_inte_andra_falt(self):
        original = self._prognos()
        omraknad = likviditetsprognos_med_varningstroskel(original, Decimal("500"))
        assert omraknad["nuvarande_kassa"] == original["nuvarande_kassa"]
        assert omraknad["dagar"][0]["utgaende_kassa"] == original["dagar"][0]["utgaende_kassa"]
        assert omraknad["dagar"][0]["handelser"] == original["dagar"][0]["handelser"]

    def test_none_troskel_ar_no_op(self):
        original = self._prognos()
        omraknad = likviditetsprognos_med_varningstroskel(original, None)
        statusar_original = [d["status"] for d in original["dagar"]]
        statusar_omraknad = [d["status"] for d in omraknad["dagar"]]
        assert statusar_original == statusar_omraknad
