"""test_egressgransen.py — P0: maskeringen sitter vid utflödet, inte vid hämtningen.

Maskeringsgränsen flyttades 2026-08-04. Tidigare byttes motpartsnamn mot
pseudonymer redan i `spiris_adapter.hamta_reskontra`, vilket gjorde att även
Streamlit-appens lokala vyer visade "Fiktiv Kund 3" — data användaren själv
äger och ser i Spiris. Maskeringen finns för att skydda utflödet till en
AI-leverantör, inte för att skydda användaren från sin egen bokföring.

Följden är att appen nu håller KLARTEXT i minnet, och att varje väg ut måste
maskera. Det är den enda ändringen i hela projektet som kan skapa en läcka om
den görs slarvigt, så den här sviten prövar båda sidorna:

1. **Lokalt = klartext.** Adaptern returnerar riktiga namn, med klassningen
   (`ska_maskeras`) satt men inte tillämpad.
2. **Egress = alltid maskerat.** Varje utflödesväg maskerar SJÄLV och litar
   aldrig på att anroparen gjort det.

Blir något här rött är åtgärden aldrig att lätta på kravet.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest

import compliance
import mcp_server.server as server_modul
import samtalsflode
from reskontra_tvatt import Kundpost, Leverantorspost, maskera_for_egress
from spiris_adapter import hamta_kundreskontra, hamta_reskontra

RIKTIGT_KUNDNAMN = "Anna Andersson"
RIKTIGT_LEVNAMN = "Bertil Bertilsson"


class _FejkKlient:
    """Två motparter: en fysisk person (ska maskeras) och ett bolag (ska inte)."""

    access_token = refresh_token = "T"

    def hamta_en(self, path, params=None):
        if path == "/companysettings":
            return {"Name": "Testbolag AB", "CorporateIdentityNumber": "556677-8899"}
        raise AssertionError(path)

    def hamta_alla(self, path, params=None):
        if path == "/customers":
            return [
                {"Id": "cus-1", "Name": RIKTIGT_KUNDNAMN, "OrganisationNumber": ""},
                {"Id": "cus-2", "Name": "Bolaget AB", "OrganisationNumber": "5566778899"},
            ]
        if path == "/customerinvoices":
            return [
                {"CustomerId": "cus-1", "RemainingAmount": Decimal("500"),
                 "PaymentStatus": 1, "DueDate": "2026-07-10"},
                {"CustomerId": "cus-2", "RemainingAmount": Decimal("900"),
                 "PaymentStatus": 1, "DueDate": "2026-07-11"},
            ]
        if path == "/suppliers":
            return [{"Id": "sup-1", "Name": RIKTIGT_LEVNAMN, "CorporateIdentityNumber": ""}]
        if path == "/supplierinvoices":
            return [{"SupplierId": "sup-1", "RemainingAmount": Decimal("700"),
                     "PaymentStatus": 1, "DueDate": "2026-07-01"}]
        if path.startswith("/accountbalances/"):
            return []
        return []


# --- 1. Lokalt: klartext med klassningen satt ------------------------------


def test_adaptern_lamnar_riktiga_namn_lokalt():
    """Snabbvyerna i appen ska visa vem kunden faktiskt är. En lista där den
    största kunden heter 'Fiktiv Kund 3' är oanvändbar."""
    poster = hamta_kundreskontra(_FejkKlient())
    namn = {p.kund for p in poster}

    assert RIKTIGT_KUNDNAMN in namn
    assert not any(p.maskerad for p in poster), "åtgärden ska inte vara utförd"


def test_klassningen_foljer_med_aven_i_klartext():
    """`ska_maskeras` säger VAD som gäller vid egress, utan att ha gjort det."""
    poster = {p.kund: p for p in hamta_kundreskontra(_FejkKlient())}

    assert poster[RIKTIGT_KUNDNAMN].ska_maskeras is True   # fysisk person
    assert poster["Bolaget AB"].ska_maskeras is False      # giltigt org.nr


def test_leverantorsreskontran_lamnar_ocksa_klartext():
    poster = hamta_reskontra(_FejkKlient())
    assert poster[0].leverantor == RIKTIGT_LEVNAMN
    assert poster[0].ska_maskeras is True


# --- 2. Egressfunktionen ---------------------------------------------------


def test_maskera_for_egress_byter_bara_de_klassade():
    poster = maskera_for_egress(hamta_kundreskontra(_FejkKlient()))
    namn = {p.kund for p in poster}

    assert RIKTIGT_KUNDNAMN not in namn
    assert "Bolaget AB" in namn, "juridisk person ska stå kvar i klartext"


def test_maskera_for_egress_ar_idempotent():
    """Dubbla anrop får inte ge 'Fiktiv Kund 1' -> 'Fiktiv Kund 2'."""
    en_gang = maskera_for_egress(hamta_kundreskontra(_FejkKlient()))
    tva_ganger = maskera_for_egress(en_gang)

    assert [p.kund for p in en_gang] == [p.kund for p in tva_ganger]


def test_samma_motpart_far_samma_pseudonym():
    poster = maskera_for_egress([
        Kundpost(kund="Anna Andersson", belopp=Decimal("1"), betalstatus="x", ska_maskeras=True),
        Kundpost(kund="Anna Andersson", belopp=Decimal("2"), betalstatus="x", ska_maskeras=True),
        Kundpost(kund="Bo Bosson", belopp=Decimal("3"), betalstatus="x", ska_maskeras=True),
    ])
    assert poster[0].kund == poster[1].kund
    assert poster[0].kund != poster[2].kund


def test_forfallodatum_och_motpart_id_overlever_maskeringen():
    """Bara NAMNET maskeras — beloppen och nycklarna måste följa med, annars
    slutar likviditetsprognosen och betalbeteendet fungera."""
    post = maskera_for_egress([
        Kundpost(kund="Anna Andersson", belopp=Decimal("42"), betalstatus="obetald",
                 ska_maskeras=True, forfallodatum=date(2026, 7, 1), motpart_id="cus-1")
    ])[0]

    assert post.belopp == Decimal("42")
    assert post.forfallodatum == date(2026, 7, 1)
    assert post.motpart_id == "cus-1"


# --- 3. Varje utflödesväg maskerar SJÄLV -----------------------------------


@pytest.fixture
def _uppkopplad(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    compliance.godkann_compliance()
    monkeypatch.setattr(server_modul, "bygg_klient", lambda: _FejkKlient())
    monkeypatch.setattr(server_modul, "spara_session", lambda k: None)


def test_mcp_kundreskontra_maskerar(_uppkopplad):
    svar = asyncio.run(server_modul.spiris_kundreskontra())
    assert RIKTIGT_KUNDNAMN not in str(svar)


def test_mcp_leverantorsreskontra_maskerar(_uppkopplad):
    svar = asyncio.run(server_modul.spiris_leverantorsreskontra())
    assert RIKTIGT_LEVNAMN not in str(svar)


def test_mcp_likviditetsprognos_maskerar(_uppkopplad):
    """Prognosen returnerar motpartsnamn i sina dag-för-dag-poster."""
    svar = asyncio.run(server_modul.spiris_likviditetsprognos("2026-12-31"))
    assert RIKTIGT_KUNDNAMN not in str(svar)
    assert RIKTIGT_LEVNAMN not in str(svar)


def test_chattkontexten_maskerar_aven_otvattad_indata():
    """Den viktigaste i hela sviten.

    `app.py` håller numera klartext, så `bygg_saker_kontext` kan inte längre
    anta att den får färdigtvättad data. Den måste tvätta SJÄLV — annars går
    riktiga kundnamn till AI-leverantören så fort någon glömmer ett anrop."""
    from sekretesslager import maskera_siefil
    from sie4_parser import parse_sie4
    from pathlib import Path

    sie = parse_sie4(str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"))
    maskeringsresultat = maskera_siefil(sie)

    # OTVÄTTAD indata, precis som appen numera håller den.
    kontext = samtalsflode.bygg_saker_kontext(
        sie, maskeringsresultat, None,
        reskontra=[Leverantorspost(leverantor=RIKTIGT_LEVNAMN, belopp=Decimal("700"),
                                   betalstatus="obetald", ska_maskeras=True)],
        kundreskontra=[Kundpost(kund=RIKTIGT_KUNDNAMN, belopp=Decimal("500"),
                                betalstatus="obetald", ska_maskeras=True)],
    )

    assert RIKTIGT_KUNDNAMN not in kontext
    assert RIKTIGT_LEVNAMN not in kontext


def test_chattkontexten_slapper_igenom_juridisk_person():
    """Maskeringen får inte bli en yxa: ett bolag är ingen personuppgift."""
    from sekretesslager import maskera_siefil
    from sie4_parser import parse_sie4
    from pathlib import Path

    sie = parse_sie4(str(Path(__file__).parent.parent / "samples" / "SIE4_Exempelfil.SE"))
    kontext = samtalsflode.bygg_saker_kontext(
        sie, maskera_siefil(sie), None,
        kundreskontra=[Kundpost(kund="Bolaget AB", belopp=Decimal("900"),
                                betalstatus="obetald", ska_maskeras=False)],
    )
    assert "Bolaget AB" in kontext


# --- 4. Statiskt: ingen egressväg kan glömma tvätten ----------------------


def test_varje_reskontraväg_i_spiris_rag_anropar_egressmaskeringen():
    """Statiskt skydd mot att ett framtida verktyg glömmer gränsen."""
    import inspect

    import spiris_rag

    for namn in ("hamta_leverantorsreskontra", "hamta_kundreskontra_rag",
                 "hamta_likviditetsprognos"):
        kalla = inspect.getsource(getattr(spiris_rag, namn))
        assert "maskera_for_egress" in kalla, f"{namn} saknar egressmaskering"


def test_adaptern_maskerar_inte_langre():
    """Regressionsskydd åt andra hållet: skulle någon återinföra maskering i
    hämtningen blir de lokala snabbvyerna obrukbara igen."""
    import inspect

    import spiris_adapter

    for namn in ("hamta_reskontra", "hamta_kundreskontra"):
        kalla = inspect.getsource(getattr(spiris_adapter, namn))
        assert "maskera_for_egress" not in kalla
