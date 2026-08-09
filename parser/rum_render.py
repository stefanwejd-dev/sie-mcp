"""rum_render.py — Den enda ritmodulen för rummen (Streamlit-medveten)."""
import streamlit as st
import datetime
from datetime import date, timedelta
from decimal import Decimal
from ordbok import Begrepp, hamta
import snabbvyer
import snabbvy_render
import navigering
import fpa_dashboard
import sessionslogg
import utkast
import app_config
from app_tillstand import _hitta_originaltext
from fpa_vy import formatera_kr
from formatering_ui import hamta_val
from samtalsflode import ChattMeddelande
from spiris_klient import SpirisKlient, SpirisKlientFel
from spiris_session import SpirisSessionFel
from spiris_auth_vy import SpirisTokens
from app_vy import (
    sok_lika_kunder, 
    bygg_ny_kund_payload,
    bygg_oversikt
)
from spiris_adapter import kraver_rot_flaggning, FAKTURATYP_JURIDISK_PERSON, bygg_kundfaktura_payload, _FAKTURATYP_ETIKETTER
from spiris_adapter import (
    MAL_BOKFOR,
    MAL_UTKAST,
    UTATRIKTADE_TYPER,
    hamta_granskad_mottagare,
    skapa_kund,
    utfor_utkast,
)
from app_vy import (
    obeslutade_behov,
    unika_namn_behov,
    markera_kanslig_text,
    BESLUT_AVVAKTA,
    BESLUT_MASKERA,
    BESLUT_INGEN_MASKERING,
    bygg_granskade_behov_per_namn,
    tillämpa_liggare,
    namn_att_undanta,
)
from masking_memory import lagg_till_maskeringsminne, verifikation_id
from app_vy import verifikation_till_visningsrad
from app_tillstand import _rendera_notiser
from assistent_funcs import _rendera_utflodeslogg

_BESLUTSETIKETTER = {
    BESLUT_AVVAKTA: "Avvakta",
    BESLUT_MASKERA: "Maskera",
    BESLUT_INGEN_MASKERING: "Ingen maskering",
}

def tomt_lage(st, begrepp: Begrepp, vad_rummet_visar: str) -> None:
    st.header(begrepp.namn)
    st.info(f"{vad_rummet_visar} saknas.")
    col1, col2 = st.columns(2)
    col1.button("Anslut ett affärssystem", disabled=True, help="Kommer i Fas 3")
    col2.button("Ladda upp en SIE4-fil", disabled=True, help="Kommer i Fas 3")
    st.caption(begrepp.forklaring)

def _bygg_spiris_klient_fran_session(client_id: str, client_secret: str) -> SpirisKlient:
    """Bygger en SpirisKlient ur sessionens sparade token. Egen liten
    funktion (i stället för att återanvända sidomenyns lokala variabel)
    eftersom fakturaflödet behöver en klient på flera åtskilda ställen
    (kundsökning, artikeluppslag, POST) över flera Streamlit-reruns."""
    return SpirisKlient(
        access_token=st.session_state.spiris_tokens.access_token,
        refresh_token=st.session_state.spiris_tokens.refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )


def _spara_uppdaterade_tokens(klient: SpirisKlient) -> None:
    """En ev. token-refresh under anropet ska överleva nästa rerun — samma
    mönster som resten av app.py:s Spiris-anrop."""
    st.session_state.spiris_tokens = SpirisTokens(klient.access_token, klient.refresh_token)


def _rendera_fakturautkast_formular() -> None:
    st.write("**Skapa kundfaktura** — fyll i uppgifterna nedan.")
    with st.form("faktura_formular"):
        kundnamn = st.text_input("Kundnamn")
        fakturatyp = st.selectbox(
            "Fakturatyp", list(_FAKTURATYP_ETIKETTER), format_func=_FAKTURATYP_ETIKETTER.get,
        )
        kol1, kol2 = st.columns(2)
        arbetskostnad = kol1.number_input("Arbetskostnad (kr)", min_value=0.0, value=0.0, step=500.0)
        materielkostnad = kol2.number_input("Materielkostnad (kr)", min_value=0.0, value=0.0, step=500.0)

        rot_falt = {}
        if kraver_rot_flaggning(fakturatyp):
            st.caption(
                "ROT kräver fastighetsuppgifter, fastighetsägarens personnummer (kort "
                "format ÅÅMMDD-XXXX — Spiris avvisar ett fullständigt personnummer), "
                "arbetstimmar och det ROT-avdrag som ska fördelas. Ingen procentsats "
                "hårdkodas här (den är lagstiftning, inte en teknisk konstant) — "
                "ange den aktuella satsen själv."
            )
            rot_falt["fastighetsbeteckning"] = st.text_input("Fastighetsbeteckning")
            rot_falt["personnummer"] = st.text_input("Fastighetsägarens personnummer (ÅÅMMDD-XXXX)")
            rot_falt["arbetstimmar"] = st.number_input(
                "Arbetstimmar (krävs av Spiris)", min_value=0.0, value=0.0, step=1.0
            )
            rot_falt["rot_avdrag"] = st.number_input(
                "ROT-avdrag att fördela (kr)", min_value=0.0, value=0.0, step=100.0
            )

        byggt = st.form_submit_button("Bygg utkast")

    if not byggt:
        return
    if not kundnamn.strip():
        st.error("Ange ett kundnamn.")
        return
    if arbetskostnad <= 0 and materielkostnad <= 0:
        st.error("Ange minst en kostnad (arbete eller material).")
        return
    if kraver_rot_flaggning(fakturatyp) and (
        not rot_falt["fastighetsbeteckning"].strip()
        or len(rot_falt["personnummer"].strip()) != 11
        or rot_falt["arbetstimmar"] < 1
        or rot_falt["rot_avdrag"] <= 0
    ):
        st.error(
            "ROT kräver fastighetsbeteckning, ett personnummer i kort format "
            "(11 tecken, ÅÅMMDD-XXXX), minst 1 arbetstimme och ett ROT-avdrag > 0."
        )
        return

    st.session_state.aktivt_fakturautkast = {
        "typ": "faktura",
        "fas": "sok_kund",
        "kundnamn": kundnamn,
        "fakturatyp": fakturatyp,
        "arbetskostnad": Decimal(str(arbetskostnad)),
        "materielkostnad": Decimal(str(materielkostnad)),
        **{k: (Decimal(str(v)) if isinstance(v, float) else v) for k, v in rot_falt.items()},
    }
    st.rerun()


