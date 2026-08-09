"""Tester för app_vy.py — visningslogik för Streamlit-appens första steg
(DEL A). Ren transformation, ingen Streamlit-import här och därför fullt
testbar utan UI-runtime.
"""

from __future__ import annotations
from dataclasses import replace

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ackumulering import AckumuleringsResultat
from domain_model import SIEFil, Tolkningsbehov, Transaktion, Verifikation
from sekretesslager import Maskeringsbehov, Maskeringsresultat

from app_vy import (
    BESLUT_AVVAKTA,
    BESLUT_INGEN_MASKERING,
    BESLUT_MASKERA,
    Fakturaradsforslag,
    Kundkandidat,
    KundutkastForslag,
    Valfraga,
    bygg_fakturautkast,
    bygg_ny_kund_payload,
    bygg_granskade_behov,
    bygg_granskade_behov_per_namn,
    bygg_oversikt,
    bygg_risksammanfattning,
    fakturarader_for_betalning,
    kontering_fran_utkast,
    läs_och_maskera_fil,
    markera_kanslig_text,
    maskera_inlast_siefil,
    maskeringsbehov_till_visningsrad,
    nyckel_for_behov,
    tillampa_kontonr_andringar,
    tillämpa_liggare,
    namn_att_undanta,
    obeslutade_behov,
    sok_lika_kunder,
    tolka_fakturaverktygsanrop,
    tolka_kundverktygsanrop,
    tolka_valverktygsanrop,
    unika_namn_behov,
    verifikation_till_visningsrad,
)

_EXEMPELFIL = Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"


def _verifikation(serie="A", vernr="1", vertext="Test", antal_trans=2) -> Verifikation:
    return Verifikation(
        serie=serie,
        vernr=vernr,
        verdatum=date(2025, 1, 1),
        vertext=vertext,
        transaktioner=[
            Transaktion(kontonr="1930", belopp=Decimal("100")) for _ in range(antal_trans)
        ],
    )


def _maskeringsresultat(
    maskeringsbehov=None,
    sandningsbara=None,
    blockerade=None,
    prosa_sandningsbar=None,
) -> Maskeringsresultat:
    return Maskeringsresultat(
        maskerad_siefil=SIEFil(),
        kodnyckel={},
        maskeringsbehov=maskeringsbehov or [],
        blockerade_verifikationer=blockerade or set(),
        sandningsbara_verifikationer=sandningsbara or [],
        prosa_sandningsbar=prosa_sandningsbar,
    )


class TestByggOversikt:
    def test_rakningar_speglar_indata_korrekt(self):
        sie = SIEFil(
            verifikationer=[_verifikation(), _verifikation()],
            tolkningsbehov=[
                Tolkningsbehov(radnummer=5, råtext="#VER x", etikett="VER", anledning="trasig"),
            ],
        )
        resultat = _maskeringsresultat(
            maskeringsbehov=[
                Maskeringsbehov(
                    plats="serie=A vernr=1",
                    fältnamn="vertext",
                    misstänkt_text="Erik Svensson",
                    träffkälla="namnmönster",
                    status="väntar_granskning",
                ),
            ],
            sandningsbara=[_verifikation()],
            blockerade={("A", "1")},
            prosa_sandningsbar="Maskerad text",
        )

        översikt = bygg_oversikt(sie, resultat)

        assert översikt.antal_verifikationer == 2
        assert översikt.antal_tolkningsbehov == 1
        assert översikt.antal_maskeringsbehov == 1
        assert översikt.antal_sandningsbara_verifikationer == 1
        assert översikt.antal_blockerade_verifikationer == 1

    def test_tom_indata_ger_nollor(self):
        sie = SIEFil()
        resultat = _maskeringsresultat()

        översikt = bygg_oversikt(sie, resultat)

        assert översikt.antal_verifikationer == 0
        assert översikt.antal_tolkningsbehov == 0
        assert översikt.antal_maskeringsbehov == 0
        assert översikt.antal_sandningsbara_verifikationer == 0
        assert översikt.antal_blockerade_verifikationer == 0


class TestProsaSandningsbarMappning:
    def test_maskerad_prosa_text_ger_ja(self):
        sie = SIEFil()
        resultat = _maskeringsresultat(prosa_sandningsbar="Årsredovisning för BOLAG_1")

        översikt = bygg_oversikt(sie, resultat)

        assert översikt.prosa_sandningsbar == "ja"

    def test_none_ger_nej(self):
        """None täcker både 'blockerad av olöst prosa-maskeringsbehov' och
        'ingen prosa fanns alls' — sekretesslager.py:s eget kontrakt
        (_prosa_sandningsbar) skiljer inte mellan de två fallen. Vylagret
        gör det konservativa valet: visa 'nej' i båda, hellre än att gissa
        en tredje betydelse som inte finns i källan."""
        sie = SIEFil()
        resultat = _maskeringsresultat(prosa_sandningsbar=None)

        översikt = bygg_oversikt(sie, resultat)

        assert översikt.prosa_sandningsbar == "nej"


