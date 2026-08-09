"""rotera_hemligheter — R-01: rotera nycklar och tokens som historiskt låg i
den Google Drive-synkade projektmappen.

Migreringen (Paket B2, `migrera_lagring.py`) flyttade hemligheterna till
`%LOCALAPPDATA%\\sie-mcp`. Den gör dem INTE ogiltiga. En nyckel som en gång
synkats till Google Drive kan finnas kvar i Drives versionshistorik, i
papperskorgen, i en säkerhetskopia eller på en annan enhet som var kopplad till
kontot. Först rotationen stänger risken — därför står R-01 kvar som blockerande
i `RISKREGISTER.md` trots att migreringen är klar.

**Fällan verktyget finns för.** `app_config.las_maskeringsliggare` är fail-safe:
fel nyckel ger en TOM liggare, inte ett fel. Att byta Fernet-nyckel för hand
skulle alltså **tyst radera** maskeringsliggaren, undantagslistan och
konteringsminnet — utan ett enda felmeddelande, och utan att någon märker det
förrän pseudonymerna plötsligt är andra. Verktyget dekrypterar därför med den
gamla nyckeln, krypterar om med den nya, verifierar rundturen, och byter nyckel
FÖRST när allt är bevisat läsbart.

Invarianter (samma som `migrera_lagring.py`):

- **Dry-run är default.** Verklig ändring kräver BÅDE ``--utfor`` OCH
  ``--bekrafta``.
- **Aldrig innehåll.** Verktyget skriver aldrig ut en nyckel, en token, ett
  liggarvärde eller ett personnamn. Bara namn, storlekar, antal och status.
- **Fail-closed.** Kan en liggare inte dekrypteras med den gamla nyckeln
  avbryts HELA rotationen — den filen skulle annars gå förlorad.
- **Backup före byte**, i en guardad katalog under `state/`.

Vad verktyget INTE kan göra: rotera din Anthropic-nyckel eller din
Spiris-klienthemlighet. De skapas hos respektive leverantör och måste roteras
där. Kör ``--checklista`` för stegen.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_PARSER_DIR = Path(__file__).resolve().parent.parent / "parser"
if str(_PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(_PARSER_DIR))

from cryptography.fernet import Fernet, InvalidToken  # noqa: E402
from dotenv import dotenv_values, set_key  # noqa: E402

import app_config  # noqa: E402
import saker_lagring  # noqa: E402

FERNET_NYCKEL = "SIE_MCP_FERNET_KEY"
SESSION_NAMN = ".spiris_session"

# De Fernet-krypterade liggarna. Namnen hämtas ur app_config så att en
# omdöpning där inte tyst gör att en liggare glöms vid rotationen.
LIGGARE = (
    app_config.MASK_DICT_NAMN,
    app_config.ALLOWLIST_NAMN,
    app_config.KONTERINGSMINNE_NAMN,
)

# Hemligheter som INTE kan roteras härifrån — de ägs av en extern leverantör.
EXTERNA = {
    "SIE_MCP_AI_API_NYCKEL": (
        "AI-leverantörens API-nyckel. Återkalla den gamla i leverantörens "
        "konsol (Anthropic: console.anthropic.com -> API keys -> Revoke) och "
        "klistra in en ny i appens sidomeny. Återkalla FÖRE du skapar den nya, "
        "annars är det lätt att låta den gamla ligga kvar aktiv."
    ),
    "SIE_MCP_SPIRIS_CLIENT_SECRET": (
        "Spiris/Visma klienthemlighet. Generera om i Vismas utvecklarportal "
        "(developer.visma.com) för din integration, och uppdatera värdet i "
        "appens sidomeny. Client ID ändras normalt inte."
    ),
}


class RotationsFel(Exception):
    """Rotationen avbröts. Ingenting har ändrats."""


def _env_fil() -> Path:
    return saker_lagring.secrets_dir() / app_config.ENV_NAMN


def _nuvarande_nyckel() -> str | None:
    return dotenv_values(str(_env_fil())).get(FERNET_NYCKEL) or None


def _liggarsokvag(namn: str) -> Path:
    return saker_lagring.state_dir() / namn


# --- Status -----------------------------------------------------------------


def bygg_status() -> dict:
    """Inventering utan att röra eller visa något innehåll."""
    env = _env_fil()
    varden = dotenv_values(str(env)) if env.exists() else {}
    session = saker_lagring.secrets_dir() / SESSION_NAMN

    return {
        "env_finns": env.exists(),
        "fernet_satt": bool(varden.get(FERNET_NYCKEL)),
        "externa": {
            namn: bool(varden.get(namn)) for namn in EXTERNA
        },
        "spiris_session_finns": session.exists(),
        "liggare": {
            namn: (_liggarsokvag(namn).stat().st_size if _liggarsokvag(namn).exists() else None)
            for namn in LIGGARE
        },
    }


def _skriv_status(status: dict) -> None:
    print("R-01 — status för lokala hemligheter\n")
    print(f"  secrets/{app_config.ENV_NAMN:26} {'finns' if status['env_finns'] else 'SAKNAS'}")
    print(f"  {FERNET_NYCKEL:34} {'satt' if status['fernet_satt'] else 'saknas'}")
    print(f"  {'Spiris-session (DPAPI)':34} "
          f"{'finns' if status['spiris_session_finns'] else 'saknas'}")
    print()
    print("  Fernet-krypterade liggare:")
    for namn, storlek in status["liggare"].items():
        print(f"    {namn:30} {str(storlek) + ' byte' if storlek is not None else 'saknas'}")
    print()
    print("  Måste roteras hos leverantören (kan inte göras härifrån):")
    for namn, satt in status["externa"].items():
        print(f"    {namn:34} {'satt — behöver roteras' if satt else 'ej satt'}")


# --- Fernet-rotation --------------------------------------------------------


def rotera_fernet(*, utfor: bool) -> dict:
    """Roterar Fernet-nyckeln och krypterar om liggarna.

    Ordningen är vald så att inget kan gå förlorat: dekryptera allt -> verifiera
    -> backup -> skriv nya chiffer -> byt nyckel SIST. Ett avbrott före det
    sista steget lämnar de gamla filerna läsbara med den gamla nyckeln.
    """
    gammal = _nuvarande_nyckel()
    if not gammal:
        raise RotationsFel(
            f"{FERNET_NYCKEL} saknas i secrets/.env — det finns ingen nyckel att rotera."
        )

    gammal_fernet = Fernet(gammal.encode())

    # 1. Dekryptera ALLT först. Ett enda misslyckande avbryter hela rotationen:
    #    att fortsätta skulle innebära att den filen aldrig går att läsa igen.
    klartexter: dict[str, bytes] = {}
    for namn in LIGGARE:
        sokvag = _liggarsokvag(namn)
        if not sokvag.exists():
            continue
        try:
            klartexter[namn] = gammal_fernet.decrypt(sokvag.read_bytes())
        except InvalidToken as fel:
            raise RotationsFel(
                f"{namn} kan inte dekrypteras med nuvarande nyckel. Rotationen "
                "avbryts — filen hade blivit permanent oläsbar. Töm liggaren i "
                "appen om den är trasig, och kör om."
            ) from fel
        except OSError as fel:
            raise RotationsFel(f"Kunde inte läsa {namn}: {type(fel).__name__}.") from fel

    ny = Fernet.generate_key().decode()
    ny_fernet = Fernet(ny.encode())

    # 2. Kryptera om och verifiera rundturen INNAN något skrivs.
    nya_chiffer: dict[str, bytes] = {}
    for namn, klartext in klartexter.items():
        chiffer = ny_fernet.encrypt(klartext)
        if ny_fernet.decrypt(chiffer) != klartext:
            raise RotationsFel(f"Rundturskontrollen misslyckades för {namn}.")
        nya_chiffer[namn] = chiffer

    resultat = {
        "omkrypterade": sorted(nya_chiffer),
        "hoppade_over": [n for n in LIGGARE if n not in klartexter],
        "utfort": False,
        "backup": None,
    }
    if not utfor:
        return resultat

    # 3. Backup av de GAMLA chiffren (de är värdelösa utan den gamla nyckeln,
    #    men räddar en avbruten körning).
    stampel = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = saker_lagring.state_dir() / f"rotation-backup-{stampel}"
    saker_lagring.kontrollera_saker_plats(backup)
    backup.mkdir(parents=True, exist_ok=True)
    saker_lagring._begransa_behorighet(backup)
    for namn in nya_chiffer:
        (backup / namn).write_bytes(_liggarsokvag(namn).read_bytes())

    # 4. Skriv nya chiffer atomiskt.
    for namn, chiffer in nya_chiffer.items():
        mal = _liggarsokvag(namn)
        tmp = mal.with_suffix(mal.suffix + ".tmp")
        tmp.write_bytes(chiffer)
        os.replace(tmp, mal)

    # 5. Byt nyckel SIST.
    set_key(str(_env_fil()), FERNET_NYCKEL, ny)

    resultat["utfort"] = True
    resultat["backup"] = str(backup)
    return resultat


# --- Spiris-session ---------------------------------------------------------


def rotera_spiris_session(*, utfor: bool) -> dict:
    """Raderar den persisterade OAuth-sessionen. Nästa användning kräver ny
    inloggning, vilket ger nya tokens.

    Detta ersätter INTE att återkalla den gamla behörigheten hos Visma — en
    refresh token som läckt fortsätter fungera tills den återkallas där."""
    session = saker_lagring.secrets_dir() / SESSION_NAMN
    fanns = session.exists()
    if utfor and fanns:
        session.unlink()
    return {"fanns": fanns, "utfort": bool(utfor and fanns)}


# --- Checklista -------------------------------------------------------------

CHECKLISTA = """R-01 — rotationsordning

