import re

def main():
    with open("mcp_server/server.py", "r", encoding="utf-8") as f:
        content = f.read()

    new_tools = """
@mcp.tool()
async def forbered_utkastandring(
    utkasttyp: str, utkast_id: str, andringar: dict,
    ctx: Context | None = None,
) -> dict:
    \"\"\"Förbereder en ÄNDRING av ett befintligt utkast.

    utkasttyp: "verifikat" (andra är inte fastställda ännu)
    utkast_id: utkastets id
    andringar: {fältnamn: nytt värde}
    
    För 'verifikat' tillåts: datum, text, serie, rader.

    Detta ändrar ingenting i Spiris — det lägger bara ett förslag i
    utkastkön för mänskligt godkännande.
    \"\"\"
    sammanfattning = [
        ["Åtgärd", f"Ändra {utkasttyp}utkast"],
        ["Utkast-id", str(utkast_id)],
    ]
    for _nyckel, _varde in (andringar or {}).items():
        sammanfattning.append([f"Nytt värde: {_nyckel}", str(_varde)])

    def _bygg():
        if utkasttyp != "verifikat":
            raise ValueError("Bara 'verifikat' stöds för utkaständring i dagsläget.")
        if not str(utkast_id).strip():
            raise ValueError("utkast_id saknas")
        if not andringar:
            raise ValueError("inga ändringar angivna")
        
        u = utkast.skapa(
            "utkastandring",
            {"utkasttyp": utkasttyp, "utkast_id": str(utkast_id).strip(),
             "andringar": dict(andringar)},
            sammanfattning,
        )
        return _utkastsvar(u, f"Ändring av {utkasttyp}utkast föreslås.")

    return await _kor_utkastverktyg(
        _bygg, ctx, f"Förslag: ändra {utkasttyp}utkast {utkast_id}", sammanfattning
    )


@mcp.tool()
async def forbered_utkastborttagning(
    utkasttyp: str, utkast_id: str,
    ctx: Context | None = None,
) -> dict:
    \"\"\"Förbereder BORTTAGNING av ett utkast.

    utkasttyp: "verifikat", "kundfaktura", "leverantorsfaktura"
    utkast_id: utkastets id

    Detta tar INTE bort utkastet. Det förbereder bara en oåterkallelig DELETE
    för mänskligt godkännande. En borttagning måste vara meningsfull — att radera
    ett utkast som är ofullständigt eller fel är ofta rätt beslut.
    \"\"\"
    try:
        klient = bygg_klient()
        # Enkeluppslaget kräver suffixet "utkast" för dessa
        if utkasttyp == "verifikat":
            uppslagstyp = "verifikatutkast"
        else:
            uppslagstyp = f"{utkasttyp}utkast"
            
        rå = spiris_adapter.hamta_ett(klient, uppslagstyp, utkast_id)
        if utkasttyp == "verifikat":
            utk = rå["verifikat"]
            datum = utk.get("datum", "")
            text = utk.get("text", "")
            belopp = sum(abs(r.get("belopp", 0)) for r in utk.get("rader", [])) / 2
            radantal = len(utk.get("rader", []))
        else:
            datum = rå.get("InvoiceDate") or rå.get("VoucherDate") or ""
            text = rå.get("InvoiceText") or rå.get("VoucherText") or ""
            belopp = rå.get("TotalAmountInvoiceCurrency") or 0
            radantal = len(rå.get("Rows") or [])
    except Exception as e:
        # U2.2: Fungerar inte hämtningen läggs inget förslag (fail-closed).
        return _fel("Kunde inte hämta utkastet från Spiris. Inget förslag lades.")

    sammanfattning = [
        ["Åtgärd", f"TA BORT {utkasttyp}utkast"],
        ["Utkast-id", str(utkast_id)],
        ["Datum", str(datum)],
        ["Text", str(text)],
        ["Belopp", str(belopp)],
        ["Varning", "Borttagningen kan inte ångras."],
    ]

    def _bygg():
        u = utkast.skapa(
            "utkastborttagning",
            {"utkasttyp": utkasttyp, "utkast_id": str(utkast_id).strip()},
            sammanfattning,
        )
        return _utkastsvar(
            u, f"Borttagning av {utkasttyp}utkast föreslås. Åtgärden går inte att ångra."
        )

    return await _kor_utkastverktyg(
        _bygg, ctx, f"Förslag: ta bort {utkasttyp}utkast {utkast_id}", sammanfattning
    )


@mcp.tool()
async def forbered_utkastbokforing(
    utkasttyp: str, utkast_id: str,
    ctx: Context | None = None,
) -> dict:
    \"\"\"Förbereder KONVERTERING av ett utkast till en bokförd post.

    utkasttyp: "verifikat", "kundfaktura", "leverantorsfaktura"
    utkast_id: utkastets id

    Detta bokför INTE utkastet — det förbereder åtgärden för granskning.
    Oåterkalleligt vid godkännande.
    \"\"\"
    try:
        klient = bygg_klient()
        if utkasttyp == "verifikat":
            uppslagstyp = "verifikatutkast"
        else:
            uppslagstyp = f"{utkasttyp}utkast"
            
        rå = spiris_adapter.hamta_ett(klient, uppslagstyp, utkast_id)
        if utkasttyp == "verifikat":
            utk = rå["verifikat"]
            datum = utk.get("datum", "")
            text = utk.get("text", "")
            belopp = sum(abs(r.get("belopp", 0)) for r in utk.get("rader", [])) / 2
            radantal = len(utk.get("rader", []))
        else:
            datum = rå.get("InvoiceDate") or rå.get("VoucherDate") or ""
            text = rå.get("InvoiceText") or rå.get("VoucherText") or ""
            belopp = rå.get("TotalAmountInvoiceCurrency") or 0
            radantal = len(rå.get("Rows") or [])
    except Exception as e:
        return _fel("Kunde inte hämta utkastet från Spiris. Inget förslag lades.")

    sammanfattning = [
        ["Åtgärd", f"BOKFÖR {utkasttyp}utkast"],
        ["Utkast-id", str(utkast_id)],
        ["Datum", str(datum)],
        ["Text", str(text)],
        ["Belopp", str(belopp)],
        ["Radantal", str(radantal)],
        ["Varning", "Bokföringen är oåterkallelig."],
    ]

    def _bygg():
        u = utkast.skapa(
            "utkastbokforing",
            {"utkasttyp": utkasttyp, "utkast_id": str(utkast_id).strip()},
            sammanfattning,
        )
        return _utkastsvar(
            u, f"Bokföring av {utkasttyp}utkast föreslås. Åtgärden är oåterkallelig."
        )

    return await _kor_utkastverktyg(
        _bygg, ctx, f"Förslag: bokför {utkasttyp}utkast {utkast_id}", sammanfattning
    )
"""
    if "async def forbered_utkastandring" not in content:
        content = content + "\n\n" + new_tools

    with open("mcp_server/server.py", "w", encoding="utf-8") as f:
        f.write(content)

    # Now update tests/test_mcp_villkorssparr.py
    with open("tests/test_mcp_villkorssparr.py", "r", encoding="utf-8") as f:
        tests_content = f.read()

    new_args = """
    "forbered_utkastandring": ("verifikat", "1", {}),
    "forbered_utkastborttagning": ("verifikat", "1"),
    "forbered_utkastbokforing": ("verifikat", "1"),
"""
    if "forbered_utkastandring" not in tests_content:
        tests_content = tests_content.replace(
            "    \"forbered_masterdataborttagning\": (\"kund\", \"1\", \"felkund\"),\n",
            "    \"forbered_masterdataborttagning\": (\"kund\", \"1\", \"felkund\"),\n" + new_args
        )

    new_funcs = """
        lambda: server_modul.forbered_utkastandring("verifikat", "1", {}),
        lambda: server_modul.forbered_utkastborttagning("verifikat", "1"),
        lambda: server_modul.forbered_utkastbokforing("verifikat", "1"),
"""
    if "forbered_utkastandring(" not in tests_content:
        tests_content = tests_content.replace(
            "        lambda: server_modul.forbered_masterdataborttagning(\"kund\", \"1\", \"felkund\"),\n",
            "        lambda: server_modul.forbered_masterdataborttagning(\"kund\", \"1\", \"felkund\"),\n" + new_funcs
        )
        
    skrivande_verktyg = """| {"forbered_utkastandring", "forbered_utkastborttagning", "forbered_utkastbokforing"}"""
    
    if "forbered_utkastandring" not in tests_content.split("UTATRIKTAT")[0]: # Just to ensure we add to Skrivande
        tests_content = tests_content.replace(
            "| {\"forbered_masterdataandring\", \"forbered_masterdataborttagning\"}",
            "| {\"forbered_masterdataandring\", \"forbered_masterdataborttagning\"}\n        " + skrivande_verktyg
        )

    with open("tests/test_mcp_villkorssparr.py", "w", encoding="utf-8") as f:
        f.write(tests_content)

if __name__ == "__main__":
    main()