def _rendera_fakturautkast(spiris_client_id: str, spiris_client_secret: str) -> None:
    """Hela 'Skapa kundfaktura'/'Skapa kund'-flödet: formulär ELLER ett
    AI-verktygsanrop (Fas 9) -> sök kund -> ev. 'kund saknas' ->
    (för faktura) granskningsbart utkast -> Godkänn och Skicka. Faserna
    hålls i st.session_state.aktivt_fakturautkast så de överlever
    Streamlit-reruns medan användaren interagerar.

    tillstand["typ"] skiljer de två inflödena åt: "faktura" (formulär-
    knappen ELLER AI:ts skapa_kundfaktura-verktyg) går hela vägen till
    kontering/granskning; "kund" (AI:ts skapa_kund-verktyg) stannar vid att
    bekräfta/skapa kunden — det finns ingen kontering att granska för en
    ren kundpost. Default "faktura" håller den ursprungliga knapp-vägen
    (som alltid sätter typ explicit numera, se _rendera_fakturautkast_
    formular) bakåtkompatibel om något glömde sätta den."""
    tillstand = st.session_state.aktivt_fakturautkast
    if tillstand is None:
        return
    typ = tillstand.get("typ", "faktura")

    with st.chat_message("assistant"):
        if tillstand["fas"] == "formular":
            _rendera_fakturautkast_formular()
            return

        if tillstand["fas"] == "sok_kund":
            try:
                klient = _bygg_spiris_klient_fran_session(spiris_client_id, spiris_client_secret)
                kunder = klient.hamta_alla("/customers")
                _spara_uppdaterade_tokens(klient)
            except SpirisKlientFel as fel:
                st.error(f"Kunde inte slå upp kunder i Spiris: {fel}")
                return
            träff = next(
                (k for k in kunder if (k.get("Name") or "").casefold() == tillstand["kundnamn"].casefold()),
                None,
            )
            if träff is None:
                nasta_fas = "kund_saknas"
                kandidater = sok_lika_kunder(tillstand["kundnamn"], kunder)
            elif typ == "kund":
                nasta_fas = "kund_finns_redan"
                kandidater = []
            else:
                nasta_fas = "bygg_utkast"
                kandidater = []
            st.session_state.aktivt_fakturautkast = {
                **tillstand, "fas": nasta_fas, "kund_id": träff.get("Id") if träff else None,
                "kandidater": kandidater,
            }
            st.rerun()

        elif tillstand["fas"] == "kund_finns_redan":
            # Bara typ == "kund" når hit (se "sok_kund" ovan) — AI:t bads
            # skapa en kund som redan finns. Inget att godkänna, bara att
            # visa och låta användaren gå vidare.
            st.info(
                f"Kunden '{tillstand['kundnamn']}' finns redan i Spiris "
                f"(Id: {tillstand['kund_id']}). Ingen ny kund skapades."
            )
            if st.button("OK", key="kund_finns_redan_ok"):
                st.session_state.samtal_historik.append(
                    ChattMeddelande(roll="user", text=f"Skapa kunden {tillstand['kundnamn']}.")
                )
                st.session_state.samtal_historik.append(ChattMeddelande(
                    roll="assistant",
                    text=f"Kunden '{tillstand['kundnamn']}' fanns redan i Spiris — skapade ingen ny.",
                ))
                st.session_state.aktivt_fakturautkast = None
                st.rerun()

        elif tillstand["fas"] == "kund_saknas":
            # Ingen exakt träff: gränssnittet får ALDRIG falla tillbaka på en
            # fritext-motfråga här — bara strukturerade knappval, oavsett om
            # kunden saknas helt eller namnet är tvetydigt (t.ex.
            # "Karl Svensson" mot en befintlig "Carl Svensson", se
            # app_vy.sok_lika_kunder).
            st.warning(f"Ingen kund vid namn '{tillstand['kundnamn']}' hittades i Spiris.")
            kandidater = tillstand.get("kandidater", [])
            if kandidater:
                st.write("Menade du en av dessa befintliga kunder?")
                for i, kandidat in enumerate(kandidater):
                    kol_namn, kol_knapp = st.columns([3, 2])
                    kol_namn.caption(f"{kandidat.namn} ({round(kandidat.likhet * 100)}% likhet)")
                    if kol_knapp.button(f"Använd '{kandidat.namn}'", key=f"kund_kandidat_{i}"):
                        nasta_fas = "kund_finns_redan" if typ == "kund" else "bygg_utkast"
                        st.session_state.aktivt_fakturautkast = {
                            **tillstand, "fas": nasta_fas, "kund_id": kandidat.kund_id,
                        }
                        st.rerun()
            if st.button(f"➕ Skapa ny kund '{tillstand['kundnamn']}'", key="skapa_ny_kund_knapp"):
                # typ == "faktura" har redan sin privatperson-status via
                # fakturatyp (samma härledning som innan) och behöver därför
                # inget extra knappval — bara typ == "kund" (AI:ts egen
                # gissning, som kan vara fel) frågar uttryckligen.
                if typ == "kund":
                    st.session_state.aktivt_fakturautkast = {**tillstand, "fas": "ny_kund_typ"}
                else:
                    st.session_state.aktivt_fakturautkast = {
                        **tillstand, "fas": "ny_kund_uppgifter",
                        "ar_privatperson": tillstand["fakturatyp"] != FAKTURATYP_JURIDISK_PERSON,
                    }
                st.rerun()
            if st.button("Avbryt", key="avbryt_kund_saknas"):
                st.session_state.aktivt_fakturautkast = None
                st.rerun()

        elif tillstand["fas"] == "ny_kund_typ":
            # Bara typ == "kund" når hit (se "kund_saknas" ovan) — AI:ts
            # gissning på privatperson/företag kan vara fel och ska gå att
            # rätta med ett enda tydligt knappval, INTE en fritextfråga.
            st.write(f"**Ny kund: '{tillstand['kundnamn']}'** — privatperson eller företag?")
            kol_foretag, kol_privat = st.columns(2)
            if kol_foretag.button("🏢 Företag", key="ny_kund_foretag"):
                st.session_state.aktivt_fakturautkast = {
                    **tillstand, "fas": "ny_kund_uppgifter", "ar_privatperson": False,
                }
                st.rerun()
            if kol_privat.button("🧍 Privatperson", key="ny_kund_privatperson"):
                st.session_state.aktivt_fakturautkast = {
                    **tillstand, "fas": "ny_kund_uppgifter", "ar_privatperson": True,
                }
                st.rerun()
            if st.button("Avbryt", key="avbryt_ny_kund_typ"):
                st.session_state.aktivt_fakturautkast = None
                st.rerun()

        elif tillstand["fas"] == "ny_kund_uppgifter":
            ar_privatperson = tillstand["ar_privatperson"]
            st.write(
                f"**Ny kund: '{tillstand['kundnamn']}'** "
                f"({'privatperson' if ar_privatperson else 'företag'}) — "
                "ange grunduppgifter innan fakturaflödet fortsätter."
            )
            with st.form("ny_kund_uppgifter_formular"):
                orgnr_personnr = st.text_input(
                    "Personnummer (ÅÅMMDD-XXXX)" if ar_privatperson
                    else "Organisationsnummer (XXXXXX-XXXX)"
                )
                adress = st.text_input("Adress (gata)")
                kol_postnr, kol_ort = st.columns(2)
                postnr = kol_postnr.text_input("Postnummer")
                ort = kol_ort.text_input("Ort")
                skapa_klart = st.form_submit_button("Skapa kund och fortsätt")

            if skapa_klart:
                if not orgnr_personnr.strip():
                    st.error("Ange person-/organisationsnummer.")
                else:
                    try:
                        klient = _bygg_spiris_klient_fran_session(
                            spiris_client_id, spiris_client_secret
                        )
                        ny_kund = skapa_kund(klient, bygg_ny_kund_payload(
                            tillstand["kundnamn"], ar_privatperson, orgnr_personnr.strip(),
                            adress=adress.strip(), postnr=postnr.strip(), ort=ort.strip(),
                        ))
                        _spara_uppdaterade_tokens(klient)
                    except SpirisKlientFel as fel:
                        st.error(f"Kunde inte skapa kunden i Spiris: {fel}")
                    else:
                        if typ == "kund":
                            st.session_state.samtal_historik.append(ChattMeddelande(
                                roll="user", text=f"Skapa kunden {tillstand['kundnamn']}.",
                            ))
                            st.session_state.samtal_historik.append(ChattMeddelande(
                                roll="assistant",
                                text=(
                                    f"✅ Kund skapad hos Spiris (Id: {ny_kund['Id']}) för "
                                    f"'{tillstand['kundnamn']}'."
                                ),
                            ))
                            st.session_state.aktivt_fakturautkast = None
                        else:
                            st.session_state.aktivt_fakturautkast = {
                                **tillstand, "fas": "bygg_utkast", "kund_id": ny_kund["Id"],
                            }
                        st.rerun()
            if st.button("Avbryt", key="avbryt_ny_kund_uppgifter"):
                st.session_state.aktivt_fakturautkast = None
                st.rerun()

        elif tillstand["fas"] == "rot_lokalt":
            # Fynd B: AI-vägen (agentens skapa_kundfaktura) bär ALDRIG ROT-
            # uppgifterna längre. Saknas de för en ROT-faktura samlas de in HÄR,
            # i ett lokalt formulär som aldrig når någon AI. Manuella formulär-
            # vägen fyller redan i dem och passerar därför förbi den här fasen.
            st.write(
                f"**ROT-uppgifter för {tillstand['kundnamn']}** — fyll i lokalt. "
                "Fastighetsägarens personnummer stannar i appen och skickas aldrig "
                "till någon AI."
            )
            with st.form("rot_lokalt_formular"):
                r_fastighet = st.text_input("Fastighetsbeteckning")
                r_personnummer = st.text_input("Fastighetsägarens personnummer (ÅÅMMDD-XXXX)")
                r_timmar = st.number_input(
                    "Arbetstimmar (krävs av Spiris)", min_value=0.0, value=0.0, step=1.0
                )
                r_avdrag = st.number_input(
                    "ROT-avdrag att fördela (kr)", min_value=0.0, value=0.0, step=100.0
                )
                r_klar = st.form_submit_button("Spara ROT-uppgifter och fortsätt")
            if r_klar:
                if (
                    not r_fastighet.strip()
                    or len(r_personnummer.strip()) != 11
                    or r_timmar < 1
                    or r_avdrag <= 0
                ):
                    st.error(
                        "ROT kräver fastighetsbeteckning, ett personnummer i kort format "
                        "(11 tecken, ÅÅMMDD-XXXX), minst 1 arbetstimme och ett ROT-avdrag > 0."
                    )
                else:
                    st.session_state.aktivt_fakturautkast = {
                        **tillstand, "fas": "bygg_utkast",
                        "fastighetsbeteckning": r_fastighet.strip(),
                        "personnummer": r_personnummer.strip(),
                        "arbetstimmar": Decimal(str(r_timmar)),
                        "rot_avdrag": Decimal(str(r_avdrag)),
                    }
                    st.rerun()
            if st.button("Avbryt", key="avbryt_rot_lokalt"):
                st.session_state.aktivt_fakturautkast = None
                st.rerun()

        elif tillstand["fas"] == "bygg_utkast":
            # Fynd B: en ROT-faktura som saknar fastighetsägarens personnummer
            # (AI-vägen samlar det aldrig) måste först kompletteras lokalt.
            if kraver_rot_flaggning(tillstand["fakturatyp"]) and not str(
                tillstand.get("personnummer", "")
            ).strip():
                st.session_state.aktivt_fakturautkast = {**tillstand, "fas": "rot_lokalt"}
                st.rerun()

            # Kort mellansteg, aldrig visat — bygger utkastet (kan slå upp
            # konteringsminnet) nu när kund_id är känt, innan granskningen.
            poster = []
            if tillstand["arbetskostnad"] > 0:
                poster.append({
                    "beskrivning": "Arbetskostnad", "kategori": "arbete",
                    "belopp": tillstand["arbetskostnad"],
                })
            if tillstand["materielkostnad"] > 0:
                poster.append({
                    "beskrivning": "Materielkostnad", "kategori": "materiel",
                    "belopp": tillstand["materielkostnad"],
                })
            utkast = bygg_fakturautkast(
                tillstand["kundnamn"], tillstand["fakturatyp"], poster,
                st.session_state.konteringsminne,
            )
            st.session_state.aktivt_fakturautkast = {**tillstand, "fas": "granskning", "utkast": utkast}
            st.rerun()

        elif tillstand["fas"] == "granskning":
            st.write(
                f"**Fakturautkast — {tillstand['kundnamn']}** "
                f"({_FAKTURATYP_ETIKETTER[tillstand['fakturatyp']]})"
            )
            andringar: dict[int, str] = {}
            for i, rad in enumerate(tillstand["utkast"]):
                källa = "📚 tidigare mönster" if rad.kall_ur_minne else "🤖 AI-förslag (konteringsmotorn)"
                kol_besk, kol_konto, kol_kalla = st.columns([2, 1, 2])
                kol_besk.write(f"{rad.beskrivning} — {rad.belopp} kr")
                nytt = kol_konto.text_input(
                    "Kontonr", value=rad.kontonr, key=f"faktura_kontonr_{i}",
                    label_visibility="collapsed",
                )
                kol_kalla.caption(källa)
                if nytt != rad.kontonr:
                    andringar[i] = nytt

            kol_godkann, kol_avbryt = st.columns(2)
            if kol_godkann.button("✅ Godkänn och Skicka"):
                godkänt = tillampa_kontonr_andringar(tillstand["utkast"], andringar)
                try:
                    klient = _bygg_spiris_klient_fran_session(spiris_client_id, spiris_client_secret)
                    fakturarader = losa_artikel_ider_for_fakturarader(
                        klient, fakturarader_for_betalning(godkänt)
                    )
                    rot_uppgifter = None
                    if kraver_rot_flaggning(tillstand["fakturatyp"]):
                        for rad, löst in zip(godkänt, fakturarader):
                            if rad.kategori == "arbete":
                                löst["arbetstyp"] = ARBETSTYP_ROT_BYGGARBETE
                                löst["arbetstimmar"] = tillstand["arbetstimmar"]
                        rot_uppgifter = bygg_rot_uppgifter(
                            fastighetsbeteckning=tillstand["fastighetsbeteckning"],
                            personnummer_fastighetsagare=tillstand["personnummer"],
                            personer=[{
                                "Ssn": tillstand["personnummer"], "Amount": tillstand["rot_avdrag"],
                            }],
                            rot_belopp=tillstand["rot_avdrag"],
                        )
                    payload = bygg_kundfaktura_payload(
                        tillstand["kund_id"], fakturarader,
                        date.today().isoformat(),
                        (date.today() + timedelta(days=30)).isoformat(),
                        rot_uppgifter=rot_uppgifter,
                    )
                    skapad = skapa_kundfaktura(klient, payload)
                    _spara_uppdaterade_tokens(klient)
                except SpirisKlientFel as fel:
                    st.error(f"Kunde inte skicka fakturan till Spiris: {fel}")
                else:
                    kontering = kontering_fran_utkast(godkänt)
                    st.session_state.konteringsminne = app_config.uppdatera_konteringsminne(
                        st.session_state.konteringsminne, tillstand["kundnamn"],
                        tillstand["fakturatyp"], kontering,
                    )
                    app_config.spara_konteringsminne(st.session_state.konteringsminne)
                    st.session_state.samtal_historik.append(ChattMeddelande(
                        roll="user",
                        text=f"Skapa en kundfaktura för {tillstand['kundnamn']}.",
                    ))
                    st.session_state.samtal_historik.append(ChattMeddelande(
                        roll="assistant",
                        text=(
                            f"✅ Faktura skapad hos Spiris (fakturanr "
                            f"{skapad.get('InvoiceNumber', skapad.get('Id'))}) för "
                            f"{tillstand['kundnamn']}. Kontering inlärd: {kontering}."
                        ),
                    ))
                    st.session_state.aktivt_fakturautkast = None
                    st.rerun()
            if kol_avbryt.button("Avbryt", key="avbryt_granskning"):
                st.session_state.aktivt_fakturautkast = None
                st.rerun()