class TestMaskeringsbehovVisningsrad:
    def test_mappar_alla_falt(self):
        behov = Maskeringsbehov(
            plats="serie=A vernr=1",
            fältnamn="vertext",
            misstänkt_text="Erik Svensson",
            träffkälla="namnmönster",
            status="väntar_granskning",
        )

        rad = maskeringsbehov_till_visningsrad(behov)

        assert rad["Plats"] == "serie=A vernr=1"
        assert rad["Fältnamn"] == "vertext"
        assert rad["Misstänkt text"] == "Erik Svensson"
        assert rad["Träffkälla"] == "namnmönster"
        assert rad["Status"] == "väntar_granskning"


class TestVerifikationVisningsrad:
    def test_mappar_alla_falt_inklusive_antal_transaktioner(self):
        verifikation = _verifikation(serie="A", vernr="42", vertext="Inköp", antal_trans=3)

        rad = verifikation_till_visningsrad(verifikation)

        assert rad["Serie"] == "A"
        assert rad["Vernr"] == "42"
        assert rad["Vertext"] == "Inköp"
        assert rad["Antal transaktioner"] == 3


def _ackumulering(status_netto="grön", status_brutto="grön", **overrides) -> AckumuleringsResultat:
    bas = dict(
        summa_netto=Decimal("0"),
        summa_brutto=Decimal("0"),
        status_netto=status_netto,
        status_brutto=status_brutto,
        antal_felaktigheter=0,
        antal_okänd_riktning=0,
        felaktigheter=[],
    )
    bas.update(overrides)
    return AckumuleringsResultat(**bas)


class TestByggRisksammanfattning:
    def test_alla_grona_ger_ser_rimligt_ut(self):
        resultat = bygg_risksammanfattning(_ackumulering("grön", "grön"))

        assert resultat.etikett == "Ser rimligt ut"
        assert resultat.emoji_netto == "🟢"
        assert resultat.emoji_brutto == "🟢"

    def test_nagon_rod_ger_kraver_uppmarksamhet(self):
        resultat = bygg_risksammanfattning(_ackumulering("grön", "röd"))

        assert resultat.etikett == "Kräver uppmärksamhet"
        assert resultat.emoji_netto == "🟢"
        assert resultat.emoji_brutto == "🔴"

    def test_nagon_gul_utan_rod_ger_bor_granskas(self):
        resultat = bygg_risksammanfattning(_ackumulering("grön", "gul"))

        assert resultat.etikett == "Bör granskas"
        assert resultat.emoji_brutto == "🟡"

    def test_rod_vager_tyngre_an_gul(self):
        resultat = bygg_risksammanfattning(_ackumulering("gul", "röd"))

        assert resultat.etikett == "Kräver uppmärksamhet"


class TestLasOchMaskeraFil:
    def test_lyckad_inlasning_ger_sie_och_maskeringsresultat_utan_felmeddelande(self):
        resultat = läs_och_maskera_fil(_EXEMPELFIL)

        assert resultat.sie is not None
        assert resultat.maskeringsresultat is not None
        assert resultat.felmeddelande is None
        assert len(resultat.sie.verifikationer) > 0

    def test_saknad_fil_ger_statiskt_felmeddelande_inte_ra_exception_text(self):
        """Fail-closed, samma policy som ai_konfiguration.py:s
        ModellhämtningsFel: den råa exception-texten (som här skulle
        avslöja hela filsökvägen) får ALDRIG nå felmeddelande-fältet —
        bara ett statiskt, generiskt meddelande."""
        saknad_sökväg = "C:/finns-inte/hemlig-mapp-som-inte-ska-lacka/spokfil.se"

        resultat = läs_och_maskera_fil(saknad_sökväg)

        assert resultat.sie is None
        assert resultat.maskeringsresultat is None
        assert resultat.felmeddelande is not None
        assert saknad_sökväg not in resultat.felmeddelande
        assert "hemlig-mapp" not in resultat.felmeddelande


class TestMaskeraInlastSiefil:
    """maskera_inlast_siefil kör en redan inläst SIEFil (t.ex. hämtad från
    Spiris) genom sekretesslagret med SAMMA fail-closed-policy och
    InläsningsResultat-kontrakt som läs_och_maskera_fil — så app.py kan
    behandla Spiris-data exakt som en filuppladdning nedströms."""

    def test_giltig_siefil_ger_maskeringsresultat_utan_felmeddelande(self):
        sie = SIEFil(företagsnamn="X Sandbox", verifikationer=[_verifikation()])

        resultat = maskera_inlast_siefil(sie)

        assert resultat.sie is sie
        assert resultat.maskeringsresultat is not None
        assert resultat.felmeddelande is None

    def test_fel_i_maskeringen_ger_statiskt_felmeddelande_inte_krasch(self):
        # Fail-closed: går maskeringen fel (här: ogiltig indata som får
        # maskera_siefil att kasta) returneras ett statiskt meddelande,
        # aldrig rå exception-text — samma policy som läs_och_maskera_fil.
        resultat = maskera_inlast_siefil(None)

        assert resultat.sie is None
        assert resultat.maskeringsresultat is None
        assert resultat.felmeddelande is not None