Rotera i den här ordningen. Steg 1-2 kan bara du göra; de sker hos leverantören.

1. AI-leverantörens API-nyckel
   Återkalla den GAMLA först (Anthropic: console.anthropic.com -> API keys ->
   Revoke), skapa sedan en ny och klistra in den i appens sidomeny.
   Att skapa den nya först gör det lätt att glömma återkalla den gamla.

2. Spiris/Visma
   a) Återkalla integrationens behörighet för bolaget, så att befintliga
      refresh tokens slutar gälla. En läckt refresh token fungerar tills den
      återkallas — att bara radera den lokalt räcker inte.
   b) Generera om klienthemligheten i developer.visma.com och uppdatera den
      i appens sidomeny.
   c) Kör:  python tools/rotera_hemligheter.py --spiris-session --utfor --bekrafta
      och logga in på nytt i appen.

3. Fernet-nyckeln (lokal — verktyget sköter det)
   python tools/rotera_hemligheter.py --fernet --utfor --bekrafta
   Liggarna krypteras om med den nya nyckeln. Gör INTE detta för hand:
   maskeringsliggaren, undantagslistan och konteringsminnet töms tyst om
   nyckeln byts utan omkryptering.

4. Efteråt
   - Töm Google Drives papperskorg och kontrollera versionshistoriken för den
     gamla projektmappen.
   - Uppdatera R-01 i RISKREGISTER.md med datum och vad som roterades.
   - Notera i DATASKYDD.md 4.3 att rotationen är genomförd.
