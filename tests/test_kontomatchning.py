"""Testskelett för Modul 4 (kontomatchning) — wrapper-lagret.

Se ARCHITECTURE_tillagg_modul4.md. Detta är ett SKELETT: det etablerar
kontraktet och täcker de fail-closed-kritiska scenarierna, men är inte
en uttömmande svit. Byggs ut tillsammans med Claude Code, i linje med
hur test_kontotyp_vakt.py startade som skelett innan Modul 2 var klar.

Dessa tester kräver ALDRIG en riktig API-nyckel — haiku_anropare är
alltid en fejkad funktion. Träffsäkerhets-facit mot riktiga Haiku-svar
är en separat process, se §8 i arkitekturtillägget.
"""

from __future__ import annotations

from datetime import date

import pytest

from domain_model import Konto, Transaktion, Verifikation
from kontomatchning import Kontobedömning, bedöm_transaktioner, bygg_bunt, tolka_haiku_svar

# --- Fixtures ----------------------------------------------------------------

KONTON = {
    "5611": Konto(kontonr="5611", namn="Drivmedel personbilar"),
    "6110": Konto(kontonr="6110", namn="Kontorsmaterial"),
}


def _verifikation(serie="A", vernr="1", **kwargs) -> Verifikation:
    defaults = dict(verdatum=date(2025, 1, 1), transaktioner=[])
    defaults.update(kwargs)
    return Verifikation(serie=serie, vernr=vernr, **defaults)


def _transaktion(kontonr="5611", transtext="Drivmedel Circle K", **kwargs) -> Transaktion:
    defaults = dict(belopp=500)
    defaults.update(kwargs)
    return Transaktion(kontonr=kontonr, transtext=transtext, **defaults)


# --- Buntbygge -----------------------------------------------------------------

class TestBuntbygge:
    def test_en_transaktion_ger_ratt_faltvarden_i_bunten(self):
        ver = _verifikation(transaktioner=[_transaktion()])

        buntar = bygg_bunt([ver], KONTON, max_storlek=40)

        assert len(buntar) == 1
        assert len(buntar[0]) == 1
        underlag = buntar[0][0]
        assert underlag["kontonr"] == "5611"
        assert underlag["kontonamn"] == "Drivmedel personbilar"
        assert underlag["transtext"] == "Drivmedel Circle K"
        assert underlag["plats"] == "serie=A vernr=1 radindex=0"

    def test_flera_transaktioner_over_max_storlek_delas_i_flera_buntar(self):
        ver = _verifikation(
            transaktioner=[_transaktion(transtext=f"Rad {i}") for i in range(5)]
        )

        buntar = bygg_bunt([ver], KONTON, max_storlek=2)

        assert len(buntar) == 3  # 2 + 2 + 1
        assert sum(len(b) for b in buntar) == 5

    def test_verifikation_utan_transaktioner_ger_ingen_bunt(self):
        ver = _verifikation(transaktioner=[])

        buntar = bygg_bunt([ver], KONTON, max_storlek=40)

        assert buntar == [] or all(len(b) == 0 for b in buntar)

    def test_saknad_transtext_faller_tillbaka_pa_vertext(self):
        ver = _verifikation(
            vertext="Bensin på resa",
            transaktioner=[_transaktion(transtext=None)],
        )

        buntar = bygg_bunt([ver], KONTON, max_storlek=40)

        assert buntar[0][0]["transtext"] == "Bensin på resa"


# --- Svarstolkning: den fail-closed-kritiska delen -----------------------------

