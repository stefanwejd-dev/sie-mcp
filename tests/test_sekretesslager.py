"""
Testfall — Modul 3: Sekretesslager (maskering)

STATUS: Röd fas (TDD). `sekretesslager.py` existerar ännu inte. Dessa tester
är fullständigt utskrivna med assertions (inte stubbar) — samma standard som
test_vasentlighet.py och test_kontotyp_vakt.py. De ska rimligen misslyckas
med ImportError/AttributeError innan sekretesslager.py är skrivet, inte med
NotImplementedError.

VIKTIGT OM FÄLTNAMN:
  Attributnamnen på SIEFil/Adress/Objekt/Dimension/Verifikation/Transaktion
  nedan är rekonstruerade utifrån SIE4-specens fältordning
  (SIE_filformat_ver_4C_20250806.pdf) och tidigare sessioners beslut om att
  Adress- och Objekt-dataclasser existerar. Om de inte matchar er faktiska
  domain_model.py exakt: justera ENDAST attributnamnen (mekanisk
  sök-och-ersätt). Rör inte testlogiken, assertions eller facit-värdena.
  Det är en namnkorrigering, inte en omskrivning av testerna.

VIKTIGT OM TESTDATA:
  Samtliga namn och personnummer nedan är syntetiska. Personnumren har en
  matematiskt korrekt Luhn-kontrollsiffra (uträknad separat, se
  chattens verktygsanrop) men är INTE kopplade till någon verklig individ.

AVGRÄNSNING (v1, ej testat här):
  Samordningsnummer (dag+60, t.ex. dag 61–91) testas inte i denna fil —
  öppen fråga för en senare fas, se ARCHITECTURE_tillagg_sekretesslager.md.
  "+"-tecknet nedan testas endast som separator-variant (markerar person
  över 100 år), inte som samordningsnummer.
"""

from dataclasses import replace
from pathlib import Path

import pytest

# --- Platshållare: byt till er faktiska modulstruktur ----------------------
from sekretesslager import (
    Maskeringsbehov,
    Maskeringsresultat,
    maskera_chattmeddelande,
    maskera_kontonamn,
    maskera_siefil,
    demaskera_text,
    uppdatera_efter_granskning,
    är_giltigt_personnummer,
)
from sie4_parser import parse_sie4  # byt om er entry-point heter annat
from domain_model import (
    SIEFil,
    Konto,
    Verifikation,
    Transaktion,
    Objekt,
    Dimension,
    Adress,
)
# -----------------------------------------------------------------------

SAMPLE_FIL = Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"

# Syntetiska personnummer, Luhn-kontrollsiffra manuellt uträknad och
# verifierad. Ej kopplade till verklig individ.
GILTIGT_PERSONNUMMER_LANG = "19900102-1238"
GILTIGT_PERSONNUMMER_KORT = "900102-1238"
GILTIGT_PERSONNUMMER_PLUS = "900102+1238"   # separator för 100+ år
OGILTIG_KONTROLLSIFFRA = "19900102-1239"     # sista siffran trasig med avsikt


def _bygg_referenslista() -> set[str]:
    """Testfixture: syntetisk lista över 'anställda' för Lager 3a.
    Motsvarar INTE den skarpa referenslistan."""
    return {"Anna Andersson", "Björn Bengtsson"}


def _bygg_siefil(
    *,
    företagsnamn: str = "Testbolaget AB",
    organisationsnummer: str = "556000-0001",
    prosa: str = "",
    adress: Adress | None = None,
    konton: dict | None = None,
    dimensioner: dict | None = None,
    objektregister: dict | None = None,
    verifikationer: list | None = None,
) -> SIEFil:
    """Hjälpfunktion: minimal SIEFil för isolerade enhetstester.
    Se modulens docstring angående fältnamn."""
    return SIEFil(
        företagsnamn=företagsnamn,
        orgnr=organisationsnummer,
        prosa=prosa,
        adress=adress if adress is not None else Adress(
            kontakt="", utdelningsadress="", postadress="", telefon="",
        ),
        konton=konton if konton is not None else {},
        dimensioner=dimensioner if dimensioner is not None else {},
        objektregister=objektregister if objektregister is not None else {},
        verifikationer=verifikationer if verifikationer is not None else [],
    )


# ---------------------------------------------------------------------------
# Lager 1 — Strukturell maskering (100% säker)
# ---------------------------------------------------------------------------

class TestLager1Strukturell:
    def test_maskerar_foretagsnamn(self):
        fil = _bygg_siefil(företagsnamn="Andersson Bygg AB")
        resultat = maskera_siefil(fil)
        maskerat = resultat.maskerad_siefil.företagsnamn
        assert maskerat != "Andersson Bygg AB"
        assert maskerat.startswith("BOLAG_")
        # Kodnyckelns värde för en delad bolagstoken är en kombination av
        # företagsnamn och orgnr (se arkitektbeslutet om gemensam bolagstoken)
        # — kontrollera att företagsnamnet ingår, inte exakt likhet.
        assert "Andersson Bygg AB" in resultat.kodnyckel[maskerat]

    @pytest.mark.parametrize("orgnr", ["556677-8899", "5566778899"])
    def test_maskerar_organisationsnummer(self, orgnr):
        fil = _bygg_siefil(organisationsnummer=orgnr)
        resultat = maskera_siefil(fil)
        maskerat = resultat.maskerad_siefil.orgnr
        assert maskerat != orgnr
        assert maskerat.startswith("BOLAG_")
        assert orgnr in resultat.kodnyckel[maskerat]

    def test_foretagsnamn_och_orgnr_far_samma_bolagstoken(self):
        """Namn och orgnr identifierar samma juridiska person och ska dela
        token (BOLAG_1), inte få varsin — annars läcker kopplingen mellan
        de två ändå implicit via två olika men korrelerade tokens."""
        fil = _bygg_siefil(
            företagsnamn="Andersson Bygg AB",
            organisationsnummer="556677-8899",
        )
        resultat = maskera_siefil(fil)
        assert (
            resultat.maskerad_siefil.företagsnamn
            == resultat.maskerad_siefil.orgnr
        )

    def test_maskerar_adress_samtliga_falt(self):
        fil = _bygg_siefil(adress=Adress(
            kontakt="Anna Andersson",
            utdelningsadress="Storgatan 1",
            postadress="791 71 Falun",
            telefon="023-123 45 67",
        ))
        resultat = maskera_siefil(fil)
        maskerad = resultat.maskerad_siefil.adress
        ursprung = {
            maskerad.kontakt: "Anna Andersson",
            maskerad.utdelningsadress: "Storgatan 1",
            maskerad.postadress: "791 71 Falun",
            maskerad.telefon: "023-123 45 67",
        }
        for maskerat_värde, ursprungsvärde in ursprung.items():
            assert maskerat_värde != ursprungsvärde
            assert resultat.kodnyckel[maskerat_värde] == ursprungsvärde

    def test_maskerar_objekt_under_personaldimension(self):
        fil = _bygg_siefil(
            dimensioner={7: Dimension(dimensionsnr=7, namn="Anställningsnummer")},
            objektregister={(7, "456"): Objekt(dimensionsnr=7, objektnr="456", namn="Anna Andersson")},
        )
        resultat = maskera_siefil(fil)
        maskerat_objekt = resultat.maskerad_siefil.objektregister[(7, "456")]
        assert maskerat_objekt.namn != "Anna Andersson"
        assert maskerat_objekt.namn.startswith("PERSON_")
        assert resultat.kodnyckel[maskerat_objekt.namn] == "Anna Andersson"

    @pytest.mark.parametrize("dimensionsnamn", [
        "Anställningsnummer", "anställningsnummer", "Personalkategori", "Medarbetare",
    ])
    def test_kanner_igen_personaldimension_oavsett_skiftlage_och_variant(self, dimensionsnamn):
        fil = _bygg_siefil(
            dimensioner={1: Dimension(dimensionsnr=1, namn=dimensionsnamn)},
            objektregister={(1, "001"): Objekt(dimensionsnr=1, objektnr="001", namn="Björn Bengtsson")},
        )
        resultat = maskera_siefil(fil)
        assert resultat.maskerad_siefil.objektregister[(1, "001")].namn != "Björn Bengtsson"

    def test_maskerar_inte_objekt_under_ickepersonaldimension(self):
        fil = _bygg_siefil(
            dimensioner={6: Dimension(dimensionsnr=6, namn="Projekt")},
            objektregister={(6, "P100"): Objekt(dimensionsnr=6, objektnr="P100", namn="Huvudkontor")},
        )
        resultat = maskera_siefil(fil)
        assert resultat.maskerad_siefil.objektregister[(6, "P100")].namn == "Huvudkontor"


