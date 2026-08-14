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

import utkast
from chatt_renderare import _bygg_tabellhtml
from svarskontrakt import KolumnDef, TabellBlock
from snabbvyer import Snabbvy, Snabbvyresultat, Sektion
from vy_modell import Atgardsforslag, Atgardsknapp

# Allvarlighet (samma tre nivåer som bokslutskontroll.modell.Fynd) -> samma
# färgnivåer som Sektion.niva. Se hantverksbok/UI_ATGARDER_I_VYN.md §3.2.
_ALLVARLIGHET_NIVA = {
    "avvikelse": "rod",
    "observation": "gul",
    "upplysning": "neutral",
}

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


_MAX_PER_RAD = 4


def rendera_knapprad(st, vyer: tuple[Snabbvy, ...], nyckel: str) -> str | None:
    """Ritar knappraden (i flera rader om det behövs) och returnerar id:t för
    den valda vyn.

    Valet lagras i session_state under `nyckel`, så vyn överlever en omkörning
    (varje knapptryck i Streamlit kör om hela skriptet). Ingen vy är vald från
    början — användaren ska se fliken som vanligt tills hon klickar.

    Två sorters spärr, som aldrig får se likadana ut (hantverksbok/
    UI_ATGARDER_I_VYN.md §4.2–4.3): `status == "kommande"` (funktionen finns
    inte än) ritas låsmärkt och `disabled=True`, oavsett `kraver`-mekanikens
    `st.info`-beteende (som ligger i `rendera_snabbvyfalt`, oförändrat)."""
    if nyckel not in st.session_state:
        st.session_state[nyckel] = None

    def _rita_knapp(kolumn, vy):
        kommande = getattr(vy, "status", "byggd") == "kommande"
        aktiv = st.session_state[nyckel] == vy.id
        etikett = f"🔒 {vy.ikon} {vy.etikett}" if kommande else f"{vy.ikon} {vy.etikett}"
        if kolumn.button(
            etikett,
            key=f"{nyckel}_{vy.id}",
            help=vy.hjalptext,
            type="primary" if aktiv else "secondary",
            width="stretch",
            disabled=kommande,
        ):
            st.session_state[nyckel] = None if aktiv else vy.id
            st.rerun()

    # Rader om högst _MAX_PER_RAD knappar. Ingen domänspecifik gruppering
    # (t.ex. "Kundfakturor"/"Leverantörsfakturor") görs här längre — den låg
    # tidigare hårdkodad för ALLA knapprader med fler än fyra vyer, vilket gav
    # fel bildtexter för t.ex. registerrummets 14 knappar. Ett rum som vill ha
    # egna gruppcaptioner ritar dem själv innan anropet.
    rader = [vyer[i : i + _MAX_PER_RAD] for i in range(0, len(vyer), _MAX_PER_RAD)] or [()]
    sista_kolumner = None
    for rad in rader:
        kolumner = st.columns(len(rad) + (1 if rad is rader[-1] else 0))
        for kolumn, vy in zip(kolumner, rad):
            _rita_knapp(kolumn, vy)
        if rad is rader[-1]:
            sista_kolumner = kolumner

    if sista_kolumner is not None and st.session_state[nyckel] is not None:
        if sista_kolumner[-1].button("✕ Stäng", key=f"{nyckel}_stang", width="stretch"):
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
        
    if getattr(sektion, "dold_detalj", False):
        with st.expander("Visa detaljer"):
            st.markdown(_bygg_tabellhtml(sektion.tabell), unsafe_allow_html=True)
    else:
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