class TestSvarstolkning:
    def test_matchning_tolkas_korrekt(self):
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "5611",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "matchning", "motivering": None}]

        resultat = tolka_haiku_svar(bunt, haiku_svar)

        assert len(resultat) == 1
        assert resultat[0].status == "matchning"

    def test_avvikelse_tolkas_korrekt(self):
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "6110",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "avvikelse",
                        "motivering": "Texten talar om drivmedel, kontot är kontorsmaterial"}]

        resultat = tolka_haiku_svar(bunt, haiku_svar)

        assert resultat[0].status == "avvikelse"
        assert "drivmedel" in resultat[0].motivering.lower()

    def test_saknat_svar_for_bunt_id_ger_osaker_inte_tyst_matchning(self):
        """Kritiskt: om Haiku glömmer ett bunt-id ska raden INTE tystas
        ner till 'matchning' bara för att den inte nämndes."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "5611",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar: list[dict] = []  # Haiku svarade inte alls för T1

        resultat = tolka_haiku_svar(bunt, haiku_svar)

        assert len(resultat) == 1
        assert resultat[0].status == "osäker"

    def test_trasigt_svar_ger_osaker(self):
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "5611",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "helt_okänt_värde"}]  # ogiltigt enligt schema

        resultat = tolka_haiku_svar(bunt, haiku_svar)

        assert resultat[0].status == "osäker"

    def test_motivering_med_avvikande_kontonummer_tvingas_till_osaker(self):
        """Skyddslager 2 i §4: om motivering råkar innehålla ett annat
        kontonummer än det analyserade kontot, ska det tolkas som ett
        förtäckt kontoförslag — inte släppas igenom som en ren flagga."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "6110",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "avvikelse",
                        "motivering": "Borde bokas på 5611 istället"}]

        resultat = tolka_haiku_svar(bunt, haiku_svar)

        assert resultat[0].status == "osäker"
        assert resultat[0].motivering is not None  # bevaras som diagnostik

    def test_motivering_med_belopp_flaggas_inte_som_avvikande_konto(self):
        """Ett belopp som '2340 kr' i motiveringen är inte ett smuget
        kontoförslag bara för att det råkar vara fyra siffror — bara
        riktiga kontonummer i kontoplanen ska trigga skyddslager 2."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "5611",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "avvikelse",
                        "motivering": "Beloppet 2340 kr är ovanligt högt"}]

        resultat = tolka_haiku_svar(bunt, haiku_svar, konton=KONTON)

        assert resultat[0].status == "avvikelse"  # inte nedgraderat

    def test_foreslaget_kontonr_populeras_vid_avvikelse(self):
        """Gap 3: vid status
        'avvikelse' och ett giltigt förslag från Haiku ska
        Kontobedömning bära föreslaget_kontonr — det behövs för att
        Modul 5 ska kunna härleda riktning (över/under) för Modul 4:s
        avvikelser."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "6110",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "avvikelse",
                        "motivering": "Texten talar om drivmedel, kontot är kontorsmaterial",
                        "föreslaget_kontonr": "5611"}]

        resultat = tolka_haiku_svar(bunt, haiku_svar, konton=KONTON)

        assert resultat[0].status == "avvikelse"
        assert resultat[0].föreslaget_kontonr == "5611"

    def test_foreslaget_kontonr_ar_none_vid_osaker(self):
        """Haiku är per definition inte säker nog för ett kontoförslag
        när status är 'osäker' — föreslaget_kontonr ska då alltid vara
        None, även om Haiku råkat skicka med ett värde ändå."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "5611",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "osäker", "motivering": "Oklart",
                        "föreslaget_kontonr": "6110"}]

        resultat = tolka_haiku_svar(bunt, haiku_svar, konton=KONTON)

        assert resultat[0].status == "osäker"
        assert resultat[0].föreslaget_kontonr is None

    def test_ogiltigt_foreslaget_kontonr_fail_closed_till_none(self):
        """Skyddslager 2, återanvänt: föreslår Haiku ett kontonummer som
        inte finns i kontoplanen ska föreslaget_kontonr bli None — samma
        fail-closed-princip som redan gäller för avvikande kontonummer i
        motivering (samma skydd, återanvänt, inte en parallell kontroll)."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "6110",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "avvikelse",
                        "motivering": "Kontot verkar fel",
                        "föreslaget_kontonr": "9999"}]  # finns inte i KONTON

        resultat = tolka_haiku_svar(bunt, haiku_svar, konton=KONTON)

        assert resultat[0].föreslaget_kontonr is None

    def test_foreslaget_kontonr_ar_none_vid_matchning(self):
        """Samma princip som för 'osäker': ett föreslaget_kontonr hör bara
        hemma vid 'avvikelse'. Skickar Haiku ändå med ett värde vid
        'matchning' ska det nollas, inte råka slinka igenom."""
        bunt = [{"bunt_id": "T1", "plats": "serie=A vernr=1 radindex=0", "kontonr": "5611",
                 "text_analyserad": "Drivmedel Circle K"}]
        haiku_svar = [{"bunt_id": "T1", "status": "matchning", "motivering": None,
                        "föreslaget_kontonr": "6110"}]

        resultat = tolka_haiku_svar(bunt, haiku_svar, konton=KONTON)

        assert resultat[0].status == "matchning"
        assert resultat[0].föreslaget_kontonr is None


# --- Orkestrering och privacygränsen --------------------------------------------