# ---------------------------------------------------------------------------
# Lager 2 — Personnummer (regex + kontrollsiffra)
# ---------------------------------------------------------------------------

class TestLager2Personnummer:
    @pytest.mark.parametrize("personnummer", [
        GILTIGT_PERSONNUMMER_LANG,
        GILTIGT_PERSONNUMMER_KORT,
        GILTIGT_PERSONNUMMER_PLUS,
    ])
    def test_kanner_igen_samtliga_personnummerformat(self, personnummer):
        assert är_giltigt_personnummer(personnummer) is True

    def test_verifierar_kontrollsiffra_med_luhn(self):
        assert är_giltigt_personnummer(GILTIGT_PERSONNUMMER_LANG) is True
        assert är_giltigt_personnummer(OGILTIG_KONTROLLSIFFRA) is False

    def test_maskerar_personnummer_i_transtext(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615", vertext="Utlägg",
                transaktioner=[Transaktion(kontonr="1910", belopp=-500.0,
                    transtext=f"Utlägg {GILTIGT_PERSONNUMMER_LANG}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert GILTIGT_PERSONNUMMER_LANG not in trans.transtext
        assert "PERSONNUMMER_" in trans.transtext

    def test_maskerar_personnummer_i_vertext(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                vertext=f"Reseräkning {GILTIGT_PERSONNUMMER_KORT}",
                transaktioner=[Transaktion(kontonr="1910", belopp=-500.0, transtext="")]),
        ])
        resultat = maskera_siefil(fil)
        vertext = resultat.maskerad_siefil.verifikationer[0].vertext
        assert GILTIGT_PERSONNUMMER_KORT not in vertext
        assert "PERSONNUMMER_" in vertext

    def test_maskerar_personnummer_i_prosa(self):
        fil = _bygg_siefil(prosa=f"Kommentar från revisor: {GILTIGT_PERSONNUMMER_KORT}")
        resultat = maskera_siefil(fil)
        assert GILTIGT_PERSONNUMMER_KORT not in resultat.maskerad_siefil.prosa
        assert "PERSONNUMMER_" in resultat.maskerad_siefil.prosa

    def test_skannar_personnummer_oavsett_kontoklass(self):
        """Kontrollfall för den universella skanningsprincipen: ett
        personnummer på ett konto UTANFÖR kontoklass 7 (representation,
        konto 6071) ska fångas lika säkert som på ett klass-7-konto."""
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="6071", belopp=-450.0,
                    transtext=f"Representation {GILTIGT_PERSONNUMMER_LANG}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert GILTIGT_PERSONNUMMER_LANG not in trans.transtext


# ---------------------------------------------------------------------------
# Lager 3a — Namn via referenslista
# ---------------------------------------------------------------------------

class TestLager3aReferenslista:
    def test_maskerar_namn_som_finns_i_referenslistan(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                    transtext="Lön Anna Andersson juni")]),
        ])
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Anna Andersson" not in trans.transtext
        assert "PERSON_" in trans.transtext
        assert resultat.maskeringsbehov == []  # känd träff, inget att granska

    @pytest.mark.parametrize("variant", [
        "anna andersson",
        "ANNA ANDERSSON",
        "Anna  Andersson",  # dubbelt mellanslag
    ])
    def test_normaliserar_smaskillnader_i_stavning(self, variant):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                    transtext=f"Lön {variant} juni")]),
        ])
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert variant not in trans.transtext
        assert "PERSON_" in trans.transtext

    def test_samma_person_far_samma_token_inom_sessionen(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                    transtext="Lön Anna Andersson juni")]),
            Verifikation(serie="A", vernr="2", verdatum="20260715",
                transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                    transtext="Lön Anna Andersson juli")]),
        ])
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        tokens_för_anna = [
            token for token, verkligt in resultat.kodnyckel.items()
            if verkligt == "Anna Andersson"
        ]
        assert len(tokens_för_anna) == 1, "Anna Andersson ska ha EN token, inte en per omnämnande"
        token = tokens_för_anna[0]
        assert token in resultat.maskerad_siefil.verifikationer[0].transaktioner[0].transtext
        assert token in resultat.maskerad_siefil.verifikationer[1].transaktioner[0].transtext


# ---------------------------------------------------------------------------
# Lager 3b — Namn via regex-fallback + Maskeringsbehov
# ---------------------------------------------------------------------------

