"""Tester för fpa_motor.bygg_likviditetsprognos / berakna_kundbetalbeteende —
dag-för-dag-kassaprognosen. Ren beräkningslogik, inget nätverk, ingen
väggklocka: prognosdatum är alltid ett explicit argument i testerna nedan,
aldrig date.today().
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from fpa_motor import (
    LIKVIDITETSPROGNOS_DAGAR,
    berakna_kundbetalbeteende,
    bygg_likviditetsprognos,
    nasta_momsforfallodag,
)

PROGNOSDATUM = date(2026, 1, 1)


def _leverantorsfaktura(belopp="-1000.00", forfallodatum=None, **overrides) -> dict:
    rad = {
        "fakturanr": "L-1",
        "motpart": "3M Sverige AB",
        "belopp": Decimal(belopp),
        "forfallodatum": forfallodatum or PROGNOSDATUM,
    }
    rad.update(overrides)
    return rad


def _kundfaktura(belopp="1000.00", forfallodatum=None, motpart_id="c1", **overrides) -> dict:
    rad = {
        "fakturanr": "K-1",
        "motpart": "Redovisningsbyrån AB",
        "motpart_id": motpart_id,
        "belopp": Decimal(belopp),
        "forfallodatum": forfallodatum or PROGNOSDATUM,
    }
    rad.update(overrides)
    return rad


class TestGrundlaggandeSerie:
    def test_serien_har_ratt_antal_dagar(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [])
        assert len(resultat["dagar"]) == LIKVIDITETSPROGNOS_DAGAR == 90

    def test_dag_1_ar_prognosdatum(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [])
        assert resultat["dagar"][0]["dag_nr"] == 1
        assert resultat["dagar"][0]["datum"] == PROGNOSDATUM

    def test_sista_dagen_ar_prognosdatum_plus_antal_dagar_minus_1(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [], antal_dagar=5)
        assert len(resultat["dagar"]) == 5
        assert resultat["dagar"][-1]["datum"] == date(2026, 1, 5)

    def test_utan_fakturor_forblir_kassan_oforandrad_varje_dag(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [])
        assert all(d["utgaende_kassa"] == Decimal("10000") for d in resultat["dagar"])
        assert all(d["ingaende_kassa"] == Decimal("10000") for d in resultat["dagar"])
        assert all(d["handelser"] == [] for d in resultat["dagar"])

    def test_anpassat_antal_dagar(self):
        resultat = bygg_likviditetsprognos(
            Decimal("10000"), PROGNOSDATUM, [], [], antal_dagar=30
        )
        assert len(resultat["dagar"]) == 30
        assert resultat["antal_dagar"] == 30

    def test_ickepositivt_antal_dagar_hojer_valueerror(self):
        with pytest.raises(ValueError):
            bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [], antal_dagar=0)


class TestKedjadDagsserie:
    """Varje dags utgående_kassa blir nästa dags ingående — det är själva
    poängen med en dag-för-dag-serie i stället för tre fasta horisonter."""

    def test_utgaende_blir_nasta_dags_ingaende(self):
        leverantor = [_leverantorsfaktura(
            "-500.00", forfallodatum=date(2026, 1, 2)
        )]
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, leverantor, [])

        dag1, dag2, dag3 = resultat["dagar"][0], resultat["dagar"][1], resultat["dagar"][2]
        assert dag1["utgaende_kassa"] == Decimal("10000")
        assert dag2["ingaende_kassa"] == Decimal("10000")
        assert dag2["utgaende_kassa"] == Decimal("9500")
        assert dag3["ingaende_kassa"] == Decimal("9500")

    def test_flera_handelser_samma_dag_ackumuleras(self):
        leverantorer = [
            _leverantorsfaktura("-300.00", forfallodatum=PROGNOSDATUM, fakturanr="L-1"),
            _leverantorsfaktura("-200.00", forfallodatum=PROGNOSDATUM, fakturanr="L-2"),
        ]
        kunder = [_kundfaktura("1000.00", forfallodatum=PROGNOSDATUM, fakturanr="K-1")]

        resultat = bygg_likviditetsprognos(Decimal("5000"), PROGNOSDATUM, leverantorer, kunder)
        dag1 = resultat["dagar"][0]

        assert dag1["leverantorsutbetalningar"] == Decimal("500.00")
        assert dag1["kundinbetalningar"] == Decimal("1000.00")
        assert dag1["netto_forandring"] == Decimal("500.00")
        assert dag1["utgaende_kassa"] == Decimal("5500.00")


class TestTeckenkonvention:
    """Samma RAW SIE-tecken som RemainingAmount/Leverantorspost.belopp/
    Kundpost.belopp redan använder — motorn normaliserar internt, anroparen
    skickar in data oförändrad."""

    def test_leverantorsbelopp_ar_negativt_i_indata_men_minskar_kassan(self):
        leverantor = [_leverantorsfaktura("-750.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert resultat["dagar"][0]["utgaende_kassa"] == Decimal("250.00")

    def test_kundbelopp_ar_positivt_i_indata_och_okar_kassan(self):
        kund = [_kundfaktura("750.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, [], kund)
        assert resultat["dagar"][0]["utgaende_kassa"] == Decimal("1750.00")

    def test_handelsens_belopp_ar_alltid_positiv_magnitud(self):
        leverantor = [_leverantorsfaktura("-750.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        handelse = resultat["dagar"][0]["handelser"][0]
        assert handelse["belopp"] == Decimal("750.00")
        assert handelse["belopp_signerat"] == Decimal("-750.00")

    def test_kundhandelsens_belopp_signerat_ar_positivt(self):
        kund = [_kundfaktura("750.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, [], kund)
        handelse = resultat["dagar"][0]["handelser"][0]
        assert handelse["belopp"] == Decimal("750.00")
        assert handelse["belopp_signerat"] == Decimal("750.00")


class TestForfallnaFakturorKlippsTillDag1:
    def test_redan_forfallen_leverantorsfaktura_hamnar_pa_dag_1(self):
        leverantor = [_leverantorsfaktura(
            "-100.00", forfallodatum=date(2025, 12, 1)  # 31 dagar innan prognosdatum
        )]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert resultat["dagar"][0]["leverantorsutbetalningar"] == Decimal("100.00")

    def test_forfallodatum_lika_med_prognosdatum_hamnar_pa_dag_1(self):
        leverantor = [_leverantorsfaktura("-100.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert resultat["dagar"][0]["leverantorsutbetalningar"] == Decimal("100.00")


class TestUtanforFonstretExkluderasHelt:
    def test_faktura_efter_sista_dagen_utelamnas(self):
        leverantor = [_leverantorsfaktura(
            "-100.00", forfallodatum=date(2026, 1, 1)
        )]
        # 5-dagarsfönster, fakturan förfaller dag 200 (långt utanför).
        sen_faktura = [_leverantorsfaktura(
            "-100.00", forfallodatum=date(2026, 6, 1), fakturanr="L-sen"
        )]
        resultat = bygg_likviditetsprognos(
            Decimal("1000"), PROGNOSDATUM, sen_faktura, [], antal_dagar=5
        )
        assert all(d["leverantorsutbetalningar"] == Decimal("0") for d in resultat["dagar"])
        assert resultat["alla_handelser"] == []

    def test_faktura_pa_exakt_sista_dagen_inkluderas(self):
        sista_dagens_datum = date(2026, 1, 5)
        leverantor = [_leverantorsfaktura("-100.00", forfallodatum=sista_dagens_datum)]
        resultat = bygg_likviditetsprognos(
            Decimal("1000"), PROGNOSDATUM, leverantor, [], antal_dagar=5
        )
        assert resultat["dagar"][-1]["leverantorsutbetalningar"] == Decimal("100.00")


class TestKundbetalbeteendeJustering:
    def test_kund_utan_kand_historik_far_ingen_justering(self):
        kund = [_kundfaktura("500.00", forfallodatum=date(2026, 1, 10), motpart_id="okand")]
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, [], kund)
        handelse = resultat["alla_handelser"][0]
        assert handelse["dagar_justering"] == 0
        assert handelse["justerat_datum"] == date(2026, 1, 10)
        assert handelse["har_historisk_justering"] is False

    def test_kund_som_betalar_sent_skjuter_fram_inbetalningen(self):
        kund = [_kundfaktura("500.00", forfallodatum=date(2026, 1, 10), motpart_id="c1")]
        resultat = bygg_likviditetsprognos(
            Decimal("0"), PROGNOSDATUM, [], kund, kundbetalbeteende={"c1": 3}
        )
        handelse = resultat["alla_handelser"][0]
        assert handelse["justerat_datum"] == date(2026, 1, 13)
        assert handelse["dagar_justering"] == 3
        assert handelse["har_historisk_justering"] is True
        assert handelse["dag_nr"] == 13  # dag 10 + 3 dagars justering

    def test_kund_som_betalar_tidigt_tidigarelagger_inbetalningen(self):
        kund = [_kundfaktura("500.00", forfallodatum=date(2026, 1, 10), motpart_id="c1")]
        resultat = bygg_likviditetsprognos(
            Decimal("0"), PROGNOSDATUM, [], kund, kundbetalbeteende={"c1": -4}
        )
        handelse = resultat["alla_handelser"][0]
        assert handelse["justerat_datum"] == date(2026, 1, 6)
        assert handelse["dagar_justering"] == -4

    def test_leverantorsutbetalning_justeras_aldrig(self):
        # Uppdraget bad bara om justering på kundsidan — leverantörens
        # förfallodatum är alltid det som gäller.
        leverantor = [_leverantorsfaktura("-500.00", forfallodatum=date(2026, 1, 10))]
        resultat = bygg_likviditetsprognos(
            Decimal("0"), PROGNOSDATUM, leverantor, [], kundbetalbeteende={"3M Sverige AB": 30}
        )
        handelse = resultat["alla_handelser"][0]
        assert handelse["justerat_datum"] == date(2026, 1, 10)
        assert handelse["dagar_justering"] == 0

    def test_tom_motpart_id_far_ingen_justering(self):
        kund = [_kundfaktura("500.00", forfallodatum=date(2026, 1, 10), motpart_id="")]
        resultat = bygg_likviditetsprognos(
            Decimal("0"), PROGNOSDATUM, [], kund, kundbetalbeteende={"": 10}
        )
        # "" ska aldrig slå upp mot en eventuell ""-nyckel i profilen.
        assert resultat["alla_handelser"][0]["dagar_justering"] == 0


class TestLagstaKassaOchUnderskott:
    def test_lagsta_kassa_identifieras_ratt(self):
        leverantor = [
            _leverantorsfaktura("-800.00", forfallodatum=date(2026, 1, 5), fakturanr="L-1"),
        ]
        kund = [_kundfaktura("300.00", forfallodatum=date(2026, 1, 10), fakturanr="K-1")]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, kund)

        assert resultat["lagsta_kassa"] == Decimal("200.00")
        assert resultat["lagsta_kassa_datum"] == date(2026, 1, 5)

    def test_ingen_negativ_kassa_ger_none_for_forsta_underskottsdag(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [])
        assert resultat["forsta_dag_med_underskott"] is None
        assert "VARNING" not in resultat["info"]

    def test_forsta_dag_med_underskott_identifieras(self):
        leverantor = [_leverantorsfaktura("-1500.00", forfallodatum=date(2026, 1, 5))]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert resultat["forsta_dag_med_underskott"] == date(2026, 1, 5)
        assert "VARNING" in resultat["info"]

    def test_kassan_forblir_negativ_pa_efterföljande_dagar_utan_ny_inbetalning(self):
        leverantor = [_leverantorsfaktura("-1500.00", forfallodatum=date(2026, 1, 2))]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [], antal_dagar=5)
        assert all(d["utgaende_kassa"] == Decimal("-500.00") for d in resultat["dagar"][1:])


class TestStatusFargkodning:
    def test_positiv_kassa_utan_troskel_ar_gron(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [])
        assert all(d["status"] == "grön" for d in resultat["dagar"])

    def test_negativ_kassa_ar_alltid_rod(self):
        leverantor = [_leverantorsfaktura("-2000.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert resultat["dagar"][0]["status"] == "röd"

    def test_utan_varningstroskel_finns_aldrig_gult(self):
        # Låg men positiv kassa, ingen tröskel given -> binärt grön/röd.
        leverantor = [_leverantorsfaktura("-999.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert resultat["dagar"][0]["status"] == "grön"

    def test_med_varningstroskel_flaggas_lag_positiv_kassa_gul(self):
        leverantor = [_leverantorsfaktura("-999.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(
            Decimal("1000"), PROGNOSDATUM, leverantor, [], varningströskel=Decimal("500")
        )
        assert resultat["dagar"][0]["status"] == "gul"

    def test_med_varningstroskel_kassa_over_troskeln_ar_fortfarande_gron(self):
        resultat = bygg_likviditetsprognos(
            Decimal("10000"), PROGNOSDATUM, [], [], varningströskel=Decimal("500")
        )
        assert resultat["dagar"][0]["status"] == "grön"

    def test_troskel_overtrumfar_aldrig_rott(self):
        leverantor = [_leverantorsfaktura("-2000.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(
            Decimal("1000"), PROGNOSDATUM, leverantor, [], varningströskel=Decimal("50000")
        )
        assert resultat["dagar"][0]["status"] == "röd"


class TestHandelsemetadataForUI:
    """UI:t ska kunna rendera en interaktiv graf och identifiera/färgkoda
    enskilda händelser (t.ex. historiskt sena kunder) utifrån den här
    metadatan utan att räkna om något själv."""

    def test_handelse_id_ar_unik_per_faktura(self):
        leverantorer = [
            _leverantorsfaktura("-100.00", forfallodatum=PROGNOSDATUM, fakturanr="L-1"),
            _leverantorsfaktura("-200.00", forfallodatum=PROGNOSDATUM, fakturanr="L-2"),
        ]
        kunder = [_kundfaktura("300.00", forfallodatum=PROGNOSDATUM, fakturanr="K-1")]
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, leverantorer, kunder)

        ider = [h["handelse_id"] for h in resultat["alla_handelser"]]
        assert len(ider) == len(set(ider)) == 3

    def test_motpart_och_fakturanr_foljer_med_for_forklaring(self):
        leverantor = [_leverantorsfaktura(
            "-100.00", forfallodatum=PROGNOSDATUM, motpart="Acme AB", fakturanr="F-42"
        )]
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, leverantor, [])
        handelse = resultat["alla_handelser"][0]
        assert handelse["motpart"] == "Acme AB"
        assert handelse["fakturanr"] == "F-42"

    def test_typ_skiljer_handelsetyperna(self):
        leverantor = [_leverantorsfaktura("-100.00", forfallodatum=PROGNOSDATUM)]
        kund = [_kundfaktura("100.00", forfallodatum=PROGNOSDATUM)]
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, leverantor, kund)
        typer = {h["typ"] for h in resultat["alla_handelser"]}
        assert typer == {"leverantorsutbetalning", "kundinbetalning"}

    def test_alla_handelser_ar_taggade_med_dag_nr_och_datum(self):
        kund = [_kundfaktura("100.00", forfallodatum=date(2026, 1, 15))]
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, [], kund)
        handelse = resultat["alla_handelser"][0]
        assert handelse["datum"] == date(2026, 1, 15)
        assert handelse["dag_nr"] == 15

    def test_alla_handelser_matchar_dagarnas_egna_handelselistor(self):
        leverantor = [_leverantorsfaktura("-100.00", forfallodatum=date(2026, 1, 3))]
        kund = [_kundfaktura("200.00", forfallodatum=date(2026, 1, 7))]
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, leverantor, kund)

        platta_ider = {h["handelse_id"] for h in resultat["alla_handelser"]}
        nastlade_ider = {
            h["handelse_id"] for dag in resultat["dagar"] for h in dag["handelser"]
        }
        assert platta_ider == nastlade_ider == {"leverantorsfaktura_0", "kundfaktura_0"}

    def test_historiskt_sen_kund_kan_identifieras_via_har_historisk_justering(self):
        kunder = [
            _kundfaktura("100.00", forfallodatum=date(2026, 1, 10),
                         motpart_id="punktlig", fakturanr="K-1"),
            _kundfaktura("200.00", forfallodatum=date(2026, 1, 10),
                         motpart_id="sen-betalare", fakturanr="K-2"),
        ]
        resultat = bygg_likviditetsprognos(
            Decimal("0"), PROGNOSDATUM, [], kunder,
            kundbetalbeteende={"sen-betalare": 5},
        )
        sena = [h for h in resultat["alla_handelser"] if h["har_historisk_justering"]]
        assert len(sena) == 1
        assert sena[0]["fakturanr"] == "K-2"
        assert sena[0]["motpart_id"] == "sen-betalare"


class TestFailClosedValidering:
    def test_leverantorsfaktura_utan_belopp_hojer_valueerror(self):
        trasig = [{"forfallodatum": PROGNOSDATUM}]
        with pytest.raises(ValueError):
            bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, trasig, [])

    def test_leverantorsfaktura_utan_forfallodatum_hojer_valueerror(self):
        trasig = [{"belopp": Decimal("-100.00")}]
        with pytest.raises(ValueError):
            bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, trasig, [])

    def test_kundfaktura_utan_belopp_hojer_valueerror(self):
        trasig = [{"forfallodatum": PROGNOSDATUM, "motpart_id": "c1"}]
        with pytest.raises(ValueError):
            bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, [], trasig)

    def test_kundfaktura_utan_forfallodatum_hojer_valueerror(self):
        trasig = [{"belopp": Decimal("100.00"), "motpart_id": "c1"}]
        with pytest.raises(ValueError):
            bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, [], trasig)

    def test_kundfaktura_utan_motpart_id_hojer_inte(self):
        # Fail-SAFE, inte fail-closed: en okänd motpart är normalt, bara ett
        # missat belopp/förfallodatum är ett datafel.
        giltig = [_kundfaktura("100.00", forfallodatum=PROGNOSDATUM)]
        giltig[0].pop("motpart_id")
        resultat = bygg_likviditetsprognos(Decimal("0"), PROGNOSDATUM, [], giltig)
        assert resultat["alla_handelser"][0]["dagar_justering"] == 0


class TestInfoText:
    def test_info_namner_inget_underskott_nar_allt_ar_grönt(self):
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [])
        assert "VARNING" not in resultat["info"]

    def test_info_namner_datumet_for_forsta_underskottet(self):
        leverantor = [_leverantorsfaktura("-1500.00", forfallodatum=date(2026, 1, 20))]
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, leverantor, [])
        assert "2026-01-20" in resultat["info"]


class TestBeraknaKundbetalbeteende:
    def test_snitt_dagar_forsent_raknas_ratt(self):
        historik = [
            {"motpart_id": "c1", "forfallodatum": date(2026, 1, 1), "betaldatum": date(2026, 1, 4)},
            {"motpart_id": "c1", "forfallodatum": date(2026, 1, 1), "betaldatum": date(2026, 1, 2)},
        ]
        profil = berakna_kundbetalbeteende(historik)
        assert profil["c1"] == Decimal(2)  # (3 + 1) / 2 = 2

    def test_betalar_i_forskott_ger_negativt_snitt(self):
        historik = [
            {"motpart_id": "c1", "forfallodatum": date(2026, 1, 10), "betaldatum": date(2026, 1, 6)},
        ]
        profil = berakna_kundbetalbeteende(historik)
        assert profil["c1"] == Decimal(-4)

    def test_flera_kunder_far_egna_profiler(self):
        historik = [
            {"motpart_id": "c1", "forfallodatum": date(2026, 1, 1), "betaldatum": date(2026, 1, 4)},
            {"motpart_id": "c2", "forfallodatum": date(2026, 1, 1), "betaldatum": date(2026, 1, 1)},
        ]
        profil = berakna_kundbetalbeteende(historik)
        assert profil == {"c1": Decimal(3), "c2": Decimal(0)}

    def test_rad_utan_motpart_id_hoppas_over(self):
        historik = [{"forfallodatum": date(2026, 1, 1), "betaldatum": date(2026, 1, 4)}]
        assert berakna_kundbetalbeteende(historik) == {}

    def test_rad_med_motpart_id_men_utan_datum_hojer_valueerror(self):
        historik = [{"motpart_id": "c1"}]
        with pytest.raises(ValueError):
            berakna_kundbetalbeteende(historik)

    def test_tom_historik_ger_tom_profil(self):
        assert berakna_kundbetalbeteende([]) == {}

    def test_profilen_kan_matas_direkt_in_i_likviditetsprognosen(self):
        historik = [
            {"motpart_id": "c1", "forfallodatum": date(2025, 12, 1), "betaldatum": date(2025, 12, 4)},
        ]
        profil = berakna_kundbetalbeteende(historik)
        kund = [_kundfaktura("500.00", forfallodatum=date(2026, 1, 10), motpart_id="c1")]

        resultat = bygg_likviditetsprognos(
            Decimal("0"), PROGNOSDATUM, [], kund, kundbetalbeteende=profil
        )

        handelse = resultat["alla_handelser"][0]
        assert handelse["justerat_datum"] == date(2026, 1, 13)


class TestNastaMomsforfallodag:
    def test_fore_den_12e_ger_denna_manads_12e(self):
        assert nasta_momsforfallodag(date(2026, 1, 5)) == date(2026, 1, 12)

    def test_pa_den_12e_ger_samma_dag(self):
        # Redan förfallet-klippningen i bygg_likviditetsprognos hanterar
        # "idag" som dag 1 — konsekvent att förfallodagen INTE hoppar över
        # den dag den precis inträffar.
        assert nasta_momsforfallodag(date(2026, 1, 12)) == date(2026, 1, 12)

    def test_efter_den_12e_ger_nasta_manads_12e(self):
        assert nasta_momsforfallodag(date(2026, 1, 13)) == date(2026, 2, 12)

    def test_rullar_over_arsskifte(self):
        assert nasta_momsforfallodag(date(2026, 12, 20)) == date(2027, 1, 12)

    def test_anpassningsbar_dag_i_manaden(self):
        assert nasta_momsforfallodag(date(2026, 1, 1), dag_i_manaden=26) == date(2026, 1, 26)


class TestMomshandelseILikviditetsprognosen:
    def test_ingen_momshandelse_ger_noll_moms_forandring(self):
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, [], [])
        assert all(dag["moms_forandring"] == Decimal("0") for dag in resultat["dagar"])
        assert resultat["alla_handelser"] == []

    def test_skuld_negativt_belopp_ger_utbetalning(self):
        moms = {"belopp": Decimal("-5000"), "forfallodatum": date(2026, 1, 12)}
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [], momshandelse=moms)

        dag = resultat["dagar"][11]  # dag_nr 12 = index 11 (dag_nr 1 == PROGNOSDATUM)
        assert dag["moms_forandring"] == Decimal("-5000")
        assert dag["utgaende_kassa"] == Decimal("5000")

    def test_fordran_positivt_belopp_ger_inbetalning(self):
        moms = {"belopp": Decimal("3000"), "forfallodatum": date(2026, 1, 12)}
        resultat = bygg_likviditetsprognos(Decimal("1000"), PROGNOSDATUM, [], [], momshandelse=moms)

        dag = resultat["dagar"][11]
        assert dag["moms_forandring"] == Decimal("3000")
        assert dag["utgaende_kassa"] == Decimal("4000")

    def test_handelsemetadata(self):
        moms = {"belopp": Decimal("-5000"), "forfallodatum": date(2026, 1, 12)}
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [], momshandelse=moms)

        handelse = resultat["alla_handelser"][0]
        assert handelse["typ"] == "moms"
        assert handelse["motpart"] == "Skatteverket"
        assert handelse["belopp"] == Decimal("5000")
        assert handelse["belopp_signerat"] == Decimal("-5000")
        assert handelse["har_historisk_justering"] is False

    def test_redan_forfallen_momshandelse_klipps_till_dag_1(self):
        moms = {"belopp": Decimal("-1000"), "forfallodatum": date(2025, 12, 1)}
        resultat = bygg_likviditetsprognos(Decimal("5000"), PROGNOSDATUM, [], [], momshandelse=moms)

        assert resultat["dagar"][0]["moms_forandring"] == Decimal("-1000")

    def test_momshandelse_utanfor_fonstret_exkluderas(self):
        moms = {"belopp": Decimal("-1000"), "forfallodatum": date(2026, 4, 15)}
        resultat = bygg_likviditetsprognos(
            Decimal("5000"), PROGNOSDATUM, [], [], antal_dagar=30, momshandelse=moms
        )

        assert resultat["alla_handelser"] == []
        assert all(dag["moms_forandring"] == Decimal("0") for dag in resultat["dagar"])

    def test_saknade_faltet_hojer_valueerror(self):
        with pytest.raises(ValueError):
            bygg_likviditetsprognos(
                Decimal("1000"), PROGNOSDATUM, [], [], momshandelse={"belopp": Decimal("-1")}
            )

    def test_moms_paverkar_lagsta_kassa(self):
        moms = {"belopp": Decimal("-8000"), "forfallodatum": date(2026, 1, 12)}
        resultat = bygg_likviditetsprognos(Decimal("10000"), PROGNOSDATUM, [], [], momshandelse=moms)

        assert resultat["lagsta_kassa"] == Decimal("2000")
        assert resultat["lagsta_kassa_datum"] == date(2026, 1, 12)
