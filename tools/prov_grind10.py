"""prov_grind10 — sandbox-prov för GRIND 10 i `PLAN_SPIRIS_ETAPP8.md`.

Provet svarar på tre frågor som specen påstår sig svara på, men som kodbasens
historik säger att man inte ska tro på utan att ha sett det själv (`Type` för
svenska bolag, `#KTYP` i sie4export, `/offers` som egentligen heter `/quotes`
— specen har ljugit varje gång det spelat roll):

1. **Landsspärrarna.** Specen säger att `POST /paymentvoucher` bara finns för
   norska och nederländska bolag, att `POST /voucherwithoverunderpayment`
   INTE finns för svenska bolag, och att `GET /accounts/standardaccounts` bara
   finns för nederländska. Den mellersta är den som bränner: kodbasen har
   redan ett verktyg (`forbered_betalningsverifikat`) byggt på den. Provet
   avgör om verktyget är dödfött mot ett svenskt bolag.

2. **Kvittningsvägen.** `POST /supplierinvoices/{id}/offset` är fullt
   specificerad (`DebitInvoiceIds`, `VoucherDate`). Provet kartlägger om
   bolaget överhuvudtaget har en kreditfaktura att kvitta, och kör vid
   uttryckligt medgivande en skarp kvittning.

3. **Feltexterna.** Vad Spiris FAKTISKT svarar när något inte är tillåtet.
   `SpirisKlient` fail-closar och kastar bort svarskroppen med flit — det är
   rätt beteende i drift och obrukbart i ett prov. Skriptet gör därför sina
   anrop med httpx direkt och skriver ut rå status och rå kropp. Det är den
   ENDA platsen i kodbasen där det är motiverat, och det är motiverat just för
   att provets hela poäng är att se det klienten döljer.

Säkerhetsinvarianter, samma som `migrera_lagring.py` och
`rotera_hemligheter.py`:

- **Torrkörning är standard.** Ingen skrivning sker utan BÅDE ``--utfor`` OCH
  ``--bekrafta``.
- **Bolagsgrind.** ``--bolag`` är obligatoriskt och måste matcha bolagets
  faktiska namn i Spiris. Ett prov som skriver i fel bolag är inte ett prov.
- **Aldrig hemligheter.** Access- och refresh-token skrivs aldrig ut, varken
  hela eller delvis, varken vid fel eller framgång.
- **Fas 1 och 2 ändrar ingenting.** De läser, och sonderar med medvetet
  ofullständiga kroppar — ett HTTP 400 skapar inget.

VARNING OM UTDATA: skriptet skriver ut riktiga bolagsuppgifter — leverantörs-
namn, fakturanummer, belopp. Utdatat är alltså inte maskerat och ska inte
klistras in i en AI-chatt. Det är ett lokalt diagnostikverktyg, inte ett
verktygssvar.

Körexempel:

    python tools/prov_grind10.py --bolag "Mitt Sandboxbolag"
    python tools/prov_grind10.py --bolag "Mitt Sandboxbolag" --offset
    python tools/prov_grind10.py --bolag "Mitt Sandboxbolag" --offset \\
        --utfor --bekrafta
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROT / "parser"))

import httpx  # noqa: E402

import saker_lagring  # noqa: E402
from spiris_klient import API_BAS, SpirisKlientFel  # noqa: E402
from spiris_session import bygg_klient, spara_session  # noqa: E402

_TIMEOUT = 30.0

# De tre operationer specen påstår är landsbegränsade. Sonderas med en TOM
# kropp: en operation som inte finns för bolaget ska svara annorlunda än en
# som finns men fick ogiltig indata, och skillnaden är hela svaret vi vill ha.
_LANDSPROV: tuple[tuple[str, str, str], ...] = (
    ("POST", "/paymentvoucher",
     "Specen: endast norska och nederländska bolag."),
    ("POST", "/voucherwithoverunderpayment",
     "Specen: INTE för svenska bolag. forbered_betalningsverifikat "
     "bygger på den här."),
    ("GET", "/accounts/standardaccounts",
     "Specen: endast nederländska bolag. R8.6 i planen begärde den."),
)


def _las_env() -> None:
    """Läser .env ur den säkra lagringen och speglar SIE_MCP_-prefixen till de
    namn `bygg_klient` läser. Samma bootstrap som `probe_u7.py` använde."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("python-dotenv saknas — installera requirements.txt.")
        raise SystemExit(2)
    load_dotenv(saker_lagring.artefakt_sokvag(None, kategori="secret", namn=".env"))
    for kort, lang in (
        ("SPIRIS_CLIENT_ID", "SIE_MCP_SPIRIS_CLIENT_ID"),
        ("SPIRIS_CLIENT_SECRET", "SIE_MCP_SPIRIS_CLIENT_SECRET"),
    ):
        if os.environ.get(lang) and not os.environ.get(kort):
            os.environ[kort] = os.environ[lang]