class TestLager3bRegexFallback:
    def test_okant_versalmonster_skapar_maskeringsbehov(self):
        """'Erik Svensson' finns INTE i referenslistan men matchar
        versalmönstret 'Förnamn Efternamn' — ska INTE auto-maskeras,
        ska generera ett Maskeringsbehov och lämna texten orörd."""
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=1200.0,
                    transtext="Kurs Erik Svensson")]),
        ])
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Erik Svensson" in trans.transtext
        assert len(resultat.maskeringsbehov) == 1
        assert resultat.maskeringsbehov[0].misstänkt_text == "Erik Svensson"
        assert resultat.maskeringsbehov[0].träffkälla == "regex_fallback"
        assert resultat.maskeringsbehov[0].status == "väntar_granskning"

    def test_maskeringsbehov_innehaller_ratt_metadata(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="M", vernr="7", verdatum="20260620",
                transaktioner=[Transaktion(kontonr="7690", belopp=800.0,
                    transtext="Utlägg Karin Nilsson")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        assert len(resultat.maskeringsbehov) == 1
        behov = resultat.maskeringsbehov[0]
        assert "M" in behov.plats and "7" in behov.plats
        assert behov.fältnamn == "transtext"
        assert behov.misstänkt_text == "Karin Nilsson"
        assert behov.status == "väntar_granskning"

    def test_kant_ord_med_versal_flaggar_inte_i_onodan(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="1910", belopp=-100.0,
                    transtext="Insättning Kassa")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        assert resultat.maskeringsbehov == []


# ---------------------------------------------------------------------------
# Spärrmekanism — blockering vid Maskeringsbehov
#
# OBS: gränssnittet nedan (blockerade_verifikationer, sandningsbara_
# verifikationer, uppdatera_efter_granskning) är INTE slutgiltigt beslutat
# i ARCHITECTURE.md utan ett rimligt förslag från denna session. Bekräfta
# med Stefan (Arkitekten) om det ska justeras innan Fas 6 implementeras.
# ---------------------------------------------------------------------------

class TestSparrmekanism:
    def test_verifikation_med_maskeringsbehov_blockeras_fran_sandning(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        assert ("A", "1") in resultat.blockerade_verifikationer
        assert resultat.maskerad_siefil.verifikationer[0] not in resultat.sandningsbara_verifikationer

    def test_ovriga_verifikationer_i_samma_bunt_flyter_vidare(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
            Verifikation(serie="A", vernr="2", verdatum="20260616",
                transaktioner=[Transaktion(kontonr="4010", belopp=-2000.0,
                    transtext="Materialinköp")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        assert ("A", "1") in resultat.blockerade_verifikationer
        assert ("A", "2") not in resultat.blockerade_verifikationer
        vernr_sandningsbara = {v.vernr for v in resultat.sandningsbara_verifikationer}
        assert "2" in vernr_sandningsbara
        assert "1" not in vernr_sandningsbara

    def test_godkand_ej_pii_haver_blockeringen(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        behov = resultat.maskeringsbehov[0]
        behov.status = "godkänd_ej_pii"
        uppdaterat = uppdatera_efter_granskning(resultat, [behov])
        assert ("A", "1") not in uppdaterat.blockerade_verifikationer
        trans = uppdaterat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert trans.transtext == "Kurs Erik Svensson"

    def test_bekraftad_pii_maskerar_och_haver_blockeringen(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        behov = resultat.maskeringsbehov[0]
        behov.status = "bekräftad_pii"
        uppdaterat = uppdatera_efter_granskning(resultat, [behov])
        assert ("A", "1") not in uppdaterat.blockerade_verifikationer
        trans = uppdaterat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Erik Svensson" not in trans.transtext
        assert "PERSON_" in trans.transtext

    def test_verifikation_med_tva_maskeringsbehov_forblir_blockerad_om_bara_en_granskas(self):
        """Regression: en verifikation kan ha flera oberoende
        maskeringsbehov (t.ex. ett i vertext, ett i en transtext). Om bara
        ETT av dem granskas ska verifikationen INTE hävas från blockering
        — syskon-flaggan väntar fortfarande. Fail-closed enligt §5, inte
        fail-open."""
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                vertext="möte med Erik Svensson",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Utlägg Anna Bergström")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        assert len(resultat.maskeringsbehov) == 2
        assert ("A", "1") in resultat.blockerade_verifikationer

        erik_behov = next(b for b in resultat.maskeringsbehov if b.misstänkt_text == "Erik Svensson")
        erik_behov.status = "godkänd_ej_pii"
        uppdaterat = uppdatera_efter_granskning(resultat, [erik_behov])

        assert ("A", "1") in uppdaterat.blockerade_verifikationer, (
            "Anna Bergström väntar fortfarande på granskning — verifikationen får inte hävas än"
        )
        vernr_sandningsbara = {v.vernr for v in uppdaterat.sandningsbara_verifikationer}
        assert "1" not in vernr_sandningsbara

    def test_verifikation_med_tva_maskeringsbehov_havs_forst_nar_alla_ar_granskade(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                vertext="möte med Erik Svensson",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Utlägg Anna Bergström")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        erik_behov = next(b for b in resultat.maskeringsbehov if b.misstänkt_text == "Erik Svensson")
        anna_behov = next(b for b in resultat.maskeringsbehov if b.misstänkt_text == "Anna Bergström")

        erik_behov.status = "godkänd_ej_pii"
        delvis_granskat = uppdatera_efter_granskning(resultat, [erik_behov])
        assert ("A", "1") in delvis_granskat.blockerade_verifikationer

        anna_behov.status = "bekräftad_pii"
        helt_granskat = uppdatera_efter_granskning(delvis_granskat, [anna_behov])
        assert ("A", "1") not in helt_granskat.blockerade_verifikationer
        trans = helt_granskat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Anna Bergström" not in trans.transtext
        assert "PERSON_" in trans.transtext
        vernr_sandningsbara = {v.vernr for v in helt_granskat.sandningsbara_verifikationer}
        assert "1" in vernr_sandningsbara


# ---------------------------------------------------------------------------
# Lager 2 — Personnummer UTAN separator (fynd 4)
# ---------------------------------------------------------------------------

# Samma syntetiska personnummer som ovan, men utan bindestreck. Luhn stämmer
# (kontrollerad ur separator-varianten); datumdelen (ÅÅMMDD = 900102) är giltig.
GILTIGT_PNR_UTAN_SEP_10 = "9001021238"
GILTIGT_PNR_UTAN_SEP_12 = "199001021238"
PNR_UTAN_SEP_TRASIG_LUHN = "9001021239"   # giltig datumdel, trasig kontrollsiffra
ORGNR_UTAN_SEP = "5566778899"             # månadsdel 66 -> aldrig ett personnummer


class TestLager2PersonnummerUtanSeparator:
    @pytest.mark.parametrize("pnr", [GILTIGT_PNR_UTAN_SEP_10, GILTIGT_PNR_UTAN_SEP_12])
    def test_giltigt_personnummer_utan_separator_ar_giltigt(self, pnr):
        assert är_giltigt_personnummer(pnr) is True

    def test_trasig_luhn_utan_separator_ar_ogiltigt(self):
        assert är_giltigt_personnummer(PNR_UTAN_SEP_TRASIG_LUHN) is False

    def test_orgnr_form_ar_inte_personnummer(self):
        # Organisationsnummer har månadsdel >= 20 och ska aldrig tolkas som pnr.
        assert är_giltigt_personnummer(ORGNR_UTAN_SEP) is False

    @pytest.mark.parametrize("pnr", [GILTIGT_PNR_UTAN_SEP_10, GILTIGT_PNR_UTAN_SEP_12])
    def test_maskerar_personnummer_utan_separator_i_transtext(self, pnr):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="1910", belopp=-500.0,
                    transtext=f"Utlägg {pnr}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert pnr not in trans.transtext
        assert "PERSONNUMMER_" in trans.transtext

    def test_maskerar_inte_trasig_luhn(self):
        # Ett tal med giltig datumdel men trasig Luhn är inte ett personnummer.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="1910", belopp=-500.0,
                    transtext=f"Ref {PNR_UTAN_SEP_TRASIG_LUHN}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert PNR_UTAN_SEP_TRASIG_LUHN in trans.transtext


# ---------------------------------------------------------------------------
# Lager 2 — Organisationsnummer i fritext (kontroll.md / omgranskning)
# ---------------------------------------------------------------------------

class TestOrganisationsnummerIFritext:
    def test_maskerar_orgnr_utan_separator(self):
        # Ett AB-orgnr i fritext (separatorlöst) fångades förr inte — månadsdelen
        # >= 20 föll på personnummer-datumkontrollen. Nu maskeras det som orgnr.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="6570", belopp=-500.0,
                    transtext=f"Motpart org {ORGNR_UTAN_SEP}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert ORGNR_UTAN_SEP not in trans.transtext
        assert "ORGANISATIONSNUMMER_" in trans.transtext

    def test_maskerar_orgnr_med_separator_som_orgnr(self):
        # Med bindestreck maskerades det förr (som PERSONNUMMER); nu får det rätt
        # typ. Fortfarande maskerat oavsett — ingen täckningsregression.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="6570", belopp=-500.0,
                    transtext="Faktura till 556677-8899")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "556677-8899" not in trans.transtext
        assert "ORGANISATIONSNUMMER_" in trans.transtext

    def test_orgnr_ar_inte_ett_giltigt_personnummer(self):
        # Maskeras som orgnr, men klassas ändå aldrig som personnummer (och kan
        # därför inte allowlistas via är_giltigt_personnummer-spärren).
        assert är_giltigt_personnummer(ORGNR_UTAN_SEP) is False

    def test_maskerar_orgnr_i_chattmeddelande(self):
        maskerat = maskera_chattmeddelande(f"Kolla org {ORGNR_UTAN_SEP}").text
        assert ORGNR_UTAN_SEP not in maskerat
        assert "ORGANISATIONSNUMMER_" in maskerat


# ---------------------------------------------------------------------------
# Lager 2b — E-post / telefon / adress / bankgiro (fynd 5)
# ---------------------------------------------------------------------------

class TestLager2bFritextmonster:
    def test_maskerar_epost(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="6250", belopp=-100.0,
                    transtext="Faktura anna.andersson@gmail.com")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "anna.andersson@gmail.com" not in trans.transtext
        assert "EPOST_" in trans.transtext

    @pytest.mark.parametrize("telefon", ["070-123 45 67", "+46 70 123 45 67", "0701234567"])
    def test_maskerar_telefon(self, telefon):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="6250", belopp=-100.0,
                    transtext=f"Ring Anna {telefon}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert telefon not in trans.transtext
        assert "TELEFON_" in trans.transtext

    def test_maskerar_gatuadress_i_fritext(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="5010", belopp=-8000.0,
                    transtext="Hyra lgh Storgatan 12")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Storgatan 12" not in trans.transtext
        assert "ADRESS_" in trans.transtext

    def test_maskerar_bankgiro_och_iban(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="1930", belopp=-500.0,
                    transtext="Betalning BG 5050-1055 IBAN SE45 5000 0000 0583 9825 7466")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "5050-1055" not in trans.transtext
        assert "SE45 5000 0000 0583 9825 7466" not in trans.transtext
        assert "BANKGIRO_" in trans.transtext

    def test_iban_maskeras_som_en_helhet_inte_kannibaliserat_av_telefon(self):
        # Regression: telefon-mönstret åt förr upp IBAN:ets sifferblock och
        # lämnade "SE45 5000 0000" i klartext. IBAN maskeras nu FÖRST, som ETT
        # BANKGIRO-token, utan något TELEFON-token eller kvarlämnad SE-prefix.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="1930", belopp=-500.0,
                    transtext="Överföring till SE45 5000 0000 0583 9825 7466")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "SE45" not in trans.transtext
        assert "5000 0000" not in trans.transtext
        assert "TELEFON_" not in trans.transtext
        assert trans.transtext == "Överföring till BANKGIRO_1"

    def test_belopp_med_bindestreck_ar_inte_bankgiro(self):
        # Ett vanligt belopp/intervall får inte falskt maskeras som bankgiro.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="3010", belopp=100.0,
                    transtext="Rabatt 10-20 procent")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert trans.transtext == "Rabatt 10-20 procent"

    def test_fakturanummer_pa_bankgiroform_maskeras_inte(self):
        # "2026-0456" har bankgiroformen NNNN-NNNN men fel Luhn-kontrollsiffra —
        # ett fakturanummer, inte ett bankgiro. Får inte falskt maskeras.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="1930", belopp=-500.0,
                    transtext="Betalning faktura 2026-0456")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert trans.transtext == "Betalning faktura 2026-0456"

    def test_belopp_med_tusentalsavgransare_ar_inte_telefon(self):
        # Omgranskningens fynd 2: "1 000 000 000" åts förr upp som "1 TELEFON_n"
        # (nollgrupperna matchade riktnummer+grupper). Siffran efter den ledande
        # nollan måste nu vara 1-9 — inget svenskt riktnummer börjar "00".
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="3010", belopp=100.0,
                    transtext="Omsättning 1 000 000 000 kr i år")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert trans.transtext == "Omsättning 1 000 000 000 kr i år"

    def test_arsprefix_foljt_av_tal_ar_inte_telefon(self):
        # Omgranskningens fynd 2: i "Perioden 2026-07 22 000 kr" matchade förr
        # "07 22 000" som telefon. Lookbehind förbjuder nu ett föregående "-".
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="3010", belopp=100.0,
                    transtext="Perioden 2026-07 22 000 kr")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert trans.transtext == "Perioden 2026-07 22 000 kr"

    @pytest.mark.parametrize("adress", [
        "Karlaplan 5", "Storallén 12", "Björkstigen 4", "Strandpromenaden 2",
        "Fiskebacken 7", "Industrileden 30",
    ])
    def test_maskerar_bredare_gatusuffix(self, adress):
        # Omgranskningens fynd 3: allén/stigen/backen/plan/leden/promenaden
        # m.fl. passerade förr — suffixlistan var för smal.
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="5010", belopp=-8000.0,
                    transtext=f"Hyra {adress}")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert adress not in trans.transtext
        assert "ADRESS_" in trans.transtext

    def test_maskerar_postbox(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="6250", belopp=-100.0,
                    transtext="Faktureringsadress Box 1234, Göteborg")]),
        ])
        resultat = maskera_siefil(fil)
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Box 1234" not in trans.transtext
        assert "ADRESS_" in trans.transtext


