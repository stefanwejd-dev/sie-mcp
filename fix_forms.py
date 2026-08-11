import re

with open('parser/atgardsformular.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We want to replace from KUND_FORMULAR down to the end of ALLA_FORMULAR list.
# Let's locate KUND_FORMULAR
start_idx = content.find("KUND_FORMULAR = Atgardsformular(")

# Let's locate the end of ALLA_FORMULAR
end_idx = content.find("]", content.find("ALLA_FORMULAR = [")) + 1

new_content = content[:start_idx] + """KUND_FORMULAR = Atgardsformular(
    utkasttyp="kund",
    rubrik="Skapa kund",
    ikon="👤",
    falt=(),
    bygg_nyttolast=lambda v: {},
    bygg_sammanfattning=lambda v: [["Namn", str(v.get("Name", v.get("kundnamn", "")))]],
    egen_ritare=lambda st: None,
)

def _kundfaktura_nyttolast(v: dict[str, Any]) -> dict[str, Any]:
    req = ["rader", "kundnamn", "forfallodatum", "fakturadatum"]
    for k in req:
        if k not in v: raise ValueError(f"Saknar obligatorisk nyckel: {k}")
    return {k: v[k] for k in req}

KUNDFAKTURA_FORMULAR = Atgardsformular(
    utkasttyp="kundfaktura",
    rubrik="Skapa kundfaktura",
    ikon="📄",
    falt=(),
    bygg_nyttolast=_kundfaktura_nyttolast,
    bygg_sammanfattning=lambda v: [
        ["Kundnamn", str(v.get("kundnamn", ""))],
        ["Fakturadatum", str(v.get("fakturadatum", ""))],
        ["Förfallodatum", str(v.get("forfallodatum", ""))]
    ],
    egen_ritare=_ritare_kundfaktura,
)

ALLA_FORMULAR = [
    BETALNINGSVERIFIKAT,
    VERIFIKAT, SIE4IMPORT, 
    FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK, SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD,
    LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST,
    MASTERDATAANDRING, MASTERDATABORTTAGNING,
    UTKASTANDRING, UTKASTBORTTAGNING, UTKASTBOKFORING,
    PERIODISERING,
    KUND_FORMULAR,
    KUNDFAKTURA_FORMULAR,
]""" + content[end_idx:]

with open('parser/atgardsformular.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