def _behov(
    plats="serie=A vernr=4",
    fältnamn="vertext",
    misstänkt_text="Karl Svensson",
    träffkälla="regex_fallback",
    status="väntar_granskning",
) -> Maskeringsbehov:
    return Maskeringsbehov(
        plats=plats,
        fältnamn=fältnamn,
        misstänkt_text=misstänkt_text,
        träffkälla=träffkälla,
        status=status,
    )


class TestMarkeraKansligText:
    """markera_kanslig_text markerar den känsliga delsträngen grafiskt i
    originaltexten (för Sektion 4:s förhandsvisning av vad som ska maskeras)
    utan att förvanska resten av texten. Ren funktion, testbar utan Streamlit."""

    def test_kansligt_ord_markeras_visuellt(self):
        resultat = markera_kanslig_text("Kundfaktura till Karl Svensson", "Karl Svensson")

        # Ordet finns kvar men inramat med en visuell markör (överstrykning).
        assert "Karl Svensson" in resultat
        assert "<span" in resultat
        assert "line-through" in resultat

    def test_omgivande_text_ror_inte(self):
        resultat = markera_kanslig_text("Kundfaktura till Karl Svensson", "Karl Svensson")

        assert resultat.startswith("Kundfaktura till ")

    def test_saknad_delstrang_ger_texten_oforandrad(self):
        text = "Leverantörsfaktura utan känsligt namn"
        assert markera_kanslig_text(text, "Karl Svensson") == text

    def test_tomt_kansligt_ord_markerar_ingenting(self):
        # Tomt/saknat känsligt ord får INTE rama in hela texten.
        text = "Kundfaktura till Karl Svensson"
        assert markera_kanslig_text(text, "") == text


class TestByggGranskadeBehov:
    """bygg_granskade_behov omvandlar UI-besluten (maskera ja/nej + ev. manuellt
    överskriven text) till Maskeringsbehov med rätt status/misstänkt_text, redo
    att matas till sekretesslager.uppdatera_efter_granskning."""

    def test_maskera_ja_ger_bekraftad_pii(self):
        behov = _behov()
        beslut = {nyckel_for_behov(behov, 0): {"maskera": True, "text": "Karl Svensson"}}

        ut = bygg_granskade_behov([behov], beslut)

        assert ut[0].status == "bekräftad_pii"
        assert ut[0].misstänkt_text == "Karl Svensson"

    def test_maskera_nej_ger_godkand_ej_pii(self):
        behov = _behov()
        beslut = {nyckel_for_behov(behov, 0): {"maskera": False, "text": "Karl Svensson"}}

        ut = bygg_granskade_behov([behov], beslut)

        assert ut[0].status == "godkänd_ej_pii"

    def test_manuell_overskrivning_hamnar_i_ersattningstext(self):
        """Användaren rättar AI:ts bedömning till bara förnamnet.

        Överskrivningen hamnar i ersättningstext och misstänkt_text lämnas
        ORÖRD — den senare är radens identitet när sekretesslagret väver
        tillbaka besluten i behovslistan (_sla_ihop_granskade). Skrevs
        misstänkt_text över kunde raden inte längre matchas mot sitt original,
        och blockeringen hävdes aldrig."""
        behov = _behov(misstänkt_text="Karl Svensson")
        beslut = {nyckel_for_behov(behov, 0): {"maskera": True, "text": "Karl"}}

        ut = bygg_granskade_behov([behov], beslut)

        assert ut[0].ersättningstext == "Karl"
        assert ut[0].misstänkt_text == "Karl Svensson"

    def test_oforandrad_text_ger_ingen_ersattningstext(self):
        # Rör användaren inte textfältet ska ingen överskrivning registreras.
        behov = _behov(misstänkt_text="Karl Svensson")
        beslut = {nyckel_for_behov(behov, 0): {"maskera": True, "text": "Karl Svensson"}}

        ut = bygg_granskade_behov([behov], beslut)

        assert ut[0].ersättningstext is None

    def test_saknat_beslut_defaultar_till_maskera_fail_closed(self):
        # Inget beslut för raden (t.ex. state hann inte sättas) -> maskera,
        # aldrig släppa igenom oavsiktligt.
        behov = _behov()

        ut = bygg_granskade_behov([behov], beslut={})

        assert ut[0].status == "bekräftad_pii"
        assert ut[0].misstänkt_text == "Karl Svensson"

    def test_alla_behov_kommer_med(self):
        behov_lista = [_behov(misstänkt_text="Karl Svensson"), _behov(plats="serie=A vernr=5", misstänkt_text="Anna Ek")]

        ut = bygg_granskade_behov(behov_lista, beslut={})

        assert len(ut) == len(behov_lista) == 2

    def test_identiska_behov_far_unika_nycklar_och_egna_beslut(self):
        # Regression: samma känsliga text på flera rader i samma verifikation
        # (identisk plats/fält/misstänkt_text) gav förr KROCKANDE nycklar ->
        # Streamlit-widgetkrasch. Index i nyckeln gör varje rad unik och
        # individuellt beslutbar.
        behov_lista = [_behov(), _behov()]  # helt identiska
        assert nyckel_for_behov(behov_lista[0], 0) != nyckel_for_behov(behov_lista[1], 1)

        beslut = {
            nyckel_for_behov(behov_lista[0], 0): {"maskera": True, "text": "Karl Svensson"},
            nyckel_for_behov(behov_lista[1], 1): {"maskera": False, "text": "Karl Svensson"},
        }
        ut = bygg_granskade_behov(behov_lista, beslut)

        assert ut[0].status == "bekräftad_pii"
        assert ut[1].status == "godkänd_ej_pii"