# ---------------------------------------------------------------------------
# Diakritiska tecken i namn (omgranskningens fynd 4)
# ---------------------------------------------------------------------------

class TestDiakritiskaNamn:
    """[a-zåäö] täckte förr inte é/è/ü/æ/ø m.fl. — André, Linnéa, Renée
    passerade både Lager 3b (flaggning) och kontonamnsmaskeringen omaskerade."""

    def test_lager3b_flaggar_namn_med_diakrit(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                    transtext="Kurs André Cederkvist")]),
        ])
        resultat = maskera_siefil(fil)
        assert any(
            behov.misstänkt_text == "André Cederkvist"
            for behov in resultat.maskeringsbehov
        )

    def test_kontonamn_med_diakrit_automaskeras(self):
        ut = maskera_kontonamn("Fordran André Linnéa")
        assert "André" not in ut
        assert "Linnéa" not in ut
        assert "PERSON_" in ut

    def test_versal_diakrit_inleder_namn(self):
        # Även ett namn som BÖRJAR med diakritversal ("Édith") ska fångas.
        ut = maskera_kontonamn("Lån Édith Söderström")
        assert "Édith" not in ut
        assert "PERSON_" in ut


# ---------------------------------------------------------------------------
# Fynd A — Kontonamn maskeras innan de når AI
# ---------------------------------------------------------------------------

class TestFyndAKontonamn:
    def test_maskerar_personnamn_i_kontonamn(self):
        fil = _bygg_siefil(konton={
            "7010": Konto(kontonr="7010", namn="Lön Anna Andersson"),
            "1910": Konto(kontonr="1910", namn="Kassa"),
        })
        resultat = maskera_siefil(fil)
        maskerade = resultat.maskerad_siefil.konton
        assert "Anna Andersson" not in maskerade["7010"].namn
        assert "PERSON_" in maskerade["7010"].namn
        # Kontonumret (nyckeln) rörs aldrig.
        assert maskerade["7010"].kontonr == "7010"
        # Standardkontonamn utan PII lämnas orört.
        assert maskerade["1910"].namn == "Kassa"

    def test_kontonamn_ger_inte_maskeringsbehov(self):
        # Kontoplanen har ingen spärr per verifikation — okänt namn i ett
        # kontonamn auto-maskeras (fail-closed), flaggas ALDRIG för granskning.
        fil = _bygg_siefil(konton={
            "2893": Konto(kontonr="2893", namn="Skuld till aktieägaren Erik Svensson"),
        })
        resultat = maskera_siefil(fil)
        assert resultat.maskeringsbehov == []
        assert "Erik Svensson" not in resultat.maskerad_siefil.konton["2893"].namn

    def test_personnummer_i_kontonamn_maskeras(self):
        fil = _bygg_siefil(konton={
            "1685": Konto(kontonr="1685", namn=f"Fordran {GILTIGT_PERSONNUMMER_KORT}"),
        })
        resultat = maskera_siefil(fil)
        assert GILTIGT_PERSONNUMMER_KORT not in resultat.maskerad_siefil.konton["1685"].namn
        assert "PERSONNUMMER_" in resultat.maskerad_siefil.konton["1685"].namn

    def test_fristaende_maskera_kontonamn(self):
        assert maskera_kontonamn("Kassa") == "Kassa"
        maskerat = maskera_kontonamn("Lön Anna Andersson")
        assert "Anna Andersson" not in maskerat
        assert "PERSON_" in maskerat


# ---------------------------------------------------------------------------
# Svaghet 4 — #GEN-signatur och objekt utanför personaldimension
# ---------------------------------------------------------------------------

