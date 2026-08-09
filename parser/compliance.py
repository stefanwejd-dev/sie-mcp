"""compliance.py — obligatorisk villkorsspärr före all användning av sie-mcp.

Modulen är EN sanning för villkorstexten och för godkännandet. Både
Streamlit-appen (`app.py`) och MCP-servern (`mcp_server/server.py`) läser
härifrån, så att ingen väg in i programvaran kan öppnas utan att
slutanvändaren uttryckligen har godkänt samtliga ansvarspunkter.

Tre bärande principer, som inte får tas bort:

1. **Fail-closed.** Saknas ett giltigt godkännande — eller går det inte att
   läsa — returnerar `ar_compliance_godkand()` False. Ett fel i lagringen ska
   låsa programvaran, aldrig öppna den.
2. **Punkt för punkt.** Godkännandet är inte en enda kryssruta. Varje
   ansvarspunkt i `VILLKORSPUNKTER` måste bekräftas var för sig och lagras
   med sin nyckel. Ett godkännande som saknar en punkt som senare lagts till
   är ogiltigt — därför jämförs mot `VILLKORSPUNKTER` vid varje kontroll, inte
   bara mot versionssträngen.
3. **Godkännande kan ALDRIG ske via MCP.** En MCP-klient är en AI. En AI får
   inte ingå avtal eller acceptera ansvar för människan som kör den. Därför
   finns ingen skrivande MCP-väg hit — MCP-servern kan bara LÄSA villkoren och
   hänvisa till den lokala CLI:n eller Streamlit-appen, där en människa sitter.

Ändras villkorens innebörd ska `COMPLIANCE_VERSION` höjas. Då blir alla
tidigare godkännanden ogiltiga och användaren måste ta ställning på nytt.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from saker_lagring import SakerLagringFel, state_dir

# Höj vid varje MATERIELL ändring av villkoren nedan. Ogiltigförklarar alla
# tidigare godkännanden — det är avsikten.
COMPLIANCE_VERSION = "2026-08-04-v4"

_FILNAMN = "compliance_accepted.json"


@dataclass(frozen=True)
class Villkorspunkt:
    """En ansvarspunkt som måste bekräftas var för sig.

    `nyckel` lagras i godkännandefilen och är det som gör ett godkännande
    spårbart till exakt vad användaren tog ställning till. Byt aldrig
    innebörden av en befintlig nyckel — lägg till en ny och höj versionen.
    """

    nyckel: str
    rubrik: str
    text: str


VILLKORSPUNKTER: tuple[Villkorspunkt, ...] = (
    Villkorspunkt(
        nyckel="fullt_eget_ansvar",
        rubrik="Jag bär hela det juridiska ansvaret",
        text=(
            "Jag bär ensam och fullt ut allt juridiskt ansvar för min användning av "
            "programvaran, för all data jag matar in i den, för allt som sänds vidare "
            "till externa tjänster och för varje resultat, beslut, åtgärd eller "
            "leverans som användningen leder till. Upphovsmän, utvecklare och "
            "bidragsgivare bakom sie-mcp bär inget som helst ansvar — under några "
            "omständigheter, på någon rättslig grund och oavsett vem som framställer "
            "anspråket: varken mot mig, mot mina klienter, mot registrerade personer, "
            "mot andra tredje män eller mot myndigheter. Jag håller dem dessutom "
            "skadeslösa för anspråk som riktas mot dem till följd av min användning."
        ),
    ),
    Villkorspunkt(
        nyckel="inga_garantier",
        rubrik="Programvaran lämnar inga garantier",
        text=(
            "Programvaran tillhandahålls i befintligt skick, utan garantier av något "
            "slag, uttryckliga eller underförstådda. Inga utfästelser lämnas om "
            "funktion, riktighet, tillgänglighet, säkerhet eller lämplighet för något "
            "ändamål. Jag använder den helt på egen risk."
        ),
    ),
    Villkorspunkt(
        nyckel="resultat_ej_verklighet",
        rubrik="Resultaten kan inte antas motsvara verkligheten",
        text=(
            "Siffror, tabeller, analyser, diagram, nyckeltal, väsentlighetstal, "
            "klassificeringar och AI-genererade svar som programvaran visar utgör "
            "INTE en utsaga om faktiska förhållanden och kan inte antas motsvara "
            "verkligheten, den underliggande bokföringen eller gällande regelverk. "
            "De kan vara ofullständiga, felaktiga, missvisande eller helt påhittade. "
            "Jag ansvarar ensam för att självständigt kontrollera och verifiera varje "
            "uppgift mot källmaterialet innan jag använder eller förlitar mig på den."
        ),
    ),
    Villkorspunkt(
        nyckel="ingen_professionell_radgivning",
        rubrik="Detta är inte professionell rådgivning",
        text=(
            "Programvaran utgör inte revisions-, redovisnings-, skatte-, finansiell "
            "eller juridisk rådgivning, och ersätter inte min egen professionella "
            "bedömning enligt ISA, god revisionssed, god redovisningssed, BFN:s "
            "allmänna råd (K2/K3), bokföringslagen eller annan tillämplig reglering. "
            "Jag ansvarar ensam för mina yrkesmässiga bedömningar och för det jag "
            "levererar till mina egna klienter."
        ),
    ),
    Villkorspunkt(
        nyckel="ingen_efterlevnadsutfastelse",
        rubrik="Ingen utfästelse om efterlevnad av GDPR eller annan lag",
        text=(
            "Programvaran gör inget anspråk på, och lämnar ingen utfästelse om, att "
            "den — eller min användning av den — uppfyller dataskyddsförordningen "
            "(GDPR), dataskyddslagen, personuppgiftsbiträdesavtal, AI-förordningen, "
            "bokföringslagen eller någon annan lagstiftning. Att bedöma och säkerställa "
            "att min användning är laglig är helt och hållet mitt eget ansvar."
        ),
    ),
    Villkorspunkt(
        nyckel="pseudonymisering_utan_garanti",
        rubrik="Pseudonymiseringen är en funktion — inte ett skydd jag kan förlita mig på",
        text=(
            "Programvarans maskerings- och pseudonymiseringsfunktion är enbart ett "
            "tekniskt hjälpmedel utan garanti. Den har kända och dokumenterade "
            "begränsningar (se DISCLAIMER_AND_TERMS.md), och personuppgifter kan nå en "
            "extern AI-leverantör i klartext utan att jag varnas. Pseudonymiserad data "
            "förblir dessutom personuppgifter i GDPR:s mening. Jag förlitar mig inte på "
            "funktionen som ett dataskydd och ansvarar ensam för vilken data jag väljer "
            "att sända."
        ),
    ),
    Villkorspunkt(
        nyckel="byok_egna_avtal",
        rubrik="Egna nycklar, egna konton, egna avtal (BYOK/BYOA)",
        text=(
            "Alla anslutningar till AI-leverantörer och affärssystem sker med mina egna "
            "API-nycklar, mina egna utvecklar- och användarkonton och under mina egna "
            "avtal. Jag ansvarar ensam för att teckna nödvändiga "
            "personuppgiftsbiträdesavtal, för giltig grund för tredjelandsöverföring, "
            "och för att följa respektive leverantörs villkor — inklusive Vismas/Spiris "
            "utvecklarvillkor. Upphovsmännen bakom sie-mcp är inte part i något av "
            "dessa avtal."
        ),
    ),
    Villkorspunkt(
        nyckel="utkast_och_skrivning",
        rubrik="Jag ansvarar för varje åtgärd jag godkänner",
        text=(
            "Programvaran kan låta en AI-assistent FÖRESLÅ åtgärder i mitt "
            "affärssystem — nya kunder, kundfakturor och verifikat. Inget förslag "
            "utförs förrän jag själv har granskat de verkliga uppgifterna och "
            "uttryckligen godkänt dem. Ett förslag är inte ett beslut och inte ett "
            "utfört uppdrag. Jag ansvarar ensam för att kontrollera varje uppgift "
            "innan jag godkänner, och för allt som följer av åtgärden — inklusive "
            "att en bokförd post uppfyller bokföringslagens krav och att en "
            "utskickad faktura är riktig. Ett verifikat kan inte tas bort i "
            "efterhand, bara rättas med ett nytt."
        ),
    ),
    Villkorspunkt(
        nyckel="lokala_loggar",
        rubrik="Jag ansvarar för de lokala loggarna och filerna",
        text=(
            "Programvaran skriver lokala, okrypterade loggfiler som kan innehålla "
            "personuppgifter och den faktiska nyttolast som sänts till externa "
            "tjänster. Jag ansvarar ensam för dessa filers säkerhet, åtkomst, "
            "gallring och för hur de behandlas i min egen verksamhet."
        ),
    ),
)


# Kort, statisk text som visas där en människa faktiskt inte sitter (MCP-svar,
# CLI-utskrift). Får aldrig innehålla ett trygghetsbudskap — den ska säga vad
# som gäller, inte lugna.
SPARRTEXT_KORT = (
    "Blockerad: användarvillkoren för sie-mcp har inte godkänts på den här datorn. "
    "Programvaran lämnar inga garantier, utgör inte professionell rådgivning och "
    "gör inget anspråk på att uppfylla GDPR eller annan lagstiftning — hela det "
    "juridiska ansvaret för användningen ligger på slutanvändaren. "
    "En människa måste godkänna villkoren lokalt innan verktygen kan användas: "
    "kör `python parser/compliance.py --godkann` i en terminal på den här datorn, "
    "eller starta Streamlit-appen (`streamlit run app.py`) och godkänn där. "
    "Godkännande kan inte ske via MCP."
)

INLEDNING = (
    "sie-mcp är fri programvara som körs lokalt på din egen dator. Den tillhandahålls "
    "i befintligt skick, utan garantier, och lämnar inga utfästelser om riktighet, "
    "säkerhet eller efterlevnad av lagstiftning. Genom att godkänna nedanstående "
    "punkter bekräftar du att hela det juridiska ansvaret för användningen och för "
    "dess resultat är ditt, och att upphovsmännen bakom programvaran inte bär något "
    "ansvar. Godkänner du inte samtliga punkter får programvaran inte användas."
)


def villkorstext() -> str:
    """Villkoren som löpande text — för CLI, MCP-svar och dokumentation."""
    rader = [
        f"sie-mcp — användarvillkor och ansvarsfriskrivning (version {COMPLIANCE_VERSION})",
        "",
        INLEDNING,
        "",
    ]
    for i, punkt in enumerate(VILLKORSPUNKTER, start=1):
        rader.append(f"{i}. {punkt.rubrik}")
        rader.append(f"   {punkt.text}")
        rader.append("")
    rader.append(
        "Fullständiga villkor: DISCLAIMER_AND_TERMS.md och LICENSE i programvarans katalog."
    )
    return "\n".join(rader)


def _filsokvag() -> Path:
    return state_dir() / _FILNAMN


def ar_compliance_godkand() -> bool:
    """True endast om SAMTLIGA gällande villkorspunkter är godkända.

    Fail-closed: saknad fil, fel version, saknad punkt, trasig JSON eller ett
    lagringsfel ger alltid False.
    """
    try:
        fil = _filsokvag()
        if not fil.exists():
            return False
        data = json.loads(fil.read_text(encoding="utf-8"))
    except (SakerLagringFel, OSError, ValueError):
        return False

    if not isinstance(data, dict):
        return False
    if data.get("version") != COMPLIANCE_VERSION:
        return False
    if data.get("godkand") is not True:
        return False

    godkanda = data.get("godkanda_punkter")
    if not isinstance(godkanda, list):
        return False
    return all(punkt.nyckel in godkanda for punkt in VILLKORSPUNKTER)


def godkann_compliance() -> None:
    """Lagra ett fullständigt godkännande lokalt (i %LOCALAPPDATA%).

    Anropas endast från en väg där en MÄNNISKA har bekräftat varje punkt:
    Streamlit-spärren eller CLI:n nedan. Aldrig från MCP-servern.
    """
    fil = _filsokvag()
    fil.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": COMPLIANCE_VERSION,
        "godkand": True,
        "datum": datetime.now().isoformat(),
        "roll": "slutanvandare_byok",
        "godkanda_punkter": [punkt.nyckel for punkt in VILLKORSPUNKTER],
    }
    fil.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def aterkalla_compliance() -> None:
    """Ta bort godkännandet. Fail-safe: saknad fil är inget fel."""
    try:
        _filsokvag().unlink(missing_ok=True)
    except (SakerLagringFel, OSError):
        pass


# --- Streamlit-spärren ------------------------------------------------------
# Renderingen ligger HÄR och inte i app.py, av två skäl: den måste kunna testas
# utan Streamlit-runtime (st injiceras), och den måste vara omöjlig att råka
# koppla loss från st.stop() vid en framtida redigering av app.py.

_KRYSSPREFIX = "compliance_punkt_"


def krav_godkannande(st) -> None:
    """Fail-closed villkorsspärr för Streamlit.

    Returnerar bara om användaren har godkänt samtliga punkter. I annat fall
    renderas villkoren och `st.stop()` anropas — ingen kod efter anropet körs,
    och därmed ritas ingen uppladdning, ingen Spiris-inloggning och ingen
    AI-yta. Anropas som allra första sak i `app.py`, efter `set_page_config`.
    """
    if ar_compliance_godkand():
        return

    st.error("⚖️ Användarvillkoren måste godkännas innan sie-mcp kan användas.")
    st.markdown(f"### Användarvillkor och ansvarsfriskrivning\n\n{INLEDNING}")

    alla_kryssade = True
    for punkt in VILLKORSPUNKTER:
        kryssad = st.checkbox(
            f"**{punkt.rubrik}** — {punkt.text}",
            key=f"{_KRYSSPREFIX}{punkt.nyckel}",
        )
        if not kryssad:
            alla_kryssade = False

    st.caption(
        "Fullständiga villkor finns i DISCLAIMER_AND_TERMS.md och LICENSE. "
        "Samtliga punkter måste kryssas i. Godkänner du inte får programvaran inte användas."
    )

    if st.button(
        "Jag har läst och godkänner samtliga villkor ovan",
        type="primary",
        disabled=not alla_kryssade,
        key="godkann_compliance_btn",
    ):
        godkann_compliance()
        st.rerun()

    st.stop()
    # Nås aldrig i en riktig Streamlit-runtime (st.stop() avbryter skriptet).
    # Returen finns för fejkade st-objekt i testsviten, så att spärren beter sig
    # likadant där: inget efter den här punkten körs.
    return


# --- CLI för headless-godkännande (MCP-användare) ---------------------------


def _cli(argv: list[str] | None = None) -> int:
    """Godkännande från terminalen, för den som bara kör MCP-servern.

    Kräver att användaren skriver bekräftelsefrasen exakt. Ingen flagga och
    ingen miljövariabel kan ersätta det: godkännandet ska vara en medveten
    mänsklig handling, inte något ett startskript råkar sätta.
    """
    try:  # svenska tecken i en Windows-konsol med cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    p = argparse.ArgumentParser(
        prog="compliance.py",
        description="Godkänn eller granska användarvillkoren för sie-mcp.",
    )
    p.add_argument("--godkann", action="store_true", help="Läs villkoren och godkänn dem.")
    p.add_argument("--status", action="store_true", help="Visa om villkoren är godkända.")
    p.add_argument("--aterkalla", action="store_true", help="Återkalla ett godkännande.")
    args = p.parse_args(argv)

    if args.status:
        print("Godkänt" if ar_compliance_godkand() else "INTE godkänt")
        return 0

    if args.aterkalla:
        aterkalla_compliance()
        print("Godkännandet är återkallat. sie-mcp är nu spärrad.")
        return 0

    if not args.godkann:
        p.print_help()
        return 1

    print(villkorstext())
    print()
    print("Skriv exakt JAG GODKÄNNER för att acceptera samtliga punkter ovan.")
    print("(JAG GODKANNER utan prickar går också, för konsoler som inte kan skriva Ä.)")
    print("Skriv något annat (eller avbryt med Ctrl+C) för att inte godkänna.")
    try:
        svar = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nInget godkännande registrerat. sie-mcp förblir spärrad.")
        return 1

    # Versaler krävs: frasen ska vara en medveten handling, inte ett reflexmässigt
    # "ja". Bara ä-lösa varianten accepteras utöver den rätta — allt annat, och
    # varje feltolkad teckenkodning, fail-closar till spärrat läge.
    if svar not in ("JAG GODKÄNNER", "JAG GODKANNER"):
        print("Inget godkännande registrerat. sie-mcp förblir spärrad.")
        return 1

    godkann_compliance()
    print(f"Godkännande registrerat (version {COMPLIANCE_VERSION}). sie-mcp kan nu användas.")
    return 0


if __name__ == "__main__":  # pragma: no cover — täcks via _cli i testsviten
    raise SystemExit(_cli())
