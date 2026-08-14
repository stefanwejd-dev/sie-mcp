"""avstamning.sekretess — maskering av kontoutdrag.

Lager 1b, se hantverksbok/BOKSLUTSPROGRAMMET.md §4.4 och §4.5 steg 5. Ett
kontoutdrag är det mest personuppgiftstäta materialet i hela systemet — varje
rad kan bära en motparts namn, ofta en privatpersons. Det är värre än
SIE-filen.

MCP-vägen maskerar FÖRE kontrollen, precis som lager 1
(hantverksbok/BOKSLUTSKONTROLLER.md invariant I-3, B-5). Maskeringen
återanvänder samma primitiv som `sekretesslager.maskera_siefil` använder för
verifikationstext (`_maskera_fritext`) och samma spärrprincip: en rad med ett
olöst maskeringsbehov utesluts från det som går vidare till kontrollen, i
stället för att skickas halvmaskerad.

Sökvägsvakten (`_tillaten_kontoutdrag`) bor i `mcp_server/server.py`, samma
plats som `_tillaten_siefil` — den är en MCP-gränsangelägenhet, inte en
domänmodul. Den här modulen håller inget tillstånd mellan anrop och skriver
aldrig något till disk — §4.4: "Läs, jämför, släpp."."""

from __future__ import annotations

from dataclasses import dataclass, replace

from sekretesslager import Maskeringsbehov, _Tokengenerator, _maskera_fritext, normalisera_undantag

from .camt053 import Utdrag, Utdragsrad


@dataclass(frozen=True)
class MaskeratUtdrag:
    """`sandningsbara_rader` utesluter varje rad med ett olöst
    maskeringsbehov — samma fail-closed-princip som
    `Maskeringsresultat.sandningsbara_verifikationer` i sekretesslager.py."""

    maskerat_utdrag: Utdrag
    maskeringsbehov: list[Maskeringsbehov]
    sandningsbara_rader: tuple[Utdragsrad, ...]


def _plats_for_rad(index: int) -> str:
    return f"kontoutdragsrad={index}"


def maskera_utdrag(
    utdrag: Utdrag,
    referenslista: set[str] | None = None,
    undantagslista: set[str] | None = None,
) -> MaskeratUtdrag:
    """Maskerar `text` och `motpart` på varje rad — samma `_maskera_fritext`
    som lager 1:s `maskera_siefil` använder. `datum`, `belopp`, `referens`
    och `kontonr` rörs aldrig; de är inte fritext.

    `referenslista` = namn som ALLTID maskeras (lager 3a). `undantagslista`
    = strängar en människa bedömt som icke-PII (lager 3b:s allowlist) —
    samma två parametrar och samma betydelse som i `maskera_siefil`."""
    referenslista = referenslista or set()
    undantag = {normalisera_undantag(text) for text in (undantagslista or set())}
    tokens = _Tokengenerator()
    maskeringsbehov: list[Maskeringsbehov] = []

    maskerade_rader: list[Utdragsrad] = []
    for index, rad in enumerate(utdrag.rader):
        plats = _plats_for_rad(index)
        maskerad_text = _maskera_fritext(
            rad.text, tokens, referenslista, maskeringsbehov, plats, "text", undantag
        )
        maskerad_motpart = _maskera_fritext(
            rad.motpart, tokens, referenslista, maskeringsbehov, plats, "motpart", undantag
        )
        maskerade_rader.append(replace(rad, text=maskerad_text, motpart=maskerad_motpart))

    maskerat_utdrag = replace(utdrag, rader=tuple(maskerade_rader))

    olosta_platser = {
        behov.plats for behov in maskeringsbehov if behov.status == "väntar_granskning"
    }
    sandningsbara = tuple(
        rad
        for index, rad in enumerate(maskerade_rader)
        if _plats_for_rad(index) not in olosta_platser
    )

    return MaskeratUtdrag(
        maskerat_utdrag=maskerat_utdrag,
        maskeringsbehov=maskeringsbehov,
        sandningsbara_rader=sandningsbara,
    )