class TestSvaghet4SignOchObjekt:
    def test_maskerar_namn_i_genererad_sign_via_referenslista(self):
        fil = _bygg_siefil()
        fil.genererad_sign = "Anna Andersson"
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        assert resultat.maskerad_siefil.genererad_sign != "Anna Andersson"
        assert "PERSON_" in resultat.maskerad_siefil.genererad_sign

    def test_initialer_i_genererad_sign_passerar(self):
        fil = _bygg_siefil()
        fil.genererad_sign = "AA"
        resultat = maskera_siefil(fil)
        assert resultat.maskerad_siefil.genererad_sign == "AA"

    def test_maskerar_personnummer_i_genererad_sign(self):
        fil = _bygg_siefil()
        fil.genererad_sign = GILTIGT_PERSONNUMMER_LANG
        resultat = maskera_siefil(fil)
        assert resultat.maskerad_siefil.genererad_sign != GILTIGT_PERSONNUMMER_LANG
        assert "PERSONNUMMER_" in resultat.maskerad_siefil.genererad_sign

    def test_maskerar_dolt_namn_i_ickepersonalobjekt(self):
        fil = _bygg_siefil(
            dimensioner={6: Dimension(dimensionsnr=6, namn="Projekt")},
            objektregister={
                (6, "P1"): Objekt(dimensionsnr=6, objektnr="P1", namn="Ombyggnad Anna Andersson"),
            },
        )
        resultat = maskera_siefil(fil)
        objekt = resultat.maskerad_siefil.objektregister[(6, "P1")]
        assert "Anna Andersson" not in objekt.namn
        assert "PERSON_" in objekt.namn


# ---------------------------------------------------------------------------
# Fynd B — maskering av chattmeddelanden innan de når AI:n
# ---------------------------------------------------------------------------

class TestChattmeddelande:
    def test_maskerar_personnummer_i_chatt(self):
        meddelande = f"Skapa ROT-faktura åt kunden, personnummer {GILTIGT_PERSONNUMMER_KORT}"
        resultat = maskera_chattmeddelande(meddelande)
        assert GILTIGT_PERSONNUMMER_KORT not in resultat.text
        assert "PERSONNUMMER_" in resultat.text
        assert resultat.blockerad is False

    def test_maskerar_personnummer_utan_separator_i_chatt(self):
        resultat = maskera_chattmeddelande(f"pnr {GILTIGT_PNR_UTAN_SEP_10}")
        assert GILTIGT_PNR_UTAN_SEP_10 not in resultat.text
        assert "PERSONNUMMER_" in resultat.text

    def test_tillampar_maskeringsliggaren(self):
        liggare = {"Anna Andersson": "[PERSON 1]"}
        resultat = maskera_chattmeddelande("Fakturera Anna Andersson", liggare)
        assert "Anna Andersson" not in resultat.text
        assert "[PERSON 1]" in resultat.text
        # Namnet finns i liggaren -> avidentifierat, alltså inte blockerat.
        assert resultat.blockerad is False

    def test_kant_namn_ur_referenslistan_maskeras_lager3a(self):
        # M1: Lager 3a körs nu även på chattmeddelanden — ett känt namn
        # auto-maskeras deterministiskt (blockerar inte).
        resultat = maskera_chattmeddelande(
            "Fakturera Anna Andersson", referenslista={"Anna Andersson"}
        )
        assert "Anna Andersson" not in resultat.text
        assert "PERSON_" in resultat.text
        assert resultat.blockerad is False

    def test_okant_versalnamn_blockeras_failclosed(self):
        # M1: ett OKÄNT namn (varken i liggare eller referenslista) tokeniseras
        # inte (skulle förvanska legitima frågor) utan BLOCKERAR sändningen —
        # det avgörs lokalt, den råa texten lämnar aldrig datorn.
        meddelande = "Vad tycker du om Xavier Zetterlund som kund?"
        resultat = maskera_chattmeddelande(meddelande)
        assert resultat.blockerad is True
        assert "Xavier Zetterlund" in resultat.misstänkta_namn

    def test_okant_namn_forsvinner_nar_det_finns_i_referenslistan(self):
        # Samma mening, men nu är namnet känt -> Lager 3a maskerar, ingen block.
        meddelande = "Vad tycker du om Xavier Zetterlund som kund?"
        resultat = maskera_chattmeddelande(
            meddelande, referenslista={"Xavier Zetterlund"}
        )
        assert resultat.blockerad is False
        assert "Xavier Zetterlund" not in resultat.text

    def test_tomt_meddelande_ger_tomt_och_inte_blockerat(self):
        resultat = maskera_chattmeddelande("")
        assert resultat.text == ""
        assert resultat.blockerad is False

    def test_prosa_sandningsbar_ar_none_medan_maskeringsbehov_vantar(self):
        """prosa är inte knuten till en enskild verifikation, så den
        behöver sin egen fail-closed-spärr (prosa_sandningsbar) utöver
        blockerade_verifikationer."""
        fil = _bygg_siefil(prosa="Kommentar om Erik Svensson från revisionen")
        resultat = maskera_siefil(fil, referenslista=set())
        assert resultat.prosa_sandningsbar is None

    def test_prosa_sandningsbar_fylls_i_nar_inget_vantar(self):
        fil = _bygg_siefil(prosa="Ingen känslig information här")
        resultat = maskera_siefil(fil, referenslista=set())
        assert resultat.prosa_sandningsbar == "Ingen känslig information här"

    def test_prosa_sandningsbar_havs_efter_granskning(self):
        fil = _bygg_siefil(prosa="Kommentar om Erik Svensson från revisionen")
        resultat = maskera_siefil(fil, referenslista=set())
        assert resultat.prosa_sandningsbar is None

        behov = next(b for b in resultat.maskeringsbehov if b.fältnamn == "prosa")
        behov.status = "bekräftad_pii"
        uppdaterat = uppdatera_efter_granskning(resultat, [behov])

        assert uppdaterat.prosa_sandningsbar is not None
        assert "Erik Svensson" not in uppdaterat.prosa_sandningsbar
        assert "PERSON_" in uppdaterat.prosa_sandningsbar


# ---------------------------------------------------------------------------
# Pseudonymisering — kodnyckel och demaskering
# ---------------------------------------------------------------------------

class TestPseudonymisering:
    def test_demaskera_text_aterstaller_korrekt_varde(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                    transtext="Lön Anna Andersson juni")]),
        ])
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        maskerad_text = resultat.maskerad_siefil.verifikationer[0].transaktioner[0].transtext
        återställd = demaskera_text(maskerad_text, resultat.kodnyckel)
        assert återställd == "Lön Anna Andersson juni"

    def test_kodnyckel_skrivs_aldrig_till_disk(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        filer_fore = set(tmp_path.rglob("*"))
        fil = _bygg_siefil(
            företagsnamn="Andersson Bygg AB",
            verifikationer=[
                Verifikation(serie="A", vernr="1", verdatum="20260615",
                    transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                        transtext="Lön Anna Andersson juni")]),
            ],
        )
        maskera_siefil(fil, referenslista=_bygg_referenslista())
        filer_efter = set(tmp_path.rglob("*"))
        assert filer_efter == filer_fore, "Maskeringskörningen skapade oväntade filer på disk"

    def test_tokens_ar_typade_per_kategori(self):
        fil = _bygg_siefil(
            företagsnamn="Andersson Bygg AB",
            verifikationer=[
                Verifikation(serie="A", vernr="1", verdatum="20260615",
                    transaktioner=[Transaktion(kontonr="7010", belopp=25000.0,
                        transtext=f"Lön Anna Andersson {GILTIGT_PERSONNUMMER_KORT}")]),
            ],
        )
        resultat = maskera_siefil(fil, referenslista=_bygg_referenslista())
        alla_tokens = list(resultat.kodnyckel.keys())
        assert any(t.startswith("BOLAG_") for t in alla_tokens)
        assert any(t.startswith("PERSON_") for t in alla_tokens)
        assert any(t.startswith("PERSONNUMMER_") for t in alla_tokens)
        # Räknarna är oberoende per typ -- BOLAG_1 och PERSON_1 kan
        # samexistera utan kollision
        assert "BOLAG_1" in alla_tokens
        assert "PERSON_1" in alla_tokens


