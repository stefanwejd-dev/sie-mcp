import re

# Fix test_etapp5.py
with open("tests/test_etapp5.py", "r", encoding="utf-8") as f:
    code = f.read()
code = code.replace("@pytest.mark.asyncio\nasync def test_kvittningskandidater_rag():\n    k = MockKlient()\n    res = await spiris_rag.hamta_kvittningskandidater(k, \"c-1\")",
                    "def test_kvittningskandidater_rag():\n    k = MockKlient()\n    res = asyncio.run(spiris_rag.hamta_kvittningskandidater(k, \"c-1\"))")
code = code.replace('res["data"]', 'res["meddelande"]')
with open("tests/test_etapp5.py", "w", encoding="utf-8") as f:
    f.write(code)

# Fix server.py implementation of forbered_betalningsverifikat
with open("mcp_server/server.py", "r", encoding="utf-8") as f:
    server = f.read()

# Replace the inner `_bygg` function in forbered_betalningsverifikat
new_forbered = """@mcp.tool()
async def forbered_betalningsverifikat(
    beskrivning: str,
    transaktionsdatum: str,
    rader: list[dict],
    ctx: Context | None = None,
) -> dict:
    '''Förbereder ett betalningsverifikat för över- eller underbetalning.
    
    rader: lista med {"konto": kontonummer, "debet": tal, "kredit": tal, "text": radtext}.
    Måste balansera.'''
    _rensade: list[dict] = []
    _debet = _kredit = 0.0
    for _rad in rader:
        _d = float(_rad.get("debet") or 0)
        _k = float(_rad.get("kredit") or 0)
        _rensade.append({
            "konto": str(_rad.get("konto") or ""), "debet": _d, "kredit": _k,
            "text": str(_rad.get("text") or ""),
        })
        _debet += _d
        _kredit += _k
    sammanfattning = [
        ["Beskrivning", beskrivning],
        ["Datum", transaktionsdatum],
        ["Debet", f"{_debet:,.2f}"],
        ["Kredit", f"{_kredit:,.2f}"],
    ]
    _balanserar = abs(_debet - _kredit) <= 0.005 and bool(_rensade)

    def _bygg():
        if not _balanserar:
            raise ValueError(f"Verifikatet balanserar inte! Debet: {_debet:.2f}, Kredit: {_kredit:.2f}")

        nyttolast = {
            "beskrivning": beskrivning,
            "transaktionsdatum": transaktionsdatum,
            "rader": _rensade,
        }
        u = utkast.skapa("betalningsverifikat", nyttolast, sammanfattning)
        return _utkastsvar(u, f"Ett betalningsverifikat på {_debet:,.2f} kr föreslås.")

    return await _kor_utkastverktyg(
        _bygg, ctx, f"Förslag: betalningsverifikat på {_debet:,.2f} kr", sammanfattning if _balanserar else None
    )
"""

# Find the old forbered_betalningsverifikat and replace it
server = re.sub(
    r'@mcp\.tool\(\)\nasync def forbered_betalningsverifikat\(.*?return await _kor_utkastverktyg\(\n        _bygg, ctx, f"Förslag: betalningsverifikat på \{_debet:,\.2f\} kr", sammanfattning\n    \)\n',
    new_forbered,
    server,
    flags=re.DOTALL
)

with open("mcp_server/server.py", "w", encoding="utf-8") as f:
    f.write(server)
