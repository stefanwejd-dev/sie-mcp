"""Regressionssvit — Modul 5: ISA 450-ackumulering.

`ackumulering.py` är fullt implementerad; detta är den verifierade,
gröna testsviten (se ARCHITECTURE.md, avsnittet om Modul 5, för
grundarkitekturen). Bevarar dokumentationen av de tre arkitektbeslut som
kompletterar den ursprungliga arkitekturskissen, eftersom de fortfarande
förklarar VARFÖR koden ser ut som den gör:

1. `härled_riktning_modul4(bedömning, kontoplan)` tar kontoplanen som
   andra argument — riktning härleds från korsningen
   (typ(föreslaget_kontonr), typ(kontonr)), samma princip som Modul 2:s
   (rätt typ, bokförd typ). Saknas föreslaget_kontonr, saknas kontot i
   kontoplanen, eller är någon typ None — fail-closed till "okänd", ingen
   exception.
2. `status == "osäker"` från Modul 4 blir INTE en Felaktighet i v1 — en
   osäker AI-bedömning är inte samma sak som en identifierad felaktighet.
   Exkluderingen är medveten och testas explicit (inte tyst bortfall).
3. `ackumulera(...)` tar `utfallsväsentlighet`/`väsentlighetstal` som
   färdiga Decimal-argument — härleder dem INTE från Modul 1. Modul 5:s
   tester rör bara jämförelselogiken (härledningen är en öppen fråga,
   se ARCHITECTURE.md, avsnittet om Modul 5).

Gränsvärdestolkning (bekräftad): exakt på utfallsväsentlighetsgränsen
eller väsentlighetstalsgränsen räknas som "gul" (mellan), inte
"grön"/"röd" — se TestTroskelstatus:s två gränstester. `status_netto`
bedöms mot `abs(summa_netto)` (samma sektion), så ett stort netto-
underskott väger lika tungt som ett lika stort netto-överskott.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain_model import Konto
from kontotyp_vakt import Kontotypavvikelse
from kontomatchning import Kontobedömning

from ackumulering import (
    AckumuleringsResultat,
    Felaktighet,
    ackumulera,
    bygg_felaktigheter_fran_kontobedomningar,
    bygg_felaktigheter_fran_kontotypavvikelser,
    härled_riktning_modul2,
    härled_riktning_modul4,
)


def _avvikelse(forvantad_typ: str, angiven_typ: str, **overrides) -> Kontotypavvikelse:
    bas = dict(
        kontonr="1234",
        kontonamn="Testkonto",
        angiven_typ=angiven_typ,
        forvantad_typ=forvantad_typ,
        lager=["referensmonster"],
        stod_internmonster=None,
        motivering="Testmotivering",
        saldo=Decimal("1000"),
    )
    bas.update(overrides)
    return Kontotypavvikelse(**bas)


def _bedomning(
    kontonr: str,
    föreslaget_kontonr: str | None,
    status: str = "avvikelse",
    **overrides,
) -> Kontobedömning:
    bas = dict(
        plats="serie=A vernr=1 radindex=0",
        kontonr=kontonr,
        text_analyserad="Testtext",
        status=status,
        belopp=Decimal("500"),
        motivering="Testmotivering",
        föreslaget_kontonr=föreslaget_kontonr,
    )
    bas.update(overrides)
    return Kontobedömning(**bas)


def _konto(kontonr: str, typ: str | None) -> Konto:
    return Konto(kontonr=kontonr, namn=f"Konto {kontonr}", typ=typ, enhet=None, sru_koder=[])


def _felaktighet(belopp: Decimal, riktning: str, källa: str = "modul2_kontotyp") -> Felaktighet:
    return Felaktighet(
        källa=källa,
        belopp=belopp,
        riktning=riktning,
        kontonr="1234",
        kontonamn="Testkonto",
        motivering="Testmotivering",
    )


# ---------------------------------------------------------------------------
# Datamodell
# ---------------------------------------------------------------------------

class TestFelaktighet:
    def test_kan_representera_en_modul2_felaktighet_utan_plats(self):
        felaktighet = Felaktighet(
            källa="modul2_kontotyp",
            belopp=Decimal("15000.00"),
            riktning="över",
            kontonr="2157",
            kontonamn="Ack överavskr anläggningsdjur",
            motivering="Kontot är kodat som T men förväntas vara S.",
        )

        assert felaktighet.källa == "modul2_kontotyp"
        assert felaktighet.belopp == Decimal("15000.00")
        assert isinstance(felaktighet.belopp, Decimal)
        assert felaktighet.riktning == "över"
        assert felaktighet.kontonr == "2157"
        assert felaktighet.kontonamn == "Ack överavskr anläggningsdjur"
        assert felaktighet.motivering == "Kontot är kodat som T men förväntas vara S."
        assert felaktighet.plats is None

    def test_kan_representera_en_modul4_felaktighet_med_plats(self):
        felaktighet = Felaktighet(
            källa="modul4_kontomatchning",
            belopp=Decimal("1200.00"),
            riktning="under",
            kontonr="6110",
            kontonamn="Kontorsmaterial",
            motivering="Texten pekar mot drivmedel, inte kontorsmaterial.",
            plats="serie=A vernr=1 radindex=0",
        )

        assert felaktighet.källa == "modul4_kontomatchning"
        assert felaktighet.plats == "serie=A vernr=1 radindex=0"

    @pytest.mark.parametrize("riktning", ["över", "under", "okänd"])
    def test_accepterar_alla_giltiga_riktningar(self, riktning):
        felaktighet = Felaktighet(
            källa="modul2_kontotyp",
            belopp=Decimal("100"),
            riktning=riktning,
            kontonr="1234",
            kontonamn="Test",
            motivering="Test",
        )

        assert felaktighet.riktning == riktning


# ---------------------------------------------------------------------------
# Riktningshärledning — Modul 2
# ---------------------------------------------------------------------------

class TestRiktningsharledningModul2:
    def test_kostnad_forvantad_men_kodad_som_tillgang_ger_over(self):
        avvikelse = _avvikelse(forvantad_typ="K", angiven_typ="T")
        assert härled_riktning_modul2(avvikelse) == "över"

    def test_tillgang_forvantad_men_kodad_som_kostnad_ger_under(self):
        avvikelse = _avvikelse(forvantad_typ="T", angiven_typ="K")
        assert härled_riktning_modul2(avvikelse) == "under"

    def test_intakt_forvantad_men_kodad_som_skuld_ger_under(self):
        avvikelse = _avvikelse(forvantad_typ="I", angiven_typ="S")
        assert härled_riktning_modul2(avvikelse) == "under"

    def test_skuld_forvantad_men_kodad_som_intakt_ger_over(self):
        avvikelse = _avvikelse(forvantad_typ="S", angiven_typ="I")
        assert härled_riktning_modul2(avvikelse) == "över"

    @pytest.mark.parametrize("forvantad,angiven", [("T", "S"), ("S", "T")])
    def test_tillgang_skuld_korsning_ger_okand(self, forvantad, angiven):
        avvikelse = _avvikelse(forvantad_typ=forvantad, angiven_typ=angiven)
        assert härled_riktning_modul2(avvikelse) == "okänd"

    @pytest.mark.parametrize("forvantad,angiven", [("K", "I"), ("I", "K")])
    def test_kostnad_intakt_korsning_ger_okand(self, forvantad, angiven):
        avvikelse = _avvikelse(forvantad_typ=forvantad, angiven_typ=angiven)
        assert härled_riktning_modul2(avvikelse) == "okänd"


# ---------------------------------------------------------------------------
# Riktningshärledning — Modul 4
# ---------------------------------------------------------------------------

class TestRiktningsharledningModul4:
    def test_kostnad_foreslagen_men_bokford_som_tillgang_ger_over(self):
        kontoplan = {"1234": _konto("1234", "T"), "5678": _konto("5678", "K")}
        bedömning = _bedomning(kontonr="1234", föreslaget_kontonr="5678")

        assert härled_riktning_modul4(bedömning, kontoplan) == "över"

    def test_tillgang_foreslagen_men_bokford_som_kostnad_ger_under(self):
        kontoplan = {"5678": _konto("5678", "K"), "1234": _konto("1234", "T")}
        bedömning = _bedomning(kontonr="5678", föreslaget_kontonr="1234")

        assert härled_riktning_modul4(bedömning, kontoplan) == "under"

    def test_intakt_foreslagen_men_bokford_som_skuld_ger_under(self):
        kontoplan = {"2000": _konto("2000", "S"), "3000": _konto("3000", "I")}
        bedömning = _bedomning(kontonr="2000", föreslaget_kontonr="3000")

        assert härled_riktning_modul4(bedömning, kontoplan) == "under"

    def test_skuld_foreslagen_men_bokford_som_intakt_ger_over(self):
        kontoplan = {"3000": _konto("3000", "I"), "2000": _konto("2000", "S")}
        bedömning = _bedomning(kontonr="3000", föreslaget_kontonr="2000")

        assert härled_riktning_modul4(bedömning, kontoplan) == "över"

    def test_ingen_foreslaget_kontonr_ger_okand(self):
        kontoplan = {"1234": _konto("1234", "T")}
        bedömning = _bedomning(kontonr="1234", föreslaget_kontonr=None)

        assert härled_riktning_modul4(bedömning, kontoplan) == "okänd"

    def test_foreslaget_kontonr_saknas_i_kontoplanen_ger_okand(self):
        kontoplan = {"1234": _konto("1234", "T")}
        bedömning = _bedomning(kontonr="1234", föreslaget_kontonr="9999")

        assert härled_riktning_modul4(bedömning, kontoplan) == "okänd"

    def test_bokford_kontonr_saknas_i_kontoplanen_ger_okand(self):
        kontoplan = {"5678": _konto("5678", "K")}
        bedömning = _bedomning(kontonr="9999", föreslaget_kontonr="5678")

        assert härled_riktning_modul4(bedömning, kontoplan) == "okänd"

    def test_okand_typ_i_kontoplanen_ger_okand_inte_krasch(self):
        """Ett konto kan finnas i kontoplanen utan att #KTYP satts
        (typ=None) — det ska INTE krascha, bara falla tillbaka till
        okänd, samma fail-closed-princip som resten av modulen."""
        kontoplan = {"1234": _konto("1234", None), "5678": _konto("5678", "K")}
        bedömning = _bedomning(kontonr="1234", föreslaget_kontonr="5678")

        assert härled_riktning_modul4(bedömning, kontoplan) == "okänd"

    @pytest.mark.parametrize("forvantad,angiven", [("T", "S"), ("S", "T")])
    def test_tillgang_skuld_korsning_ger_okand(self, forvantad, angiven):
        kontoplan = {"1234": _konto("1234", angiven), "5678": _konto("5678", forvantad)}
        bedömning = _bedomning(kontonr="1234", föreslaget_kontonr="5678")

        assert härled_riktning_modul4(bedömning, kontoplan) == "okänd"


# ---------------------------------------------------------------------------
# Byggning av felaktigheter — Modul 2
# ---------------------------------------------------------------------------

class TestByggFelaktigheterModul2:
    def test_bygger_en_felaktighet_med_saldo_som_belopp(self):
        avvikelser = [
            _avvikelse(
                forvantad_typ="K",
                angiven_typ="T",
                kontonr="5010",
                kontonamn="Testkostnad",
                saldo=Decimal("12345.67"),
            ),
        ]

        felaktigheter = bygg_felaktigheter_fran_kontotypavvikelser(avvikelser)

        assert len(felaktigheter) == 1
        felaktighet = felaktigheter[0]
        assert felaktighet.källa == "modul2_kontotyp"
        assert felaktighet.belopp == Decimal("12345.67")
        assert isinstance(felaktighet.belopp, Decimal)
        assert felaktighet.riktning == "över"
        assert felaktighet.kontonr == "5010"
        assert felaktighet.kontonamn == "Testkostnad"
        assert felaktighet.motivering == "Testmotivering"
        assert felaktighet.plats is None

    def test_flera_avvikelser_ger_flera_felaktigheter(self):
        avvikelser = [
            _avvikelse(forvantad_typ="K", angiven_typ="T", kontonr="A", kontonamn="A"),
            _avvikelse(forvantad_typ="S", angiven_typ="I", kontonr="B", kontonamn="B"),
        ]

        felaktigheter = bygg_felaktigheter_fran_kontotypavvikelser(avvikelser)

        assert len(felaktigheter) == 2

    def test_tom_lista_ger_tom_lista(self):
        assert bygg_felaktigheter_fran_kontotypavvikelser([]) == []


# ---------------------------------------------------------------------------
# Byggning av felaktigheter — Modul 4
# ---------------------------------------------------------------------------

class TestByggFelaktigheterModul4:
    def test_avvikelse_bygger_en_felaktighet_med_belopp_fran_kontobedomningen(self):
        kontoplan = {
            "6110": _konto("6110", "K"),
            "5611": _konto("5611", "K"),
        }
        bedömningar = [
            _bedomning(
                kontonr="6110",
                föreslaget_kontonr="5611",
                status="avvikelse",
                belopp=Decimal("543.21"),
                motivering="Fel konto",
            ),
        ]

        felaktigheter = bygg_felaktigheter_fran_kontobedomningar(bedömningar, kontoplan)

        assert len(felaktigheter) == 1
        felaktighet = felaktigheter[0]
        assert felaktighet.källa == "modul4_kontomatchning"
        assert felaktighet.belopp == Decimal("543.21")
        assert isinstance(felaktighet.belopp, Decimal)
        assert felaktighet.kontonr == "6110"
        assert felaktighet.motivering == "Fel konto"
        assert felaktighet.plats == "serie=A vernr=1 radindex=0"

    def test_matchning_skapar_ingen_felaktighet(self):
        kontoplan = {"6110": _konto("6110", "K")}
        bedömningar = [
            _bedomning(
                kontonr="6110",
                föreslaget_kontonr=None,
                status="matchning",
                motivering=None,
            ),
        ]

        felaktigheter = bygg_felaktigheter_fran_kontobedomningar(bedömningar, kontoplan)

        assert felaktigheter == []

    def test_osaker_bedomning_skapar_INTE_en_felaktighet_i_v1(self):
        """Arkitektbeslut: en osäker AI-bedömning är inte samma sak som
        en identifierad felaktighet — den exkluderas medvetet från
        ackumulatorns felaktighetslista i v1 (kan fortfarande följas upp
        i sin egen granskningsström, bara inte räknas här). Detta test
        dokumenterar exkluderingen explicit, den sker inte tyst."""
        kontoplan = {"6110": _konto("6110", "K")}
        bedömningar = [
            _bedomning(
                kontonr="6110",
                föreslaget_kontonr=None,
                status="osäker",
                motivering="Kan inte avgöra",
            ),
        ]

        felaktigheter = bygg_felaktigheter_fran_kontobedomningar(bedömningar, kontoplan)

        assert felaktigheter == []

    def test_blandad_lista_filtrerar_matchning_och_osaker_behaller_avvikelse(self):
        kontoplan = {"6110": _konto("6110", "K"), "5611": _konto("5611", "K")}
        bedömningar = [
            _bedomning(kontonr="6110", föreslaget_kontonr=None, status="matchning",
                       motivering=None, belopp=Decimal("100")),
            _bedomning(kontonr="6110", föreslaget_kontonr=None, status="osäker",
                       motivering="Oklart", belopp=Decimal("200")),
            _bedomning(kontonr="6110", föreslaget_kontonr="5611", status="avvikelse",
                       motivering="Fel", belopp=Decimal("300")),
        ]

        felaktigheter = bygg_felaktigheter_fran_kontobedomningar(bedömningar, kontoplan)

        assert len(felaktigheter) == 1
        assert felaktigheter[0].belopp == Decimal("300")

    def test_tom_lista_ger_tom_lista(self):
        assert bygg_felaktigheter_fran_kontobedomningar([], {}) == []


# ---------------------------------------------------------------------------
# Ackumulering
# ---------------------------------------------------------------------------

class TestAckumulering:
    def test_brutto_summerar_alla_belopp_oavsett_riktning(self):
        felaktigheter = [
            _felaktighet(Decimal("100"), "över"),
            _felaktighet(Decimal("200"), "under"),
            _felaktighet(Decimal("300"), "okänd"),
        ]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.summa_brutto == Decimal("600")

    def test_netto_lagger_till_over_drar_ifran_under_och_okand_bidrar_med_noll(self):
        felaktigheter = [
            _felaktighet(Decimal("100"), "över"),
            _felaktighet(Decimal("200"), "under"),
            _felaktighet(Decimal("300"), "okänd"),
        ]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.summa_netto == Decimal("-100")

    def test_antal_felaktigheter_raknas_korrekt(self):
        felaktigheter = [
            _felaktighet(Decimal("100"), "över"),
            _felaktighet(Decimal("200"), "okänd"),
        ]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.antal_felaktigheter == 2

    def test_antal_okand_riktning_raknas_korrekt(self):
        felaktigheter = [
            _felaktighet(Decimal("100"), "över"),
            _felaktighet(Decimal("200"), "okänd"),
            _felaktighet(Decimal("300"), "okänd"),
        ]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.antal_okänd_riktning == 2

    def test_felaktighetslistan_foljer_med_ofoerandrad_i_resultatet(self):
        felaktigheter = [_felaktighet(Decimal("100"), "över")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.felaktigheter == felaktigheter

    def test_tom_lista_ger_nollsummor_och_inga_felaktigheter(self):
        resultat = ackumulera(
            [], utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.summa_brutto == Decimal("0")
        assert resultat.summa_netto == Decimal("0")
        assert resultat.antal_felaktigheter == 0
        assert resultat.antal_okänd_riktning == 0
        assert resultat.felaktigheter == []


# ---------------------------------------------------------------------------
# Tröskelstatus
# ---------------------------------------------------------------------------

class TestTroskelstatus:
    def test_brutto_under_utfallsvasentlighet_ger_gron(self):
        felaktigheter = [_felaktighet(Decimal("100"), "okänd")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_brutto == "grön"

    def test_brutto_mellan_trosklarna_ger_gul(self):
        felaktigheter = [_felaktighet(Decimal("1500"), "okänd")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_brutto == "gul"

    def test_brutto_over_vasentlighetstal_ger_rod(self):
        felaktigheter = [_felaktighet(Decimal("2500"), "okänd")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_brutto == "röd"

    def test_netto_under_utfallsvasentlighet_ger_gron(self):
        felaktigheter = [_felaktighet(Decimal("100"), "över")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_netto == "grön"

    def test_netto_mellan_trosklarna_ger_gul(self):
        felaktigheter = [_felaktighet(Decimal("1500"), "över")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_netto == "gul"

    def test_netto_over_vasentlighetstal_ger_rod(self):
        felaktigheter = [_felaktighet(Decimal("2500"), "över")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_netto == "röd"

    def test_stort_netto_understatement_ger_rod_via_absolutbelopp(self):
        """Arkitektbeslut: status_netto bedöms mot |summa_netto|, inte den
        signerade summan — ett stort netto-UNDERskott är lika allvarligt
        som ett lika stort netto-ÖVERskott. summa_netto själv förblir dock
        signerat (negativt här)."""
        felaktigheter = [_felaktighet(Decimal("2500"), "under")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.summa_netto == Decimal("-2500")
        assert resultat.status_netto == "röd"

    def test_netto_och_brutto_kan_ge_olika_status_samtidigt(self):
        """Ett stort över + ett lika stort under ger netto nära noll men
        brutto som är summan av båda beloppen — de två statusarna ska
        kunna skilja sig åt, inte alltid vara låsta till samma värde."""
        felaktigheter = [
            _felaktighet(Decimal("1500"), "över"),
            _felaktighet(Decimal("1500"), "under"),
        ]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.summa_netto == Decimal("0")
        assert resultat.summa_brutto == Decimal("3000")
        assert resultat.status_netto == "grön"
        assert resultat.status_brutto == "röd"

    def test_exakt_pa_utfallsvasentlighetsgransen_ger_gul_inte_gron(self):
        """Gränsdragningsval, ej arkitekturbekräftat (flaggat i
        modulens docstring): 'under' tolkas strikt (<), så en summa
        exakt på utfallsväsentlighetsgränsen räknas som 'mellan', inte
        'under'."""
        felaktigheter = [_felaktighet(Decimal("1000"), "okänd")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_brutto == "gul"

    def test_exakt_pa_vasentlighetstalsgransen_ger_gul_inte_rod(self):
        """Samma gränsdragningsval som ovan, spegelvänt: 'över' tolkas
        strikt (>), så exakt på väsentlighetstalsgränsen är 'mellan'."""
        felaktigheter = [_felaktighet(Decimal("2000"), "okänd")]

        resultat = ackumulera(
            felaktigheter, utfallsväsentlighet=Decimal("1000"), väsentlighetstal=Decimal("2000")
        )

        assert resultat.status_brutto == "gul"