# ---------------------------------------------------------------------------
# Integrationstest mot exempelfilen
# ---------------------------------------------------------------------------

class TestIntegrationMotExempelfil:
    def test_maskera_hela_exempelfilen_utan_krasch(self):
        fil = parse_sie4(SAMPLE_FIL)
        resultat = maskera_siefil(fil, referenslista=set())
        assert resultat is not None

    def test_ingen_orgnr_eller_fnamn_kvar_i_maskerad_output(self):
        fil = parse_sie4(SAMPLE_FIL)
        ursprungligt_orgnr = fil.orgnr
        ursprungligt_namn = fil.företagsnamn
        resultat = maskera_siefil(fil, referenslista=set())

        # Bygg en enkel textrepresentation av hela den maskerade filen
        # för att söka igenom den, samma facit-princip som Lager 1-testerna.
        delar = [
            resultat.maskerad_siefil.företagsnamn,
            resultat.maskerad_siefil.orgnr,
        ]
        for verifikation in resultat.maskerad_siefil.verifikationer:
            delar.append(verifikation.vertext)
            for transaktion in verifikation.transaktioner:
                delar.append(transaktion.transtext)
        helhet = " ".join(del_ for del_ in delar if del_)

        assert ursprungligt_orgnr not in helhet
        assert ursprungligt_namn not in helhet


# ---------------------------------------------------------------------------
# Undantagslista (allowlist) — strängar en människa bedömt som icke-PII
#
# Lagrets ENDA fail-open-mekanism. Den verkar uteslutande på lager 3b:s
# regex-gissningar; lager 2 (personnummer) körs innan och kan aldrig undantas.
# ---------------------------------------------------------------------------

class TestUndantagslista:
    def _fil_med_namn(self, text="Kundfaktura till Danske Disks"):
        return _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="3010", belopp=-500.0,
                    transtext=text)]),
        ])

    def test_utan_undantagslista_flaggas_namnet_som_forut(self):
        resultat = maskera_siefil(self._fil_med_namn())
        assert [b.misstänkt_text for b in resultat.maskeringsbehov] == ["Danske Disks"]

    def test_undantaget_namn_flaggas_inte(self):
        resultat = maskera_siefil(
            self._fil_med_namn(), undantagslista={"Danske Disks"}
        )
        assert resultat.maskeringsbehov == []

    def test_undantaget_namn_blockerar_inte_verifikationen(self):
        """Poängen med undantagslistan: verifikationen ska flyta vidare direkt,
        utan att någon människa behöver klicka bort flaggan igen."""
        resultat = maskera_siefil(
            self._fil_med_namn(), undantagslista={"Danske Disks"}
        )
        assert ("A", "1") not in resultat.blockerade_verifikationer
        assert len(resultat.sandningsbara_verifikationer) == 1

    def test_matchningen_ar_skiftlagesokanslig_och_whitespace_tolerant(self):
        resultat = maskera_siefil(
            self._fil_med_namn("Kundfaktura till DANSKE   DISKS"),
            undantagslista={"danske disks"},
        )
        assert resultat.maskeringsbehov == []

    def test_undantag_tystar_inte_andra_namn(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="3010", belopp=-500.0,
                    transtext="Kundfaktura till Danske Disks")]),
            Verifikation(serie="A", vernr="2", verdatum="20260616",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
        ])
        resultat = maskera_siefil(fil, undantagslista={"Danske Disks"})
        assert [b.misstänkt_text for b in resultat.maskeringsbehov] == ["Erik Svensson"]
        assert ("A", "2") in resultat.blockerade_verifikationer

    def test_undantag_kan_inte_slappa_igenom_ett_personnummer(self):
        """Lager 2 maskerar personnummer INNAN flaggningen, så undantagslistan
        får aldrig någon chans att tysta dem — oavsett vad som står i den."""
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=100.0,
                    transtext=f"Utbetalning {GILTIGT_PERSONNUMMER_LANG}")]),
        ])
        resultat = maskera_siefil(fil, undantagslista={GILTIGT_PERSONNUMMER_LANG})
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert GILTIGT_PERSONNUMMER_LANG not in trans.transtext
        assert "PERSONNUMMER_" in trans.transtext


# ---------------------------------------------------------------------------
# Granskningens returkontrakt — behovslistan speglar vad som återstår
#
# Regression: uppdatera_efter_granskning returnerade förr originallistan
# oförändrad och kontrollerade blockeringen mot den. UI:t bygger KOPIOR
# (dataclasses.replace) medan testerna muterar på plats, så via UI-vägen såg
# kontrollen alltid "väntar_granskning" — blockeringen hävdes aldrig och
# granskade rader låg kvar i åtgärdslistan för alltid.
# ---------------------------------------------------------------------------

class TestGranskningReturkontrakt:
    def _resultat(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
        ])
        return maskera_siefil(fil, referenslista=set())

    def test_kopierade_behov_haver_blockeringen(self):
        """UI-vägen: granskade behov är KOPIOR, inte de ursprungliga objekten."""
        resultat = self._resultat()
        kopia = replace(resultat.maskeringsbehov[0], status="bekräftad_pii")

        uppdaterat = uppdatera_efter_granskning(resultat, [kopia])

        assert ("A", "1") not in uppdaterat.blockerade_verifikationer
        assert len(uppdaterat.sandningsbara_verifikationer) == 1

    def test_granskad_rad_forsvinner_ur_behovslistan(self):
        resultat = self._resultat()
        kopia = replace(resultat.maskeringsbehov[0], status="godkänd_ej_pii")

        uppdaterat = uppdatera_efter_granskning(resultat, [kopia])

        assert all(b.status != "väntar_granskning" for b in uppdaterat.maskeringsbehov)

    def test_avvaktande_rad_ligger_kvar_och_fortsatter_blockera(self):
        """Tredje läget: användaren tog inte ställning. Raden ska INTE
        försvinna och verifikationen ska förbli blockerad."""
        resultat = self._resultat()
        oförändrad = replace(resultat.maskeringsbehov[0], status="väntar_granskning")

        uppdaterat = uppdatera_efter_granskning(resultat, [oförändrad])

        assert len(uppdaterat.maskeringsbehov) == 1
        assert uppdaterat.maskeringsbehov[0].status == "väntar_granskning"
        assert ("A", "1") in uppdaterat.blockerade_verifikationer

    def test_ersattningstext_styr_vad_som_maskeras(self):
        """Användaren rättar till bara förnamnet: det är ersättningstext som
        söks upp och ersätts, medan misstänkt_text bevarar radens identitet."""
        resultat = self._resultat()
        kopia = replace(
            resultat.maskeringsbehov[0], status="bekräftad_pii", ersättningstext="Erik"
        )

        uppdaterat = uppdatera_efter_granskning(resultat, [kopia])

        trans = uppdaterat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Erik" not in trans.transtext
        assert "Svensson" in trans.transtext  # bara förnamnet maskerades
        assert ("A", "1") not in uppdaterat.blockerade_verifikationer

    def test_blandad_omgang_haver_bara_det_som_beslutats(self):
        fil = _bygg_siefil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7690", belopp=500.0,
                    transtext="Kurs Erik Svensson")]),
            Verifikation(serie="A", vernr="2", verdatum="20260616",
                transaktioner=[Transaktion(kontonr="7690", belopp=300.0,
                    transtext="Utlägg Anna Bergström")]),
        ])
        resultat = maskera_siefil(fil, referenslista=set())
        erik = next(b for b in resultat.maskeringsbehov if b.misstänkt_text == "Erik Svensson")

        uppdaterat = uppdatera_efter_granskning(
            resultat, [replace(erik, status="bekräftad_pii")]
        )

        assert ("A", "1") not in uppdaterat.blockerade_verifikationer
        assert ("A", "2") in uppdaterat.blockerade_verifikationer
        kvar = [b.misstänkt_text for b in uppdaterat.maskeringsbehov
                if b.status == "väntar_granskning"]
        assert kvar == ["Anna Bergström"]


