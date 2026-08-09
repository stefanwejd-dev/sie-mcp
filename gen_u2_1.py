import re

def main():
    with open("parser/spiris_adapter.py", "r", encoding="utf-8") as f:
        content = f.read()

    utkast_andring = """
_UTKASTSLAG: dict[str, str] = {
    "verifikat": "/voucherdrafts",
    "kundfaktura": "/customerinvoicedrafts",
    "leverantorsfaktura": "/supplierinvoicedrafts",
}

_UTKASTANDRING: dict[str, tuple[str, dict[str, str]]] = {
    "verifikat": ("/voucherdrafts", {
        "datum": "VoucherDate",
        "text": "VoucherText",
        "serie": "NumberSeries",
        "rader": "Rows"
    })
}

def bygg_utkastuppdatering(
    nuvarande: dict, andringar: dict, objekttyp: str
) -> dict:
    \"\"\"Lägger ändringarna ovanpå det NUVARANDE objektet och returnerar hela
    objektet, redo för PUT. Ren funktion, ingen I/O.
    Fail-closed på en nyckel som inte står i ändringsallowlisten.
    Returnerar hela objektet just för att PUT nollar det som utelämnas.\"\"\"
    if objekttyp not in _UTKASTANDRING:
        giltiga = ", ".join(repr(t) for t in _UTKASTANDRING)
        raise SpirisKlientFel(
            f"Okänd utkasttyp: {objekttyp!r}. Giltiga är: {giltiga}."
        )
    _, allowlist = _UTKASTANDRING[objekttyp]
    if not andringar:
        raise ValueError("Inga ändringar angivna.")

    okanda = [nyckel for nyckel in andringar if nyckel not in allowlist]
    if okanda:
        giltiga = ", ".join(sorted(allowlist))
        raise SpirisKlientFel(
            f"Följande går inte att ändra på ett {objekttyp}utkast: "
            f"{sorted(okanda)}. Ändringsbara fält: {giltiga}."
        )

    uppdaterat = dict(nuvarande)
    for nyckel, varde in andringar.items():
        uppdaterat[allowlist[nyckel]] = varde
    return uppdaterat


def andra_utkast(
    klient: _Spirisklient, typ: str, id: str, andringar: dict
) -> dict:
    \"\"\"Läser utkastet, lägger på ändringarna och skriver tillbaka HELA
    utkastet.\"\"\"
    if typ not in _UTKASTANDRING:
        giltiga = ", ".join(repr(t) for t in _UTKASTANDRING)
        raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}. Giltiga är: {giltiga}.")
    
    prefix, _ = _UTKASTANDRING[typ]
    nuvarande = klient.hamta_en(f"{prefix}/{id}")
    uppdaterat = bygg_utkastuppdatering(nuvarande, andringar, typ)
    try:
        svar = klient.uppdatera(f"{prefix}/{id}", uppdaterat)
    except SpirisKlientFel:
        _logger.error("Kunde inte uppdatera utkast %s (Id=%s).", typ, id)
        raise
    _logger.info(
        "Utkast uppdaterat: %s (Id=%s, fält=%s).",
        typ, id, sorted(andringar)
    )
    return svar


def ta_bort_utkast(klient: _Spirisklient, typ: str, id: str) -> None:
    \"\"\"Tar bort ett utkast. Oåterkallelig DELETE.\"\"\"
    if typ not in _UTKASTSLAG:
        giltiga = ", ".join(repr(t) for t in _UTKASTSLAG)
        raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}. Giltiga är: {giltiga}.")
    
    prefix = _UTKASTSLAG[typ]
    try:
        klient.ta_bort(f"{prefix}/{id}")
    except SpirisKlientFel:
        _logger.error("Kunde inte ta bort utkast %s (Id=%s).", typ, id)
        raise
    _logger.info("Utkast borttaget: %s (Id=%s).", typ, id)


def bokfor_utkast(klient: _Spirisklient, typ: str, id: str) -> dict:
    \"\"\"Konverterar ett utkast till en bokförd post. Oåterkalleligt.\"\"\"
    if typ not in _UTKASTSLAG:
        giltiga = ", ".join(repr(t) for t in _UTKASTSLAG)
        raise SpirisKlientFel(f"Okänd utkasttyp: {typ!r}. Giltiga är: {giltiga}.")
    
    prefix = _UTKASTSLAG[typ]
    try:
        # Konvertering görs alltid med POST och tom kropp, per specen U2.3.
        svar = klient.skicka(f"{prefix}/{id}/convert", None)
    except SpirisKlientFel:
        _logger.error("Kunde inte bokföra utkast %s (Id=%s).", typ, id)
        raise
    _logger.info("Utkast bokfört: %s (Id=%s).", typ, id)
"""

    if "_UTKASTSLAG" not in content:
        # Insert before andra_masterdata
        content = content.replace("def andra_masterdata(", utkast_andring + "\n\ndef andra_masterdata(")
    
    # Now in utfor_utkast add the UTKASTTYP_UTKASTANDRING, UTKASTTYP_UTKASTBORTTAGNING, UTKASTTYP_UTKASTBOKFORING
    # Wait, we need to add them to parser/spiris_adapter.py UTKASTTYP_* constants.
    constants = """
UTKASTTYP_UTKASTANDRING = "utkastandring"
UTKASTTYP_UTKASTBORTTAGNING = "utkastborttagning"
UTKASTTYP_UTKASTBOKFORING = "utkastbokforing"
"""
    if "UTKASTTYP_UTKASTANDRING" not in content:
        content = content.replace("UTKASTTYP_MASTERDATABORTTAGNING = \"masterdataborttagning\"", "UTKASTTYP_MASTERDATABORTTAGNING = \"masterdataborttagning\"\n" + constants)
    
    handlers = """
    if typ == UTKASTTYP_UTKASTANDRING:
        return andra_utkast(
            klient, nyttolast["utkasttyp"], nyttolast["utkast_id"],
            nyttolast["andringar"]
        )

    if typ == UTKASTTYP_UTKASTBORTTAGNING:
        ta_bort_utkast(klient, nyttolast["utkasttyp"], nyttolast["utkast_id"])
        return {"borttaget": nyttolast["utkast_id"]}

    if typ == UTKASTTYP_UTKASTBOKFORING:
        return bokfor_utkast(klient, nyttolast["utkasttyp"], nyttolast["utkast_id"])
"""
    if "UTKASTTYP_UTKASTANDRING" not in content.split("def utfor_utkast(")[1]:
        # Add inside utfor_utkast
        content = content.replace(
            "if typ == UTKASTTYP_MASTERDATAANDRING:",
            handlers + "\n    if typ == UTKASTTYP_MASTERDATAANDRING:"
        )

    with open("parser/spiris_adapter.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
