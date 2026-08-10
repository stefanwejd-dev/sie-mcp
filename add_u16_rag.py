import os

fpath = "parser/spiris_rag.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

new_code = '''
async def hamta_prislistor(k: _Spirisklient, prislista_id: str | None = None) -> list[dict]:
    """U16.1 — spiris_prislistor"""
    if not prislista_id:
        rader = await asynk_hamta_alla(k, "/salespricelists")
        res = []
        for r in rader:
            res.append({
                "Id": r.get("Id"),
                "Name": r.get("Name"),
                "Number": r.get("Number"),
                "CurrencyCode": r.get("CurrencyCode"),
                "IsStandard": r.get("IsStandard"),
                "IsActive": r.get("IsActive"),
            })
        return res
    else:
        rader = await asynk_hamta_alla(k, f"/salespricelists/prices/{prislista_id}")
        res = []
        for r in rader:
            res.append({
                "SalesPriceListId": r.get("SalesPriceListId"),
                "ArticleId": r.get("ArticleId"),
                "NetPrice": str(r.get("NetPrice")) if r.get("NetPrice") is not None else None,
                "GrossPrice": str(r.get("GrossPrice")) if r.get("GrossPrice") is not None else None,
                "CurrencyCode": r.get("CurrencyCode"),
            })
        return res


async def hamta_rabattavtal(k: _Spirisklient) -> list[dict]:
    """U16.2 — spiris_rabattavtal"""
    rader = await asynk_hamta_alla(k, "/discountagreements")
    res = []
    for r in rader:
        res.append({
            "Id": r.get("Id"),
            "Name": r.get("Name"),
            "Number": r.get("Number"),
            "IsActive": r.get("IsActive"),
        })
    return res


async def hamta_etiketter(k: _Spirisklient, typ: str) -> list[dict]:
    """U16.3 — spiris_etiketter"""
    if typ not in ("kund", "artikel"):
        raise ValueError(f"Okänd etiketttyp: {typ}. Måste vara 'kund' eller 'artikel'.")
        
    ep = "/customerlabels" if typ == "kund" else "/articlelabels"
    rader = await asynk_hamta_alla(k, ep)
    res = []
    for r in rader:
        res.append({
            "Id": r.get("Id"),
            "Name": r.get("Name"),
            "Description": r.get("Description"),
        })
    return res
'''

content += new_code

with open(fpath, "w", encoding="utf-8") as f:
    f.write(content)