# ---------------------------------------------------------------------------
# Lager 3b v2 — strängstart, delad detektor, ekonomisk stopplista
# ---------------------------------------------------------------------------

def _transtext_resultat(text: str, referenslista=None):
    """Kör ETT transtext-fält genom maskera_siefil och returnerar resultatet."""
    fil = _bygg_siefil(verifikationer=[
        Verifikation(serie="A", vernr="1", verdatum="20260615",
            transaktioner=[Transaktion(kontonr="7690", belopp=100.0, transtext=text)]),
    ])
    return maskera_siefil(
        fil, referenslista=(set() if referenslista is None else referenslista)
    )


def _har_behov(resultat, misstänkt: str) -> bool:
    return any(b.misstänkt_text == misstänkt for b in resultat.maskeringsbehov)


class TestLager3bStrangstart:
    """Kärnluckan: ett okänt namn allra FÖRST i en sträng måste fångas
    (blockeras för fritext/chatt, tokenmaskeras för kontonamn)."""

    def test_okant_namn_i_strangstart_transtext_blockerar(self):
        resultat = _transtext_resultat("Xerxes Qoolio är sen")
        assert _har_behov(resultat, "Xerxes Qoolio")
        assert ("A", "1") in resultat.blockerade_verifikationer

    def test_okant_namn_i_mitten(self):
        resultat = _transtext_resultat("faktura Xerxes Qoolio betald")
        assert _har_behov(resultat, "Xerxes Qoolio")

    def test_okant_namn_i_slutet(self):
        resultat = _transtext_resultat("Betalning mottagen Xerxes Qoolio")
        assert _har_behov(resultat, "Xerxes Qoolio")

    def test_treordsnamn_i_strangstart(self):
        resultat = _transtext_resultat("Karl Gustav Nilsson närvarade")
        assert _har_behov(resultat, "Karl Gustav Nilsson")

    def test_svenska_tecken(self):
        resultat = _transtext_resultat("André Ödqvist deltog")
        assert _har_behov(resultat, "André Ödqvist")

    def test_bindestreck_i_fornamn(self):
        resultat = _transtext_resultat("Anna-Lena Björk ringde")
        assert _har_behov(resultat, "Anna-Lena Björk")

    def test_bindestreck_i_efternamn(self):
        resultat = _transtext_resultat("Sven Björk-Ström kom")
        assert _har_behov(resultat, "Sven Björk-Ström")

    def test_apostrof_i_efternamn(self):
        resultat = _transtext_resultat("Anna O'Brien betalade")
        assert _har_behov(resultat, "Anna O'Brien")

    def test_kant_3a_namn_maskeras_och_blockerar_inte(self):
        # Lager 3a körs FÖRE 3b: ett känt namn auto-maskeras och blockerar inte,
        # även i strängstart.
        resultat = _transtext_resultat(
            "Xerxes Qoolio ringde", referenslista={"Xerxes Qoolio"}
        )
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Xerxes Qoolio" not in trans.transtext
        assert "PERSON_" in trans.transtext
        assert resultat.maskeringsbehov == []
        assert resultat.blockerade_verifikationer == set()

    def test_okant_namn_strangstart_chatt_blockerar(self):
        resultat = maskera_chattmeddelande("Xerxes Qoolio är sen med betalning")
        assert resultat.blockerad is True
        assert "Xerxes Qoolio" in resultat.misstänkta_namn

    def test_kontonamn_bart_namn_strangstart_maskeras(self):
        maskerat = maskera_kontonamn("Xerxes Qoolio")
        assert "Xerxes Qoolio" not in maskerat
        assert "PERSON_" in maskerat

    def test_kontonamn_endast_ett_misstankt_par(self):
        # Ett kontonamn med exakt ett misstänkt namnpar: namnet maskeras,
        # det ekonomiska ram-ordet bevaras.
        maskerat = maskera_kontonamn("Lön Xerxes Qoolio")
        assert "Xerxes Qoolio" not in maskerat
        assert "PERSON_" in maskerat
        assert maskerat.startswith("Lön ")


class TestLager3bEkonomiskaRubriker:
    """Falsk-positiv-vakt: vanliga ekonomiska/BAS-rubriker (versalpar) får
    ALDRIG bli 3b-träffar, ens i strängstart."""

    RUBRIKER = [
        "Ingående Balans", "Utgående Balans", "Eget Kapital", "Årets Resultat",
        "Fria Reserver", "Bundna Reserver", "Upplupna Kostnader",
        "Förutbetalda Intäkter", "Övriga Kostnader", "Ackumulerade Avskrivningar",
        "Obeskattade Reserver", "Balanserat Resultat",
    ]

    @pytest.mark.parametrize("rubrik", RUBRIKER)
    def test_ekonomisk_rubrik_flaggas_inte(self, rubrik):
        resultat = _transtext_resultat(rubrik)
        assert resultat.maskeringsbehov == []
        assert resultat.blockerade_verifikationer == set()

    def test_ekonomisk_rubrik_i_chatt_blockerar_inte(self):
        resultat = maskera_chattmeddelande("Vad betyder Eget Kapital i balansräkningen?")
        assert resultat.blockerad is False

    def test_ram_ord_plus_namn_flaggar_bara_namnet(self):
        # 'Ingående' är ram; ett namn intill ska ändå fångas, men bara namnet.
        resultat = _transtext_resultat("Kassa Xerxes Qoolio")
        assert _har_behov(resultat, "Xerxes Qoolio")


class TestEkonomiskaTermerModul:
    def test_version_ar_satt(self):
        import ekonomiska_termer
        assert isinstance(ekonomiska_termer.VERSION, int)
        assert ekonomiska_termer.VERSION >= 1

    def test_kanda_rubrikord_ingar(self):
        import ekonomiska_termer
        for ord_ in ["Ingående", "Balans", "Eget", "Kapital", "Resultat", "Kassa"]:
            assert ekonomiska_termer.ar_ekonomisk_term(ord_)

    def test_vanliga_efternamn_ar_aldrig_stoppord(self):
        # Kritiskt: ett efternamn i stopplistan skulle tysta ett verkligt namn.
        import ekonomiska_termer
        for namn in ["Andersson", "Svensson", "Björk", "Nilsson", "Berg", "Lund",
                     "Qoolio", "Cederkvist"]:
            assert not ekonomiska_termer.ar_ekonomisk_term(namn)

    def test_skiftlagesokanslig(self):
        import ekonomiska_termer
        assert ekonomiska_termer.ar_ekonomisk_term("BALANS")
        assert ekonomiska_termer.ar_ekonomisk_term("balans")


# ---------------------------------------------------------------------------
# Paket A — Nya säkerhetsluckor: Lager 3c, Unicode, Samordningsnummer,
#           Kortnummer, Referenslöp & Genitiv, samt Delade verktyg
# ---------------------------------------------------------------------------

