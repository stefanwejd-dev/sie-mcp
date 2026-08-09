import re

with open("parser/spiris_rag.py", "r", encoding="utf-8") as f:
    text = f.read()

# Fix hamta_leverantorsreskontra syntax error
text = text.replace(
    "return _envelope([_leverantorspost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit) for p in poster], antal_exkluderade=0)",
    "return _envelope([_leverantorspost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit)"
)

# Fix hamta_kundreskontra_rag not getting the arguments
text = text.replace(
    "async def hamta_kundreskontra_rag(klient: _Spirisklient) -> dict[str, Any]:",
    "async def hamta_kundreskontra_rag(klient: _Spirisklient, offset: int = 0, limit: int = 0) -> dict[str, Any]:"
)
text = text.replace(
    "return _envelope([_kundpost_till_dict(p) for p in poster], antal_exkluderade=0)",
    "return _envelope([_kundpost_till_dict(p) for p in poster], antal_exkluderade=0, offset=offset, limit=limit)"
)

with open("parser/spiris_rag.py", "w", encoding="utf-8") as f:
    f.write(text)

with open("mcp_server/server.py", "r", encoding="utf-8") as f:
    text = f.read()

# Make sure spiris_kundreskontra calls hamta_kundreskontra_rag correctly
text = text.replace(
    "lambda k: spiris_rag.hamta_kundreskontra_rag(k)",
    "lambda k: spiris_rag.hamta_kundreskontra_rag(k, offset, limit)"
)

with open("mcp_server/server.py", "w", encoding="utf-8") as f:
    f.write(text)

