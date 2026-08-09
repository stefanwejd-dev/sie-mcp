import re
from pathlib import Path

tests = Path("G:/My Drive/Claude Cowork/sie-mcp/tests/test_spiris_adapter.py")
c = tests.read_text("utf-8")

u15_test = '''
class TestU15_Enkeluppslag:
    class _FejkKlient:
        def hamta_en(self, path, **kwargs):
            return {"Id": "123", "Name": "Test"}
        def hamta_alla(self, path, **kwargs):
            return [{"Id": "123", "Name": "Test"}]

    def test_hamta_ett_kunder(self):
        from spiris_adapter import hamta_ett
        res = hamta_ett(self._FejkKlient(), "kund", "123")
        assert "namn" in res

    def test_hamta_ett_verifikatutkast(self):
        from spiris_adapter import hamta_ett
        kl = self._FejkKlient()
        def hamta_en_mock(p, **kw): return {"Id": "123", "VoucherDate": "2026-08-01", "NumberAndNumberSeries": "A1"}
        kl.hamta_en = hamta_en_mock
        res = hamta_ett(kl, "verifikatutkast", "123")
        assert "verifikat" in res
'''
if "class TestU15_Enkeluppslag" not in c:
    c += u15_test
tests.write_text(c, "utf-8")