# --- Interaktiva val i chatten (Fas 10) ----------------------------------------
# När AI:t anropar efterfraga_val (chatt_klient.py) i stället för att skriva
# en textfråga, renderas alternativen som knappar HÄR — direkt under AI:ts
# meddelande i "Fråga om filen" (se den flikens historik-loop). Ett klick
# lägger BARA till valet som ett nytt användarmeddelande och kör st.rerun():
# själva AI-anropet görs av flikens "steg A" på nästa körning, precis som
# ett skrivet svar i st.chat_input — samma enda kodväg oavsett hur svaret
# kom in. "Skriv eget..." finns ALLTID med, oavsett vilka alternativ AI:t
# föreslog — användaren ska aldrig sitta fast utan möjlighet att skriva
# något AI:t inte tänkte på.

def rendera_oversikt() -> None:
    st.header("🏠 Översikt")
    datakälla = st.session_state.get("aktiv_datakälla", "Ladda upp lokal SIE4-fil")
    sie = st.session_state.get("sie")
    maskeringsresultat = st.session_state.get("maskeringsresultat")
    st.header("⚙️ Datastatus")
    _rendera_notiser()
    # Utanför if/else nedan: loggen hör till APPSESSIONEN, inte till en inläst
    # fil, och ska gå att hitta även innan någon data laddats.
    _rendera_utflodeslogg()

    if sie is None or maskeringsresultat is None:
        st.info("Ladda in data i sidomenyn (Datakälla → Data) för att komma igång.")
    else:
        st.caption(f"Datakälla: {datakälla}")

        st.subheader("Översikt")
        översikt = bygg_oversikt(sie, maskeringsresultat)
        kol1, kol2, kol3, kol4, kol5, kol6 = st.columns(6)
        kol1.metric("Verifikationer", översikt.antal_verifikationer)
        kol2.metric("Tolkningsbehov", översikt.antal_tolkningsbehov)
        kol3.metric("Maskeringsbehov", översikt.antal_maskeringsbehov)
        kol4.metric("Sandningsbara ver.", översikt.antal_sandningsbara_verifikationer)
        kol5.metric("Blockerade ver.", översikt.antal_blockerade_verifikationer)
        kol6.metric("Prosa sändningsbar", översikt.prosa_sandningsbar)

        st.divider()
        st.subheader("Tolkningsbehov")
        if sie.tolkningsbehov:
            st.dataframe(
                [
                    {
                        "Radnummer": tolkningsbehov.radnummer,
                        "Råtext": tolkningsbehov.råtext,
                        "Etikett": tolkningsbehov.etikett,
                        "Anledning": tolkningsbehov.anledning,
                    }
                    for tolkningsbehov in sie.tolkningsbehov
                ]
            )
        else:
            st.write("Inga tolkningsbehov.")

        st.divider()
        st.subheader("Sandningsbara verifikationer")
        st.caption(
            "Verifikationer med olösta maskeringsbehov blockeras från senare "
            "AI-analys. Ingen rad försvinner tyst — de hanteras i fliken Åtgärder."
        )
        if maskeringsresultat.sandningsbara_verifikationer:
            st.dataframe(
                [
                    verifikation_till_visningsrad(v)
                    for v in maskeringsresultat.sandningsbara_verifikationer
                ]
            )
        else:
            st.write("Inga sandningsbara verifikationer.")