"""


def _bygg_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rotera_hemligheter.py",
        description="R-01: rotera lokala nycklar och tokens. Dry-run som standard.",
    )
    ap.add_argument("--fernet", action="store_true",
                    help="Rotera Fernet-nyckeln och kryptera om liggarna.")
    ap.add_argument("--spiris-session", action="store_true",
                    help="Radera den persisterade OAuth-sessionen (kräver ny inloggning).")
    ap.add_argument("--checklista", action="store_true",
                    help="Visa rotationsordningen, inklusive stegen hos leverantörerna.")
    ap.add_argument("--utfor", action="store_true", help="Utför ändringen (annars dry-run).")
    ap.add_argument("--bekrafta", action="store_true", help="Krävs tillsammans med --utfor.")
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    args = _bygg_argparser().parse_args(argv)

    if args.checklista:
        print(CHECKLISTA)
        return 0

    if not (args.fernet or args.spiris_session):
        _skriv_status(bygg_status())
        print()
        print("Kör --checklista för rotationsordningen, eller --fernet / "
              "--spiris-session (lägg till --utfor --bekrafta för att ändra).")
        return 0

    utfor = args.utfor and args.bekrafta
    if args.utfor and not args.bekrafta:
        print("--utfor kräver även --bekrafta. Ingenting har ändrats.")
        return 1

    try:
        if args.fernet:
            r = rotera_fernet(utfor=utfor)
            läge = "ROTERAD" if r["utfort"] else "dry-run — inget ändrat"
            print(f"Fernet-nyckel: {läge}")
            print(f"  krypteras om: {', '.join(r['omkrypterade']) or '(inga liggare finns)'}")
            if r["hoppade_over"]:
                print(f"  saknas (hoppas över): {', '.join(r['hoppade_over'])}")
            if r["backup"]:
                print(f"  backup av gamla chiffer: {r['backup']}")

        if args.spiris_session:
            r = rotera_spiris_session(utfor=utfor)
            if not r["fanns"]:
                print("Spiris-session: ingen sparad session finns.")
            elif r["utfort"]:
                print("Spiris-session: raderad — logga in på nytt i appen.")
                print("  OBS: återkalla även behörigheten hos Visma, annars "
                      "fortsätter en läckt refresh token att gälla.")
            else:
                print("Spiris-session: finns och skulle raderas (dry-run).")
    except (RotationsFel, saker_lagring.SakerLagringFel) as fel:
        print(f"AVBRUTEN: {fel}")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover — täcks via main() i testsviten
    raise SystemExit(main())
