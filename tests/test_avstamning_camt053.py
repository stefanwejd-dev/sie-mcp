"""Lager 1b, steg 1 — test av avstamning.camt053.

Se hantverksbok/BOKSLUTSPROGRAMMET.md §4.5. `test_bokslutskontroll_motor.py::
test_varje_registrerad_kontroll_finns_i_registret_och_tvartom` förblir röd
till och med steg 4 (§4.5, "Registret är redan skrivet") — det testet ska
INTE röras här."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from avstamning.camt053 import Camt053Fel, Utdrag, Utdragsrad, parse_camt053

_NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"


def _skriv_camt053(tmp_path: Path, innehall: str) -> Path:
    fil = tmp_path / "utdrag.xml"
    fil.write_text(innehall, encoding="utf-8")
    return fil


_KOMPLETT = f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="{_NS}">
  <BkToCstmrStmt>
    <Stmt>
      <Id>STMT-1</Id>
      <Acct>
        <Id>
          <IBAN>SE4550000000058398257466</IBAN>
        </Id>
      </Acct>
      <FrToDt>
        <FrDtTm>2026-06-01T00:00:00</FrDtTm>
        <ToDtTm>2026-06-30T23:59:59</ToDtTm>
      </FrToDt>
      <Bal>
        <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="SEK">10000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
      </Bal>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="SEK">10500.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
      </Bal>
      <Ntry>
        <NtryRef>REF-1</NtryRef>
        <Amt Ccy="SEK">1000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-06-05</Dt></BookgDt>
        <NtryDtls>
          <TxDtls>
            <Refs><AcctSvcrRef>TX-1</AcctSvcrRef></Refs>
            <RltdPties><Dbtr><Nm>Kundbolaget AB</Nm></Dbtr></RltdPties>
            <RmtInf><Ustrd>Faktura 100</Ustrd></RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="SEK">500.00</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-06-10</Dt></BookgDt>
        <RmtInf><Ustrd>Kontorsmaterial</Ustrd></RmtInf>
        <RltdPties><Cdtr><Nm>Leverantören AB</Nm></Cdtr></RltdPties>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def test_parsar_konto_period_och_saldon_fran_fil(tmp_path):
    fil = _skriv_camt053(tmp_path, _KOMPLETT)
    utdrag = parse_camt053(fil)

    assert utdrag.kontonr == "SE4550000000058398257466"
    assert utdrag.period_start == date(2026, 6, 1)
    assert utdrag.period_slut == date(2026, 6, 30)
    assert utdrag.ingaende_saldo == Decimal("10000.00")
    assert utdrag.utgaende_saldo == Decimal("10500.00")


def test_kredit_och_debet_tecknas_ratt(tmp_path):
    fil = _skriv_camt053(tmp_path, _KOMPLETT)
    utdrag = parse_camt053(fil)

    assert len(utdrag.rader) == 2
    insattning, uttag = utdrag.rader
    assert insattning.belopp == Decimal("1000.00")
    assert uttag.belopp == Decimal("-500.00")


def test_text_motpart_referens_lases_fran_nastlade_txdtls(tmp_path):
    fil = _skriv_camt053(tmp_path, _KOMPLETT)
    utdrag = parse_camt053(fil)
    insattning = utdrag.rader[0]

    assert insattning.datum == date(2026, 6, 5)
    assert insattning.text == "Faktura 100"
    assert insattning.motpart == "Kundbolaget AB"
    # NtryRef (direkt under Ntry) har högst prioritet i _entry_referens och
    # vinner här över den nästlade TxDtls/Refs/AcctSvcrRef ("TX-1").
    assert insattning.referens == "REF-1"


def test_referens_faller_tillbaka_pa_nastlad_txdtls_utan_ntryref(tmp_path):
    xml = _KOMPLETT.replace("<NtryRef>REF-1</NtryRef>\n        ", "")
    fil = _skriv_camt053(tmp_path, xml)
    utdrag = parse_camt053(fil)
    assert utdrag.rader[0].referens == "TX-1"


def test_text_och_motpart_lases_aven_direkt_under_ntry(tmp_path):
    """Vissa banker lägger RmtInf/RltdPties direkt under Ntry i stället för
    under NtryDtls/TxDtls — andra Ntry-posten i fixturen prövar den vägen."""
    fil = _skriv_camt053(tmp_path, _KOMPLETT)
    utdrag = parse_camt053(fil)
    uttag = utdrag.rader[1]

    assert uttag.text == "Kontorsmaterial"
    assert uttag.motpart == "Leverantören AB"
    assert uttag.referens is None  # ingen referens angiven för denna rad


def test_rad_utan_belopp_hoppas_over_utan_att_falla_hela_filen(tmp_path):
    xml = _KOMPLETT.replace(
        "</Ntry>\n    </Stmt>",
        """</Ntry>
      <Ntry>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-06-15</Dt></BookgDt>
      </Ntry>
    </Stmt>""",
    )
    fil = _skriv_camt053(tmp_path, xml)
    utdrag = parse_camt053(fil)
    assert len(utdrag.rader) == 2  # den tredje (utan Amt) hoppades över


def test_ogiltig_xml_kastar_camt053fel(tmp_path):
    fil = tmp_path / "trasig.xml"
    fil.write_text("inte alls xml <<<", encoding="utf-8")
    with pytest.raises(Camt053Fel):
        parse_camt053(fil)


def test_xml_utan_bktocstmrstmt_kastar_camt053fel(tmp_path):
    fil = tmp_path / "fel_dokument.xml"
    fil.write_text(f'<Document xmlns="{_NS}"><NagotAnnat/></Document>', encoding="utf-8")
    with pytest.raises(Camt053Fel):
        parse_camt053(fil)


def test_saknad_fil_kastar_camt053fel(tmp_path):
    with pytest.raises(Camt053Fel):
        parse_camt053(tmp_path / "finns_inte.xml")


def test_utdragsrad_och_utdrag_ar_frysta():
    rad = Utdragsrad(datum=date(2026, 1, 1), belopp=Decimal("1"))
    with pytest.raises(Exception):
        rad.belopp = Decimal("2")  # type: ignore[misc]

    utdrag = Utdrag(kontonr=None, period_start=None, period_slut=None,
                     ingaende_saldo=None, utgaende_saldo=None)
    with pytest.raises(Exception):
        utdrag.kontonr = "x"  # type: ignore[misc]