def _namnbehov(text, plats="serie=A vernr=1", fältnamn="vertext") -> Maskeringsbehov:
    return Maskeringsbehov(
        plats=plats, fältnamn=fältnamn, misstänkt_text=text,
        träffkälla="regex_fallback", status="väntar_granskning",
    )


class TestTillämpaLiggare:
    """Pre-pass: global sök-och-ersätt av kända namn -> mask i alla fritextfält,
    INNAN maskera_siefil körs. Rör inte den låsta maskeringskärnan."""

    def _sie(self):
        return SIEFil(
            verifikationer=[
                Verifikation(
                    serie="A", vernr="1", verdatum=date(2025, 1, 1),
                    vertext="Faktura Kalle Eriksson", sign="Kalle Eriksson",
                    transaktioner=[
                        Transaktion(kontonr="3010", belopp=Decimal("100"),
                                    transtext="Betalt av Kalle Eriksson")
                    ],
                )
            ],
            prosa="Notering: Kalle Eriksson godkände.",
        )

    def test_ersatter_i_alla_fritextfalt(self):
        ut = tillämpa_liggare(self._sie(), {"Kalle Eriksson": "[PERSON 1]"})
        v = ut.verifikationer[0]
        assert "Kalle Eriksson" not in v.vertext and "[PERSON 1]" in v.vertext
        assert "[PERSON 1]" in v.sign
        assert "[PERSON 1]" in v.transaktioner[0].transtext
        assert "[PERSON 1]" in ut.prosa

    def test_tom_liggare_lamnar_orort(self):
        sie = self._sie()
        assert tillämpa_liggare(sie, {}).verifikationer[0].vertext == "Faktura Kalle Eriksson"

    def test_ror_inte_originalet(self):
        sie = self._sie()
        tillämpa_liggare(sie, {"Kalle Eriksson": "[PERSON 1]"})
        assert sie.verifikationer[0].vertext == "Faktura Kalle Eriksson"  # deepcopy


class TestGrupperingPerNamn:
    def test_unika_namn_behov_en_per_namn(self):
        behov = [
            _namnbehov("Kalle Eriksson", plats="serie=A vernr=1"),
            _namnbehov("Kalle Eriksson", plats="serie=B vernr=2", fältnamn="transtext"),
            _namnbehov("Anna Berg", plats="serie=C vernr=3"),
        ]
        unika = unika_namn_behov(behov)
        assert {b.misstänkt_text for b in unika} == {"Kalle Eriksson", "Anna Berg"}
        assert len(unika) == 2

    def test_beslut_appliceras_pa_alla_forekomster(self):
        behov = [
            _namnbehov("Kalle Eriksson", plats="serie=A vernr=1"),
            _namnbehov("Kalle Eriksson", plats="serie=B vernr=2"),
            _namnbehov("Anna Berg", plats="serie=C vernr=3"),
        ]
        beslut = {
            "Kalle Eriksson": {"maskera": True, "text": "Kalle Eriksson"},
            "Anna Berg": {"maskera": False, "text": "Anna Berg"},
        }
        granskade = bygg_granskade_behov_per_namn(behov, beslut)
        kalle = [g for g in granskade if g.misstänkt_text == "Kalle Eriksson"]
        assert len(kalle) == 2 and all(g.status == "bekräftad_pii" for g in kalle)
        anna = [g for g in granskade if g.misstänkt_text == "Anna Berg"]
        assert len(anna) == 1 and anna[0].status == "godkänd_ej_pii"

    def test_saknat_beslut_ar_failclosed(self):
        granskade = bygg_granskade_behov_per_namn([_namnbehov("Okänd Person")], {})
        assert granskade[0].status == "bekräftad_pii"  # fail-closed: maskeras


