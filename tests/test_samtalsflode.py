"""Tester för samtalsflode.py — orkestrering av den pedagogiska
samtalsytan (Sektion 9).

Fokus: att bygg_saker_kontext ALDRIG läcker rå, omaskerad fritext (raka
motsatsen till vad den ska bevisa: att den bara innehåller redan vetta,
aggregerade fakta), och att ställ_fraga är fail-closed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ackumulering import AckumuleringsResultat, Felaktighet
from analysflode import AnalysResultat
from domain_model import Konto, Saldopost, SIEFil, Tolkningsbehov
from fpa_motor import bygg_likviditetsprognos
from reskontra_tvatt import Kundpost, Leverantorspost
from sekretesslager import Maskeringsresultat
from vasentlighet import Vasentlighetstal

from chatt_klient import AgentSvar, Verktygsanrop
from samtalsflode import (
    FÖRESLAGNA_FRÅGOR,
    SVARSLÄGEN,
    ChattMeddelande,
    bygg_saker_kontext,
    ställ_fraga,
    ställ_fraga_till_agent,
)


def _sie(**overrides) -> SIEFil:
    bas = dict(
        företagsnamn="HemligtBolagsnamn AB",
        orgnr="556677-8899",
        verifikationer=[],
        tolkningsbehov=[
            Tolkningsbehov(
                radnummer=5,
                råtext="#VER hemlig-rå-text-med-Kalle-Karlsson",
                etikett="VER",
                anledning="trasig",
            ),
        ],
    )
    bas.update(overrides)
    return SIEFil(**bas)


def _maskeringsresultat(**overrides) -> Maskeringsresultat:
    bas = dict(
        maskerad_siefil=SIEFil(företagsnamn="BOLAG_1"),
        kodnyckel={},
        maskeringsbehov=[],
        blockerade_verifikationer=set(),
        sandningsbara_verifikationer=[],
        prosa_sandningsbar=None,
    )
    bas.update(overrides)
    return Maskeringsresultat(**bas)


def _analys_resultat(**overrides) -> AnalysResultat:
    bas = dict(
        vasentlighetstal=Vasentlighetstal(
            omsattning=Decimal("1000000"),
            resultat=Decimal("100000"),
            balansomslutning=Decimal("500000"),
            eget_kapital=Decimal("300000"),
        ),
        ackumulering=AckumuleringsResultat(
            summa_netto=Decimal("5000"),
            summa_brutto=Decimal("8000"),
            status_netto="grön",
            status_brutto="gul",
            antal_felaktigheter=1,
            antal_okänd_riktning=0,
            felaktigheter=[
                Felaktighet(
                    källa="modul2_kontotyp",
                    belopp=Decimal("5000"),
                    riktning="över",
                    kontonr="2157",
                    kontonamn="Ack överavskrivning",
                    motivering="Kontot är kodat som T men förväntas vara S.",
                ),
            ],
        ),
        felmeddelande=None,
    )
    bas.update(overrides)
    return AnalysResultat(**bas)


class TestByggSakerKontext:
    def test_lacker_aldrig_ra_foretagsnamn_eller_orgnr(self):
        sie = _sie()
        maskeringsresultat = _maskeringsresultat()

        kontext = bygg_saker_kontext(sie, maskeringsresultat, analys_resultat=None)

        assert "HemligtBolagsnamn AB" not in kontext
        assert "556677-8899" not in kontext

    def test_lacker_aldrig_ra_tolkningsbehov_ratext(self):
        """Kritiskt: sie.tolkningsbehov[].råtext är en obehandlad rad
        direkt från källfilen — helt utanför maskeringslagret. Den får
        aldrig hamna i samtalskontexten."""
        sie = _sie()
        maskeringsresultat = _maskeringsresultat()

        kontext = bygg_saker_kontext(sie, maskeringsresultat, analys_resultat=None)

        assert "Kalle-Karlsson" not in kontext
        assert "hemlig-rå-text" not in kontext

    def test_utan_analys_visar_bara_oversikt(self):
        sie = _sie()
        maskeringsresultat = _maskeringsresultat()

        kontext = bygg_saker_kontext(sie, maskeringsresultat, analys_resultat=None)

        assert "ingen isa 450-analys" in kontext.lower()

    def test_med_analys_innehaller_vasentlighetstal_och_felaktigheter(self):
        sie = _sie()
        maskeringsresultat = _maskeringsresultat()
        analys = _analys_resultat()

        kontext = bygg_saker_kontext(sie, maskeringsresultat, analys)

        assert "1000000" in kontext
        assert "2157" in kontext
        assert "Ack överavskrivning" in kontext

    def test_misslyckad_analys_behandlas_som_ingen_analys(self):
        analys = _analys_resultat(
            vasentlighetstal=None, ackumulering=None, felmeddelande="Något gick fel"
        )

        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), analys)

        assert "2157" not in kontext
        assert "ingen isa 450-analys" in kontext.lower()


class TestKontosaldonIKontext:
    """Alternativ B: aggregerade kontosaldon (kontonr + kontonamn + saldo)
    exponeras i kontexten så chatten kan svara på balansfrågor ('hur stor är
    kassan', 'totala leverantörsskulder'). Fortfarande bara aggregerade
    siffror — inga personnamn, ingen reskontra (den gränsen hör till C)."""

    def _sie_med_saldon(self) -> SIEFil:
        return SIEFil(
            konton={
                "1910": Konto(kontonr="1910", namn="Kassa"),
                "1930": Konto(kontonr="1930", namn="Företagskonto"),
                "2440": Konto(kontonr="2440", namn="Leverantörsskulder"),
                "3041": Konto(kontonr="3041", namn="Försäljning tjänster"),
            },
            utgående_balanser=[
                Saldopost(årsnr=0, kontonr="1910", objektreferenser={}, saldo=Decimal("15000")),
                Saldopost(årsnr=0, kontonr="1930", objektreferenser={}, saldo=Decimal("48000")),
                Saldopost(årsnr=0, kontonr="2440", objektreferenser={}, saldo=Decimal("-12000")),
            ],
            resultat=[
                Saldopost(årsnr=0, kontonr="3041", objektreferenser={}, saldo=Decimal("-27900")),
            ],
        )

    def test_balanskonton_med_namn_och_saldo_finns_i_kontexten(self):
        # Kontonamnen tas ur den MASKERADE kontoplanen (fynd A). I produktion
        # speglar maskerad_siefil.konton alltid sie.konton (maskera_siefil
        # deepcopy:ar) — standardnamn som "Kassa" är oförändrade av maskeringen.
        sie = self._sie_med_saldon()
        kontext = bygg_saker_kontext(
            sie, _maskeringsresultat(maskerad_siefil=sie), analys_resultat=None
        )

        assert "1910" in kontext and "Kassa" in kontext and "15000" in kontext
        assert "2440" in kontext and "Leverantörsskulder" in kontext and "-12000" in kontext

    def test_resultatkonton_finns_ocksa(self):
        sie = self._sie_med_saldon()
        kontext = bygg_saker_kontext(
            sie, _maskeringsresultat(maskerad_siefil=sie), analys_resultat=None
        )

        assert "3041" in kontext and "Försäljning tjänster" in kontext

    def test_utan_saldon_ingen_kontosaldo_sektion(self):
        # Tomt underlag ska inte ge en vilseledande tom rubrik.
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), analys_resultat=None)

        assert "KONTOSALDON" not in kontext


class TestReskontraIKontext:
    """Fas C: den GDPR-tvättade leverantörsreskontran vävs in i kontexten så
    chatten kan svara på 'vilka leverantörsfakturor är obetalda' — med
    juridiska personer i klartext och fysiska personer pseudonymiserade."""

    def _reskontra(self) -> list[Leverantorspost]:
        return [
            Leverantorspost(leverantor="3M Sverige AB", belopp=Decimal("-1275.00"),
                            betalstatus="Förfallen", maskerad=False),
            Leverantorspost(leverantor="Fiktiv Leverantör 1 [Maskerad: Ej juridisk person]",
                            belopp=Decimal("-800.00"), betalstatus="Obetald", maskerad=True),
        ]

    def test_reskontra_finns_i_kontexten(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None, reskontra=self._reskontra())
        assert "LEVERANTÖRSRESKONTRA" in kontext
        assert "3M Sverige AB" in kontext
        assert "1275" in kontext

    def test_maskerat_namn_bevaras_i_kontexten(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None, reskontra=self._reskontra())
        assert "Fiktiv Leverantör 1" in kontext

    def test_utan_reskontra_ingen_sektion(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None)
        assert "LEVERANTÖRSRESKONTRA" not in kontext


class TestKundreskontraIKontext:
    """Fas D: den tvättade kundreskontran vävs in så chatten kan svara på
    'vilka kunder är skyldiga oss pengar' — juridiska kunder i klartext,
    privatpersoner pseudonymiserade."""

    def _kundreskontra(self) -> list[Kundpost]:
        return [
            Kundpost(kund="Redovisningsbyrån AB", belopp=Decimal("5000.00"),
                     betalstatus="Förfallen", maskerad=False),
            Kundpost(kund="Fiktiv Kund 1 [Maskerad: Ej juridisk person]",
                     belopp=Decimal("1200.00"), betalstatus="Obetald", maskerad=True),
        ]

    def test_kundreskontra_finns_i_kontexten(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None,
                                     kundreskontra=self._kundreskontra())
        assert "KUNDRESKONTRA" in kontext
        assert "Redovisningsbyrån AB" in kontext
        assert "5000" in kontext

    def test_maskerat_kundnamn_bevaras(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None,
                                     kundreskontra=self._kundreskontra())
        assert "Fiktiv Kund 1" in kontext

    def test_utan_kundreskontra_ingen_sektion(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None)
        assert "KUNDRESKONTRA" not in kontext


class TestLikviditetsprognosIKontext:
    """Likviditetsprognosen vävs in som en AGGREGERAD sammanfattning (nuvarande
    kassa, lägsta kassa, ev. underskottsvarning, historiskt sena kunder) —
    ALDRIG de ~90 råa dagsraderna, i linje med modulens princip att bara
    skicka redan vetta fakta till AI:t."""

    def _prognos(self, **overrides) -> dict:
        bas = dict(
            nuvarande_kassa=Decimal("10000"),
            prognosdatum=date(2026, 1, 1),
            obetalda_leverantorsfakturor=[],
            obetalda_kundfakturor=[],
            antal_dagar=10,
        )
        bas.update(overrides)
        return bygg_likviditetsprognos(**bas)

    def test_likviditetsprognos_finns_i_kontexten(self):
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=self._prognos(),
        )
        assert "LIKVIDITETSPROGNOS" in kontext
        assert "10000" in kontext

    def test_utan_likviditetsprognos_ingen_sektion(self):
        kontext = bygg_saker_kontext(_sie(), _maskeringsresultat(), None)
        assert "LIKVIDITETSPROGNOS" not in kontext

    def test_underskottsvarning_namns_i_kontexten(self):
        prognos = self._prognos(
            nuvarande_kassa=Decimal("100"),
            obetalda_leverantorsfakturor=[
                {"belopp": Decimal("-500.00"), "forfallodatum": date(2026, 1, 3)}
            ],
        )
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=prognos,
        )
        assert "VARNING" in kontext
        assert "2026-01-03" in kontext

    def test_ingen_varning_nar_kassan_forblir_positiv(self):
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=self._prognos(),
        )
        assert "förbli positiv" in kontext

    def test_historiskt_sen_kund_namns_med_motpart_och_riktning(self):
        prognos = self._prognos(
            obetalda_kundfakturor=[
                {"motpart": "Fiktiv Kund 1 [Maskerad: Ej juridisk person]",
                 "motpart_id": "c1", "belopp": Decimal("500.00"),
                 "forfallodatum": date(2026, 1, 5)},
            ],
            kundbetalbeteende={"c1": 3},
        )
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=prognos,
        )
        assert "Fiktiv Kund 1" in kontext
        assert "3 dagar sent" in kontext

    def test_kund_som_betalar_i_forskott_namns_med_ratt_riktning(self):
        prognos = self._prognos(
            obetalda_kundfakturor=[
                {"motpart": "Punktlig AB", "motpart_id": "c2",
                 "belopp": Decimal("500.00"), "forfallodatum": date(2026, 1, 5)},
            ],
            kundbetalbeteende={"c2": -2},
        )
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=prognos,
        )
        assert "2 dagar i förskott" in kontext

    def test_ingen_sen_kund_rad_utan_historisk_justering(self):
        prognos = self._prognos(
            obetalda_kundfakturor=[
                {"motpart": "Ny Kund", "motpart_id": "c3",
                 "belopp": Decimal("500.00"), "forfallodatum": date(2026, 1, 5)},
            ],
        )
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=prognos,
        )
        assert "brukar betala" not in kontext

    def test_momsbetalning_namns_i_kontexten(self):
        prognos = self._prognos(
            antal_dagar=15,
            momshandelse={"belopp": Decimal("-4000"), "forfallodatum": date(2026, 1, 12)},
        )
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=prognos,
        )
        assert "Moms" in kontext
        assert "betalning" in kontext
        assert "4000" in kontext
        assert "2026-01-12" in kontext

    def test_momsatervinning_namns_med_ratt_riktning(self):
        prognos = self._prognos(
            antal_dagar=15,
            momshandelse={"belopp": Decimal("2500"), "forfallodatum": date(2026, 1, 12)},
        )
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=prognos,
        )
        assert "återbäring" in kontext

    def test_ingen_momsrad_utan_momshandelse(self):
        kontext = bygg_saker_kontext(
            _sie(), _maskeringsresultat(), None, likviditetsprognos=self._prognos(),
        )
        assert "Moms:" not in kontext


class TestStallFraga:
    def test_returnerar_anroparens_svar(self):
        def fejk_anropare(fraga: str, kontext: str) -> str:
            return f"Svar på: {fraga}"

        svar = ställ_fraga("Är bolaget lönsamt?", "kontext", fejk_anropare)

        assert svar == "Svar på: Är bolaget lönsamt?"

    def test_fraga_och_kontext_nar_anroparen(self):
        """fraga ska nå anroparen helt oförändrad — precis vad användaren
        skrev. kontext får (sedan svarsläge infördes) en prependad
        svarsstilsinstruktion, så vi kräver bara att den ursprungliga
        kontextsträngen finns kvar i vad som skickas, inte exakt likhet."""
        mottaget: list[tuple[str, str]] = []

        def fejk_anropare(fraga: str, kontext: str) -> str:
            mottaget.append((fraga, kontext))
            return "svar"

        ställ_fraga("min-fraga", "min-kontext-sträng", fejk_anropare)

        assert len(mottaget) == 1
        mottagen_fraga, mottagen_kontext = mottaget[0]
        assert mottagen_fraga == "min-fraga"
        assert "min-kontext-sträng" in mottagen_kontext

    def test_ovantat_fel_ger_statiskt_svar_inte_ra_exception_text(self):
        def trasig_anropare(fraga: str, kontext: str) -> str:
            raise RuntimeError("hemlig intern detalj som inte får synas")

        svar = ställ_fraga("fråga", "kontext", trasig_anropare)

        assert "hemlig intern detalj" not in svar
        assert isinstance(svar, str) and svar != ""


class TestStallFragaTillAgent:
    """Fas 9/10: samma svarsläge/fail-closed-mönster som ställ_fraga, men
    mot en agent-anropare som tar HELA konversationshistoriken (Fas 10) och
    returnerar AgentSvar i stället för str."""

    def test_returnerar_anroparens_agentsvar(self):
        def fejk_agentanropare(meddelanden: list[dict], kontext: str) -> AgentSvar:
            return AgentSvar(text=f"Svar på: {meddelanden[-1]['text']}")

        meddelanden = [{"roll": "user", "text": "Är bolaget lönsamt?"}]
        svar = ställ_fraga_till_agent(meddelanden, "kontext", fejk_agentanropare)

        assert svar == AgentSvar(text="Svar på: Är bolaget lönsamt?")

    def test_verktygsanrop_nar_anroparen_oforandrat(self):
        förväntat = Verktygsanrop(namn="skapa_kund", indata={"kundnamn": "Lisa Andersson"})

        def fejk_agentanropare(meddelanden: list[dict], kontext: str) -> AgentSvar:
            return AgentSvar(verktygsanrop=förväntat)

        meddelanden = [{"roll": "user", "text": "Skapa kunden Lisa Andersson"}]
        svar = ställ_fraga_till_agent(meddelanden, "kontext", fejk_agentanropare)

        assert svar.verktygsanrop == förväntat

    def test_hela_historiken_och_kontext_nar_anroparen(self):
        mottaget: list[tuple[list[dict], str]] = []

        def fejk_agentanropare(meddelanden: list[dict], kontext: str) -> AgentSvar:
            mottaget.append((meddelanden, kontext))
            return AgentSvar(text="svar")

        historik = [
            {"roll": "user", "text": "min-fraga"},
            {"roll": "assistant", "text": "Vilken fakturatyp?"},
            {"roll": "user", "text": "Byggmoms"},
        ]
        ställ_fraga_till_agent(historik, "min-kontext-sträng", fejk_agentanropare)

        assert len(mottaget) == 1
        mottagen_historik, mottagen_kontext = mottaget[0]
        assert mottagen_historik == historik
        assert "min-kontext-sträng" in mottagen_kontext

    def test_ovantat_fel_ger_statiskt_agentsvar_utan_verktygsanrop(self):
        def trasig_agentanropare(meddelanden: list[dict], kontext: str) -> AgentSvar:
            raise RuntimeError("hemlig intern detalj som inte får synas")

        meddelanden = [{"roll": "user", "text": "fråga"}]
        svar = ställ_fraga_till_agent(meddelanden, "kontext", trasig_agentanropare)

        assert svar.verktygsanrop is None
        assert svar.text is not None and "hemlig intern detalj" not in svar.text


class TestChattMeddelande:
    """Fas 10: ChattMeddelande är den enhetliga byggstenen i app.py:s
    samtal_historik — ETT meddelande, med plats för ett interaktivt
    flerval (alternativ)."""

    def test_standardvarde_har_inga_alternativ(self):
        meddelande = ChattMeddelande(roll="assistant", text="Hej")

        assert meddelande.alternativ is None

    def test_kan_bara_ett_interaktivt_flerval(self):
        meddelande = ChattMeddelande(
            roll="assistant", text="Vilken fakturatyp?",
            alternativ=["Byggmoms", "Juridisk person"],
        )

        assert meddelande.alternativ == ["Byggmoms", "Juridisk person"]

    def test_standardvarde_saknar_strukturerat_svar(self):
        # Fas 11: fältet är opt-in — ett vanligt textsvar renderas precis
        # som förut.
        meddelande = ChattMeddelande(roll="assistant", text="Hej")

        assert meddelande.strukturerat is None

    def test_kan_bara_ett_strukturerat_svar_som_dict(self):
        # Serialiserat (inte Pydantic-objekt): session_state överlever
        # Streamlits rerun bättre med rena dictar, och app.py validerar
        # tillbaka det vid rendering.
        strukturerat = {"block": [{"typ": "text", "innehall": "Hej"}]}

        meddelande = ChattMeddelande(
            roll="assistant", text="Hej", strukturerat=strukturerat
        )

        assert meddelande.strukturerat == strukturerat


class TestSvarslage:
    def test_standard_svarslage_ar_pedagogisk(self):
        assert "pedagogisk" in SVARSLÄGEN

    def test_fraga_forblir_oforandrad_oavsett_svarslage(self):
        mottagna_fragor: list[str] = []

        def fejk_anropare(fraga: str, kontext: str) -> str:
            mottagna_fragor.append(fraga)
            return "svar"

        ställ_fraga("Är bolaget lönsamt?", "kontext", fejk_anropare, svarsläge="kort")

        assert mottagna_fragor == ["Är bolaget lönsamt?"]

    def test_olika_svarslagen_ger_olika_kontext(self):
        mottagna_kontext: list[str] = []

        def fejk_anropare(fraga: str, kontext: str) -> str:
            mottagna_kontext.append(kontext)
            return "svar"

        ställ_fraga("fråga", "bas-kontext", fejk_anropare, svarsläge="kort")
        ställ_fraga("fråga", "bas-kontext", fejk_anropare, svarsläge="analytisk")

        assert mottagna_kontext[0] != mottagna_kontext[1]

    def test_okant_svarslage_faller_tillbaka_till_pedagogisk(self):
        """Fail-closed: ett ogiltigt svarsläge (borde aldrig hända via
        UI:t, som bara erbjuder SVARSLÄGEN) ska falla tillbaka till
        pedagogisk, inte krascha."""
        mottagna_kontext: list[str] = []

        def fejk_anropare(fraga: str, kontext: str) -> str:
            mottagna_kontext.append(kontext)
            return "svar"

        ställ_fraga("fråga", "bas-kontext", fejk_anropare, svarsläge="ogiltigt-läge")
        ställ_fraga("fråga", "bas-kontext", fejk_anropare, svarsläge="pedagogisk")

        assert mottagna_kontext[0] == mottagna_kontext[1]


class TestForeslagnaFragor:
    def test_finns_mellan_fyra_och_sju_fragor(self):
        # Övre gränsen höjd 6->7 för likviditetsprognos-frågan. Knapparna
        # radas i grupper om 3 (se app.py) — sju blir alltså två fulla rader
        # plus en ensam knapp på tredje raden, ett medvetet, litet kosmetiskt
        # pris för att göra prognosen upptäckbar utan att hitta på fler frågor
        # bara för att fylla ut raden.
        assert 4 <= len(FÖRESLAGNA_FRÅGOR) <= 7

    def test_alla_har_icketomt_etikett_och_fraga(self):
        assert all(
            f.etikett.strip() and f.fråga.strip() for f in FÖRESLAGNA_FRÅGOR
        )

    def test_etiketter_ar_kortare_an_fragorna(self):
        """Etiketten är knapptexten — ska vara kort. Frågan är vad som
        faktiskt skickas till AI:t — får vara en fullständig mening."""
        assert all(len(f.etikett) < len(f.fråga) for f in FÖRESLAGNA_FRÅGOR)
