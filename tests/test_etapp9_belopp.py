import asyncio
import pytest
from decimal import Decimal
from mcp_server import server as server_modul
import compliance

class _FejkCtx:
    def __init__(self):
        self.session_id = "test_session"
    async def log_info(self, *args, **kwargs):
        pass

@pytest.fixture(autouse=True)
def _godkann():
    compliance.godkann_compliance()

def test_belopp_parser_komma_och_punkt():
    assert server_modul._belopp("1234.50", "f") == Decimal("1234.50")
    assert server_modul._belopp("1234,50", "f") == Decimal("1234.50")
    assert server_modul._belopp("1 234,50", "f") == Decimal("1234.50")
    assert server_modul._belopp("1\xa0234.50", "f") == Decimal("1234.50")

def test_belopp_parser_tvetydigt():
    with pytest.raises(ValueError, match="innehåller både punkt och komma"):
        server_modul._belopp("1.234,50", "f")
        
def test_belopp_parser_ogiltig_strang():
    with pytest.raises(ValueError, match="inte ett giltigt tal"):
        server_modul._belopp("abc", "f")

def test_belopp_parser_ogiltig_typ():
    with pytest.raises(ValueError, match="måste anges som sträng, inte int"):
        server_modul._belopp(123, "f")
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        server_modul._belopp(123.0, "f")
    with pytest.raises(ValueError, match="måste anges som sträng, inte bool"):
        server_modul._belopp(True, "f")

# 1. betalningspaminnelse
def test_forbered_betalningspaminnelse_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_betalningspaminnelse("1", "50.00", ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_betalningspaminnelse_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        asyncio.run(server_modul.forbered_betalningspaminnelse("1", 50.00, ctx=ctx))

# 2. betalningsregistrering
def test_forbered_betalningsregistrering_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_betalningsregistrering("1", "50.00", "2026-08-01", "bank", ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_betalningsregistrering_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        asyncio.run(server_modul.forbered_betalningsregistrering("1", 50.00, "2026-08-01", "bank", ctx=ctx))

# 3. leverantorsfakturautkast
def test_forbered_leverantorsfakturautkast_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_leverantorsfakturautkast("L", [{"konto": "4000", "debet": "50.00"}], "2026-08-01", "2026-08-30", totalbelopp="50.00", ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_leverantorsfakturautkast_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        asyncio.run(server_modul.forbered_leverantorsfakturautkast("L", [{"konto": "4000", "debet": "50.00"}], "2026-08-01", "2026-08-30", totalbelopp=50.00, ctx=ctx))

# 4. leverantorsbetalning
def test_forbered_leverantorsbetalning_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_leverantorsbetalning("1", "50.00", "2026-08-01", "bank", ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_leverantorsbetalning_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        asyncio.run(server_modul.forbered_leverantorsbetalning("1", 50.00, "2026-08-01", "bank", ctx=ctx))

# 5. periodisering
def test_forbered_periodisering_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_periodisering("2026-01-01", "1200.00", 3000, 12, leverantorsfaktura_id="1", leverantorsfaktura_rad=1, ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_periodisering_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        asyncio.run(server_modul.forbered_periodisering("2026-01-01", 1200.00, 3000, 12, leverantorsfaktura_id="1", leverantorsfaktura_rad=1, ctx=ctx))

# 6. kundfaktura
def test_forbered_kundfaktura_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_kundfaktura("K1", [{"artikel": "Test", "antal": "1", "pris": "100.00"}], ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_kundfaktura_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte float"):
        asyncio.run(server_modul.forbered_kundfaktura("K1", [{"artikel": "Test", "antal": "1", "pris": 100.00}], ctx=ctx))

# 7. verifikat
def test_forbered_verifikat_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_verifikat("Test", "2026-08-01", [{"konto": "1930", "debet": "100.00"}, {"konto": "3000", "kredit": "100.00"}], ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_verifikat_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte int"):
        asyncio.run(server_modul.forbered_verifikat("Test", "2026-08-01", [{"konto": "1930", "debet": 100}, {"konto": "3000", "kredit": "100.00"}], ctx=ctx))

# 8. betalningsverifikat
def test_forbered_betalningsverifikat_str():
    ctx = _FejkCtx()
    res = asyncio.run(server_modul.forbered_betalningsverifikat("Test", "2026-08-01", [{"konto": "1930", "debet": "100.00"}, {"konto": "3000", "kredit": "100.00"}], ctx=ctx))
    assert res["utkast_id"] is not None

def test_forbered_betalningsverifikat_float():
    ctx = _FejkCtx()
    with pytest.raises(ValueError, match="måste anges som sträng, inte int"):
        asyncio.run(server_modul.forbered_betalningsverifikat("Test", "2026-08-01", [{"konto": "1930", "debet": 100}, {"konto": "3000", "kredit": "100.00"}], ctx=ctx))