class TestTrelagesbeslut:
    """Trelägesvalet: "maskera" och "ingen maskering" är båda AKTIVA beslut som
    rensar raden ur listan, medan "avvakta" lämnar den kvar. Utan det tredje
    läget gick ett medvetet nej inte att skilja från en orörd rad, och
    undantagslistan hade fyllts av rader ingen tagit ställning till."""

    def test_maskera_ger_bekraftad_pii(self):
        ut = bygg_granskade_behov_per_namn(
            [_namnbehov("Karl Svensson")],
            {"Karl Svensson": {"beslut": BESLUT_MASKERA, "text": "Karl Svensson"}},
        )
        assert ut[0].status == "bekräftad_pii"

    def test_ingen_maskering_ger_godkand_ej_pii(self):
        ut = bygg_granskade_behov_per_namn(
            [_namnbehov("Danske Disks")],
            {"Danske Disks": {"beslut": BESLUT_INGEN_MASKERING, "text": "Danske Disks"}},
        )
        assert ut[0].status == "godkänd_ej_pii"

    def test_avvakta_lamnar_raden_ogranskad(self):
        ut = bygg_granskade_behov_per_namn(
            [_namnbehov("Karl Svensson")],
            {"Karl Svensson": {"beslut": BESLUT_AVVAKTA, "text": "Karl Svensson"}},
        )
        assert ut[0].status == "väntar_granskning"

    def test_okant_beslut_ar_failclosed(self):
        # Skräp i state får aldrig tolkas som "släpp igenom".
        ut = bygg_granskade_behov_per_namn(
            [_namnbehov("Karl Svensson")], {"Karl Svensson": {"beslut": "nonsens"}}
        )
        assert ut[0].status == "bekräftad_pii"

    def test_aldre_booleska_beslut_stods_fortfarande(self):
        ut = bygg_granskade_behov_per_namn(
            [_namnbehov("Karl Svensson")], {"Karl Svensson": {"maskera": False}}
        )
        assert ut[0].status == "godkänd_ej_pii"


class TestObeslutadeBehov:
    def test_bara_vantande_visas(self):
        behov = [
            _namnbehov("Kvar IListan"),
            replace(_namnbehov("Redan Maskerad"), status="bekräftad_pii"),
            replace(_namnbehov("Redan Undantagen"), status="godkänd_ej_pii"),
        ]
        assert [b.misstänkt_text for b in obeslutade_behov(behov)] == ["Kvar IListan"]

    def test_bade_maskerade_och_undantagna_forsvinner(self):
        """Kravet rakt av: ett aktivt beslut åt BÅDA hållen rensar raden."""
        behov = [
            replace(_namnbehov("A B"), status="bekräftad_pii"),
            replace(_namnbehov("C D"), status="godkänd_ej_pii"),
        ]
        assert obeslutade_behov(behov) == []


class TestNamnAttUndanta:
    def test_bara_aktivt_undantagna_namn_returneras(self):
        granskade = [
            replace(_namnbehov("Danske Disks"), status="godkänd_ej_pii"),
            replace(_namnbehov("Karl Svensson"), status="bekräftad_pii"),
            _namnbehov("Obeslutad Rad"),
        ]
        assert namn_att_undanta(granskade) == {"Danske Disks"}

    def test_flaggad_text_undantas_inte_ersattningstexten(self):
        """Undantagslistan matchar mot det sekretesslagret FLAGGAR, inte mot
        vad användaren råkade skriva i maskeringsfältet."""
        granskade = [
            replace(
                _namnbehov("Danske Disks"),
                status="godkänd_ej_pii",
                ersättningstext="Något annat",
            )
        ]
        assert namn_att_undanta(granskade) == {"Danske Disks"}


# ---------------------------------------------------------------------------
# Fakturautkast: Smart Godkännande / HITL (Fas 7)
# ---------------------------------------------------------------------------

def _post(kategori="arbete", beskrivning="Snickeriarbete", belopp="5000.00") -> dict:
    return {"beskrivning": beskrivning, "kategori": kategori, "belopp": Decimal(belopp)}