# --- Flik: 🔴/🟢 Åtgärder ------------------------------------------------------
# Alla aktiva human-in-the-loop-uppgifter. Badgen ovan speglar exakt innehållet
# här: maskeringsbehov som väntar på beslut + obehandlade verifikationsavvikelser.


def rendera_beslut(spiris_client_id: str, spiris_client_secret: str) -> None:
    datakälla = st.session_state.get("aktiv_datakälla", "Ladda upp lokal SIE4-fil")
    sie = st.session_state.get("sie")
    maskeringsresultat = st.session_state.get("maskeringsresultat")
    vantande_utkast = []
    try:
        vantande_utkast = utkast.lista(status=utkast.VANTAR)
    except Exception:
        pass
    avvikelser = navigering.hitta_verifikationsavvikelser(sie, maskeringsresultat) if sie and maskeringsresultat else []
    atgardsstatus = navigering.bygg_atgardsstatus(
        navigering.ohanterade_maskeringsbehov(maskeringsresultat) if maskeringsresultat else [],
        avvikelser,
        antal_utkast=len(vantande_utkast),
    )
    st.header(f"{atgardsstatus.badge} Åtgärder")

    # --- Utkast från MCP-klient (Steg 2) ---------------------------------
    # Ligger FÖRE sie-kontrollen med flit: den som använder MCP-servern har
    # ofta inte laddat någon fil i appen alls, och måste ändå kunna granska
    # och godkänna sina utkast. Det här är den enda platsen i hela systemet
    # där en skrivning mot Spiris kan utlösas.
    if vantande_utkast:
        st.subheader(f"📝 Utkast som väntar på ditt godkännande ({len(vantande_utkast)})")
        st.caption(
            "Förslagen kommer från en AI-assistent via MCP. **Ingenting har skickats.** "
            "Granska varje uppgift mot ditt eget underlag — du ansvarar för innehållet, "
            "inte assistenten. Ett utkast som är äldre än ett dygn kan inte längre "
            "godkännas."
        )
        for u in vantande_utkast:
            with st.expander(
                f"{u.typ.capitalize()} — skapat {u.skapad}"
                + ("  ⚠️ UTGÅNGET" if u.ar_utgangen else ""),
                expanded=not u.ar_utgangen,
            ):
                for etikett, varde in u.sammanfattning:
                    st.markdown(f"- **{etikett}:** {varde}")

                if u.ar_utgangen:
                    st.warning(
                        "Utkastet är äldre än "
                        f"{utkast.STANDARD_LIVSLANGD_TIMMAR} timmar. Underlaget kan ha "
                        "ändrats i Spiris sedan det skapades — be assistenten skapa ett nytt."
                    )
                    if st.button("Ta bort", key=f"utkast_bort_{u.utkast_id}"):
                        utkast.avvisa(u.utkast_id)
                        st.rerun()
                else:
                    # Destinationsvalet. Standard är utkast i Spiris: det är
                    # återkalleligt (går att ändra och ta bort där), medan ett
                    # bokfört verifikat enligt bokföringslagen 5 kap. bara kan
                    # rättas med ett nytt. Valet ligger utanför den hashbundna
                    # nyttolasten — hashen binder VAD som skrivs, inte VART
                    # (se spiris_adapter.utfor_utkast).
                    mal = MAL_UTKAST
                    if u.typ in ("verifikat", "kundfaktura"):
                        mal = st.radio(
                            "Vad ska hända när du godkänner?",
                            options=[MAL_UTKAST, MAL_BOKFOR],
                            format_func=lambda m: (
                                "Skapa utkast i Spiris — du bokför själv där (rekommenderas)"
                                if m == MAL_UTKAST
                                else "Bokför direkt — kan inte ångras"
                            ),
                            key=f"utkast_mal_{u.utkast_id}",
                            horizontal=False,
                        )
                        if mal == MAL_BOKFOR:
                            st.warning(
                                "Direktbokföring kan inte ångras. Ett bokfört "
                                "verifikat kan bara rättas med ett nytt, och en "
                                "bokförd faktura kan mejlas till mottagaren."
                            )

                    # Mottagarvisningen (Steg 5). En utåtriktad åtgärd når en
                    # tredje man och kan inte kallas tillbaka. AI:n kan per
                    # konstruktion inte se adressen — hamta_kunder hämtar aldrig
                    # EmailAddress — så den hämtas HÄR, lokalt, och visas innan
                    # knappen blir användbar. Adressen går aldrig vidare till
                    # någon AI; den skickas bara till utfor_utkast som det
                    # granskade värdet.
                    granskad_mottagare = None
                    if u.typ in UTATRIKTADE_TYPER:
                        try:
                            klient_g = _bygg_spiris_klient_fran_session(
                                spiris_client_id, spiris_client_secret
                            )
                            granskad_mottagare = hamta_granskad_mottagare(
                                klient_g, u.typ, u.nyttolast
                            )
                            _spara_uppdaterade_tokens(klient_g)
                        except (SpirisKlientFel, SpirisSessionFel, KeyError):
                            granskad_mottagare = None
                            st.error(
                                "Kunde inte läsa fakturans mottagare från Spiris. "
                                "Ingenting kan skickas förrän mottagaren går att visa."
                            )

                        if granskad_mottagare:
                            st.info(f"📧 Skickas till: **{granskad_mottagare}**")
                            st.caption(
                                "Kontrollera adressen. Ett skickat meddelande "
                                "kan inte kallas tillbaka."
                            )
                        elif granskad_mottagare == "":
                            st.error(
                                "Fakturan saknar registrerad e-postadress i Spiris. "
                                "Lägg till en adress där först — ingenting skickas "
                                "till en mottagare du inte har sett."
                            )

                    kol_ja, kol_nej = st.columns(2)
                    _far_skicka = (
                        u.typ not in UTATRIKTADE_TYPER or bool(granskad_mottagare)
                    )
                    if kol_ja.button(
                        "✅ Godkänn och skicka", type="primary",
                        key=f"utkast_ja_{u.utkast_id}", disabled=not _far_skicka,
                    ):
                        try:
                            nyttolast = utkast.bekrafta_for_sandning(u.utkast_id)
                            klient = _bygg_spiris_klient_fran_session(
                                spiris_client_id, spiris_client_secret
                            )
                            svar = utfor_utkast(
                                klient, u.typ, nyttolast, mal, granskad_mottagare
                            )
                            _spara_uppdaterade_tokens(klient)
                            utkast.markera_skickat(u.utkast_id, svar)
                            if mal == MAL_UTKAST and u.typ in ("verifikat", "kundfaktura"):
                                st.success(
                                    "Utkast skapat i Spiris. Det påverkar inte "
                                    "räkenskaperna förrän du bokför det i Spiris."
                                )
                            else:
                                st.success("Skickat till Spiris.")
                        except utkast.UtkastFel as fel:
                            st.error(str(fel))
                        except (SpirisKlientFel, SpirisSessionFel):
                            utkast.markera_misslyckat(
                                u.utkast_id, "Spiris avvisade eller kunde inte nås"
                            )
                            st.error("Kunde inte skicka till Spiris. Utkastet är kvar.")
                        st.rerun()
                    if kol_nej.button("✖ Avvisa", key=f"utkast_nej_{u.utkast_id}"):
                        utkast.avvisa(u.utkast_id)
                        st.rerun()
        st.divider()

    if sie is None or maskeringsresultat is None:
        if not vantande_utkast:
            st.info("Ladda in data i sidomenyn för att se vad som behöver åtgärdas.")
    else:
        kol_mask, kol_avv, kol_tot = st.columns(3)
        kol_mask.metric("Maskeringsbehov", atgardsstatus.antal_maskeringsbehov)
        kol_avv.metric("Verifikationsavvikelser", atgardsstatus.antal_verifikationsavvikelser)
        kol_tot.metric("Totalt att åtgärda", atgardsstatus.antal_totalt)

        if not atgardsstatus.kräver_åtgärd:
            st.success("🟢 Inget väntar på handläggning.")

        st.divider()
        st.subheader("Maskeringsbehov (human-in-the-loop)")
        # Bara rader som fortfarande väntar på beslut visas. Redan avgjorda
        # rader — maskerade SÅVÄL SOM undantagna — försvinner ur listan.
        behov_lista = obeslutade_behov(maskeringsresultat.maskeringsbehov)
        if not behov_lista:
            st.write("Inga maskeringsbehov (kända namn maskeras redan automatiskt).")
        else:
            # Gruppera per unikt namn — varje namn visas EXAKT en gång, oavsett hur
            # många verifikationer det förekommer i.
            unika = unika_namn_behov(behov_lista)
            st.write(
                f"AI:n hittade **{len(unika)}** unika namn att granska. Välj per namn "
                "om det ska **maskeras** eller lämnas som **ingen maskering**, och "
                "justera texten vid behov. Vid **Tillämpa maskering** sparas maskerade "
                "namn i det krypterade maskeringsminnet, och namn markerade som ingen "
                "maskering läggs i den krypterade undantagslistan — de flaggas då "
                "aldrig igen i framtida filer eller sessioner. Rader du lämnar som "
                "**avvakta** ligger kvar och fortsätter blockera sina verifikationer."
            )

            # Globala knappar sätter alla per-namn-val och kör om.
            kol_alla, kol_ingen = st.columns(2)
            if kol_alla.button("Maskera alla"):
                for behov in unika:
                    st.session_state[f"beslut_namn_{behov.misstänkt_text}"] = BESLUT_MASKERA
                st.rerun()
            # Medvetet en annan etikett än förr: knappen allowlistar numera varje
            # namn permanent, vilket är ett helt annat åtagande än att bara låta
            # bli att bocka i en ruta.
            if kol_ingen.button("Undanta alla (ingen maskering)"):
                for behov in unika:
                    st.session_state[f"beslut_namn_{behov.misstänkt_text}"] = (
                        BESLUT_INGEN_MASKERING
                    )
                st.rerun()

            beslut_per_namn: dict[str, dict] = {}
            for behov in unika:
                namn = behov.misstänkt_text
                beslut_nyckel = f"beslut_namn_{namn}"
                text_nyckel = f"override_namn_{namn}"
                if beslut_nyckel not in st.session_state:
                    # Default är AVVAKTA, inte "maskera": raden ska kräva ett
                    # aktivt mänskligt beslut för att försvinna ur listan.
                    # Avvakta blockerar fortsatt sändning, så defaulten läcker
                    # ingenting — den är bara ärlig om att inget beslutats än.
                    st.session_state[beslut_nyckel] = BESLUT_AVVAKTA
                if text_nyckel not in st.session_state:
                    st.session_state[text_nyckel] = namn

                antal = sum(1 for b in behov_lista if b.misstänkt_text == namn)
                st.markdown("---")
                st.caption(f"{antal} förekomst(er) · källa: {behov.träffkälla}")
                st.markdown(
                    markera_kanslig_text(_hitta_originaltext(sie, behov), namn),
                    unsafe_allow_html=True,
                )
                kol_val, kol_text = st.columns([2, 2])
                beslut = kol_val.radio(
                    "Beslut",
                    options=[BESLUT_AVVAKTA, BESLUT_MASKERA, BESLUT_INGEN_MASKERING],
                    format_func=_BESLUTSETIKETTER.get,
                    key=beslut_nyckel,
                )
                text = kol_text.text_input("Text att maskera", key=text_nyckel)
                beslut_per_namn[namn] = {"beslut": beslut, "text": text}

            if st.button("Tillämpa maskering"):
                granskade = bygg_granskade_behov_per_namn(behov_lista, beslut_per_namn)
                nytt_resultat = uppdatera_efter_granskning(maskeringsresultat, granskade)
                st.session_state.maskeringsresultat = nytt_resultat

                # Lär in bekräftade namn i den KRYPTERADE maskeringsliggaren + global
                # sök-och-ersätt i sessionens sie, så namnen förblir maskerade i alla
                # framtida filer/sessioner. Ej-PII-namn lärs aldrig in.
                bekräftade = {g.misstänkt_text for g in granskade if g.status == "bekräftad_pii"}
                if bekräftade:
                    liggare = dict(st.session_state.maskeringsliggare)
                    for namn in sorted(bekräftade):
                        if namn not in liggare:
                            liggare[namn] = f"[PERSON {len(liggare) + 1}]"
                    app_config.spara_maskeringsliggare(liggare)
                    st.session_state.maskeringsliggare = liggare
                    st.session_state.sie = tillämpa_liggare(st.session_state.sie, liggare)

                # Spegelbilden: namn användaren aktivt markerat som "ingen
                # maskering" läggs i den krypterade undantagslistan, så
                # sekretesslagret slutar flagga dem i nya filer och sessioner.
                undantagna = namn_att_undanta(granskade)
                if undantagna:
                    kvar = app_config.lagg_till_undantag(
                        st.session_state.undantagslista, sorted(undantagna)
                    )
                    app_config.spara_undantagslista(kvar)
                    st.session_state.undantagslista = kvar

                # Kom ihåg de nu sändningsbara verifikaten (Spiris-läge) så de inte
                # tas med vid nästa hämtning — blockerade sparas INTE (fail-closed).
                # Fingeravtrycket (svaghet 5) måste räknas på SAMMA representation
                # som filtrera_bort_sedda ser vid nästa hämtning: den råa
                # st.session_state.sie, inte de maskerade sandningsbara. Annars
                # skulle personnummer/fritext skilja sig (maskerad vs rå) och inget
                # matcha. Vi väljer bara de verifikat vars (serie, vernr) blev
                # sändningsbara.
                if datakälla == "Koppla till Spiris" and st.session_state.sie is not None:
                    _sandningsbar_nycklar = {
                        (v.serie, v.vernr)
                        for v in nytt_resultat.sandningsbara_verifikationer
                    }
                    lagg_till_maskeringsminne(
                        verifikation_id(v)
                        for v in st.session_state.sie.verifikationer
                        if (v.serie, v.vernr) in _sandningsbar_nycklar
                    )
                st.success(
                    f"{len(bekräftade)} namn maskerade, {len(undantagna)} undantagna — "
                    "Datastatus, Rapporter och AI-Assistent uppdateras utifrån dem."
                )
                st.rerun()

        st.divider()
        st.subheader("Verifikationsavvikelser")
        if not avvikelser:
            st.caption(
                "Inga obehandlade avvikelser. Avvikelseregeln är ännu inte byggd "
                "(navigering.hitta_verifikationsavvikelser) — listan är därför tom, "
                "inte grönmålad."
            )
        else:
            st.dataframe(
                [
                    {"Plats": avvikelse.plats, "Beskrivning": avvikelse.beskrivning}
                    for avvikelse in avvikelser
                ],
                hide_index=True,
            )



