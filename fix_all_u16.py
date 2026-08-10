import os

fpath = "tests/test_mcp_villkorssparr.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

new_args = '''    "spiris_prislistor": (),
    "spiris_rabattavtal": (),
    "spiris_etiketter": ("kund",),
'''

content = content.replace('"spiris_offertutkast": (),', '"spiris_offertutkast": (),\n' + new_args)

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)

# Fix test_etapp16_strukturer.py
fpath2 = "tests/test_etapp16_strukturer.py"
with open(fpath2, "r", encoding="utf-8") as f:
    content2 = f.read()

content2 = content2.replace("@pytest.mark.asyncio\nasync def", "def")
content2 = content2.replace("res = await ", "res = asyncio.run(")
content2 = content2.replace("with pytest.raises(ValueError):\n        await hamta_etiketter(k, \"ogiltig\")", "with pytest.raises(ValueError):\n        asyncio.run(hamta_etiketter(k, \"ogiltig\"))")

# Ensure asyncio.run syntax is correct
content2 = content2.replace("asyncio.run(hamta_prislistor(k))", "asyncio.run(hamta_prislistor(k))")
content2 = content2.replace("asyncio.run(hamta_prislistor(k, \"l-1\"))", "asyncio.run(hamta_prislistor(k, \"l-1\"))")
content2 = content2.replace("asyncio.run(hamta_rabattavtal(k))", "asyncio.run(hamta_rabattavtal(k))")
content2 = content2.replace("asyncio.run(hamta_etiketter(k, \"kund\"))", "asyncio.run(hamta_etiketter(k, \"kund\"))")
content2 = content2.replace("asyncio.run(hamta_etiketter(k, \"artikel\"))", "asyncio.run(hamta_etiketter(k, \"artikel\"))")

with open(fpath2, "w", encoding="utf-8") as f:
    f.write(content2)
