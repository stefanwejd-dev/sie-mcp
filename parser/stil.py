"""stil — designtokens och den enda CSS-injektionen i appen.

UI-fri: modulen bygger CSS-strängar, den renderar dem inte. Anledningen är
densamma som för navigering.py — färgval och kontrast ska kunna testas utan
UI-runtime, och tokenlagret ska överleva ett byte av ritlager.

Färg bär betydelse och är aldrig dekoration. Principen fanns redan i
snabbvy_render.py:7-11 men var lokal; här är den generell."""

from dataclasses import dataclass
from typing import Literal

# --- Betydelsebärande nivåer ------------------------------------------------
Niva = Literal["neutral", "rod", "gul", "gron"]

NIVAFARG: dict[Niva, str] = {
    "rod": "#d62728",
    "gul": "#e8a33d",
    "gron": "#2ca02c",
    "neutral": "rgba(128,128,128,0.35)",
}

BAKGRUND_LJUS = "#ffffff"
BAKGRUND_MORK = "#0e1117"

# --- Härkomstmärken ---------------------------------------------------------
@dataclass(frozen=True)
class Harkomstmarke:
    tecken: str
    namn: str
    forklaring: str

HARKOMST_KALLA    = Harkomstmarke("◇", "Från källan",   "Hämtat oförändrat från affärssystemet.")
HARKOMST_LOKAL    = Harkomstmarke("⌗", "Lokalt beräknat", "Beräknat på din dator, deterministiskt. Ingen AI inblandad.")
HARKOMST_AI       = Harkomstmarke("✦", "AI-genererat",  "Producerat av en språkmodell. Kan vara fel — verifiera mot källan.")
HARKOMST_MASKERAD = Harkomstmarke("▒", "Pseudonymiserat", "Identifierande uppgifter ersattes med tokens innan utflöde.")

ALLA_HARKOMST: tuple[Harkomstmarke, ...] = (
    HARKOMST_KALLA, HARKOMST_LOKAL, HARKOMST_AI, HARKOMST_MASKERAD,
)

def bakgrundsfarg(tematyp: str | None) -> str:
    """Ogenomskinlig bakgrund åt den sticky flikraden, matchad mot aktivt tema.
    Okänt tema behandlas som ljust — Streamlits eget standardläge."""
    return BAKGRUND_MORK if tematyp == "dark" else BAKGRUND_LJUS

def _linear_channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def kontrastkvot(forgrund: str, bakgrund: str) -> float:
    """WCAG 2.1 relativ luminans."""
    def parse_hex(h: str) -> tuple[float, float, float]:
        if h.startswith("rgba"):
            # Simple fallback for rgba, approximating with background
            return 128/255, 128/255, 128/255
        h = h.lstrip('#')
        return int(h[0:2], 16)/255.0, int(h[2:4], 16)/255.0, int(h[4:6], 16)/255.0
    
    def mix_rgba_with_bg(fg: str, bg: str) -> tuple[float, float, float]:
        if fg.startswith("rgba"):
            parts = fg.replace("rgba(", "").replace(")", "").split(",")
            r, g, b, a = int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3])
            bgr, bgg, bgb = parse_hex(bg)
            out_r = (r/255)*a + bgr*(1-a)
            out_g = (g/255)*a + bgg*(1-a)
            out_b = (b/255)*a + bgb*(1-a)
            return out_r, out_g, out_b
        return parse_hex(fg)

    fr, fg, fb = mix_rgba_with_bg(forgrund, bakgrund)
    br, bg, bb = parse_hex(bakgrund)

    L_f = 0.2126 * _linear_channel(fr) + 0.7152 * _linear_channel(fg) + 0.0722 * _linear_channel(fb)
    L_b = 0.2126 * _linear_channel(br) + 0.7152 * _linear_channel(bg) + 0.0722 * _linear_channel(bb)
    
    L_light = max(L_f, L_b)
    L_dark = min(L_f, L_b)
    return (L_light + 0.05) / (L_dark + 0.05)

def global_css(bakgrund: str) -> str:
    """ETT <style>-block för hela appen."""
    return f"""\
<style>
.sie-snabbvy-sektion {{
  border-left: 4px solid var(--sie-niva);
  padding: 0.35rem 0 0.35rem 0.9rem;
  margin: 0.6rem 0 1.1rem 0;
}}
.sie-snabbvy-sektion h4 {{ margin: 0 0 0.25rem 0; font-size: 1.02rem; }}
.sie-snabbvy-sektion .sie-snabbvy-beskrivning {{
  opacity: 0.75; font-size: 0.88rem; margin: 0 0 0.6rem 0;
}}
.sie-snabbvy-fotnot {{ opacity: 0.65; font-size: 0.82rem; margin-top: 0.8rem; }}

.sie-chatt-tabell-wrap {{
    overflow-x: auto;
}}
.sie-chatt-tabell {{
    width: 100%;
    border-collapse: collapse;
    font-family: Inter, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 0.88rem;
    margin: 0.6rem 0 0.3rem 0;
}}
.sie-chatt-tabell thead th {{
    text-align: left;
    font-weight: 600;
    padding: 0.45rem 0.65rem;
    border-bottom: 2px solid rgba(128, 128, 128, 0.35);
    border-right: 1px solid rgba(128, 128, 128, 0.12);
    white-space: nowrap;
}}
.sie-chatt-tabell thead th:last-child {{
    border-right: none;
}}
.sie-chatt-tabell tbody td {{
    padding: 0.4rem 0.65rem;
    border-right: 1px solid rgba(128, 128, 128, 0.12);
    border-bottom: 1px solid rgba(128, 128, 128, 0.08);
}}
.sie-chatt-tabell tbody td:last-child {{
    border-right: none;
}}
.sie-chatt-tabell tbody tr:nth-child(even) {{
    background-color: rgba(128, 128, 128, 0.08);
}}
.sie-chatt-tabell .sie-hoger {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}}
.sie-chatt-tabell tbody tr.sie-summa-rad td {{
    border-top: 2px solid rgba(128, 128, 128, 0.45);
    font-weight: 700;
    background-color: transparent;
}}
.sie-chatt-tabell-rubrik {{
    font-weight: 600;
    font-size: 0.95rem;
    margin: 0.5rem 0 0.15rem 0;
}}
.sie-harkomst {{
    opacity: 0.55; 
    font-size: 0.85em; 
    margin-right: 0.3em; 
    cursor: help;
}}
</style>
"""

def harkomst_html(marke: Harkomstmarke) -> str:
    return f'<span title="{marke.forklaring}" class="sie-harkomst">{marke.tecken}</span>'
