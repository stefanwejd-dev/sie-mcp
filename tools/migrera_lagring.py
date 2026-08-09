"""migrera_lagring — engångsverktyg för att flytta historiska säkerhetsdata ut
ur den (Google Drive-synkade) projektmappen till den säkra lokala lagringen
(Paket B2). **Paket B2.1: endast verktyget + tester.**

Säkerhets- och beteendeinvarianter:

- **Dry-run är default** och ändrar absolut ingenting. Verklig flytt kräver
  BÅDE ``--utfor`` OCH ``--bekrafta``.
- **Klassval** styrs av ``--secrets`` / ``--state`` / ``--logs`` / ``--session``.
  Utan klassval visas endast en plan (dry-run över allt).
- **Aldrig innehåll:** verktyget läser aldrig, parsar aldrig, skriver aldrig ut
  och loggar aldrig hemlighetsinnehåll. Byte-kopiering vid flytt exponerar inget
  (strömmas), och verifieringen använder endast filstorlek (metadata). Utskrift
  innehåller bara artefaktnamn, klass, sökväg, storlek, planerad åtgärd, status.
- **Fail-closed-guard:** alla MÅL- och BACKUP-sökvägar valideras av
  ``saker_lagring.kontrollera_saker_plats`` (blockerar relativa, repo-/projekt-
  och synkade sökvägar). Källan förväntas ligga i projektmappen och guardas inte.
- **Korsvolyms-säker flytt** (t.ex. G: -> C:): kopiera till en temporär fil på
  MÅLvolymen, flush + ``os.fsync``, storlekskontroll, ``os.replace`` (atomiskt
  på målvolymen), verifiera, och **radera källan sist**. Vid fel bevaras källan
  och tempfilen städas.
- **Saknad artefakt** redovisas som "saknas" (neutral no-op) och nyproduceras
  aldrig.
- **Session/DPAPI:** ``--session``/``--dpapi`` är no-op i B2.1 (ingen flytt,
  ingen DPAPI-konvertering, ingen ny sessionfil). En befintlig gammal
  ``.spiris_session.json`` markeras "uppskjuten" (återautentisering i ett senare
  B2-steg). Se HOOKS nedan.

**Inte i B2.1 (framtida hooks, avsiktligt ej implementerade):** DPAPI-konvertering
av en gammal session, samt Fernet-omkryptering/rotation. Se ``_HOOK_*``-noterna.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Kör direkt (python tools/migrera_lagring.py) behöver parser/ på sys.path för
# saker_lagring; under pytest sätts det via pyproject-pythonpath.
_PARSER_DIR = Path(__file__).resolve().parent.parent / "parser"
if str(_PARSER_DIR) not in sys.path:
    sys.path.insert(0, str(_PARSER_DIR))

import saker_lagring  # noqa: E402

# --- Exitkoder (tydliga, utan känslig information) --------------------------
EXIT_OK = 0
EXIT_ANVANDNING = 2       # felaktig användning (t.ex. --utfor utan --bekrafta)
EXIT_GUARD = 3            # osäker mål-/backup-sökväg blockerad av guarden
EXIT_MIGRERINGSFEL = 4    # minst en artefakt kunde inte flyttas (källa bevarad)

_TMP_SUFFIX = ".migrering-tmp"
# Måldelkataloger per kategori — speglar saker_lagring (secrets/state/logs).
_SUBKAT = {"secret": "secrets", "state": "state", "log": "logs"}


class MigreringsFel(Exception):
    """Fel vid en enskild artefaktflytt. Meddelandet är neutralt (artefaktnamn/
    status), aldrig innehåll."""


@dataclass(frozen=True)
class Artefakt:
    namn: str
    klass: str        # "secret" | "state" | "log" | "session"
    kategori: str     # måldir-kategori: "secret" | "state" | "log"


# Katalog över historiska artefakter (B2-inventeringen). .env -> secrets\ (aldrig
# state\). .spiris_session.json hanteras som "session" (no-op i B2.1).
ARTEFAKTER: list[Artefakt] = [
    Artefakt(".env", "secret", "secret"),
    Artefakt("mask_dict.enc", "state", "state"),
    Artefakt("allowlist.enc", "state", "state"),
    Artefakt("konteringsminne.enc", "state", "state"),
    Artefakt("masking_memory.json", "state", "state"),
    Artefakt("namnreferens.txt", "state", "state"),
    Artefakt("ai_utflodeslogg.jsonl", "log", "log"),
    Artefakt(".spiris_session.json", "session", "secret"),
]

_KLASSER = ("secret", "state", "log", "session")


@dataclass
class Plan:
    artefakt: Artefakt
    kalla: Path
    mal: Path
    finns: bool
    storlek: int | None
    atgard: str
    status: str       # "planerad" | "saknas" | "uppskjuten"


def _mal_katalog(kategori: str, data_root: Path | None) -> Path:
    """Guardad måldelkatalog. data_root (om satt) valideras av guarden; annars
    används saker_lagrings säkra standardkataloger."""
    if data_root is not None:
        rot = Path(data_root)
        saker_lagring.kontrollera_saker_plats(rot)
        d = rot / _SUBKAT[kategori]
    else:
        valj = {
            "secret": saker_lagring.secrets_dir,
            "state": saker_lagring.state_dir,
            "log": saker_lagring.logs_dir,
        }
        d = valj[kategori]()
    saker_lagring.kontrollera_saker_plats(d)
    return d


def bygg_plan(
    kalla_root: Path, valda_klasser: set[str], data_root: Path | None = None
) -> list[Plan]:
    """Bygger migreringsplanen (ren läsning av metadata). Höjer SakerLagringFel
    om en målsökväg är osäker (fångas av kor() -> EXIT_GUARD)."""
    planer: list[Plan] = []
    for a in ARTEFAKTER:
        if a.klass not in valda_klasser:
            continue
        kalla = Path(kalla_root) / a.namn
        mal = _mal_katalog(a.kategori, data_root) / a.namn
        finns = kalla.exists()
        if not finns:
            planer.append(Plan(a, kalla, mal, False, None, "ingen (saknas)", "saknas"))
        elif a.klass == "session":
            # HOOK (ej i B2.1): DPAPI-konvertering/återautentisering sker i ett
            # senare B2-steg. Här görs ingen flytt och ingen konvertering.
            planer.append(Plan(
                a, kalla, mal, True, kalla.stat().st_size,
                "uppskjuten till återautentisering (ingen åtgärd i B2.1)", "uppskjuten",
            ))
        else:
            planer.append(Plan(
                a, kalla, mal, True, kalla.stat().st_size, f"flytta -> {mal}", "planerad"
            ))
    return planer


def _kopiera(kalla: Path, mal: Path) -> None:
    """Strömmar bytes källa -> mål och tvingar ut dem till disk. Läser/parsar/
    skriver aldrig ut innehållet. (Injicerbar i test för felväg.)"""
    with open(kalla, "rb") as fin, open(mal, "wb") as fout:
        shutil.copyfileobj(fin, fout)
        fout.flush()
        os.fsync(fout.fileno())


def _saker_flytt(kalla: Path, mal: Path, *, backup_dir: Path | None = None) -> None:
    """Korsvolyms-säker flytt av EN artefakt. Guardar mål (och ev. backup),
    tar backup, kopierar till temp på målvolymen, verifierar storlek, gör ett
    atomiskt os.replace och tar bort källan SIST. Vid fel: källan bevaras,
    tempfilen städas."""
    saker_lagring.kontrollera_saker_plats(mal)
    if backup_dir is not None:
        bkp = Path(backup_dir)
        saker_lagring.kontrollera_saker_plats(bkp)
        bkp.mkdir(parents=True, exist_ok=True)
        _kopiera(kalla, bkp / kalla.name)  # backup: kopia, källan behålls

    mal.parent.mkdir(parents=True, exist_ok=True)
    tmp = mal.parent / (mal.name + _TMP_SUFFIX)
    try:
        _kopiera(kalla, tmp)
        if tmp.stat().st_size != kalla.stat().st_size:
            raise MigreringsFel("storleksmiss efter kopiering")
        os.replace(tmp, mal)  # atomiskt på målvolymen
        if not mal.exists() or mal.stat().st_size != kalla.stat().st_size:
            raise MigreringsFel("verifiering av mål misslyckades")
        kalla.unlink()  # källan tas bort SIST, efter verifierad publicering
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def utfor(planer: list[Plan], *, backup_dir: Path | None = None) -> list[tuple[Plan, str]]:
    """Genomför de planerade flyttarna. 'saknas'/'uppskjuten' hoppas över
    (neutralt). Varje artefakt är oberoende säker; ett fel bevarar just den
    källan. Returnerar (plan, status)-par för redovisning."""
    resultat: list[tuple[Plan, str]] = []
    for p in planer:
        if p.status != "planerad":
            resultat.append((p, f"hoppar över ({p.status})"))
            continue
        try:
            _saker_flytt(p.kalla, p.mal, backup_dir=backup_dir)
            resultat.append((p, "flyttad"))
        except Exception:  # noqa: BLE001 — källan bevarad, tempfil städad i _saker_flytt
            resultat.append((p, "FEL — källa bevarad, mål ej publicerat"))
    return resultat


# --- Utskrift (endast metadata, aldrig innehåll) ----------------------------

def _skriv_plan(planer: list[Plan]) -> None:
    print(f"{'artefakt':24} {'klass':8} {'status':12} {'storlek':>8}  åtgärd")
    print("-" * 76)
    for p in planer:
        storlek = "-" if p.storlek is None else str(p.storlek)
        print(f"{p.artefakt.namn:24} {p.artefakt.klass:8} {p.status:12} {storlek:>8}  {p.atgard}")


def _skriv_resultat(resultat: list[tuple[Plan, str]]) -> None:
    print("\nUtfall:")
    for p, status in resultat:
        print(f"  {p.artefakt.namn:24} {status}")


# --- CLI --------------------------------------------------------------------

def _bygg_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="migrera_lagring",
        description="Flytta historiska säkerhetsdata ut ur projektmappen (B2). "
                    "Dry-run som standard; verklig flytt kräver --utfor --bekrafta.",
    )
    ap.add_argument("--secrets", action="store_true", help="inkludera secret-klassen (.env)")
    ap.add_argument("--state", action="store_true", help="inkludera state-klassen (.enc, minne)")
    ap.add_argument("--logs", action="store_true", help="inkludera log-klassen")
    ap.add_argument("--session", action="store_true", help="inkludera session (no-op i B2.1)")
    ap.add_argument("--dpapi", action="store_true",
                    help="explicit sessionkonvertering (no-op i B2.1)")
    ap.add_argument("--utfor", action="store_true", help="genomför verklig flytt (kräver --bekrafta)")
    ap.add_argument("--bekrafta", action="store_true", help="obligatorisk bekräftelse för --utfor")
    ap.add_argument("--backup-dir", default=None, help="säker backup-katalog (guardas)")
    ap.add_argument("--kalla-root", default=None, help="källrot (default: projektroten)")
    ap.add_argument("--data-root", default=None, help="målrot (default: säkra lokala roten)")
    return ap


def _valda_klasser(args: argparse.Namespace) -> set[str]:
    valda: set[str] = set()
    if args.secrets:
        valda.add("secret")
    if args.state:
        valda.add("state")
    if args.logs:
        valda.add("log")
    if args.session or args.dpapi:
        valda.add("session")
    return valda


def kor(argv: list[str] | None = None) -> int:
    args = _bygg_argparser().parse_args(argv)

    kalla_root = Path(args.kalla_root) if args.kalla_root else saker_lagring.REPO_ROOT
    data_root = Path(args.data_root) if args.data_root else None

    valda = _valda_klasser(args)
    # Utan klassval: ren översikt/dry-run över allt, ingen åtgärd.
    dry_run_over_allt = not valda
    klasser = set(_KLASSER) if dry_run_over_allt else valda

    # Bygg plan (guardar målsökvägar).
    try:
        planer = bygg_plan(kalla_root, klasser, data_root)
    except saker_lagring.SakerLagringFel as e:
        print(f"Blockerad målsökväg (fail-closed): {e}", file=sys.stderr)
        return EXIT_GUARD

    _skriv_plan(planer)

    verklig = args.utfor and not dry_run_over_allt
    if not verklig:
        if args.utfor and dry_run_over_allt:
            print("\n(Inget klassval angivet — visar endast plan, ingen åtgärd.)")
        else:
            print("\n(Dry-run: inget ändrades. Lägg till --utfor --bekrafta för verklig flytt.)")
        return EXIT_OK

    if not args.bekrafta:
        print("\n--utfor kräver --bekrafta. Inget ändrades.", file=sys.stderr)
        return EXIT_ANVANDNING

    # Guarda backup-sökvägen upfront (innan någon fil rörs).
    backup_dir: Path | None = None
    if args.backup_dir:
        backup_dir = Path(args.backup_dir)
        try:
            saker_lagring.kontrollera_saker_plats(backup_dir)
        except saker_lagring.SakerLagringFel as e:
            print(f"Blockerad backup-sökväg (fail-closed): {e}", file=sys.stderr)
            return EXIT_GUARD

    resultat = utfor(planer, backup_dir=backup_dir)
    _skriv_resultat(resultat)

    if any(status.startswith("FEL") for _p, status in resultat):
        return EXIT_MIGRERINGSFEL
    return EXIT_OK


# --- Framtida hooks (avsiktligt EJ implementerade i B2.1) -------------------
# _HOOK_konvertera_session_dpapi(): DPAPI-konvertering av en gammal
#   .spiris_session.json. B2.1 gör i stället återautentisering senare — ingen
#   konvertering här, ingen sessionfil skapas.
# _HOOK_rotera_fernet(): omkryptering av .enc-liggarna under en ny Fernet-nyckel.
#   Får ske FÖRST efter verifierad migrering och med lokal backup; ej i B2.1.


if __name__ == "__main__":
    sys.exit(kor())