class TestByggFakturautkast:
    def test_konteringsmotorns_forslag_anvands_utan_minne(self):
        utkast = bygg_fakturautkast(
            "Ny Kund AB", "juridisk_person", [_post("arbete"), _post("materiel")]
        )
        arbete = next(r for r in utkast if r.kategori == "arbete")
        materiel = next(r for r in utkast if r.kategori == "materiel")
        assert arbete.kontonr == "3041"
        assert materiel.kontonr == "3051"
        assert arbete.kall_ur_minne is False

    def test_byggmoms_lagger_allt_pa_3231(self):
        utkast = bygg_fakturautkast(
            "Firma AB", "byggmoms", [_post("arbete"), _post("materiel")]
        )
        assert all(rad.kontonr == "3231" for rad in utkast)

    def test_tidigare_godkant_monster_atervands_och_flaggas(self):
        minne = {
            "anna andersson": {
                "visningsnamn": "Anna Andersson",
                "fakturatyp": "fysisk_person_med_rot",
                "kontering": {"arbete": "3099"},  # avvikande, mänskligt rättat konto
            }
        }
        utkast = bygg_fakturautkast(
            "Anna Andersson", "fysisk_person_med_rot", [_post("arbete")],
            konteringsminne=minne,
        )
        assert utkast[0].kontonr == "3099"
        assert utkast[0].kall_ur_minne is True

    def test_minnet_matchar_skiftlagesokansligt(self):
        minne = {"anna andersson": {"kontering": {"arbete": "3099"}}}
        utkast = bygg_fakturautkast(
            "ANNA ANDERSSON", "juridisk_person", [_post("arbete")], konteringsminne=minne,
        )
        assert utkast[0].kontonr == "3099"

    def test_minnet_saknar_kategorin_faller_tillbaka_pa_motorn(self):
        # Minnet har bara "arbete" inlärt sedan tidigare — en NY "materiel"-
        # rad för samma kund ska falla tillbaka på konteringsmotorn.
        minne = {"anna andersson": {"kontering": {"arbete": "3099"}}}
        utkast = bygg_fakturautkast(
            "Anna Andersson", "juridisk_person", [_post("materiel")], konteringsminne=minne,
        )
        assert utkast[0].kontonr == "3051"
        assert utkast[0].kall_ur_minne is False

    def test_okand_kund_utan_minne_faller_tillbaka_pa_motorn(self):
        utkast = bygg_fakturautkast("Okänd Kund", "juridisk_person", [_post("arbete")])
        assert utkast[0].kontonr == "3041"
        assert utkast[0].kall_ur_minne is False

    def test_belopp_och_beskrivning_fors_igenom_oforandrat(self):
        utkast = bygg_fakturautkast(
            "X", "juridisk_person",
            [_post("arbete", beskrivning="Golvläggning", belopp="12345.00")],
        )
        assert utkast[0].beskrivning == "Golvläggning"
        assert utkast[0].belopp == Decimal("12345.00")

    def test_antal_defaultar_till_1(self):
        utkast = bygg_fakturautkast("X", "juridisk_person", [_post("arbete")])
        assert utkast[0].antal == Decimal("1")

    def test_okand_fakturatyp_utan_minnesmatchning_hojer_valueerror(self):
        with pytest.raises(ValueError):
            bygg_fakturautkast("X", "okand_typ", [_post("arbete")])


class TestTillampaKontonrAndringar:
    def test_andrar_bara_de_angivna_indexen(self):
        utkast = bygg_fakturautkast(
            "X", "juridisk_person", [_post("arbete"), _post("materiel")]
        )
        rattat = tillampa_kontonr_andringar(utkast, {0: "3099"})
        assert rattat[0].kontonr == "3099"
        assert rattat[1].kontonr == utkast[1].kontonr  # orörd

    def test_rattad_rad_markeras_inte_langre_kall_ur_minne(self):
        minne = {"anna andersson": {"kontering": {"arbete": "3041"}}}
        utkast = bygg_fakturautkast(
            "Anna Andersson", "juridisk_person", [_post("arbete")], konteringsminne=minne,
        )
        assert utkast[0].kall_ur_minne is True
        rattat = tillampa_kontonr_andringar(utkast, {0: "3099"})
        assert rattat[0].kall_ur_minne is False

    def test_tom_andring_lamnar_raden_helt_orord(self):
        utkast = bygg_fakturautkast("X", "juridisk_person", [_post("arbete")])
        rattat = tillampa_kontonr_andringar(utkast, {0: ""})
        assert rattat[0] == utkast[0]

    def test_ror_inte_indatan(self):
        utkast = bygg_fakturautkast("X", "juridisk_person", [_post("arbete")])
        tillampa_kontonr_andringar(utkast, {0: "3099"})
        assert utkast[0].kontonr == "3041"  # originalet oförändrat


class TestKonteringFranUtkast:
    def test_extraherar_kategori_till_kontonr(self):
        utkast = [
            Fakturaradsforslag("Arbete", "arbete", Decimal("100"), kontonr="3041"),
            Fakturaradsforslag("Material", "materiel", Decimal("50"), kontonr="3051"),
        ]
        assert kontering_fran_utkast(utkast) == {"arbete": "3041", "materiel": "3051"}

    def test_tomt_utkast_ger_tom_dict(self):
        assert kontering_fran_utkast([]) == {}


