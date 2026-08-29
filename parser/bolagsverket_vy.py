"""bolagsverket_vy.py — Bolagsverketuppslag i webbgränssnittet.

Samma adapter som MCP-verktygen använder (`quiet_oppen_data.adaptrar.bolagsverket`),
men anropad direkt. Ingen MCP är inblandad: MCP är ett protokoll mellan en
AI-klient och en verktygsserver, och en webbläsare talar inte det. Adaptern är
ett vanligt Python-bibliotek och kan anropas av vem som helst i processen.

Vyn ärver villkorsspärren utan att göra något: `compliance.krav_godkannande(st)`
körs överst i `app.py` och `st.stop()`:ar innan någon sida ritas.

**Källan är Bolagsverkets fria API för värdefulla datamängder.** Styrelse,
firmatecknare och verkliga huvudmän ligger i andra API:er som medvetet inte
används — det ena är avtalsbundet, det andra bär personuppgifter om fysiska
personer och är spärrat i källregistret.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

import streamlit as st

_SIE_MCP_ROT = Path(__file__).resolve().parent.parent

# Färgerna bär samma innebörder som chattens `ton`: modellen — här registret —
# säger vad uppgiften betyder, gränssnittet väljer färgen. Kanten är signalen,
# färgen ett tillägg: den som inte skiljer färger ska kunna läsa tabellen lika bra.
_TONFARG = {
    "bekraftad": ("#2e8b57", "#1f6b45"),
    "nekad": ("#8a8f98", "#667"),
    "varning": ("#c2410c", "#9a3412"),
    "neutral": ("transparent", "inherit"),
}


def _adapter():
    """Adaptern, med de två sökvägarna satta innan biblioteket importeras.

    `QUIET_OPPEN_DATA_ROOT` läses av `register.py` vid **modulimport**, inte
    lat, och `kallor/` ligger i sie-mcps rot — inte i det installerade paketet.
    Konfigurationen måste primas av samma skäl: den delade transporten läser
    HTTP-cachens sökväg ur den, och biblioteket letar efter `config.toml` medan
    vi har `quiet_config.toml`. Utan de här två raderna ger organisationsuppslaget
    noll fakta medan dokumenthämtningen fungerar — den senare går medvetet förbi
    den delade transporten. Samma sak gör `mcp_server/server.py`.
    """
    os.environ.setdefault("QUIET_OPPEN_DATA_ROOT", str(_SIE_MCP_ROT))
    from quiet_oppen_data import konfig

    konfig.las(_SIE_MCP_ROT / "quiet_config.toml")

    from quiet_oppen_data.adaptrar.bolagsverket import BolagsverketAdapter

    return BolagsverketAdapter()


def _ton(etikett: str, varde: str) -> str:
    """Vad uppgiften betyder — inte hur den ska se ut."""
    if varde.startswith(("Nej", "Ingen")):
        return "nekad"
    if etikett.startswith("Avregistreringsdatum") or etikett.startswith("Pågående avveckling"):
        return "varning"
    if etikett.startswith("Verksam") and varde.upper().startswith("JA"):
        return "bekraftad"
    return "neutral"


def _tabell(rader: list[tuple[str, str, str]]) -> str:
    """Bygger tabellen som HTML med **escapade** värden.

    Innehållet kommer från ett myndighetsregister, men det är ändå extern text
    som renderas i sidan. `html.escape` på varje cell är billigt och tar bort
    hela frågan.
    """
    delar = [
        "<table style='width:100%;border-collapse:collapse;font-size:.95rem'>",
        "<tbody>",
    ]
    for etikett, varde, ton in rader:
        kant, textfarg = _TONFARG.get(ton, _TONFARG["neutral"])
        delar.append(
            f"<tr>"
            f"<td style='padding:7px 12px;border-bottom:1px solid rgba(128,128,128,.2);"
            f"border-left:3px solid {kant};color:#667;white-space:nowrap;width:1%'>"
            f"{html.escape(etikett)}</td>"
            f"<td style='padding:7px 12px;border-bottom:1px solid rgba(128,128,128,.2);"
            f"color:{textfarg};font-variant-numeric:tabular-nums'>"
            f"{html.escape(varde)}</td>"
            f"</tr>"
        )
    delar.append("</tbody></table>")
    return "".join(delar)


@st.cache_data(ttl=3600, show_spinner=False)
def _hamta(orgnr: str, verktyg: str | None = None, dokumentid: str | None = None):
    """Cachad hämtning. Bolagsverket tillåter 60 frågor per minut, och samma
    organisationsnummer slås ofta upp flera gånger under ett besök."""
    from quiet_oppen_data.modeller import Fragplan

    extra: dict[str, str] = {}
    if orgnr:
        extra["identitetsbeteckning"] = orgnr
    if verktyg:
        extra["verktyg"] = verktyg
    if dokumentid:
        extra["dokumentid"] = dokumentid
    utkast = _adapter().hamta(Fragplan(fraga="", extra=extra))
    return [
        {"etikett": u.etikett, "varde": u.varde, "period": u.period or ""} for u in utkast
    ]


def _saknar_nycklar() -> bool:
    return not (
        os.environ.get("BOLAGSVERKET_CLIENT_ID")
        and os.environ.get("BOLAGSVERKET_CLIENT_SECRET")
    )


def rendera_bolagsverket() -> None:
    """Sidan: slå upp ett svenskt bolag i Bolagsverkets fria register."""
    st.title("🏛️ Bolagsverket")
    st.caption(
        "Uppgifter ur Bolagsverkets API för värdefulla datamängder — myndighetens "
        "egna data, inte en kommersiell katalog."
    )

    if _saknar_nycklar():
        st.warning(
            "**Klientuppgifterna saknas.** `BOLAGSVERKET_CLIENT_ID` och "
            "`BOLAGSVERKET_CLIENT_SECRET` måste vara satta i miljön — i Coolify "
            "under applikationens Environment Variables. Uppslaget är avstängt "
            "tills dess."
        )
        return

    orgnr = st.text_input(
        "Organisationsnummer",
        placeholder="556861-2351",
        help="Tio siffror, med eller utan bindestreck.",
    )
    if not orgnr.strip():
        st.info("Ange ett organisationsnummer för att slå upp bolaget.")
        return

    rensat = "".join(t for t in orgnr if t.isdigit())
    if len(rensat) != 10:
        st.error(
            f"Ett svenskt organisationsnummer har tio siffror — det här har "
            f"{len(rensat)}."
        )
        return

    # --- Grunduppgifter ---------------------------------------------------
    with st.spinner("Hämtar ur registret …"):
        try:
            fakta = _hamta(rensat)
        except Exception as fel:  # noqa: BLE001 — ett API-fel ska visas, inte krascha sidan
            st.error(f"Uppslaget misslyckades: {fel}")
            return

    if not fakta:
        st.warning(
            f"Registret gav inget svar för **{rensat}**. Numret kan vara felaktigt, "
            f"eller så är organisationen inte registrerad hos Bolagsverket."
        )
        return

    namnpost = next((f for f in fakta if f["etikett"].startswith("Organisationsnamn")), None)
    if namnpost:
        st.subheader(namnpost["varde"])

    rader = [
        (f["etikett"].split(" för ")[0], f["varde"], _ton(f["etikett"], f["varde"]))
        for f in fakta
        if not f["etikett"].startswith("Organisationsnamn")
    ]
    st.markdown(_tabell(rader), unsafe_allow_html=True)

    st.caption(
        "Grönt = bekräftat, grått = uttryckligt nekande, orange = värt att stanna "
        "upp vid. Ett nekande är ett svar: «inte avregistrerad» är något annat än "
        "«vi vet inte»."
    )

    with st.expander("Vad som **inte** står här"):
        st.markdown(
            "* **Styrelse, VD och firmatecknare** — ligger i `foretagsinformation/v4`, "
            "som är avtalsbundet och avgiftsbelagt.\n"
            "* **Verkliga huvudmän** — eget API som bär personuppgifter om fysiska "
            "personer, och som är spärrat i källregistret.\n"
            "* **Aktiekapital och registreringshistorik** — samma avtalsbundna API."
        )

    # --- Årsredovisningar -------------------------------------------------
    st.divider()
    st.markdown("### Inlämnade årsredovisningar")

    try:
        dokument = _hamta(rensat, verktyg="bolagsverket_hvd_dokumentlista")
    except Exception as fel:  # noqa: BLE001
        st.error(f"Dokumentlistan misslyckades: {fel}")
        return

    if not dokument:
        st.info(
            "Inga **digitalt inlämnade** handlingar finns. Det betyder inte att "
            "bolaget saknar årsredovisning — år som lämnats på papper finns inte "
            "i registret."
        )
        return

    val = st.selectbox(
        "Välj handling",
        options=list(range(len(dokument))),
        format_func=lambda i: dokument[i]["varde"][:110],
    )
    varde = dokument[val]["varde"]
    dokumentid = ""
    for bit in varde.replace(";", " ").split():
        if bit.endswith("_paket"):
            dokumentid = bit
            break

    if not dokumentid:
        st.warning("Kunde inte läsa ut något dokument-id ur listposten.")
        return

    if not st.button("Läs innehållet", type="primary"):
        return

    with st.spinner("Hämtar och läser årsredovisningen …"):
        try:
            poster = _hamta("", verktyg="bolagsverket_hvd_dokument", dokumentid=dokumentid)
        except Exception as fel:  # noqa: BLE001
            st.error(f"Dokumenthämtningen misslyckades: {fel}")
            return

    if not poster:
        st.warning(
            "Handlingen gick att hämta men innehöll inga läsbara poster. Den kan "
            "sakna XBRL-taggning."
        )
        return

    st.warning(
        "**Läs enheterna.** Flerårsöversikten i förvaltningsberättelsen står i "
        "**tusental kronor** medan resultat- och balansräkningen står i **kronor**. "
        "Talen är avlästa ur handlingen, inte omräknade — jämför aldrig två poster "
        "utan att kontrollera att de har samma enhet."
    )

    perioder: dict[str, list[tuple[str, str, str]]] = {}
    for p in poster:
        perioder.setdefault(p["period"] or "utan period", []).append(
            (p["etikett"], p["varde"], "neutral")
        )

    for period in sorted(perioder, reverse=True):
        st.markdown(f"**{period}**")
        st.markdown(_tabell(perioder[period]), unsafe_allow_html=True)

    st.caption(
        "Avlästa värden, inte beräknade. Nyckeltal och förändringar mellan år "
        "räknas inte här."
    )