def rendera_pengar_in() -> None:
    st.header("📥 Pengar in")
    if not st.session_state.get("spiris_kundreskontra") and not st.session_state.get("sie"):
        tomt_lage(st, hamta("kundreskontra"), "Reskontra")
        return
        
    snabbvy_render.injicera_snabbvy_css(st)
    vydata = snabbvyer.Vydata(
        idag=datetime.date.today(),
        kundreskontra=st.session_state.spiris_kundreskontra,
        leverantorsreskontra=st.session_state.spiris_reskontra,
        kundbetalbeteende=st.session_state.get("rapportunderlag").kundbetalbeteende if st.session_state.get("rapportunderlag") else {},
        formateringsval=hamta_val(),
    )
    snabbvy_render.rendera_snabbvyfalt(st, snabbvyer.SNABBVYER_KUND, "snabbvy_pengar_in", vydata)
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK, SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD
        for f in [FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK, SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD]:
            rendera_atgardsformular(st, f)

def rendera_pengar_ut() -> None:
    st.header("📤 Pengar ut")
    if not st.session_state.get("spiris_reskontra") and not st.session_state.get("sie"):
        tomt_lage(st, hamta("leverantorsreskontra"), "Reskontra")
        return
        
    snabbvy_render.injicera_snabbvy_css(st)
    vydata = snabbvyer.Vydata(
        idag=datetime.date.today(),
        kundreskontra=st.session_state.spiris_kundreskontra,
        leverantorsreskontra=st.session_state.spiris_reskontra,
        kundbetalbeteende=st.session_state.get("rapportunderlag").kundbetalbeteende if st.session_state.get("rapportunderlag") else {},
        formateringsval=hamta_val(),
    )
    snabbvy_render.rendera_snabbvyfalt(st, snabbvyer.SNABBVYER_LEVERANTOR, "snabbvy_pengar_ut", vydata)
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST
        for f in [LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST]:
            rendera_atgardsformular(st, f)