class TestFakturaraderForBetalning:
    def test_konverterar_till_dict_form(self):
        utkast = [Fakturaradsforslag("Snickeri", "arbete", Decimal("5000"), kontonr="3041")]
        rader = fakturarader_for_betalning(utkast)
        assert rader == [
            {"beskrivning": "Snickeri", "kategori": "arbete",
             "belopp": Decimal("5000"), "antal": Decimal("1"), "kontonr": "3041"}
        ]


# ---------------------------------------------------------------------------
# AI-agenten (Tool Calling): tolka Verktygsanrop till utkast (Fas 9)
# ---------------------------------------------------------------------------

class TestTolkaKundverktygsanrop:
    def test_giltig_indata(self):
        forslag = tolka_kundverktygsanrop({"kundnamn": "Lisa Andersson", "ar_privatperson": True})
        assert forslag == KundutkastForslag(kundnamn="Lisa Andersson", ar_privatperson=True)

    def test_saknat_kundnamn_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_kundverktygsanrop({"ar_privatperson": True})

    def test_tomt_kundnamn_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_kundverktygsanrop({"kundnamn": "   ", "ar_privatperson": True})

    def test_kundnamn_trimmas(self):
        forslag = tolka_kundverktygsanrop({"kundnamn": "  Lisa Andersson  ", "ar_privatperson": False})
        assert forslag.kundnamn == "Lisa Andersson"

    def test_saknad_ar_privatperson_tolkas_som_false(self):
        # Ingen gissad default att låtsas vara sann — bool(None) är False,
        # inte ett aktivt påstående om att kunden ÄR en privatperson.
        forslag = tolka_kundverktygsanrop({"kundnamn": "Acme AB"})
        assert forslag.ar_privatperson is False


class TestTolkaFakturaverktygsanrop:
    def test_giltig_indata(self):
        tillstand = tolka_fakturaverktygsanrop({
            "kundnamn": "Anna Andersson", "fakturatyp": "juridisk_person",
            "arbetskostnad": 5000, "materielkostnad": 2000,
        })
        assert tillstand["kundnamn"] == "Anna Andersson"
        assert tillstand["fakturatyp"] == "juridisk_person"
        assert tillstand["arbetskostnad"] == Decimal("5000")
        assert tillstand["materielkostnad"] == Decimal("2000")

    def test_saknat_kundnamn_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_fakturaverktygsanrop({"fakturatyp": "juridisk_person"})

    def test_saknad_fakturatyp_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_fakturaverktygsanrop({"kundnamn": "Anna Andersson"})

    def test_saknade_belopp_defaultar_till_noll(self):
        tillstand = tolka_fakturaverktygsanrop({
            "kundnamn": "Anna Andersson", "fakturatyp": "juridisk_person",
        })
        assert tillstand["arbetskostnad"] == Decimal("0")
        assert tillstand["materielkostnad"] == Decimal("0")

    def test_belopp_blir_decimal_inte_float(self):
        tillstand = tolka_fakturaverktygsanrop({
            "kundnamn": "X", "fakturatyp": "juridisk_person", "arbetskostnad": 1234.56,
        })
        assert tillstand["arbetskostnad"] == Decimal("1234.56")
        assert isinstance(tillstand["arbetskostnad"], Decimal)

    def test_rot_falt_fran_ai_ignoreras_alltid(self):
        # Fynd B: ROT-uppgifter (särskilt personnumret) får ALDRIG propageras
        # från ett AI-verktygsanrop. Även om ett anrop skulle bära dem tvingas
        # de till tomt/noll, så app.py:s lokala 'rot_lokalt'-formulär tar över.
        tillstand = tolka_fakturaverktygsanrop({
            "kundnamn": "X", "fakturatyp": "fysisk_person_med_rot",
            "arbetskostnad": 5000, "fastighetsbeteckning": "Solberga 1:23",
            "personnummer_fastighetsagare": "800101-1234",
            "arbetstimmar": 10, "rot_avdrag": 1500,
        })
        assert tillstand["fastighetsbeteckning"] == ""
        assert tillstand["personnummer"] == ""
        assert tillstand["arbetstimmar"] == Decimal("0")
        assert tillstand["rot_avdrag"] == Decimal("0")

    def test_saknade_rot_falt_ger_tomma_strangar_och_noll(self):
        tillstand = tolka_fakturaverktygsanrop({
            "kundnamn": "X", "fakturatyp": "juridisk_person",
        })
        assert tillstand["fastighetsbeteckning"] == ""
        assert tillstand["personnummer"] == ""
        assert tillstand["arbetstimmar"] == Decimal("0")


