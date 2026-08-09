"""Tester för namnreferens.py — referenslistan (Lager 3a) som fynd 6 kopplar in.

Fokus: att den inbyggda listan finns och innehåller vanliga namn, att en lokal
extra-fil unionsläggs, att en saknad/trasig fil är fail-safe, och att listan
faktiskt biter i sekretesslagret (auto-maskerar utan att flagga för granskning).
"""

from __future__ import annotations

from decimal import Decimal

from domain_model import SIEFil, Transaktion, Verifikation
from namnreferens import STANDARDNAMN, las_namnreferens
from sekretesslager import maskera_siefil


class TestStandardnamn:
    def test_innehaller_vanliga_efternamn(self):
        assert {"Andersson", "Johansson", "Karlsson"} <= STANDARDNAMN

    def test_innehaller_vanliga_fornamn(self):
        assert {"Lars", "Anna", "Birgitta"} <= STANDARDNAMN

    def test_innehaller_diakritnamn(self):
        # Omgranskningens fynd 4: vanliga namn med diakriter ska fångas även
        # som bart namn/versalform — via referenslistan, inte bara 3b-regexen.
        assert {"André", "Linnéa", "Renée", "Désirée"} <= STANDARDNAMN


class TestLasNamnreferens:
    def test_utan_extra_fil_ar_standardlistan(self, tmp_path):
        namn = las_namnreferens(tmp_path / "finns_ej.txt")
        assert namn == set(STANDARDNAMN)

    def test_extra_fil_unionslaggs(self, tmp_path):
        fil = tmp_path / "extra.txt"
        fil.write_text("Zorro Zetterlund\n# kommentar\n\nBerit Bergkvist\n", encoding="utf-8")
        namn = las_namnreferens(fil)
        assert "Zorro Zetterlund" in namn
        assert "Berit Bergkvist" in namn
        assert "# kommentar" not in namn
        assert set(STANDARDNAMN) <= namn

    def test_saknad_fil_ger_bara_standard(self, tmp_path):
        assert las_namnreferens(tmp_path / "borta.txt") == set(STANDARDNAMN)


class TestBiterISekretesslagret:
    def test_kant_efternamnspar_auto_maskeras_utan_granskning(self):
        # "Lars Andersson" finns i referenslistan -> Lager 3a auto-maskerar,
        # inget Maskeringsbehov (till skillnad från ett okänt namn som flaggas).
        fil = SIEFil(verifikationer=[
            Verifikation(serie="A", vernr="1", verdatum="20260615",
                transaktioner=[Transaktion(kontonr="7010", belopp=Decimal("25000"),
                    transtext="Lön Lars Andersson juni")]),
        ])
        resultat = maskera_siefil(fil, referenslista=las_namnreferens())
        trans = resultat.maskerad_siefil.verifikationer[0].transaktioner[0]
        assert "Lars Andersson" not in trans.transtext
        assert "PERSON_" in trans.transtext
        assert resultat.maskeringsbehov == []