def rendera_bockerna() -> None:
    st.header("📚 Böckerna")
    
    sie = st.session_state.get("sie")
    if sie is None:
        tomt_lage(st, hamta("bokforing"), "Bokföring")
        return
        
    if "bockerna_kontoplan" not in st.session_state:
        klient = None
        if st.session_state.get("spiris_tokens"):
            try:
                # App config laddas en gång per request och är oföränderlig
                cfg = app_config.las_config()
                klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
            except Exception:
                pass
        import app_tillstand
        app_tillstand.ladda_bockerna_data(st, klient)

    soktext = st.text_input("Sök i verifikationer", value="", placeholder="Sök på verifikattext eller transaktionstext...")
    
    snabbvy_render.injicera_snabbvy_css(st)

    vasentlighet_data = None
    kontotyp_avvikelser_data = None
    if sie:
        from vasentlighet import berakna_vasentlighet
        from kontotyp_vakt import analysera_kontotyper
        try:
            vasentlighet_data = berakna_vasentlighet(sie)
        except Exception:
            pass
        try:
            kontotyp_avvikelser_data = analysera_kontotyper(sie)
        except Exception:
            pass

    vydata = snabbvyer.Vydata(
        vasentlighet=vasentlighet_data,
        kontotyp_avvikelser=kontotyp_avvikelser_data,
        idag=date.today(),
        formateringsval=hamta_val(),
        kontoplan=st.session_state.get("bockerna_kontoplan"),
        kontosaldon=st.session_state.get("bockerna_kontosaldon"),
        verifikationer=st.session_state.get("bockerna_verifikationer"),
        verifikatutkast=st.session_state.get("bockerna_verifikatutkast"),
        momsoversikt=st.session_state.get("bockerna_momsoversikt"),
        soktext=soktext,
    )
    
    snabbvy_render.rendera_snabbvyfalt(
        st, snabbvyer.SNABBVYER_BOCKERNA, "snabbvy_bockerna", vydata
    )
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import VERIFIKAT, SIE4IMPORT
        for f in [VERIFIKAT, SIE4IMPORT]:
            rendera_atgardsformular(st, f)

def rendera_rapporter() -> None:
    st.header("📊 Rapporter & analys")

    # Kund-/leverantörssnabbvyerna flyttade till Pengar in/Pengar ut (se
    # rendera_pengar_in/rendera_pengar_ut) — den här sidan är renodlad till
    # de färdigbyggda FP&A-rapporterna (resultat/balans/nyckeltal/kassaflöde),
    # samma dict-källa som Investeringskalkyl-sidan använder.
    rapportunderlag = st.session_state.get("rapportunderlag")
    if not rapportunderlag or not rapportunderlag.rapporter:
        st.info("Ladda in data i sidomenyn för att se finansiella rapporter.")
        return

    fpa_dashboard.rendera_rapporter(
        rapportunderlag.rapporter["resultat"],
        rapportunderlag.rapporter["balans"],
        rapportunderlag.rapporter["nyckeltal"],
        rapportunderlag.rapporter["kassaflode"],
        rapportunderlag.likviditetsprognos,
    )


def rendera_investeringskalkyl() -> None:
    st.header("📈 Investeringskalkyl")
    rapporter = st.session_state.get("rapportunderlag")
    if not rapporter or not rapporter.rapporter:
        tomt_lage(st, hamta("investeringskalkyl"), "Investeringskalkyl")
        return
        
    fpa_dashboard.rendera_investeringskalkyl(
        rapporter.rapporter["resultat"],
                rapporter.rapporter["balans"],
    )