class TestLager3cSkriftvakt:
    def test_kinesiskt_namn_blockeras_i_chatt(self):
        resultat = maskera_chattmeddelande("Betalat till 王小明 idag")
        assert resultat.blockerad is True
        assert "王小明" in resultat.misstänkta_namn

    def test_arabiskt_namn_blockeras_i_chatt(self):
        resultat = maskera_chattmeddelande("Avser محمد علي konsulter")
        assert resultat.blockerad is True
        assert "محمد" in resultat.misstänkta_namn and "علي" in resultat.misstänkta_namn

    def test_hebreiskt_och_thailandskt_namn_blockeras(self):
        res1 = maskera_chattmeddelande("Faktura från ישראל ישראלי")
        assert res1.blockerad is True
        res2 = maskera_chattmeddelande("Leverantör สมชาย ใจดี")
        assert res2.blockerad is True

    def test_obedombar_skrift_maskeras_i_kontonamn(self):
        namn = maskera_kontonamn("Lön 王小明")
        assert "王小明" not in namn
        assert "MOTPART_" in namn

    def test_obedombar_skrift_blockerar_verifikat(self):
        resultat = _transtext_resultat("Utbetalning 王小明 konsult")
        assert _har_behov(resultat, "王小明")
        assert ("A", "1") in resultat.blockerade_verifikationer

    def test_siffror_och_skiljetecken_ar_inte_obedombara(self):
        resultat = maskera_chattmeddelande("Faktura 12345! - betald (100 kr)")
        assert resultat.blockerad is False
        assert not resultat.misstänkta_namn

    def test_kyrilliskt_namn_fangas_av_3b_inte_3c(self):
        resultat = maskera_chattmeddelande("Betalt till Иван Петров idag")
        assert resultat.blockerad is True
        assert "Иван Петров" in resultat.misstänkta_namn
        namn = maskera_kontonamn("Lön Иван Петров")
        assert "PERSON_" in namn
        assert "MOTPART_" not in namn


class TestUnicodeTeckenklasser:
    def test_polskt_efternamn_maskeras_helt(self):
        namn = maskera_kontonamn("Jan Wiśniewski")
        assert "Wiśniewski" not in namn
        assert "śniewski" not in namn
        assert "PERSON_" in namn

    def test_tjeckiskt_och_baltiskt_namn_maskeras_helt(self):
        namn = maskera_kontonamn("Tomáš Dvořák")
        assert "Tomáš Dvořák" not in namn
        assert "PERSON_" in namn

    def test_grekiskt_namn_maskeras(self):
        namn = maskera_kontonamn("Lön Γεώργιος Παπαδόπουλος")
        assert "Γεώργιος Παπαδόπουλος" not in namn
        assert "PERSON_" in namn

    def test_svenska_namn_oforandrade(self):
        namn = maskera_kontonamn("Anna Andersson")
        assert "PERSON_" in namn
        assert "Andersson" not in namn


class TestSamordningsnummer:
    def test_samordningsnummer_utan_separator_maskeras(self):
        pnr_samord = "8506751232"
        res = maskera_chattmeddelande(f"Avser {pnr_samord} arvodet")
        assert "PERSONNUMMER_" in res.text
        assert pnr_samord not in res.text

    def test_samordningsnummer_med_separator_maskeras(self):
        pnr_samord = "850675-1232"
        res = maskera_chattmeddelande(f"Avser {pnr_samord} arvodet")
        assert "PERSONNUMMER_" in res.text
        assert pnr_samord not in res.text

    def test_orgnr_klassas_fortfarande_som_orgnr(self):
        orgnr = "556000-0001"
        res = maskera_chattmeddelande(f"Bolag {orgnr} betalade")
        assert "ORGANISATIONSNUMMER_" in res.text or "BOLAG_" in res.text

    def test_belopp_med_tio_siffror_lamnas_orort(self):
        belopp = "1000000000"
        res = maskera_chattmeddelande(f"Summa {belopp} kr")
        assert belopp in res.text


class TestKortnummer:
    def test_grupperat_kortnummer_maskeras(self):
        kort = "4532 1123 4567 8900"
        res = maskera_chattmeddelande(f"Kort {kort} debiterat")
        assert "KORTNUMMER_" in res.text
        assert "4532" not in res.text

    def test_obrutet_kortnummer_maskeras(self):
        kort = "4532112345678900"
        res = maskera_chattmeddelande(f"Kort {kort} debiterat")
        assert "KORTNUMMER_" in res.text
        assert kort not in res.text

    def test_bindestrecksseparerat_kortnummer_maskeras(self):
        kort = "4532-1123-4567-8900"
        res = maskera_chattmeddelande(f"Kort {kort} debiterat")
        assert "KORTNUMMER_" in res.text
        assert "4532" not in res.text

    def test_luhn_ogiltigt_kortnummer_lamnas_orort(self):
        kort = "4532 1123 4567 8905"
        res = maskera_chattmeddelande(f"Ref {kort} angavs")
        assert "KORTNUMMER_" not in res.text
        assert kort in res.text

    def test_stora_belopp_lamnas_orort(self):
        belopp = "1 000 000 000"
        res = maskera_chattmeddelande(f"Total {belopp} kr")
        assert belopp in res.text
        assert "KORTNUMMER_" not in res.text

    def test_fakturanummer_lamnas_orort(self):
        fakt = "2026-0456"
        res = maskera_chattmeddelande(f"Faktura {fakt} betald")
        assert fakt in res.text
        assert "KORTNUMMER_" not in res.text


class TestReferenslop:
    def test_fornamn_och_efternamn_far_ETT_token(self):
        res = maskera_chattmeddelande("Prata med Anna Andersson snarast", referenslista={"Anna Andersson"})
        assert "PERSON_1 PERSON_2" not in res.text
        assert "PERSON_1" in res.text
        assert "Anna" not in res.text
        assert "Andersson" not in res.text

    def test_tva_olika_personer_far_olika_token(self):
        res = maskera_chattmeddelande("Anna Andersson och Björn Bengtsson", referenslista={"Anna Andersson", "Björn Bengtsson"})
        assert "PERSON_1" in res.text and "PERSON_2" in res.text
        assert res.text.count("PERSON_") == 2

    def test_genitivform_maskeras(self):
        res = maskera_chattmeddelande("Avser Anna Anderssons utlägg", referenslista={"Anna Andersson"})
        assert "Anna" not in res.text
        assert "Anderssons" not in res.text
        assert "PERSON_1" in res.text

    def test_lars_trunkeras_inte_till_lar(self):
        res = maskera_chattmeddelande("Lars ringde idag", referenslista={"Lars"})
        assert "PERSON_1" in res.text
        assert "Lar" not in res.text

    def test_larsson_styckas_inte_av_lars(self):
        res = maskera_chattmeddelande("Prata med Erik Larsson", referenslista={"Lars", "Erik Larsson"})
        assert "Larsson" not in res.text
        assert "PERSON_1" in res.text

    def test_flerordigt_listnamn_med_dubbelt_mellanslag(self):
        res = maskera_chattmeddelande("Avser Anna   Andersson", referenslista={"Anna Andersson"})
        assert "Anna" not in res.text
        assert "Andersson" not in res.text
        assert "PERSON_1" in res.text


class TestDeladeVerktyg:
    def test_skapa_kontonamnsmaskerare_delar_generator(self):
        from sekretesslager import skapa_kontonamnsmaskerare
        maskera = skapa_kontonamnsmaskerare()
        n1 = maskera("Lön Anna Andersson")
        n2 = maskera("Utlägg Anna Andersson")
        n3 = maskera("Arvode Björn Bengtsson")
        assert "PERSON_1" in n1
        assert "PERSON_1" in n2
        assert "PERSON_2" in n3

    def test_innehaller_kant_personnamn(self):
        from sekretesslager import innehaller_kant_personnamn
        ref = {"Anna Andersson", "Björn Bengtsson"}
        assert innehaller_kant_personnamn("Avser Anna Andersson AB", ref) is True
        assert innehaller_kant_personnamn("Avser Anna Anderssons utlägg", ref) is True
        assert innehaller_kant_personnamn("Avser Scandinavian Photo AB", ref) is False
        assert innehaller_kant_personnamn("Avser 王小明 konsult", ref) is True

