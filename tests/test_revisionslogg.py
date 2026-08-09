"""Tester för revisionslogg.py — den lokala AI-utflödesloggen (Art. 30-stöd,
granskningens svaghet 3).

Fokus: att metadata skrivs och läses korrekt (round-trip), att INGEN nyttolast
loggas, att statistikuttaget bara ger räknare (aldrig kodnyckelns värden), och
att loggningen är fail-safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from revisionslogg import (
    las_revisionslogg,
    logga_ai_utflode,
    maskeringsstatistik_fran_resultat,
)


@dataclass
class _FejkMaskeringsresultat:
    kodnyckel: dict = field(default_factory=dict)
    maskeringsbehov: list = field(default_factory=list)
    blockerade_verifikationer: set = field(default_factory=set)
    sandningsbara_verifikationer: list = field(default_factory=list)


class TestLoggning:
    def test_round_trip(self, tmp_path):
        fil = tmp_path / "logg.jsonl"
        logga_ai_utflode(
            "Anthropic", "claude-haiku-4-5", "analys",
            datakategorier=["väsentlighetstal", "kontosaldon"],
            maskeringsstatistik={"antal_maskeringsbehov": 2},
            logg_fil=fil,
        )
        poster = las_revisionslogg(fil)
        assert len(poster) == 1
        assert poster[0]["leverantör"] == "Anthropic"
        assert poster[0]["modell"] == "claude-haiku-4-5"
        assert poster[0]["förmåga"] == "analys"
        assert poster[0]["datakategorier"] == ["väsentlighetstal", "kontosaldon"]
        assert poster[0]["maskeringsstatistik"]["antal_maskeringsbehov"] == 2
        assert "tidpunkt" in poster[0]

    def test_flera_poster_ackumuleras(self, tmp_path):
        fil = tmp_path / "logg.jsonl"
        logga_ai_utflode("Anthropic", "m", "analys", logg_fil=fil)
        logga_ai_utflode("Anthropic", "m", "samtal", logg_fil=fil)
        poster = las_revisionslogg(fil)
        assert [p["förmåga"] for p in poster] == ["analys", "samtal"]

    def test_ingen_nyttolast_eller_pii_loggas(self, tmp_path):
        # Loggen får bara bära metadata — aldrig fritext/namn/personnummer.
        fil = tmp_path / "logg.jsonl"
        logga_ai_utflode(
            "Anthropic", "m", "samtal",
            datakategorier=["chatt"],
            maskeringsstatistik={"antal_kodnyckel_poster": 3},
            logg_fil=fil,
        )
        innehall = fil.read_text(encoding="utf-8")
        assert "Anna" not in innehall
        # Bara räknaren, aldrig kodnyckelns faktiska värden.
        assert "antal_kodnyckel_poster" in innehall

    def test_saknad_fil_ger_tom_lista(self, tmp_path):
        assert las_revisionslogg(tmp_path / "finns_ej.jsonl") == []

    def test_trasig_rad_hoppas_over(self, tmp_path):
        fil = tmp_path / "logg.jsonl"
        fil.write_text('{"tidpunkt": "x"}\ntrasig rad\n', encoding="utf-8")
        poster = las_revisionslogg(fil)
        assert len(poster) == 1


class TestMaskeringsstatistik:
    def test_ger_bara_raknare(self):
        resultat = _FejkMaskeringsresultat(
            kodnyckel={"PERSON_1": "Anna Andersson", "BOLAG_1": "X AB"},
            maskeringsbehov=[object(), object()],
            blockerade_verifikationer={("A", "1")},
            sandningsbara_verifikationer=[object()],
        )
        stat = maskeringsstatistik_fran_resultat(resultat)
        assert stat == {
            "antal_kodnyckel_poster": 2,
            "antal_maskeringsbehov": 2,
            "antal_blockerade_verifikationer": 1,
            "antal_sandningsbara_verifikationer": 1,
        }
        # Ingen kodnyckel-VÄRDE läcker in i statistiken.
        assert "Anna Andersson" not in str(stat)

    def test_defensiv_mot_ofullstandig_indata(self):
        stat = maskeringsstatistik_fran_resultat(object())
        assert stat["antal_maskeringsbehov"] == 0