def _anrop(
    token: str, metod: str, path: str,
    *, params: dict | None = None, kropp: Any = None,
) -> tuple[int, str]:
    """Rått HTTP-anrop som returnerar (status, kroppstext).

    Medvetet FÖRBI `SpirisKlient`: klienten mappar varje fel till
    `SpirisKlientFel` och kastar svarskroppen, vilket är precis den information
    provet finns för att samla in. Ingen refresh sker här — den har redan
    gjorts av `_forbered_token` innan första anropet."""
    huvuden = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        svar = httpx.request(
            metod, f"{API_BAS}{path}",
            headers=huvuden, params=params or {},
            content=json.dumps(kropp) if kropp is not None else None,
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as e:
        return 0, f"(nätverksfel: {type(e).__name__})"
    return svar.status_code, (svar.text or "")[:1200]


def _forbered_token(klient: Any) -> str:
    """Tvingar fram en giltig access_token genom ett ofarligt klientanrop.

    Går anropet igenom är token giltig; var den utgången har klienten redan
    gjort sin refresh och uppdaterat `klient.access_token`. Provet slipper
    därmed egen tokenlogik, och den refreshade token persisteras av
    anroparen."""
    klient.hamta_en("/companysettings")
    return klient.access_token


# -- Fas 1: bolagsgrind och landsspärrar --------------------------------------

def fas_bolag(klient: Any, forvantat: str) -> dict:
    """Läser bolagsuppgifterna och avbryter om namnet inte matchar."""
    installningar = klient.hamta_en("/companysettings")
    namn = str(installningar.get("Name") or "")
    land = str(installningar.get("CountryCode") or "")
    print(f"Bolag:  {namn}")
    print(f"Land:   {land or '(saknas)'}")
    if forvantat.strip().lower() not in namn.lower():
        print(
            f"\nAVBRYTER: --bolag {forvantat!r} matchar inte {namn!r}.\n"
            "Bolagsgrinden finns för att ett prov aldrig ska kunna köras mot "
            "fel bolag. Ingenting har lästs vidare och ingenting har skrivits."
        )
        raise SystemExit(1)
    if land and land.upper() != "SE":
        print(
            f"\nOBS: bolaget är registrerat i {land}, inte SE. Landsspärrarna "
            "nedan gäller svenska bolag — utfallet säger då inget om den "
            "svenska vägen."
        )
    return {"namn": namn, "land": land}


def fas_landsprov(token: str) -> list[dict]:
    """Sonderar de tre landsbegränsade operationerna med tom kropp.

    Ett 400 betyder 'operationen finns, indatat dög inte'. Ett 403/404/501
    betyder 'operationen finns inte för det här bolaget'. Skillnaden är hela
    provet. Ingenting skapas i något av fallen."""
    print("\n=== FAS 1: landsspärrar (sonderande, skriver ingenting) ===")
    resultat = []
    for metod, path, notering in _LANDSPROV:
        kropp = {} if metod == "POST" else None
        status, text = _anrop(token, metod, path, kropp=kropp)
        tolkning = {
            0: "nätverksfel",
            400: "FINNS (avvisade tom kropp — vad som väntas står i texten)",
            401: "token nekades",
            403: "SPÄRRAD för bolaget",
            404: "FINNS INTE för bolaget",
            405: "fel verb",
            501: "ej implementerad för bolaget",
        }.get(status, "okänt utfall — läs kroppen")
        print(f"\n{metod} {path}")
        print(f"  {notering}")
        print(f"  HTTP {status} — {tolkning}")
        print(f"  Svar: {text.strip()[:600] or '(tom kropp)'}")
        resultat.append(
            {"metod": metod, "path": path, "status": status, "svar": text}
        )
    return resultat


# -- Fas 2: kvittningsvägen ---------------------------------------------------

def fas_kvittning_kartlagg(klient: Any) -> list[dict]:
    """Letar upp kreditfakturor på leverantörssidan och deras kvittnings-
    kandidater. Ren läsning."""
    print("\n=== FAS 2: kvittningsvägen (läsande) ===")
    try:
        fakturor = klient.hamta_alla("/supplierinvoices")
    except SpirisKlientFel as e:
        print(f"Kunde inte läsa leverantörsfakturor: {e}")
        return []

    krediter = [f for f in fakturor if f.get("IsCreditInvoice")]
    print(f"Leverantörsfakturor: {len(fakturor)}  varav krediter: {len(krediter)}")
    if not krediter:
        print(
            "Bolaget saknar kreditfaktura på leverantörssidan. Kvittningen går "
            "inte att pröva här — skapa en kreditfaktura i Spiris först, eller "
            "godta att U15b lämnas overerifierad."
        )
        return []

    underlag = []
    for kredit in krediter:
        kid = str(kredit.get("Id") or "")
        nummer = kredit.get("InvoiceNumber")
        belopp = kredit.get("TotalAmount")
        print(f"\nKredit {nummer} (id {kid})  belopp {belopp}")
        try:
            kandidater = klient.hamta_alla(
                f"/supplierinvoices/{kid}/offsetcandidates"
            )
        except SpirisKlientFel as e:
            print(f"  offsetcandidates gav fel: {e}")
            continue
        print(f"  kvittningsbara debetfakturor: {len(kandidater)}")
        for k in kandidater[:5]:
            print(
                f"    {k.get('InvoiceNumber')}  {k.get('SupplierName')}  "
                f"kvar {k.get('RemainingAmount')} {k.get('CurrencyCode')}"
            )
        if kandidater:
            underlag.append({"kredit_id": kid, "kandidater": kandidater})
    return underlag


def fas_kvittning_utfor(
    token: str, underlag: list[dict], *, utfor: bool
) -> None:
    """Bygger kvittningskroppen och skickar den bara vid uttryckligt
    medgivande.

    Kroppen är spec-fastställd (`SupplierInvoiceOffsetCreateApi`):
    `DebitInvoiceIds` och `VoucherDate`, båda obligatoriska,
    `additionalProperties: false`. Provet bekräftar alltså ett känt kontrakt —
    det gissar inte fram ett."""
    if not underlag:
        return
    from datetime import date

    post = underlag[0]
    kropp = {
        "DebitInvoiceIds": [str(post["kandidater"][0].get("InvoiceId"))],
        "VoucherDate": date.today().isoformat(),
    }
    path = f"/supplierinvoices/{post['kredit_id']}/offset"

    print("\n--- Kvittning, planerad begäran ---")
    print(f"POST {path}")
    print(json.dumps(kropp, ensure_ascii=False, indent=2))

    if not utfor:
        print(
            "\nTORRKÖRNING: ingenting skickades. Kör om med --utfor --bekrafta "
            "för att pröva skarpt.\n"
            "Observera att en kvittning skapar ett verifikat i bolaget. Den är "
            "återställbar via POST /supplierinvoices/{id}/offset/undo, men den "
            "vägen byggs aldrig i sie-mcp (beslut D5) — ångringen får göras "
            "för hand i Spiris."
        )
        return

    status, text = _anrop(token, "POST", path, kropp=kropp)
    print(f"\nHTTP {status}")
    print(text.strip()[:900] or "(tom kropp)")


# -- Sammanfattning -----------------------------------------------------------

def sammanfatta(landsprov: list[dict]) -> None:
    print("\n=== SLUTSATSER ATT SKRIVA IN I PLANEN ===")
    for r in landsprov:
        finns = r["status"] not in (403, 404, 501)
        etikett = "FINNS" if finns else "FINNS INTE"
        print(f"  {r['metod']} {r['path']}: {etikett} (HTTP {r['status']})")
    print(
        "\nOm POST /voucherwithoverunderpayment står som FINNS INTE är\n"
        "forbered_betalningsverifikat dödfött mot det här bolaget och ska\n"
        "avvecklas enligt R8.7. Står den som FINNS har specen fel igen —\n"
        "notera det, för då gäller det motsatta."
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Sandbox-prov för GRIND 10 (landsspärrar och kvittning).",
    )
    p.add_argument(
        "--bolag", required=True,
        help="Del av bolagsnamnet i Spiris. Måste matcha, annars avbryts provet.",
    )
    p.add_argument(
        "--offset", action="store_true",
        help="Kör även fas 2, kvittningsvägen.",
    )
    p.add_argument("--utfor", action="store_true", help="Tillåt skarp skrivning.")
    p.add_argument(
        "--bekrafta", action="store_true",
        help="Krävs tillsammans med --utfor. Två flaggor, ett medvetet val.",
    )
    args = p.parse_args()

    if args.utfor and not args.bekrafta:
        print("--utfor kräver --bekrafta. Ingenting kördes.")
        return 2
    utfor = args.utfor and args.bekrafta

    _las_env()
    try:
        klient = bygg_klient()
    except Exception as e:  # noqa: BLE001 — aldrig tokeninnehåll ut
        print(f"Kunde inte bygga Spiris-klienten: {type(e).__name__}. "
              "Logga in mot Spiris i Streamlit-appen först.")
        return 2

    try:
        token = _forbered_token(klient)
    except SpirisKlientFel as e:
        print(f"Sessionen dög inte: {e}")
        return 2

    try:
        fas_bolag(klient, args.bolag)
        landsprov = fas_landsprov(token)
        if args.offset:
            underlag = fas_kvittning_kartlagg(klient)
            fas_kvittning_utfor(token, underlag, utfor=utfor)
        sammanfatta(landsprov)
    finally:
        # Persistera en ev. refreshad token oavsett utfall — samma mönster som
        # mcp_server/server.py:_kor_spiris_verktyg.
        try:
            spara_session(klient)
        except Exception:  # noqa: BLE001 — ett provskript får inte dö på detta
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