def rendera_juridik() -> None:
    st.header("⚖️ Juridik & Skatt")
    st.markdown("Här pratar du med en AI som är låst till att söka i Svensk Författningssamling (SFS) och Skatteverkets vägledning. Inga gissningar, bara lag.")
    
    col1, col2, col3 = st.columns(3)
    if col1.button("Regler för leasing"):
        st.session_state.juridik_prompt = "Vilka regler gäller för bokföring av finansiell leasing (K2/K3)?"
    if col2.button("Moms på julbord"):
        st.session_state.juridik_prompt = "Hur mycket moms får jag dra av för representation och julbord?"
    if col3.button("Utdelningsutrymme"):
        st.session_state.juridik_prompt = "Vad säger Aktiebolagslagen om försiktighetsregeln vid utdelning?"

    if "juridik_samtal" not in st.session_state:
        st.session_state.juridik_samtal = []

    for msg in st.session_state.juridik_samtal:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    ny_fraga = st.chat_input("Din fråga till skattejuristen...")
    
    if "juridik_prompt" in st.session_state and st.session_state.juridik_prompt:
        ny_fraga = st.session_state.juridik_prompt
        st.session_state.juridik_prompt = None

    if ny_fraga:
        with st.chat_message("user"):
            st.markdown(ny_fraga)
        st.session_state.juridik_samtal.append({"role": "user", "content": ny_fraga})
        
        with st.chat_message("assistant"):
            with st.spinner("Slår upp i lagboken..."):
                konf = st.session_state.get("ai_konfiguration")
                if not konf or konf.leverantör != "Anthropic" or not konf.api_nyckel:
                    st.error("Detta rum kräver att Anthropic (Claude) är vald och att API-nyckel är inlagd i inställningarna.")
                else:
                    from juridik_chatt import kora_juridik_chatt
                    svar = kora_juridik_chatt(
                        st.session_state.juridik_samtal, 
                        konf.api_nyckel, 
                        konf.vald_modell or "claude-3-5-sonnet-20240620"
                    )
                    st.markdown(svar)
                    st.session_state.juridik_samtal.append({"role": "assistant", "content": svar})

def rendera_foretags_chatt() -> None:
    st.header("💬 Företagsdata")
    st.markdown("Här pratar du med en pedagogisk assistent som analyserar din uppladdade data. Du kan ändra svarsstil ovanför.")
    
    sie = st.session_state.get("sie")
    if not sie:
        tomt_lage(st, hamta("kund"), "Företagsdata")
        return
        
    from assistent import rendera_panel, AssistentKontext
    kontext = AssistentKontext(
        sie=sie,
        maskeringsresultat=st.session_state.get("maskeringsresultat")
    )
    
    rendera_panel(st, "foretag_chatt", kontext, som_expander=False)

def rendera_bank() -> None:
    st.header("🏦 Bank")
    
    sie = st.session_state.get("sie")
    if not sie:
        tomt_lage(st, hamta("bankkonto"), "Bank")
        return
        
    if "bankkonton" not in st.session_state:
        klient = None
        if st.session_state.get("spiris_tokens"):
            try:
                cfg = app_config.las_config()
                klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
            except Exception:
                pass
        import app_tillstand
        app_tillstand.ladda_bank_data(st, klient)

    bankkonton = st.session_state.get("bankkonton", [])
    bankkonto_options = [k.get("namn") or k.get("bas_konto") for k in (bankkonton or []) if k.get("bas_konto")]
    valt_konto = ""
    if bankkonto_options:
        valt_konto = st.selectbox("Välj bankkonto för att se händelser", [""] + bankkonto_options)
        
    bankhandelser = None
    if valt_konto:
        konto_id = next((k.get("id") for k in bankkonton if (k.get("namn") or k.get("bas_konto")) == valt_konto), None)
        if konto_id:
            klient = None
            if st.session_state.get("spiris_tokens"):
                try:
                    cfg = app_config.las_config()
                    klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
                except Exception:
                    pass
            if klient:
                from spiris_adapter import hamta_bankhandelser
                try:
                    bankhandelser = hamta_bankhandelser(klient, konto_id)
                except Exception:
                    pass

    snabbvy_render.injicera_snabbvy_css(st)

    vasentlighet_data = None
    kontotyp_avvikelser_data = None
    if sie:
        from vasentlighet import berakna_vasentlighet
        from kontotyp_vakt import analysera_kontotyper
        try:
            vasentlighet_data = berakna_vasentlighet(sie)
        except Exception:
            pass
        try:
            kontotyp_avvikelser_data = analysera_kontotyper(sie)
        except Exception:
            pass

    vydata = snabbvyer.Vydata(
        vasentlighet=vasentlighet_data,
        kontotyp_avvikelser=kontotyp_avvikelser_data,
        idag=date.today(),
        formateringsval=hamta_val(),
        bankkonton=st.session_state.get("bankkonton"),
        avstamningslage=st.session_state.get("avstamningslage"),
        bankhandelser=bankhandelser,
        bankkonto_id=valt_konto,
    )

    snabbvy_render.rendera_snabbvyfalt(
        st, snabbvyer.SNABBVYER_BANK, "snabbvy_bank", vydata
    )


def rendera_register() -> None:
    st.header("📇 Register")
    
    sie = st.session_state.get("sie")
    har_spiris = bool(st.session_state.get("spiris_tokens"))
    if not sie and not har_spiris:
        tomt_lage(st, hamta("kund"), "Register")
        return

    # Hämta registerdata från Spiris en gång per session (när nyckeln saknas).
    # OBS: Rensa INTE cachen vid None/[] — det skapar en oändlig loop om
    # API-hämtningen misslyckas (fel sätter None → rensas → hämtas → fel → ...).
    # Användaren kan manuellt ladda om sidan för att tvinga en ny hämtning.
    if "kunder" not in st.session_state:
        klient = None
        if har_spiris:
            try:
                cfg = app_config.las_config()
                klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
            except Exception as e:
                import logging
                logging.error(f"Kunde inte bygga klient för register: {repr(e)}")
                st.error(f"🔑 Kunde inte ansluta till Spiris för att hämta register: {e}")
        import app_tillstand
        app_tillstand.ladda_register_data(st, klient)

    # Fakturadata för drill-down — hämtas separat och cachas en gång per session.
    # Hanteras med try/except så att ett API-fel aldrig blockerar registervisningen.
    if "register_leverantorsfakturor" not in st.session_state and har_spiris:
        try:
            cfg = app_config.las_config()
            klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
            from spiris_adapter import hamta_leverantorsfakturor, hamta_kundfakturor
            try:
                st.session_state.register_leverantorsfakturor = hamta_leverantorsfakturor(klient)
            except Exception:
                st.session_state.register_leverantorsfakturor = None
            try:
                st.session_state.register_kundfakturor = hamta_kundfakturor(klient)
            except Exception:
                st.session_state.register_kundfakturor = None
        except Exception:
            st.session_state.register_leverantorsfakturor = None
            st.session_state.register_kundfakturor = None

    referens_typer = [
        "enheter", "valutor", "betalningsvillkor", "leveranssatt", 
        "leveransvillkor", "lander", "kontotyper", "momssatser"
    ]
    vald_typ = st.selectbox("Välj referensdata", [""] + referens_typer)
    
    referensdata = None
    if vald_typ:
        klient = None
        if st.session_state.get("spiris_tokens"):
            try:
                cfg = app_config.las_config()
                klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
            except Exception:
                pass
        if klient:
            from spiris_adapter import hamta_referensdata
            try:
                referensdata = hamta_referensdata(klient, vald_typ)
            except Exception:
                pass

    # Knapp för att manuellt ladda om registerdata från Spiris (t.ex. vid API-fel)
    if st.session_state.get("spiris_tokens") and st.session_state.get("kunder") is None:
        if st.button("🔄 Ladda om register från Spiris", key="ladda_om_register"):
            for nyckel in ["kunder", "leverantorer", "artiklar", "projekt", "kostnadsstallen"]:
                st.session_state.pop(nyckel, None)
            st.rerun()

    snabbvy_render.injicera_snabbvy_css(st)

    vasentlighet_data = None
    kontotyp_avvikelser_data = None
    if sie:
        from vasentlighet import berakna_vasentlighet
        from kontotyp_vakt import analysera_kontotyper
        try:
            vasentlighet_data = berakna_vasentlighet(sie)
        except Exception:
            pass
        try:
            kontotyp_avvikelser_data = analysera_kontotyper(sie)
        except Exception:
            pass

    vydata = snabbvyer.Vydata(
        vasentlighet=vasentlighet_data,
        kontotyp_avvikelser=kontotyp_avvikelser_data,
        idag=date.today(),
        formateringsval=hamta_val(),
        kunder=st.session_state.get("kunder"),
        leverantorer=st.session_state.get("leverantorer"),
        artiklar=st.session_state.get("artiklar"),
        projekt=st.session_state.get("projekt"),
        kostnadsstallen=st.session_state.get("kostnadsstallen"),
        referensdata=referensdata,
        vald_referenstyp=vald_typ,
        leverantorsfakturor=st.session_state.get("register_leverantorsfakturor"),
        kundfakturor=st.session_state.get("register_kundfakturor"),
    )
    
    snabbvy_render.rendera_snabbvyfalt(
        st, snabbvyer.SNABBVYER_REGISTER, "snabbvy_register", vydata
    )
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import MASTERDATAANDRING, MASTERDATABORTTAGNING
        for f in [MASTERDATAANDRING, MASTERDATABORTTAGNING]:
            rendera_atgardsformular(st, f)

