"""test_dataminimering_pastaenden.py — låser fast tabellen i DATASKYDD.md §3.

Avsnitt 3 påstod tidigare att AI-kontexten byggs "enbart av aggregerade fakta".
Det är sant för chatt-/agentvägen men FALSKT för Modul 4, som skickar maskerad
fritext per transaktion — vilket uppgiften (semantisk kontomatchning) kräver.
Felet upptäcktes genom att fånga den faktiska nyttolasten, inte genom att läsa
koden.

Den här sviten finns för att §3 ska förbli sann. Ändras vad som skickas blir
testet rött, och då ska tabellen i §3 ändras i samma commit.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

import samtalsflode
from analysflode import kor_analys
from sekretesslager import maskera_siefil
from sie4_parser import parse_sie4

SIE4_EXEMPEL = str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE")

# Ett verifikat med ett okänt namn (blockeras) och ett rent (släpps igenom).
SIE4_MED_BLOCKERAT = """#FLAGGA 0
#PROGRAM "Test" 1.0
#FORMAT PC8
#GEN 20260101
#SIETYP 4
#FNAMN "Testbolag AB"
#ORGNR 556677-8899
#RAR 0 20260101 20261231
#KONTO 1910 "Kassa"
#KONTO 7690 "Ovrigt"
#VER A 1 20260105 "Konsult Xerxes Qoolio"
{
#TRANS 1910 {} -1000.00 20260105 "Konsult Xerxes Qoolio"
#TRANS 7690 {} 1000.00 20260105 "Konsult Xerxes Qoolio"
}
#VER A 2 20260106 "Kaffebrod"
{
#TRANS 1910 {} -195.00 20260106 "Kaffebrod"
#TRANS 7690 {} 195.00 20260106 "Kaffebrod"
}
"""


@pytest.fixture
def modul4_nyttolast():
    """Den FAKTISKA bunt som Modul 4 skickar till AI-leverantören."""
    sie = parse_sie4(SIE4_EXEMPEL)
    maskeringsresultat = maskera_siefil(sie)
    fangat: dict = {}

    def fejk_anropare(bunt, prosa_kontext):
        fangat.setdefault("bunt", bunt)
        fangat.setdefault("prosa", prosa_kontext)
        return []

    kor_analys(sie, maskeringsresultat, fejk_anropare, Decimal("1000"), Decimal("10000"))
    return fangat.get("bunt") or []


def test_modul4_skickar_fritext_per_transaktion(modul4_nyttolast):
    """§3-tabellens rad för Modul 4: detta är INTE aggregat.

    Testet bevakar att dokumentationen inte glider tillbaka till att påstå
    minimering som inte finns."""
    assert modul4_nyttolast, "Modul 4 byggde ingen bunt — fixturen är trasig"
    post = modul4_nyttolast[0]
    assert {"transtext", "vertext", "text_analyserad"} <= set(post), (
        "Modul 4 skickar fritext per transaktion. Slutar den göra det ska "
        "DATASKYDD.md §3 uppdateras i samma commit."
    )
    assert {"kontonr", "kontonamn", "belopp", "plats"} <= set(post)


def test_chattkontexten_bar_ingen_verifikationsfritext():
    """§3-tabellens rad för chatt/agent: enbart aggregerade fakta."""
    sie = parse_sie4(SIE4_EXEMPEL)
    maskeringsresultat = maskera_siefil(sie)

    kontext = samtalsflode.bygg_saker_kontext(sie, maskeringsresultat, None)

    fritexter = {
        (t.transtext or "").strip()
        for v in maskeringsresultat.sandningsbara_verifikationer
        for t in v.transaktioner
        if (t.transtext or "").strip()
    }
    lackta = [t for t in fritexter if len(t) > 4 and t in kontext]
    assert not lackta, f"verifikationsfritext hamnade i chattkontexten: {lackta[:5]}"


def test_blockerat_verifikat_utesluts_helt(tmp_path):
    """Gemensamt för alla vägar: ett olöst maskeringsbehov utesluter hela
    verifikatet ur den sändningsbara mängden."""
    fil = tmp_path / "test.se"
    fil.write_bytes(SIE4_MED_BLOCKERAT.encode("cp437"))

    sie = parse_sie4(str(fil))
    maskeringsresultat = maskera_siefil(sie)

    assert len(sie.verifikationer) == 2
    assert maskeringsresultat.maskeringsbehov, "det okända namnet ska ge maskeringsbehov"

    vernr = {str(v.vernr) for v in maskeringsresultat.sandningsbara_verifikationer}
    assert vernr == {"2"}, f"blockerat verifikat läckte in i sändningsbar mängd: {vernr}"


def test_blockerat_verifikat_nar_inte_modul4(tmp_path):
    """Samma sak, men hela vägen: den blockerade textens ord får inte
    förekomma i den bunt som lämnar datorn."""
    fil = tmp_path / "test.se"
    fil.write_bytes(SIE4_MED_BLOCKERAT.encode("cp437"))

    sie = parse_sie4(str(fil))
    maskeringsresultat = maskera_siefil(sie)
    fangat: dict = {}

    def fejk_anropare(bunt, prosa_kontext):
        fangat["bunt"] = bunt
        return []

    kor_analys(sie, maskeringsresultat, fejk_anropare, Decimal("1000"), Decimal("10000"))

    serialiserat = str(fangat.get("bunt", []))
    assert "Xerxes" not in serialiserat
    assert "Qoolio" not in serialiserat