class TestTolkaValverktygsanrop:
    def test_giltig_indata(self):
        valfraga = tolka_valverktygsanrop({
            "fraga": "Vilken fakturatyp gäller?",
            "alternativ": ["Byggmoms", "Juridisk person"],
        })
        assert valfraga == Valfraga(
            fraga="Vilken fakturatyp gäller?", alternativ=["Byggmoms", "Juridisk person"],
        )

    def test_saknad_fraga_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_valverktygsanrop({"alternativ": ["A", "B"]})

    def test_tom_fraga_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_valverktygsanrop({"fraga": "   ", "alternativ": ["A", "B"]})

    def test_noll_alternativ_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_valverktygsanrop({"fraga": "Fråga?", "alternativ": []})

    def test_ett_enda_alternativ_hojer_valueerror(self):
        # Ett enda alternativ är inget meningsfullt flerval att rendera.
        with pytest.raises(ValueError):
            tolka_valverktygsanrop({"fraga": "Fråga?", "alternativ": ["Bara ett"]})

    def test_tomma_alternativ_rensas_bort(self):
        with pytest.raises(ValueError):
            tolka_valverktygsanrop({"fraga": "Fråga?", "alternativ": ["A", "   ", ""]})

    def test_alternativ_trimmas(self):
        valfraga = tolka_valverktygsanrop({
            "fraga": "Fråga?", "alternativ": ["  Byggmoms  ", " Juridisk person "],
        })
        assert valfraga.alternativ == ["Byggmoms", "Juridisk person"]

    def test_saknad_alternativlista_hojer_valueerror(self):
        with pytest.raises(ValueError):
            tolka_valverktygsanrop({"fraga": "Fråga?"})


_KUNDER_FOR_FUZZY = [
    {"Id": "c1", "Name": "Carl Svensson"},
    {"Id": "c2", "Name": "Anna Andersson"},
    {"Id": "c3", "Name": "Redovisningsbyrån AB"},
]


class TestSokLikaKunder:
    def test_liknande_namn_hittas(self):
        # Karl/Carl skiljer en bokstav — ska ge hög likhet.
        kandidater = sok_lika_kunder("Karl Svensson", _KUNDER_FOR_FUZZY)
        namn = [k.namn for k in kandidater]
        assert "Carl Svensson" in namn

    def test_helt_annat_namn_ger_inga_kandidater(self):
        kandidater = sok_lika_kunder("Karl Svensson", [_KUNDER_FOR_FUZZY[2]])
        assert kandidater == []

    def test_exakt_traff_exkluderas(self):
        # Exakt träff hanteras separat i app.py — ska ALDRIG dyka upp som
        # ett "menade du"-förslag på sig själv.
        kandidater = sok_lika_kunder("Carl Svensson", _KUNDER_FOR_FUZZY)
        assert all(k.namn != "Carl Svensson" for k in kandidater)

    def test_exakt_traff_case_insensitive_exkluderas(self):
        kandidater = sok_lika_kunder("carl SVENSSON", _KUNDER_FOR_FUZZY)
        assert all(k.namn.casefold() != "carl svensson" for k in kandidater)

    def test_sorterad_fallande_efter_likhet(self):
        kunder = [
            {"Id": "a", "Name": "Karlsson"},
            {"Id": "b", "Name": "Karl Svensson"},
        ]
        kandidater = sok_lika_kunder("Karl Svenson", kunder)
        assert [k.likhet for k in kandidater] == sorted(
            [k.likhet for k in kandidater], reverse=True
        )

    def test_trunkeras_till_max_antal(self):
        kunder = [{"Id": str(i), "Name": f"Karl Svensson {i}"} for i in range(10)]
        kandidater = sok_lika_kunder("Karl Svensson", kunder, max_antal=3)
        assert len(kandidater) == 3

    def test_tom_kundlista_ger_inga_kandidater(self):
        assert sok_lika_kunder("Karl Svensson", []) == []

    def test_kandidat_bar_kund_id(self):
        kandidater = sok_lika_kunder("Karl Svensson", _KUNDER_FOR_FUZZY)
        assert kandidater[0] == Kundkandidat(
            kund_id="c1", namn="Carl Svensson", likhet=kandidater[0].likhet
        )


class TestByggNyKundPayload:
    def test_grundfalt(self):
        payload = bygg_ny_kund_payload("Karl Svensson", True, "800101-1234")
        assert payload == {
            "Name": "Karl Svensson",
            "IsPrivatePerson": True,
            "CorporateIdentityNumber": "800101-1234",
        }

    def test_adressfalt_med_om_ifyllda(self):
        payload = bygg_ny_kund_payload(
            "Acme AB", False, "556677-8899",
            adress="Storgatan 1", postnr="111 22", ort="Stockholm",
        )
        assert payload["Address1"] == "Storgatan 1"
        assert payload["ZipCode"] == "111 22"
        assert payload["City"] == "Stockholm"

    def test_tomma_adressfalt_utelamnas(self):
        payload = bygg_ny_kund_payload("Karl Svensson", True, "800101-1234")
        assert "Address1" not in payload
        assert "ZipCode" not in payload
        assert "City" not in payload
