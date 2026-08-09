"""Tester för masking_memory.py — ett litet lokalt minne (masking_memory.json)
över redan granskade/maskerade verifikationer, så att en förnyad Spiris-hämtning
inte tar med verifikat som redan hanterats.

Endast verifikations-ID (serie#vernr) lagras — ingen kontodata, ingen PII.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from masking_memory import (
    filtrera_bort_sedda,
    las_maskeringsminne,
    lagg_till_maskeringsminne,
    verifikation_id,
)


@dataclass
class _FejkTransaktion:
    kontonr: str = "1910"
    belopp: str = "0"
    transtext: str = ""


@dataclass
class _FejkVerifikation:
    serie: str
    vernr: int
    vertext: str = ""
    transaktioner: list = field(default_factory=list)


class TestVerifikationId:
    def test_borjar_med_serie_och_vernr(self):
        vid = verifikation_id(_FejkVerifikation("A", 12))
        assert vid.startswith("A#12#")

    def test_innehallsfingeravtryck_ingar(self):
        # serie#vernr#<hash> — tre delar.
        assert verifikation_id(_FejkVerifikation("A", 12)).count("#") == 2

    def test_samma_innehall_ger_samma_id(self):
        a = _FejkVerifikation("A", 1, vertext="Lön juni",
                              transaktioner=[_FejkTransaktion("7010", "25000")])
        b = _FejkVerifikation("A", 1, vertext="Lön juni",
                              transaktioner=[_FejkTransaktion("7010", "25000")])
        assert verifikation_id(a) == verifikation_id(b)

    def test_andrad_text_ger_nytt_id(self):
        # Svaghet 5: ändras verifikatets text efter godkännandet ska det INTE
        # matcha det gamla ID:t (annars ärver den nya texten godkännandet).
        gammal = _FejkVerifikation("A", 1, vertext="Utlägg",
                                   transaktioner=[_FejkTransaktion("7010", "500", "Fika")])
        ny = _FejkVerifikation("A", 1, vertext="Utlägg",
                               transaktioner=[_FejkTransaktion("7010", "500", "Lön Anna Andersson")])
        assert verifikation_id(gammal) != verifikation_id(ny)

    def test_andrat_belopp_ger_nytt_id(self):
        gammal = _FejkVerifikation("A", 1, transaktioner=[_FejkTransaktion("7010", "500")])
        ny = _FejkVerifikation("A", 1, transaktioner=[_FejkTransaktion("7010", "999")])
        assert verifikation_id(gammal) != verifikation_id(ny)


class TestLasOchLaggTill:
    def test_saknad_fil_ger_tom_mangd(self, tmp_path):
        assert las_maskeringsminne(tmp_path / "finns_ej.json") == set()

    def test_trasig_fil_ger_tom_mangd_inte_krasch(self, tmp_path):
        fil = tmp_path / "trasig.json"
        fil.write_text("{ inte giltig json", encoding="utf-8")
        assert las_maskeringsminne(fil) == set()

    def test_round_trip(self, tmp_path):
        fil = tmp_path / "minne.json"
        lagg_till_maskeringsminne(["A#1", "A#2"], fil)
        assert las_maskeringsminne(fil) == {"A#1", "A#2"}

    def test_ackumulerar_union_utan_dubbletter(self, tmp_path):
        fil = tmp_path / "minne.json"
        lagg_till_maskeringsminne(["A#1"], fil)
        lagg_till_maskeringsminne(["A#1", "A#2"], fil)
        assert las_maskeringsminne(fil) == {"A#1", "A#2"}


class TestFiltreraBortSedda:
    def test_tar_bort_redan_sedda(self):
        verifikationer = [
            _FejkVerifikation("A", 1),
            _FejkVerifikation("A", 2),
            _FejkVerifikation("B", 5),
        ]
        # Sedda-mängden byggs av verifikation_id (som app.py gör), inte handskrivna
        # nycklar — id:t innehåller nu ett innehållsfingeravtryck.
        sedda = {verifikation_id(verifikationer[0]), verifikation_id(verifikationer[2])}
        kvar = filtrera_bort_sedda(verifikationer, sedda)
        assert [v.vernr for v in kvar] == [2]

    def test_andrat_verifikat_slinker_inte_igenom_som_sett(self):
        # Svaghet 5 end-to-end: ett verifikat som setts men sedan ändrats ska INTE
        # filtreras bort — det ska tas med och granskas om.
        original = _FejkVerifikation("A", 1, transaktioner=[_FejkTransaktion("7010", "500", "Fika")])
        sedda = {verifikation_id(original)}
        ändrat = _FejkVerifikation("A", 1, transaktioner=[_FejkTransaktion("7010", "500", "Lön Anna")])
        assert filtrera_bort_sedda([ändrat], sedda) == [ändrat]

    def test_tomt_minne_behaller_allt(self):
        verifikationer = [_FejkVerifikation("A", 1), _FejkVerifikation("A", 2)]
        assert filtrera_bort_sedda(verifikationer, set()) == verifikationer
