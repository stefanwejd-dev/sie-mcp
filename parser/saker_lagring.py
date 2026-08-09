"""saker_lagring — central, fail-closed sökvägsupplösning för sie-mcp:s lokala
säkerhetsdata (hemligheter, OAuth-session, krypterade liggare, loggar).

**Paket B1 — endast grund.** Modulen avgör VAR säkerhetsdata får ligga och
vägrar (fail-closed) en osäker plats. Den utför INGEN migrering, ingen
nyckel-/tokenrotation och flyttar ingen befintlig data. Sådant hör till ett
separat B2-verktyg.

Mål: säkerhetsdata får ALDRIG läsas från eller skrivas till den (potentiellt
Google Drive-synkade) projekt-/repomappen. Standardroten är per-användare och
icke-synkad:

- Windows: ``%LOCALAPPDATA%\\sie-mcp``
- övrigt (dev/CI): ``$XDG_DATA_HOME/sie-mcp`` eller ``~/.local/share/sie-mcp``

Roten kan sättas explicit med miljövariabeln ``SIE_MCP_DATA_ROOT``, men
valideras alltid av samma guard.

**Förbud (efterlevs i hela modulen):** innehållet i hemligheter/sessioner/
nycklar läses aldrig ut, skrivs aldrig ut och loggas aldrig. Modulen hanterar
bara SÖKVÄGAR och kataloger — aldrig hemlighetsvärden.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT_ENV = "SIE_MCP_DATA_ROOT"
_APPNAMN = "sie-mcp"

# Repo-/projektroten som säkerhetsdata ALDRIG får ligga i. Den här filen ligger
# i <repo>/parser/, så parents[1] är repo-roten. Resolvas en gång vid import.
REPO_ROOT = Path(__file__).resolve().parents[1]

# Försvar på djupet: katalognamn som avslöjar en molnsynkad plats. Detta är ETT
# extra lager — huvudspärren är kraven på absolut, icke-repo, explicit rot.
_SYNK_MARKORER = (
    "my drive", "google drive", "googledrive", "onedrive", "dropbox", "icloud",
)

# Underkataloger per klass.
_SECRETS = "secrets"
_STATE = "state"
_LOGS = "logs"
_AI_UTFLODE = "ai-utflode"


class SakerLagringFel(Exception):
    """Fail-closed-fel: en osäker lagringsplats (repo, synkad mapp, relativ
    sökväg) eller en plattform utan säkert skydd. Meddelandet är neutralt och
    innehåller ALDRIG ett hemlighetsvärde eller en personlig sökväg."""


def _under(barn: Path, foralder: Path) -> bool:
    try:
        barn.resolve().relative_to(foralder.resolve())
        return True
    except (ValueError, OSError):
        return False


def _har_synk_markor(p: Path) -> bool:
    for del_ in p.parts:
        dl = del_.lower()
        if any(m in dl for m in _SYNK_MARKORER):
            return True
    return False


def kontrollera_saker_plats(sokvag: Path) -> None:
    """FAIL-CLOSED-guard för säkerhetsdata (skärpning A). Höjer SakerLagringFel
    om sökvägen är osäker. Reglerna, i ordning:

    1. Relativa sökvägar tillåts inte (kräver en explicit, absolut plats).
    2. Repo-/projektroten och ALLA dess barn förbjuds.
    3. Synk-markörer i sökvägen (t.ex. "My Drive", "OneDrive") förbjuds — ett
       extra försvarslager, inte den enda spärren.
    """
    p = Path(sokvag)
    if not p.is_absolute():
        raise SakerLagringFel(
            "Osäker lagringsplats: en relativ sökväg tillåts inte för säkerhetsdata."
        )
    rp = p.resolve()
    if rp == REPO_ROOT or _under(rp, REPO_ROOT):
        raise SakerLagringFel(
            "Osäker lagringsplats: säkerhetsdata får inte ligga i projekt-/repomappen."
        )
    if _har_synk_markor(rp):
        raise SakerLagringFel(
            "Osäker lagringsplats: sökvägen ser ut att ligga i en molnsynkad mapp."
        )


def app_data_root() -> Path:
    """Roten för all lokal säkerhetsdata. SIE_MCP_DATA_ROOT (om satt) har
    företräde men valideras alltid av guarden. Annars en per-användare,
    icke-synkad plattformsstandard. Skapar ingen katalog och rör ingen data."""
    override = os.environ.get(DATA_ROOT_ENV)
    if override:
        rot = Path(override).expanduser()
        if not rot.is_absolute():
            raise SakerLagringFel(f"{DATA_ROOT_ENV} måste vara en absolut sökväg.")
        rot = rot.resolve()
        kontrollera_saker_plats(rot)
        return rot

    if os.name == "nt":
        bas = os.environ.get("LOCALAPPDATA")
        if not bas:
            raise SakerLagringFel(
                f"LOCALAPPDATA saknas i miljön; sätt {DATA_ROOT_ENV} till en säker, "
                "icke-synkad katalog."
            )
        rot = Path(bas) / _APPNAMN
    else:
        bas = os.environ.get("XDG_DATA_HOME")
        rot = (Path(bas) if bas else Path.home() / ".local" / "share") / _APPNAMN

    rot = rot.resolve()
    kontrollera_saker_plats(rot)
    return rot


def secrets_dir() -> Path:
    d = app_data_root() / _SECRETS
    kontrollera_saker_plats(d)
    return d


def state_dir() -> Path:
    d = app_data_root() / _STATE
    kontrollera_saker_plats(d)
    return d


def logs_dir() -> Path:
    d = app_data_root() / _LOGS
    kontrollera_saker_plats(d)
    return d


def ai_utflode_dir() -> Path:
    """Katalogen för sessionsloggarna över AI-utflöde (sessionslogg.py).

    Till skillnad från behandlingsloggen (revisionslogg.py, metadata) innehåller
    de här filerna den FAKTISKA nyttolast som skickades till AI-leverantören.
    De är därmed en känslig artefakt och måste ligga bakom samma guard som
    hemligheterna — aldrig i den (potentiellt molnsynkade) projektmappen."""
    d = logs_dir() / _AI_UTFLODE
    kontrollera_saker_plats(d)
    return d


def _begransa_behorighet(d: Path) -> None:
    """Best-effort restriktiv behörighet (ägare endast). Fel sväljs och inget
    innehåll rörs. På icke-Windows: chmod 700. På Windows: icacls (arv av,
    ägare full)."""
    if os.name == "nt":
        import subprocess

        anvandare = os.environ.get("USERNAME") or ""
        try:
            subprocess.run(
                ["icacls", str(d), "/inheritance:r", "/grant:r", f"{anvandare}:(OI)(CI)F"],
                capture_output=True, check=False,
            )
        except OSError:
            pass
    else:
        try:
            d.chmod(0o700)
        except OSError:
            pass


def initiera_lagring() -> None:
    """Skapar secrets/state/logs/ai_utflode idempotent med restriktiv behörighet.
    Skriver aldrig något innehåll och flyttar ingen data. Avsedd att köras en
    gång vid appstart (eller av B2-verktyget)."""
    for d in (secrets_dir(), state_dir(), logs_dir(), ai_utflode_dir()):
        d.mkdir(parents=True, exist_ok=True)
        _begransa_behorighet(d)


def artefakt_sokvag(explicit: str | os.PathLike | None, *, kategori: str, namn: str) -> Path:
    """Central upplösning av en artefakts sökväg. `explicit` (t.ex. ett test-
    argument) valideras av guarden; `None` ger den säkra standardplatsen under
    rätt klasskatalog. kategori: 'secret' | 'state' | 'log'. Skapar ingen fil
    och rör inget innehåll — anropande skrivfunktion skapar katalogen vid
    behov (se sakerstall_katalog)."""
    if explicit is not None:
        p = Path(explicit)
        kontrollera_saker_plats(p)
        return p
    valjare = {"secret": secrets_dir, "state": state_dir, "log": logs_dir}
    if kategori not in valjare:
        raise SakerLagringFel(f"Okänd artefaktkategori: {kategori!r}.")
    return valjare[kategori]() / namn


def sakerstall_katalog(sokvag: Path) -> None:
    """Ser till att en (redan guardad) artefakts katalog finns före skrivning.
    Best-effort på skrivfel längre upp; guarden har redan kört."""
    Path(sokvag).parent.mkdir(parents=True, exist_ok=True)


# --- Windows DPAPI (per-användare) via ctypes/Crypt32 -----------------------
# Inga tredjepartsberoenden. Endast Windows; på annan plattform fail-closed
# (ingen osäker fallback). Klartext/chiffer skrivs eller loggas aldrig här.

def _windows_dpapi(data: bytes, *, skydda: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    inbuf = ctypes.create_string_buffer(bytes(data), len(data))
    in_blob = DATA_BLOB(len(data), ctypes.cast(inbuf, ctypes.POINTER(ctypes.c_char)))
    ut_blob = DATA_BLOB()

    crypt32 = ctypes.windll.crypt32
    func = crypt32.CryptProtectData if skydda else crypt32.CryptUnprotectData
    func.restype = wintypes.BOOL
    func.argtypes = [
        ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    # pOptionalEntropy = None -> per-användarskydd (ingen LOCALMACHINE-flagga).
    if not func(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(ut_blob)):
        raise SakerLagringFel("DPAPI-operationen misslyckades.")
    try:
        return ctypes.string_at(ut_blob.pbData, ut_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ut_blob.pbData)


def dpapi_skydda(klartext: bytes) -> bytes:
    """Skyddar bytes med Windows DPAPI (per-användare). Höjer SakerLagringFel
    på icke-Windows — ingen osäker fallback."""
    if os.name != "nt":
        raise SakerLagringFel("DPAPI kräver Windows; ingen osäker fallback tillåts.")
    return _windows_dpapi(klartext, skydda=True)


def dpapi_avskydda(chiffer: bytes) -> bytes:
    """Återställer DPAPI-skyddade bytes. Höjer SakerLagringFel på icke-Windows
    eller vid misslyckad avkryptering."""
    if os.name != "nt":
        raise SakerLagringFel("DPAPI kräver Windows; ingen osäker fallback tillåts.")
    return _windows_dpapi(chiffer, skydda=False)
