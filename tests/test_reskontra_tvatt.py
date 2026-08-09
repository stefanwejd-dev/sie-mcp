"""Tester för reskontra_tvatt.py — GDPR-tvättmaskinen för leverantörsreskontra
(Alternativ C).

Ren transformationslogik, inget nätverk: tvättmaskinen tar redan hämtade
reskontrarader (dict:ar) och avgör per leverantör om namnet får passera till
AI-kontexten. Affärsreglerna (bekräftade med användaren):

- Finansiell integritet: INGEN faktura får försvinna — reskontrans summa ska
  alltid matcha huvudboken. len(ut) == len(in), summa belopp bevaras.
- Juridisk person (t.ex. AB): namn + belopp + betalstatus släpps igenom orört.
- Fysisk person (enskild firma, dvs personnummer) ELLER om namnet flaggas
  känsligt: namnet ersätts med "Fiktiv Leverantör N [Maskerad: Ej juridisk
  person]", men belopp och betalstatus behålls intakt.

Juridisk-vs-fysisk avgörs på den kanoniska svenska regeln: 3:e siffran i ett
organisationsnummer är >= 2, i ett personnummer <= 1 (månadens tiotal).
Fail-closed: tomt/ogiltigt/otydbart orgnr maskeras.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from reskontra_tvatt import (
    maskera_for_egress,
    Kundpost,
    Leverantorspost,
    normalisera_spiris_datum,
    tvatta_kundreskontra,
    tvatta_leverantorsreskontra,
)


# --- P0: hämtning + egress som pipeline -------------------------------------
# Maskeringsgränsen flyttades 2026-08-04: tvatta_* KLASSAR numera (sätter
# ska_maskeras) men byter inte namn — det gör maskera_for_egress, vid varje väg
# ut ur datorn. Testerna nedan prövar det SAMLADE utfallet, alltså exakt samma
# beteende som före flytten, så varje befintlig assertion är oförändrad.
# Att klassning och åtgärd hålls isär prövas separat i test_egressgransen.py.


def _lev(*a, **kw):
    return maskera_for_egress(tvatta_leverantorsreskontra(*a, **kw))


def _kund(*a, **kw):
    return maskera_for_egress(tvatta_kundreskontra(*a, **kw))


PSEUDONYM_MARKOR = "[Maskerad: Ej juridisk person]"


def _rad(namn: str, orgnr: str, belopp: str, betalstatus: str = "obetald") -> dict:
    return {"namn": namn, "orgnr": orgnr, "belopp": Decimal(belopp), "betalstatus": betalstatus}


class TestJuridiskPersonSlapperIgenom:
    def test_ab_med_organisationsnummer_behaller_namnet(self):
        # 556677-8899: 3:e siffran = 6 (>= 2) -> juridisk person.
        rader = [_rad("3M Sverige AB", "556677-8899", "1275.00")]

        ut = _lev(rader)

        assert isinstance(ut[0], Leverantorspost)
        assert ut[0].leverantor == "3M Sverige AB"
        assert ut[0].maskerad is False
        assert ut[0].belopp == Decimal("1275.00")
        assert ut[0].betalstatus == "obetald"


class TestFysiskPersonMaskeras:
    def test_enskild_firma_med_personnummer_maskeras(self):
        # 811228-9874: 3:e siffran = 1 (<= 1) -> personnummer -> fysisk person.
        rader = [_rad("Karl Svensson", "811228-9874", "800.00")]

        ut = _lev(rader)

        assert ut[0].maskerad is True
        assert "Karl Svensson" not in ut[0].leverantor
        assert ut[0].leverantor == f"Fiktiv Leverantör 1 {PSEUDONYM_MARKOR}"
        # Belopp och betalstatus är intakta — bara namnet tvättas.
        assert ut[0].belopp == Decimal("800.00")
        assert ut[0].betalstatus == "obetald"

    def test_tomt_orgnr_maskeras_fail_closed(self):
        rader = [_rad("Oklar Leverantör", "", "500.00")]

        ut = _lev(rader)

        assert ut[0].maskerad is True
        assert "Oklar Leverantör" not in ut[0].leverantor

    def test_ogiltigt_orgnr_maskeras_fail_closed(self):
        rader = [_rad("Skräp Leverantör", "sopor", "500.00")]

        ut = _lev(rader)

        assert ut[0].maskerad is True


class TestNamnSignalOverstyr:
    def test_flaggat_namn_maskeras_aven_med_juridiskt_orgnr(self):
        # Org.nr ser juridiskt ut, men den injicerade namnkontrollen flaggar
        # det som känsligt -> maskera ändå (fail-closed).
        rader = [_rad("Karl Svensson", "556677-8899", "800.00")]

        ut = _lev(
            rader, ar_kanslig_namn=lambda namn: "Svensson" in namn
        )

        assert ut[0].maskerad is True
        assert "Karl Svensson" not in ut[0].leverantor


class TestBolagsformSuffix:
    """Beslut A: ett rent svenskt org.nr-filter är för snävt för internationell
    handel. Ett känt bolagsform-suffix (AB, GmbH, Ltd, Inc, A/S, Oy…) räknas
    som juridisk person även utan svenskt org.nr. Fail-closed gäller fortsatt
    för allt som varken har giltigt org.nr eller känt suffix."""

    def test_utlandskt_bolag_med_gmbh_slapper_igenom_utan_orgnr(self):
        ut = _lev([_rad("Bachbinder GmbH", "", "241.00")])
        assert ut[0].maskerad is False
        assert ut[0].leverantor == "Bachbinder GmbH"

    def test_diverse_bolagsformer_slapper_igenom(self):
        for namn in ("Foo AB", "Acme Ltd", "Globex Inc", "Nordic A/S", "Suomi Oy"):
            ut = _lev([_rad(namn, "", "100.00")])
            assert ut[0].maskerad is False, namn

    def test_utan_orgnr_utan_suffix_maskeras_fail_closed(self):
        ut = _lev([_rad("Karl Svensson", "", "100.00")])
        assert ut[0].maskerad is True

    def test_suffix_matchas_som_helt_ord_inte_delstrang(self):
        # "Ab" i "Abrahamsson Bygg" får INTE tolkas som bolagsformen AB.
        ut = _lev([_rad("Abrahamsson Bygg", "", "100.00")])
        assert ut[0].maskerad is True


class TestFinansiellIntegritet:
    def test_ingen_rad_forsvinner_och_summan_bevaras(self):
        rader = [
            _rad("3M Sverige AB", "556677-8899", "1275.00"),
            _rad("Karl Svensson", "811228-9874", "800.00"),
            _rad("Oklar", "", "500.00"),
        ]

        ut = _lev(rader)

        assert len(ut) == len(rader) == 3
        assert sum(p.belopp for p in ut) == Decimal("2575.00")

    def test_belopp_ar_decimal(self):
        ut = _lev([_rad("Karl Svensson", "811228-9874", "800.00")])

        assert isinstance(ut[0].belopp, Decimal)


class TestTvattaKundreskontra:
    """Fas D: samma GDPR-logik som leverantörer (org.nr + bolagsform-suffix),
    men pseudonym 'Fiktiv Kund X' och en extra fail-closed-signal:
    CustomerIsPrivatePerson tvingar maskering även om org.nr ser juridiskt ut."""

    def test_juridisk_kund_slapper_igenom(self):
        ut = _kund([_rad("Redovisningsbyrån AB", "5561234567", "5000.00")])
        assert isinstance(ut[0], Kundpost)
        assert ut[0].kund == "Redovisningsbyrån AB"
        assert ut[0].maskerad is False

    def test_privatperson_via_orgnr_maskeras_till_fiktiv_kund(self):
        ut = _kund([_rad("Anna Andersson", "900101-0017", "1200.00")])
        assert ut[0].maskerad is True
        assert ut[0].kund == "Fiktiv Kund 1 [Maskerad: Ej juridisk person]"
        assert "Anna Andersson" not in ut[0].kund

    def test_privatperson_flagga_tvingar_maskering(self):
        # CustomerIsPrivatePerson=True maskerar även om org.nr ser juridiskt ut.
        rad = {"namn": "Dold Person", "orgnr": "5566778899",
               "belopp": Decimal("100.00"), "betalstatus": "Obetald", "privatperson": True}
        ut = _kund([rad])
        assert ut[0].maskerad is True
        assert "Dold Person" not in ut[0].kund

    def test_belopp_och_status_intakt(self):
        ut = _kund([_rad("Anna Andersson", "900101-0017", "1200.00", "Obetald")])
        assert ut[0].belopp == Decimal("1200.00")
        assert ut[0].betalstatus == "Obetald"

    def test_utlandskt_bolag_med_suffix_slapper_igenom(self):
        ut = _kund([_rad("Globex Inc", "", "900.00")])
        assert ut[0].maskerad is False


class TestStabilPseudonym:
    def test_samma_maskerade_leverantor_far_samma_pseudonym(self):
        # Två fakturor från samma enskilda firma -> samma pseudonym, så AI:t
        # kan resonera "denna leverantör har två obetalda fakturor".
        rader = [
            _rad("Karl Svensson", "811228-9874", "800.00"),
            _rad("Karl Svensson", "811228-9874", "1200.00"),
        ]

        ut = _lev(rader)

        assert ut[0].leverantor == ut[1].leverantor
        assert ut[0].leverantor == f"Fiktiv Leverantör 1 {PSEUDONYM_MARKOR}"

    def test_olika_maskerade_leverantorer_far_olika_nummer(self):
        rader = [
            _rad("Karl Svensson", "811228-9874", "800.00"),
            _rad("Anna Andersson", "900101-0017", "1200.00"),
        ]

        ut = _lev(rader)

        pseudonymer = {p.leverantor for p in ut}
        assert len(pseudonymer) == 2
        assert f"Fiktiv Leverantör 1 {PSEUDONYM_MARKOR}" in pseudonymer
        assert f"Fiktiv Leverantör 2 {PSEUDONYM_MARKOR}" in pseudonymer


# ---------------------------------------------------------------------------
# Genomsläpp av forfallodatum/motpart_id — krävs av
# fpa_motor.bygg_likviditetsprognos, som slår upp kundens betalbeteende via
# motpart_id och bygger sin dag-för-dag-serie av forfallodatum. Ingendera
# rör namnmaskeringen, så de ska passera OFÖRÄNDRADE oavsett om raden
# maskeras eller ej.
# ---------------------------------------------------------------------------

class TestForfallodatumGenomslapp:
    def test_forfallodatum_foljer_med_leverantor(self):
        rad = _rad("3M Sverige AB", "556677-8899", "1275.00")
        rad["forfallodatum"] = date(2026, 8, 15)

        ut = _lev([rad])

        assert ut[0].forfallodatum == date(2026, 8, 15)

    def test_saknat_forfallodatum_ger_none_inte_krasch(self):
        # _tvatta använder .get, inte krav — modulen ska vara testbar med
        # handbyggda rader utan att känna till likviditetsprognosens behov.
        ut = _lev([_rad("3M Sverige AB", "556677-8899", "1275.00")])
        assert ut[0].forfallodatum is None

    def test_forfallodatum_foljer_med_aven_nar_kunden_maskeras(self):
        rad = _rad("Karl Svensson", "811228-9874", "800.00")
        rad["forfallodatum"] = date(2026, 9, 1)

        ut = _kund([rad])

        assert ut[0].maskerad is True
        assert ut[0].forfallodatum == date(2026, 9, 1)


class TestMotpartIdGenomslapp:
    def test_motpart_id_foljer_med_kund(self):
        rad = _rad("Redovisningsbyrån AB", "556123-4567", "5000.00")
        rad["motpart_id"] = "c1"

        ut = _kund([rad])

        assert ut[0].motpart_id == "c1"

    def test_motpart_id_foljer_med_aven_nar_kunden_maskeras(self):
        # Ett opakt internt ID är ingen personuppgift — tvättmaskinen maskerar
        # bara NAMNET, aldrig id:t.
        rad = _rad("Karl Svensson", "811228-9874", "800.00")
        rad["motpart_id"] = "c2"

        ut = _kund([rad])

        assert ut[0].maskerad is True
        assert ut[0].motpart_id == "c2"

    def test_saknat_motpart_id_ger_tom_strang(self):
        ut = _kund([_rad("Redovisningsbyrån AB", "556123-4567", "5000.00")])
        assert ut[0].motpart_id == ""

    def test_ordning_och_langd_bevaras_flera_rader(self):
        # Zip:en mot rå_rader efter position kräver att _tvatta ALDRIG kastar
        # eller byter ordning på raderna — samma invariant som redan testas
        # för namn/belopp i TestFinansiellIntegritet.
        rad1 = _rad("Redovisningsbyrån AB", "556123-4567", "5000.00")
        rad1["motpart_id"] = "c1"
        rad2 = _rad("Karl Svensson", "811228-9874", "1200.00")
        rad2["motpart_id"] = "c2"

        ut = _kund([rad1, rad2])

        assert [p.motpart_id for p in ut] == ["c1", "c2"]


class TestNormaliseraSpirisDatum:
    """Sandbox-verifierat (2026-07-19): samma konceptuella datum kommer i två
    format beroende på Spiris-endpoint — kundfakturors PaymentDate som full
    ISO-datetime, leverantörsfakturors som rent datum. Båda ska normaliseras
    till samma sorts date-objekt."""

    def test_rent_datum(self):
        assert normalisera_spiris_datum("2026-06-24") == date(2026, 6, 24)

    def test_full_iso_datetime_med_z_suffix(self):
        assert normalisera_spiris_datum("2026-06-25T00:00:00Z") == date(2026, 6, 25)

    def test_bada_formaten_ger_samma_resultat_for_samma_dag(self):
        assert normalisera_spiris_datum("2026-01-01") == normalisera_spiris_datum(
            "2026-01-01T00:00:00Z"
        )