def _rendera_atgardsknapp(st, knapp: Atgardsknapp) -> None:
    """Se hantverksbok/UI_ATGARDER_I_VYN.md §3.3. Knappen skapar ett utkast,
    aldrig mer (U-3) — den anropar bara `utkast.skapa`, aldrig
    `bekrafta_for_sandning` eller en skrivfunktion.

    Nyckeln byggs av utkasttyp + en hash av nyttolasten (samma hash `utkast`
    redan använder för sin egen ändringsdetektion) så att den överlever en
    Streamlit-omkörning: efter ett tryck ska resultatet visas på SAMMA plats
    i stället för att knappen dyker upp igen."""
    nyckel = f"atgard_utkast_{knapp.utkasttyp}_{utkast.berakna_hash(knapp.nyttolast)}"

    st.caption(knapp.bekraftelsetext)
    if knapp.varning:
        st.warning(knapp.varning)

    skapat_id = st.session_state.get(nyckel)
    if skapat_id:
        st.success(f"Utkast skapat ({skapat_id}) — väntar på godkännande i Beslut.")
        return

    if st.button(knapp.etikett, key=f"{nyckel}_knapp"):
        try:
            u = utkast.skapa(knapp.utkasttyp, knapp.nyttolast, [["Åtgärd", knapp.etikett]])
        except utkast.UtkastFel:
            st.error("Kunde inte skapa utkastet.")
            return
        st.session_state[nyckel] = u.utkast_id
        st.rerun()


def _rendera_atgardsforslag(st, forslag: Atgardsforslag) -> None:
    """Se hantverksbok/UI_ATGARDER_I_VYN.md §3.2. Ordningen är bindande:
    rubrik+allvarlighet, belopp/konton, motivering, regelhänvisning,
    konteringsrader, knapp (bara om den finns — ett förslag utan knapp är
    fullt giltigt, hitta aldrig på en åtgärd)."""
    niva = _ALLVARLIGHET_NIVA.get(forslag.allvarlighet, "neutral")
    farg = _NIVAFARG.get(niva, _NIVAFARG["neutral"])
    st.markdown(
        f'<div class="sie-snabbvy-sektion" style="--sie-niva:{farg}">'
        f"<h4>{forslag.rubrik}</h4></div>",
        unsafe_allow_html=True,
    )

    detaljer = []
    if forslag.belopp:
        detaljer.append(f"Belopp: {forslag.belopp}")
    if forslag.konton:
        detaljer.append(f"Konton: {', '.join(forslag.konton)}")
    if detaljer:
        st.caption(" · ".join(detaljer))

    st.write(forslag.motivering)

    if forslag.regel_text:
        if forslag.regel_lank:
            st.markdown(f"[{forslag.regel_text}]({forslag.regel_lank})")
        else:
            st.caption(forslag.regel_text)

    if forslag.rader:
        tabell = TabellBlock(
            kolumner=[
                KolumnDef(nyckel="konto", rubrik="Konto", typ="text"),
                KolumnDef(nyckel="debet", rubrik="Debet", typ="text"),
                KolumnDef(nyckel="kredit", rubrik="Kredit", typ="text"),
            ],
            rader=[
                {"konto": rad[0], "debet": rad[1], "kredit": rad[2]}
                for rad in forslag.rader
            ],
        )
        st.markdown(_bygg_tabellhtml(tabell), unsafe_allow_html=True)

    if forslag.knapp is not None:
        _rendera_atgardsknapp(st, forslag.knapp)


def rendera_resultat(st, resultat: Snabbvyresultat, data=None) -> None:
    st.subheader(f"{resultat.rubrik} {resultat.harkomst.tecken}", help=f"{resultat.harkomst.namn}: {resultat.harkomst.forklaring}")

    if resultat.nyckeltal:
        for kolumn, tal in zip(st.columns(len(resultat.nyckeltal)), resultat.nyckeltal):
            kolumn.metric(tal.etikett, tal.varde, tal.hjalptext, delta_color="off")

    for sektion in resultat.sektioner:
        _rendera_sektion(st, sektion, data)

    # Läst defensivt (getattr): resultat kan vara ett Snabbvyresultat eller
    # ett Vyresultat, och en äldre anropare utan fältet ska inte fälla varje
    # befintlig snabbvy — se hantverksbok/UI_ATGARDER_I_VYN.md §3.1.
    for forslag in getattr(resultat, "atgarder", ()):
        _rendera_atgardsforslag(st, forslag)

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
