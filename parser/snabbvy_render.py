"""snabbvy_render — ritar snabbvyerna i Streamlit.

Tunn: all logik ligger i snabbvyer.py (UI-fri), all tabell-HTML i
chatt_renderare.py. Här finns bara knappraden, sektionsramarna och
färgnivåerna.

Färgerna bär betydelse och är inte dekoration: rött betyder "kunden har brutit
sitt normala betalmönster", gult "förfallen men väntat". De valdes med samma
WCAG-hänsyn som resten av appen och fungerar i både ljust och mörkt tema,
eftersom bakgrunden är genomskinlig och bara kantlinjen färgas — en ifylld
färgruta hade blivit oläslig i ett av lägena.
"""

from __future__ import annotations

from typing import Any

from chatt_renderare import _bygg_tabellhtml
from snabbvyer import Snabbvy, Snabbvyresultat, Sektion

_NIVAFARG = {
    "rod": "#d62728",
    "gul": "#e8a33d",
    "gron": "#2ca02c",
    "neutral": "rgba(128,128,128,0.35)",
}

SNABBVY_CSS = """\
<style>
.sie-snabbvy-sektion {
  border-left: 4px solid var(--sie-niva);
  padding: 0.35rem 0 0.35rem 0.9rem;
  margin: 0.6rem 0 1.1rem 0;
}
.sie-snabbvy-sektion h4 { margin: 0 0 0.25rem 0; font-size: 1.02rem; }
.sie-snabbvy-sektion .sie-snabbvy-beskrivning {
  opacity: 0.75; font-size: 0.88rem; margin: 0 0 0.6rem 0;
}
.sie-snabbvy-fotnot { opacity: 0.65; font-size: 0.82rem; margin-top: 0.8rem; }
</style>
"""


def injicera_snabbvy_css(st) -> None:
    st.markdown(SNABBVY_CSS, unsafe_allow_html=True)


def rendera_knapprad(st, vyer: tuple[Snabbvy, ...], nyckel: str) -> str | None:
    """Ritar knappraden (eller två rader för kunder/leverantörer) och returnerar
    id:t för den valda vyn.

    Valet lagras i session_state under `nyckel`, så vyn överlever en omkörning
    (varje knapptryck i Streamlit kör om hela skriptet). Ingen vy är vald från
    början — användaren ska se fliken som vanligt tills hon klickar."""
    if nyckel not in st.session_state:
        st.session_state[nyckel] = None

    def _rita_knapp(kolumn, vy):
        aktiv = st.session_state[nyckel] == vy.id
        if kolumn.button(
            f"{vy.ikon} {vy.etikett}",
            key=f"{nyckel}_{vy.id}",
            help=vy.hjalptext,
            type="primary" if aktiv else "secondary",
            width="stretch",
        ):
            st.session_state[nyckel] = None if aktiv else vy.id
            st.rerun()

    if len(vyer) > 4:
        st.caption("Kundfakturor")
        for kolumn, vy in zip(st.columns(4), vyer[:4]):
            _rita_knapp(kolumn, vy)

        st.caption("Leverantörsfakturor")
        lev_vyer = vyer[4:]
        kols = st.columns(len(lev_vyer) + 1)
        for kolumn, vy in zip(kols[:len(lev_vyer)], lev_vyer):
            _rita_knapp(kolumn, vy)

        if st.session_state[nyckel] is not None:
            if kols[-1].button("✕ Stäng", key=f"{nyckel}_stang",
                               width="stretch"):
                st.session_state[nyckel] = None
                st.rerun()
    else:
        kolumner = st.columns(len(vyer) + 1)
        for kolumn, vy in zip(kolumner, vyer):
            _rita_knapp(kolumn, vy)

        if st.session_state[nyckel] is not None:
            if kolumner[-1].button("✕ Stäng", key=f"{nyckel}_stang",
                                   width="stretch"):
                st.session_state[nyckel] = None
                st.rerun()

    return st.session_state[nyckel]