class TestOrkestrering:
    def test_bedom_transaktioner_anropar_haiku_per_bunt(self):
        ver = _verifikation(transaktioner=[_transaktion()])
        anrop_räknare = {"antal": 0}

        def fejk_haiku(bunt: list[dict], prosa_kontext: str | None) -> list[dict]:
            anrop_räknare["antal"] += 1
            return [{"bunt_id": rad["bunt_id"], "status": "matchning", "motivering": None}
                    for rad in bunt]

        resultat = bedöm_transaktioner([ver], KONTON, fejk_haiku, max_bunt_storlek=40)

        assert anrop_räknare["antal"] == 1
        assert len(resultat) == 1
        assert resultat[0].status == "matchning"

    def test_kontobedomning_bar_transaktionens_faktiska_belopp(self):
        """Gap 2: Kontobedömning ska
        bära transaktionens faktiska belopp, inte None eller ett saknat
        fält — Modul 5 kan annars inte ackumulera belopp som inte finns."""
        ver = _verifikation(transaktioner=[_transaktion(belopp=1234)])

        def fejk_haiku(bunt: list[dict], prosa_kontext: str | None) -> list[dict]:
            return [{"bunt_id": rad["bunt_id"], "status": "matchning", "motivering": None}
                    for rad in bunt]

        resultat = bedöm_transaktioner([ver], KONTON, fejk_haiku, max_bunt_storlek=40)

        assert resultat[0].belopp == 1234

    def test_prosa_kontext_skickas_till_haiku_anropare_i_varje_bunt(self):
        """prosa_kontext är delad bakgrundskontext för hela batchen (t.ex.
        en revisors kommentar) — inte något som analyseras per
        transaktion. Ska skickas som andra argument till haiku_anropare
        vid VARJE bunt-anrop, inte bara det första."""
        ver = _verifikation(
            transaktioner=[_transaktion(transtext=f"Rad {i}") for i in range(3)]
        )
        mottagna_kontext: list[str | None] = []

        def fejk_haiku(bunt: list[dict], prosa_kontext: str | None) -> list[dict]:
            mottagna_kontext.append(prosa_kontext)
            return [{"bunt_id": rad["bunt_id"], "status": "matchning", "motivering": None}
                    for rad in bunt]

        bedöm_transaktioner(
            [ver], KONTON, fejk_haiku, max_bunt_storlek=2,
            prosa_kontext="Ovanligt hög aktivitet i december enligt revisorn.",
        )

        assert len(mottagna_kontext) == 2  # 3 transaktioner, max_bunt_storlek=2 -> 2 buntar
        assert all(k == "Ovanligt hög aktivitet i december enligt revisorn." for k in mottagna_kontext)

    def test_ingen_prosa_kontext_skickar_none_till_haiku_anropare(self):
        ver = _verifikation(transaktioner=[_transaktion()])
        mottaget_kontext: list[str | None] = []

        def fejk_haiku(bunt: list[dict], prosa_kontext: str | None) -> list[dict]:
            mottaget_kontext.append(prosa_kontext)
            return [{"bunt_id": rad["bunt_id"], "status": "matchning", "motivering": None}
                    for rad in bunt]

        bedöm_transaktioner([ver], KONTON, fejk_haiku, max_bunt_storlek=40)

        assert mottaget_kontext == [None]

    def test_endast_sandningsbara_verifikationer_nar_haiku(self):
        """Regressionsvakt för §2: anropar man bedöm_transaktioner med en
        lista som (av misstag) innehåller en verifikation som borde ha
        blockerats av Modul 3, finns inget skyddsnät här — kontraktet är
        att ENDAST sandningsbara_verifikationer någonsin skickas in. Det
        här testet dokumenterar den gränsen explicit, snarare än att anta
        att den är självklar."""
        blockerad_liknande = _verifikation(
            serie="B", vernr="9",
            transaktioner=[_transaktion(transtext="Lön Kalle Karlsson")],
        )
        skickade_bunt: list[dict] = []

        def fejk_haiku(bunt: list[dict], prosa_kontext: str | None) -> list[dict]:
            skickade_bunt.extend(bunt)
            return [{"bunt_id": r["bunt_id"], "status": "matchning", "motivering": None} for r in bunt]

        bedöm_transaktioner([blockerad_liknande], KONTON, fejk_haiku, max_bunt_storlek=40)

        # Testet illustrerar att modulen litar blint på sin indata — det är
        # ANROPARENS ansvar (appen/Modul 4-integrationen) att aldrig skicka
        # in annat än sandningsbara_verifikationer. Om det här antagandet
        # känns för svagt, säg till — då bör bedöm_transaktioner själv
        # kräva ett Maskeringsresultat som argument istället för en rå
        # verifikationslista, och validera internt.
        assert len(skickade_bunt) == 1
