"""Lager 1b, steg 2 — test av avstamning.csvprofil.

Se hantverksbok/BOKSLUTSPROGRAMMET.md §4.2/§4.5 steg 2. Kolumnerna gissas
aldrig — varje test som prövar parse_csv anger en explicit Kolumnprofil.
test_varje_registrerad_kontroll_finns_i_registret_och_tvartom förblir röd
till och med steg 4 — rörs inte här."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from avstamning.csvprofil import (
    CsvprofilFel,
    Kolumnprofil,
    las_profil,
    parse_csv,
    spara_profil,
    ta_bort_profil,
)


def _skriv_csv(tmp_path: Path, innehall: str, namn: str = "utdrag.csv") -> Path:
    fil = tmp_path / namn
    fil.write_text(innehall, encoding="utf-8")
    return fil


# --- Profilpersistens --------------------------------------------------


def test_spara_och_las_profil_ger_samma_objekt(tmp_path):
    profilfil = tmp_path / "profiler.json"
    profil = Kolumnprofil(
        kontonr="1930", datum_kolumn=0, belopp_kolumn=2, text_kolumn=1, saldo_kolumn=3
    )
    spara_profil(profil, sokvag=profilfil)

    laest = las_profil("1930", sokvag=profilfil)
    assert laest == profil


def test_las_profil_okant_konto_ger_none(tmp_path):
    profilfil = tmp_path / "profiler.json"
    assert las_profil("finns-inte", sokvag=profilfil) is None


def test_las_profil_trasig_fil_ger_none_inte_krasch(tmp_path):
    profilfil = tmp_path / "profiler.json"
    profilfil.write_text("{inte giltig json", encoding="utf-8")
    assert las_profil("1930", sokvag=profilfil) is None


def test_las_profil_okompatibel_post_ger_none(tmp_path):
    """En profil sparad med andra fält (t.ex. äldre/nyare version) ska
    behandlas som ingen profil, inte krascha eller gissa."""
    import json

    profilfil = tmp_path / "profiler.json"
    profilfil.write_text(
        json.dumps({"1930": {"helt_annat_falt": 1}}), encoding="utf-8"
    )
    assert las_profil("1930", sokvag=profilfil) is None


def test_flera_konton_lagras_oberoende(tmp_path):
    profilfil = tmp_path / "profiler.json"
    p1 = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    p2 = Kolumnprofil(kontonr="1940", datum_kolumn=2, belopp_kolumn=3)
    spara_profil(p1, sokvag=profilfil)
    spara_profil(p2, sokvag=profilfil)

    assert las_profil("1930", sokvag=profilfil) == p1
    assert las_profil("1940", sokvag=profilfil) == p2


def test_spara_profil_ersatter_befintlig(tmp_path):
    profilfil = tmp_path / "profiler.json"
    spara_profil(Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1), sokvag=profilfil)
    ny = Kolumnprofil(kontonr="1930", datum_kolumn=5, belopp_kolumn=6)
    spara_profil(ny, sokvag=profilfil)

    assert las_profil("1930", sokvag=profilfil) == ny


def test_ta_bort_profil(tmp_path):
    profilfil = tmp_path / "profiler.json"
    spara_profil(Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1), sokvag=profilfil)
    ta_bort_profil("1930", sokvag=profilfil)
    assert las_profil("1930", sokvag=profilfil) is None


def test_ta_bort_profil_okant_konto_ar_ett_noop(tmp_path):
    profilfil = tmp_path / "profiler.json"
    ta_bort_profil("finns-inte", sokvag=profilfil)  # ska inte kasta


# --- parse_csv -----------------------------------------------------------


_ENKEL_CSV = """Datum;Text;Belopp;Saldo
2026-06-05;Faktura 100;1000.00;11000.00
2026-06-10;Kontorsmaterial;-500.00;10500.00
"""


def test_parse_csv_rader_och_belopp(tmp_path):
    fil = _skriv_csv(tmp_path, _ENKEL_CSV)
    profil = Kolumnprofil(
        kontonr="1930", datum_kolumn=0, belopp_kolumn=2, text_kolumn=1, saldo_kolumn=3
    )
    utdrag = parse_csv(fil, profil)

    assert len(utdrag.rader) == 2
    första, andra = utdrag.rader
    assert första.datum == date(2026, 6, 5)
    assert första.belopp == Decimal("1000.00")
    assert första.text == "Faktura 100"
    assert andra.belopp == Decimal("-500.00")


def test_parse_csv_saldo_ger_ingaende_och_utgaende(tmp_path):
    fil = _skriv_csv(tmp_path, _ENKEL_CSV)
    profil = Kolumnprofil(
        kontonr="1930", datum_kolumn=0, belopp_kolumn=2, text_kolumn=1, saldo_kolumn=3
    )
    utdrag = parse_csv(fil, profil)

    # Ingående = första radens saldo (11000) minus dess eget belopp (1000).
    assert utdrag.ingaende_saldo == Decimal("10000.00")
    assert utdrag.utgaende_saldo == Decimal("10500.00")
    assert utdrag.period_start == date(2026, 6, 5)
    assert utdrag.period_slut == date(2026, 6, 10)


def test_parse_csv_utan_saldokolumn_ger_none(tmp_path):
    fil = _skriv_csv(tmp_path, _ENKEL_CSV)
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=2, text_kolumn=1)
    utdrag = parse_csv(fil, profil)

    assert utdrag.ingaende_saldo is None
    assert utdrag.utgaende_saldo is None


def test_parse_csv_utan_rubrikrad(tmp_path):
    csv_utan_rubrik = "2026-06-05;Faktura 100;1000.00\n"
    fil = _skriv_csv(tmp_path, csv_utan_rubrik)
    profil = Kolumnprofil(
        kontonr="1930", datum_kolumn=0, belopp_kolumn=2, text_kolumn=1, har_rubrikrad=False
    )
    utdrag = parse_csv(fil, profil)
    assert len(utdrag.rader) == 1
    assert utdrag.rader[0].belopp == Decimal("1000.00")


def test_parse_csv_decimalkomma(tmp_path):
    csv_med_komma = "Datum;Belopp\n2026-06-05;1.234,56\n"
    fil = _skriv_csv(tmp_path, csv_med_komma)
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1, decimalkomma=True)
    utdrag = parse_csv(fil, profil)
    assert utdrag.rader[0].belopp == Decimal("1234.56")


def test_parse_csv_tomma_rader_hoppas_over(tmp_path):
    csv_med_tom_rad = "Datum;Belopp\n2026-06-05;1000.00\n\n2026-06-06;500.00\n"
    fil = _skriv_csv(tmp_path, csv_med_tom_rad)
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    utdrag = parse_csv(fil, profil)
    assert len(utdrag.rader) == 2


def test_parse_csv_ratt_kolumnantal_saknas_kastar(tmp_path):
    csv_for_fa_kolumner = "Datum;Belopp\n2026-06-05;1000.00\n"
    fil = _skriv_csv(tmp_path, csv_for_fa_kolumner)
    # Profilen begär kolumn 3 (saldo), som inte finns i denna fil.
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1, saldo_kolumn=3)
    with pytest.raises(CsvprofilFel):
        parse_csv(fil, profil)


def test_parse_csv_otolkbart_datum_kastar(tmp_path):
    csv_med_fel_datum = "Datum;Belopp\ninte-ett-datum;1000.00\n"
    fil = _skriv_csv(tmp_path, csv_med_fel_datum)
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    with pytest.raises(CsvprofilFel):
        parse_csv(fil, profil)


def test_parse_csv_otolkbart_belopp_kastar(tmp_path):
    """En felgissad beloppskolumn (t.ex. pekar på textkolumnen) ska kastas,
    inte tolkas som 0 eller hoppas över — se modulens docstring."""
    fil = _skriv_csv(tmp_path, "Datum;Text\n2026-06-05;Inte ett belopp\n")
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    with pytest.raises(CsvprofilFel):
        parse_csv(fil, profil)


def test_parse_csv_saknad_fil_kastar(tmp_path):
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    with pytest.raises(CsvprofilFel):
        parse_csv(tmp_path / "finns_inte.csv", profil)


def test_parse_csv_utan_textkolumn(tmp_path):
    fil = _skriv_csv(tmp_path, "Datum;Belopp\n2026-06-05;1000.00\n")
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    utdrag = parse_csv(fil, profil)
    assert utdrag.rader[0].text is None


def test_kolumnprofil_ar_fryst():
    profil = Kolumnprofil(kontonr="1930", datum_kolumn=0, belopp_kolumn=1)
    with pytest.raises(Exception):
        profil.kontonr = "annat"  # type: ignore[misc]