def _rendera_sektion(st, sektion: Sektion, data=None) -> None:
    farg = _NIVAFARG.get(sektion.niva, _NIVAFARG["neutral"])
    st.markdown(
        f'<div class="sie-snabbvy-sektion" style="--sie-niva:{farg}">'
        f"<h4>{sektion.rubrik}</h4>"
        + (
            f'<p class="sie-snabbvy-beskrivning">{sektion.beskrivning}</p>'
            if sektion.beskrivning
            else ""
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    if sektion.tabell is None:
        st.caption(sektion.tomtext)
        return
        
    # Rendera alltid standard HTML-tabellen så att stilen och högerställningen bevaras
    st.markdown(_bygg_tabellhtml(sektion.tabell), unsafe_allow_html=True)
    
    # --- Drill-down: fakturor per leverantör eller kund ---
    if sektion.drill_typ in ("leverantor", "kund") and data is not None:
        fakturor = (
            data.leverantorsfakturor
            if sektion.drill_typ == "leverantor"
            else data.kundfakturor
        )
        if fakturor is not None:
            # Bygg en sorterad lista unika motpartsnamn ur fakturalistan
            namnfalt = "leverantor" if sektion.drill_typ == "leverantor" else "kund"
            namn_i_fakturor = sorted(
                {str(f.get(namnfalt) or "") for f in fakturor if f.get(namnfalt)}
            )
            if namn_i_fakturor:
                st.markdown("<br>", unsafe_allow_html=True)
                drill_key = f"drill_{sektion.drill_typ}_{sektion.rubrik}"
                vald = st.selectbox(
                    f"🔍 Välj {sektion.drill_typ} för att se fakturor",
                    options=[""] + namn_i_fakturor,
                    format_func=lambda n: "Välj en post..." if not n else n,
                    key=drill_key,
                )
                if vald:
                    _rendera_drill_fakturor(st, vald, fakturor, sektion.drill_typ, data)
        else:
            # Fakturor är None = inte hämtade ännu (Spiris-klient saknades)
            st.caption("💡 Fakturadetaljer kräver en aktiv Spiris-koppling.")
        return  # Hoppa över kontoplan-drill-down nedan för denna sektionstyp

    # --- Befintlig kontoplan-drill-down ---
    har_kontonr = any(k.nyckel == "kontonr" for k in sektion.tabell.kolumner)
    if har_kontonr and len(sektion.tabell.rader) > 0 and data and data.verifikationer:
        import pandas as pd
        df = pd.DataFrame(sektion.tabell.rader)
        
        konto_options = [""] + df["kontonr"].tolist()
        def format_konto(k):
            if not k: return "Välj ett konto för att granska transaktioner..."
            namn = df[df["kontonr"] == k].iloc[0].get("kontonamn", "")
            return f"{k} - {namn}" if namn else str(k)
            
        st.markdown("<br>", unsafe_allow_html=True)
        valt_konto = st.selectbox("🔍 Transaktionsgranskning", options=konto_options, format_func=format_konto, key=f"drill_select_{sektion.rubrik}")
        
        if valt_konto:
            valt_namn = df[df["kontonr"] == valt_konto].iloc[0].get("kontonamn", "")
            
            traffar = []
            for v in data.verifikationer:
                for p in v.get("poster", []):
                    if p.get("kontonr") == valt_konto:
                        beskrivning = p.get("transaktionstext") or v.get("beskrivning") or ""
                        traffar.append({
                            "Serie": v.get("serie", ""),
                            "Ver.nr": v.get("verifikationsnummer", ""),
                            "Datum": v.get("datum", ""),
                            "Beskrivning": beskrivning,
                            "Belopp": p.get("belopp", 0)
                        })
            
            if traffar:
                from svarskontrakt import TabellBlock, KolumnDef
                from formatering import formatera_tal
                
                drill_rader = []
                for t in traffar:
                    drill_rader.append({
                        "serie": t["Serie"],
                        "vernr": str(t["Ver.nr"]),
                        "datum": t["Datum"],
                        "besk": t["Beskrivning"],
                        "belopp": f"{formatera_tal(t['Belopp'], data.formateringsval)} kr"
                    })
                    
                drill_tabell = TabellBlock(
                    rubrik=f"Transaktioner för konto {valt_konto} {valt_namn}",
                    kolumner=[
                        KolumnDef(nyckel="serie", rubrik="Serie", typ="text"),
                        KolumnDef(nyckel="vernr", rubrik="Ver.nr", typ="text"),
                        KolumnDef(nyckel="datum", rubrik="Datum", typ="text"),
                        KolumnDef(nyckel="besk", rubrik="Beskrivning", typ="text"),
                        KolumnDef(nyckel="belopp", rubrik="Belopp", typ="belopp"),
                    ],
                    rader=drill_rader
                )
                st.markdown(_bygg_tabellhtml(drill_tabell), unsafe_allow_html=True)
            else:
                st.info("Inga transaktioner hittades för detta konto under perioden.")


def _rendera_drill_fakturor(st, motpartsnamn: str, fakturor: list, drill_typ: str, data) -> None:
    """Renderar en fakturaöversikt för en vald leverantör eller kund.
    Kallas från _rendera_sektion när drill_typ är aktivt och en motpart är vald."""
    from svarskontrakt import TabellBlock, KolumnDef

    namnfalt = "leverantor" if drill_typ == "leverantor" else "kund"
    matchande = [f for f in fakturor if str(f.get(namnfalt) or "") == motpartsnamn]

    if not matchande:
        st.info(f"Inga fakturor hittades för {motpartsnamn}.")
        return

    # Bygg summor
    from decimal import Decimal
    summa_total = sum(
        Decimal(str(f.get("totalbelopp") or 0)) for f in matchande
    )
    summa_kvar = sum(
        Decimal(str(f.get("kvarvarande") or 0)) for f in matchande
    )

    kol1, kol2, kol3 = st.columns(3)
    kol1.metric("Antal fakturor", str(len(matchande)))
    kol2.metric("Summa total", f"{summa_total:,.0f} kr".replace(",", " "))
    kol3.metric("Summa obetalt", f"{summa_kvar:,.0f} kr".replace(",", " "))

    # Bygg fakturarad-tabell
    from formatering import formatera_tal
    
    rader = []
    for f in sorted(matchande, key=lambda x: x.get("fakturadatum") or ""):
        totalbelopp = Decimal(str(f.get("totalbelopp") or 0))
        kvarvarande = Decimal(str(f.get("kvarvarande") or 0))
        betald = abs(kvarvarande) < Decimal("0.01")
        status = "✅ Betald" if betald else ("🔴 Förfallen" if f.get("forfallodatum") and f.get("forfallodatum") < str(data.idag) else "⏳ Öppen")
        if f.get("kreditfaktura"):
            status = "🔄 Kredit"

        rader.append({
            "fakturanr": f.get("fakturanummer") or "—",
            "fakturadatum": f.get("fakturadatum") or "",
            "forfallodatum": f.get("forfallodatum") or "",
            "total": formatera_tal(totalbelopp, data.formateringsval) + " kr",
            "kvar": formatera_tal(kvarvarande, data.formateringsval) + " kr",
            "status": status,
        })

    faktura_tabell = TabellBlock(
        rubrik=f"Fakturor — {motpartsnamn}",
        kolumner=[
            KolumnDef(nyckel="fakturanr", rubrik="Faktura nr", typ="text"),
            KolumnDef(nyckel="fakturadatum", rubrik="Fakturadatum", typ="datum"),
            KolumnDef(nyckel="forfallodatum", rubrik="Förfallodatum", typ="datum"),
            KolumnDef(nyckel="total", rubrik="Totalbelopp", typ="belopp"),
            KolumnDef(nyckel="kvar", rubrik="Kvarvarande", typ="belopp"),
            KolumnDef(nyckel="status", rubrik="Status", typ="text"),
        ],
        rader=rader,
    )
    st.markdown(_bygg_tabellhtml(faktura_tabell), unsafe_allow_html=True)




def rendera_resultat(st, resultat: Snabbvyresultat, data=None) -> None:
    st.subheader(f"{resultat.rubrik} {resultat.harkomst.tecken}", help=f"{resultat.harkomst.namn}: {resultat.harkomst.forklaring}")

    if resultat.nyckeltal:
        for kolumn, tal in zip(st.columns(len(resultat.nyckeltal)), resultat.nyckeltal):
            kolumn.metric(tal.etikett, tal.varde, tal.hjalptext, delta_color="off")

    for sektion in resultat.sektioner:
        _rendera_sektion(st, sektion, data)

    if resultat.fotnot:
        st.markdown(
            f'<p class="sie-snabbvy-fotnot">{resultat.fotnot}</p>',
            unsafe_allow_html=True,
        )


def rendera_snabbvyfalt(st, vyer: tuple["Snabbvy", ...], nyckel: str, data: "Any", kalla=None) -> bool:
    """Hela fältet: knapprad + ev. vald vy. Returnerar True om en vy visas, så
    anroparen kan låta bli att rita flikens ordinarie innehåll under den.

    Fail-safe: ett fel i en vy visar ett meddelande i stället för att fälla
    hela fliken — en snabbvy är en bekvämlighet, inte något som får blockera
    resten av appen."""
    from snabbvyer import hitta_vy

    vald_id = rendera_knapprad(st, vyer, nyckel)
    if vald_id is None:
        return False

    vy = hitta_vy(vyer, vald_id)
    if vy is None:  # okänt id, t.ex. efter en uppdatering
        st.session_state[nyckel] = None
        return False


    if kalla and vy.kraver:
        if not vy.kraver.issubset(kalla.formagor()):
            st.info(f"Vyn '{vy.etikett}' kräver förmågor som den valda källan ({kalla.visningsnamn}) saknar.")
            return True

    try:
        rendera_resultat(st, vy.bygg(data), data)
    except Exception:  # noqa: BLE001
        st.error("Kunde inte bygga vyn. Kontrollera att data är inläst.")
    return True