def rendera_atgardsformular(st, formular) -> None:
    st.subheader(f"{formular.ikon} {formular.rubrik}")
    
    varden = {}
    falt_att_rendera = list(formular.falt)
    
    if formular.utkasttyp == "masterdataandring":
        objtyp_falt = next(f for f in falt_att_rendera if f.nyckel == "objekttyp")
        falt_att_rendera.remove(objtyp_falt)
        vald_typ = st.selectbox(objtyp_falt.etikett, objtyp_falt.alternativ, key=f"objtyp_{formular.utkasttyp}")
        varden["objekttyp"] = vald_typ
        
        st.caption("Bara fälten nedan går att ändra härifrån. Kontaktuppgifter, adresser och betalningsuppgifter bevaras oförändrade men visas inte — de hämtas aldrig hit.")
        
        from spiris_adapter import _MASTERDATA
        if vald_typ in _MASTERDATA:
            _, falt_map = _MASTERDATA[vald_typ]
            from atgardsformular import Falt
            for f_key, f_name in falt_map.items():
                if f_key in ["aktiv", "omvand_byggmoms"]:
                    falt_att_rendera.append(Falt(f_key, f_name, "kryss", obligatoriskt=False))
                elif f_key in ["pris"]:
                    falt_att_rendera.append(Falt(f_key, f_name, "tal", obligatoriskt=False))
                elif f_key in ["startdatum", "slutdatum"]:
                    falt_att_rendera.append(Falt(f_key, f_name, "datum", obligatoriskt=False))
                else:
                    falt_att_rendera.append(Falt(f_key, f_name, "text", obligatoriskt=False))

    elif formular.utkasttyp == "saljdokumentatgard":
        objtyp_falt = next(f for f in falt_att_rendera if f.nyckel == "dokumenttyp")
        falt_att_rendera.remove(objtyp_falt)
        vald_typ = st.selectbox(objtyp_falt.etikett, objtyp_falt.alternativ, key=f"objtyp_{formular.utkasttyp}")
        varden["dokumenttyp"] = vald_typ
        
        atg_falt = next(f for f in falt_att_rendera if f.nyckel == "atgard")
        falt_att_rendera.remove(atg_falt)
        from spiris_adapter import _SALJDOKUMENTATGARDER
        giltiga_atgarder = [k[1] for k in _SALJDOKUMENTATGARDER.keys() if k[0] == vald_typ]
        vald_atg = st.selectbox(atg_falt.etikett, sorted(set(giltiga_atgarder)), key=f"atg_{formular.utkasttyp}")
        varden["atgard"] = vald_atg

    with st.form(f"form_{formular.utkasttyp}", clear_on_submit=True):
        if formular.varning:
            st.error(formular.varning)
            
        for f in falt_att_rendera:
            lbl = f"{f.etikett} *" if f.obligatoriskt else f.etikett
            if f.typ == "text":
                varden[f.nyckel] = st.text_input(lbl, help=f.hjalptext)
            elif f.typ == "tal":
                varden[f.nyckel] = st.text_input(lbl, help=f.hjalptext)
            elif f.typ == "datum":
                varden[f.nyckel] = st.text_input(f"{lbl} (ÅÅÅÅ-MM-DD)", help=f.hjalptext)
            elif f.typ == "kryss":
                varden[f.nyckel] = st.checkbox(f.etikett, help=f.hjalptext)
            elif f.typ == "val":
                varden[f.nyckel] = st.selectbox(lbl, f.alternativ, help=f.hjalptext)

        submitted = st.form_submit_button("Skapa utkast")
        
    if submitted:
        saknas = [f.etikett for f in falt_att_rendera if f.obligatoriskt and not str(varden.get(f.nyckel, "")).strip() and f.typ != "kryss"]
        if saknas:
            st.error(f"Följande fält är obligatoriska: {', '.join(saknas)}")
            return
            
        try:
            nyttolast = formular.bygg_nyttolast(varden)
            sammanfattning = formular.bygg_sammanfattning(varden)
            import utkast
            utkast.skapa(formular.utkasttyp, nyttolast, sammanfattning)
            st.success("Förslaget ligger nu i **Beslut**. Ingenting har skickats förrän du godkänner det där.")
        except Exception as e:
            st.error(f"Ett fel uppstod: {e}")

def rendera_data() -> None:
    st.header("🔄 Data in/ut")
    from parser.kalla_vy import rendera_anslutning
    rendera_anslutning()
    
    st.divider()
    st.subheader("Exportera till SIE4")
    st.caption("Exportera all bokföring från Spiris till en lokal SIE4-fil.")
    
    with st.form("sie4_export_form"):
        col1, col2 = st.columns(2)
        f_fran = col1.date_input("Från datum", key="export_fran")
        f_till = col2.date_input("Till datum", key="export_till")
        
        # Detta är den ENDA skrivande knappen i hela UI-arbetet som INTE går via
        # utkastkön - och det är korrekt, eftersom en export inte ändrar något i
        # affärssystemet. Den läser.
        export_btn = st.form_submit_button("Exportera")
        
    if export_btn:
        klient = None
        try:
            import app_config
            cfg = app_config.las_config()
            klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
        except Exception:
            st.error("Du måste vara ansluten till Spiris för att kunna exportera.")
            
        if klient:
            with st.spinner("Exporterar..."):
                try:
                    from parser.spiris_adapter import ladda_ner_sie4export
                    filnamn, sokvag, storlek, p_fran, p_till = ladda_ner_sie4export(
                        klient, f_fran.isoformat(), f_till.isoformat()
                    )
                    st.success("Export slutförd!")
                    st.write(f"**Filnamn:** {filnamn}")
                    st.write(f"**Storlek:** {storlek} bytes")
                    st.write(f"**Period:** {p_fran} till {p_till}")
                    st.write(f"**Sökväg:** {sokvag}")
                    
                    st.info("Filen innehåller hela bokföringen i klartext, inklusive alla motpartsnamn. Den ligger lokalt på din dator och har inte skickats någonstans.")
                    
                    st.caption("⚠️ Exporten saknar #KTYP. (Konton kommer utan kontotyp i Spiris-exporten)")
                    
                    with open(sokvag, "rb") as f:
                        st.download_button("Ladda ner filen", f, file_name=filnamn, mime="text/plain")
                        
                except Exception as e:
                    st.error(f"Kunde inte exportera: {e}")
