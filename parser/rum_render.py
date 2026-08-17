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
                källa = "📚 tidigare mönster" if rad.kall_ur_minne else "AI-förslag (konteringsmotorn)"
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
        
        if "oversikt_filter" not in st.session_state:
            st.session_state.oversikt_filter = "alla"

        kol1, kol2, kol3, kol4, kol5, kol6 = st.columns(6)
        with kol1:
            st.metric("Verifikationer", översikt.antal_verifikationer)
            if st.button(f"🔍 Visa ({översikt.antal_verifikationer})", key="btn_ov_ver"):
                st.session_state.oversikt_filter = "verifikationer"
                st.rerun()
        with kol2:
            st.metric("Tolkningsbehov", översikt.antal_tolkningsbehov)
            if st.button(f"🔍 Visa ({översikt.antal_tolkningsbehov})", key="btn_ov_tolk"):
                st.session_state.oversikt_filter = "tolkningsbehov"
                st.rerun()
        with kol3:
            st.metric("Maskeringsbehov", översikt.antal_maskeringsbehov)
            if st.button(f"🔍 Visa ({översikt.antal_maskeringsbehov})", key="btn_ov_mask"):
                st.session_state.oversikt_filter = "maskeringsbehov"
                st.rerun()
        with kol4:
            st.metric("Sändningsbara ver.", översikt.antal_sandningsbara_verifikationer)
            if st.button(f"🔍 Visa ({översikt.antal_sandningsbara_verifikationer})", key="btn_ov_sand"):
                st.session_state.oversikt_filter = "sandningsbara"
                st.rerun()
        with kol5:
            st.metric("Blockerade ver.", översikt.antal_blockerade_verifikationer)
            if st.button(f"🔍 Visa ({översikt.antal_blockerade_verifikationer})", key="btn_ov_block"):
                st.session_state.oversikt_filter = "blockerade"
                st.rerun()
        with kol6:
            st.metric("Prosa sändningsbar", översikt.prosa_sandningsbar)
            if st.button("📋 Visa alla", key="btn_ov_alla"):
                st.session_state.oversikt_filter = "alla"
                st.rerun()

        ov_filter = st.session_state.oversikt_filter

        if ov_filter in ("alla", "tolkningsbehov"):
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

        if ov_filter in ("alla", "sandningsbara", "verifikationer"):
            st.divider()
            st.subheader("Sändningsbara verifikationer")
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

        if ov_filter in ("alla", "blockerade") and ov_filter == "blockerade":
            st.divider()
            st.subheader("Blockerade verifikationer")
            blockerade = [
                v for v in sie.verifikationer
                if v not in maskeringsresultat.sandningsbara_verifikationer
            ]
            if blockerade:
                st.dataframe([verifikation_till_visningsrad(v) for v in blockerade])
            else:
                st.write("Inga blockerade verifikationer.")


# --- Flik: 🔴/🟢 Åtgärder ------------------------------------------------------
# Alla aktiva human-in-the-loop-uppgifter. Badgen ovan speglar exakt innehållet
# här: maskeringsbehov som väntar på beslut + obehandlade verifikationsavvikelser.


def _analysera_kontoperioder(sie: Any, kontonr: str) -> list[dict[str, Any]]:
    """Analyserar månad för månad när verifikationstransaktioner och saldon registrerats."""
    from collections import defaultdict
    manader = defaultdict(lambda: {"ver_belopp": Decimal("0"), "antal_ver": 0, "ps_belopp": Decimal("0")})
    
    # 1. Verifikationsrörelser per månad
    for v in getattr(sie, "verifikationer", []):
        if not getattr(v, "verdatum", None):
            continue
        m_key = v.verdatum.strftime("%Y-%m")
        for t in getattr(v, "transaktioner", []):
            if t.kontonr == kontonr:
                manader[m_key]["ver_belopp"] += t.belopp
                manader[m_key]["antal_ver"] += 1

    # 2. Periodsaldon om det finns i SIE-filen
    for ps in getattr(sie, "periodsaldon", []):
        if ps.kontonr == kontonr and ps.årsnr == 0:
            p_str = str(ps.period)
            if len(p_str) == 6:
                m_key = f"{p_str[:4]}-{p_str[4:]}"
            else:
                m_key = p_str
            manader[m_key]["ps_belopp"] += ps.saldo

    if not manader:
        return []

    rader = []
    for m in sorted(manader.keys()):
        d = manader[m]
        diff = d["ps_belopp"] - d["ver_belopp"] if d["ps_belopp"] != Decimal("0") else None
        status = "🔴 Avvikelse" if (diff is not None and abs(diff) > Decimal("1.00")) else ("✅ Matchar" if diff is not None else "ℹ️ Bokfört")
        rader.append({
            "Månad / Period": m,
            "Bokfört i verifikationer": f"{d['ver_belopp']:,.2f} kr".replace(",", " ").replace(".", ","),
            "Antal verifikat": d["antal_ver"],
            "Periodsaldo (huvudbok)": f"{d['ps_belopp']:,.2f} kr".replace(",", " ").replace(".", ",") if d["ps_belopp"] != Decimal("0") else "—",
            "Månadsdiff": f"{diff:,.2f} kr".replace(",", " ").replace(".", ",") if diff is not None else "—",
            "Status": status,
        })
    return rader


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
        if "atgard_filter" not in st.session_state:
            st.session_state.atgard_filter = "alla"

        kol_mask, kol_avv, kol_utk, kol_tot = st.columns(4)
        with kol_mask:
            st.metric("Maskeringsbehov", atgardsstatus.antal_maskeringsbehov)
            if st.button(f"🔍 Granska maskering ({atgardsstatus.antal_maskeringsbehov})", key="btn_filt_mask"):
                st.session_state.atgard_filter = "maskering"
                st.rerun()

        with kol_avv:
            st.metric("Verifikationsavvikelser", atgardsstatus.antal_verifikationsavvikelser)
            if st.button(f"🔍 Granska avvikelser ({atgardsstatus.antal_verifikationsavvikelser})", key="btn_filt_avv"):
                st.session_state.atgard_filter = "avvikelser"
                st.rerun()

        with kol_utk:
            st.metric("Utkast i kön", len(vantande_utkast))
            if st.button(f"🔍 Granska utkast ({len(vantande_utkast)})", key="btn_filt_utk"):
                st.session_state.atgard_filter = "utkast"
                st.rerun()

        with kol_tot:
            st.metric("Totalt att åtgärda", atgardsstatus.antal_totalt)
            if st.button("📋 Visa alla delar", key="btn_filt_alla"):
                st.session_state.atgard_filter = "alla"
                st.rerun()

        aktivt_filter = st.session_state.atgard_filter

        if not atgardsstatus.kräver_åtgärd:
            st.success("🟢 Inget väntar på handläggning.")

        if aktivt_filter in ("alla", "maskering"):
            st.divider()
            st.subheader("🛡️ Maskeringsbehov (human-in-the-loop)")
            behov_lista = obeslutade_behov(maskeringsresultat.maskeringsbehov)
            if not behov_lista:
                st.write("Inga maskeringsbehov (kända namn maskeras redan automatiskt).")
            else:
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

                kol_alla, kol_ingen = st.columns(2)
                if kol_alla.button("Maskera alla"):
                    for behov in unika:
                        st.session_state[f"beslut_namn_{behov.misstänkt_text}"] = BESLUT_MASKERA
                    st.rerun()
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

                    bekräftade = {g.misstänkt_text for g in granskade if g.status == "bekräftad_pii"}
                    if bekräftade:
                        liggare = dict(st.session_state.maskeringsliggare)
                        for namn in sorted(bekräftade):
                            if namn not in liggare:
                                liggare[namn] = f"[PERSON {len(liggare) + 1}]"
                        app_config.spara_maskeringsliggare(liggare)
                        st.session_state.maskeringsliggare = liggare
                        st.session_state.sie = tillämpa_liggare(st.session_state.sie, liggare)

                    undantagna = namn_att_undanta(granskade)
                    if undantagna:
                        kvar = app_config.lagg_till_undantag(
                            st.session_state.undantagslista, sorted(undantagna)
                        )
                        app_config.spara_undantagslista(kvar)
                        st.session_state.undantagslista = kvar

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

        if aktivt_filter in ("alla", "avvikelser"):
            st.divider()
            st.subheader("⚠️ Verifikationsavvikelser & Bokslutskontroll (Lager 1)")
            
            # Hämta fullständiga fyndobjekt från motorn
            fynd_lista = []
            try:
                from bokslutskontroll import kor_kontroller
                fynd_lista = [f for f in kor_kontroller(sie, idag=date.today()) if f.allvarlighet == "avvikelse"]
            except Exception:
                fynd_lista = []

            if not fynd_lista and not avvikelser:
                st.caption("Inga obehandlade avvikelser.")
            else:
                st.write(f"Hittade **{len(fynd_lista) or len(avvikelser)}** avvikelser som kräver granskning eller rättelse. Klicka på valfri avvikelse för att granska underliggande verifikationer, konton och regelhänvisningar:")
                
                if fynd_lista:
                    for i, fynd in enumerate(fynd_lista, 1):
                        with st.expander(f"🔴 [{fynd.kontroll_id}] {fynd.rubrik}", expanded=(i <= 3)):
                            st.markdown(f"**Motivering / Analys:** {fynd.motivering}")
                            
                            if fynd.belopp is not None:
                                st.markdown(f"**Berört belopp:** `{formatera_kr(fynd.belopp)}`")
                            
                            # Berörda konton
                            if fynd.konton:
                                st.markdown("**Berörda konton:**")
                                konto_rader = []
                                for knr in fynd.konton:
                                    kobj = sie.konton.get(knr) if hasattr(sie, "konton") and isinstance(sie.konton, dict) else None
                                    knamn = getattr(kobj, "namn", getattr(kobj, "kontonamn", "—")) if kobj else "—"
                                    ktyp = getattr(kobj, "typ", getattr(kobj, "kontotyp", "—")) if kobj else "—"
                                    konto_rader.append({"Kontonr": knr, "Kontonamn": knamn, "Typ": ktyp})
                                st.dataframe(konto_rader, hide_index=True)

                                # Månadsavstämning / Tidslinje över när rörelser och differenser uppstod
                                for knr in fynd.konton:
                                    period_rader = _analysera_kontoperioder(sie, knr)
                                    if period_rader:
                                        st.markdown(f"**📅 Månadsavstämning & Tidslinje (Konto {knr}):**")
                                        st.dataframe(period_rader, hide_index=True)

                            # Berörda verifikationer med detaljerade transaktioner
                            if fynd.verifikationer:
                                st.markdown("**Berörda verifikationer & transaktioner:**")
                                for v_str in fynd.verifikationer:
                                    # v_str är t.ex. "A/1" eller "A 1"
                                    parts = v_str.replace("/", " ").split()
                                    v_serie = parts[0] if parts else ""
                                    v_nr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                                    
                                    # Slå upp verifikatet i sie
                                    match_ver = next(
                                        (v for v in sie.verifikationer if v.serie == v_serie and v.vernr == v_nr),
                                        None
                                    )
                                    if match_ver:
                                        st.caption(f"Verifikat **{match_ver.serie} {match_ver.vernr}** ({match_ver.verdatum}) — *{match_ver.vertext or 'Ingen text'}*")
                                        trans_rader = []
                                        for t in match_ver.transaktioner:
                                            kobj = sie.konton.get(t.kontonr) if hasattr(sie, "konton") and isinstance(sie.konton, dict) else None
                                            knamn = getattr(kobj, "namn", getattr(kobj, "kontonamn", "")) if kobj else ""
                                            trans_rader.append({
                                                "Konto": f"{t.kontonr} {knamn}".strip(),
                                                "Belopp": f"{t.belopp:,.2f} kr".replace(",", " ").replace(".", ","),
                                                "Text": t.transtext or "",
                                            })
                                        st.dataframe(trans_rader, hide_index=True)
                                    else:
                                        st.caption(f"Verifikat-ID: **{v_str}**")

                            # Regelhänvisning
                            if fynd.regel:
                                st.markdown(f"**Regelhänvisning:** [{fynd.regel.kalla} {fynd.regel.beteckning}]({fynd.regel.lank_manniska})")

                            # Rättelseförslag
                            if fynd.forslag:
                                st.markdown(f"**💡 Rättelseförslag:** {fynd.forslag.beskrivning}")
                                if fynd.forslag.rader:
                                    st.dataframe(
                                        [
                                            {
                                                "Konto": r.kontonr,
                                                "Debet": f"{r.debet:,.2f} kr" if r.debet else "—",
                                                "Kredit": f"{r.kredit:,.2f} kr" if r.kredit else "—",
                                                "Text": r.text or "",
                                            }
                                            for r in fynd.forslag.rader
                                        ],
                                        hide_index=True,
                                    )
                                if fynd.forslag.forbehall:
                                    st.caption(f"⚠️ *Förbehåll:* {fynd.forslag.forbehall}")
                else:
                    for avvikelse in avvikelser:
                        with st.expander(f"🔴 {avvikelse.beskrivning}"):
                            st.write(f"**Plats:** {avvikelse.plats}")



def rendera_pengar_in() -> None:
    if st.session_state.get("aktivt_fakturautkast"):
        import app_config
        cfg = app_config.las_config()
        _rendera_fakturautkast(cfg.spiris_client_id, cfg.spiris_client_secret)
        return

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
        from atgardsformular import FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK
        for f in [FAKTURAUTSKICK, BETALNINGSPAMINNELSE, BETALNINGSREGISTRERING, MAKULERING, EFAKTURAUTSKICK]:
            rendera_atgardsformular(st, f)

def rendera_saljdokument() -> None:
    st.header("🧾 Säljdokument")
    import app_config
    cfg = app_config.las_config()
    klient = None
    if st.session_state.get("spiris_tokens"):
        try:
            klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
        except Exception:
            pass

    if "saljdokument_ordrar" not in st.session_state and klient:
        try:
            st.session_state.saljdokument_ordrar = spiris_adapter.hamta_order(klient)
        except Exception:
            pass
    if "saljdokument_offerter" not in st.session_state and klient:
        try:
            st.session_state.saljdokument_offerter = spiris_adapter.hamta_offerter(klient)
        except Exception:
            pass
    if "saljdokument_offertutkast" not in st.session_state and klient:
        try:
            st.session_state.saljdokument_offertutkast = spiris_adapter.hamta_offertutkast(klient)
        except Exception:
            pass

    snabbvy_render.injicera_snabbvy_css(st)
    vydata = snabbvyer.Vydata(
        idag=datetime.date.today(),
        formateringsval=hamta_val(),
        ordrar=st.session_state.get("saljdokument_ordrar"),
        offerter=st.session_state.get("saljdokument_offerter"),
        offertutkast=st.session_state.get("saljdokument_offertutkast"),
    )
    snabbvy_render.rendera_snabbvyfalt(st, snabbvyer.SNABBVYER_SALJDOKUMENT, "snabbvy_saljdokument", vydata)
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD, OFFERTUTKAST_FORMULAR
        for f in [SALJDOKUMENTUTSKICK, SALJDOKUMENTATGARD, OFFERTUTKAST_FORMULAR]:
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
        from atgardsformular import LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST, KVITTNING
        for f in [LEVERANTORSFAKTURAUTKAST, LEVERANTORSBETALNING, ATTEST, KVITTNING]:
            rendera_atgardsformular(st, f)

def rendera_bockerna() -> None:
    st.header("📚 Böckerna")
    
    sie = st.session_state.get("sie")
    if sie is None:
        tomt_lage(st, hamta("bokforing"), "Bokföring")
        return
        
    klient = None
    if st.session_state.get("spiris_tokens"):
        try:
            # App config laddas en gång per request och är oföränderlig
            cfg = app_config.las_config()
            klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
        except Exception:
            pass

    if "bockerna_kontoplan" not in st.session_state:
        import app_tillstand
        app_tillstand.ladda_bockerna_data(st, klient)

    if "bockerna_underlag" not in st.session_state and klient:
        try:
            st.session_state.bockerna_underlag = spiris_adapter.hamta_underlag(klient)
        except Exception:
            pass

    soktext = st.text_input("Sök i verifikationer", value="", placeholder="Sök på verifikattext eller transaktionstext...")
    col1, col2 = st.columns(2)
    kontonr_sok = col1.text_input("Kontonummer (för transaktionsvy)", value="", placeholder="T.ex. 1930")
    vernr_sok = col2.text_input("Verifikat-ID (för detaljvy)", value="", placeholder="T.ex. A 1")
    
    kontotransaktioner = None
    enskilt_verifikat = None
    if klient and st.session_state.get("spiris_hamtat_ar"):
        ar_id = st.session_state.get("spiris_hamtat_ar")
        if kontonr_sok:
            try:
                kontotransaktioner = spiris_adapter.hamta_kontotransaktioner(klient, ar_id, kontonr_sok)
            except Exception:
                pass
        if vernr_sok:
            try:
                enskilt_verifikat = spiris_adapter.hamta_en_verifikation(klient, ar_id, vernr_sok)
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
        kontoplan=st.session_state.get("bockerna_kontoplan"),
        kontosaldon=st.session_state.get("bockerna_kontosaldon"),
        verifikationer=st.session_state.get("bockerna_verifikationer"),
        verifikatutkast=st.session_state.get("bockerna_verifikatutkast"),
        momsoversikt=st.session_state.get("bockerna_momsoversikt"),
        ingaende_balanser=st.session_state.get("bockerna_ingaende_balanser"),
        kontotransaktioner=kontotransaktioner,
        verifikationer_alla=st.session_state.get("bockerna_verifikationer_alla"),
        enskilt_verifikat=enskilt_verifikat,
        periodiseringar=st.session_state.get("bockerna_periodiseringar"),
        kontoplan_alla=st.session_state.get("bockerna_kontoplan_alla"),
        momsrapporter=st.session_state.get("bockerna_momsrapporter"),
        momskoder=st.session_state.get("bockerna_momskoder"),
        soktext=soktext,
        underlag=st.session_state.get("bockerna_underlag"),
    )
    
    snabbvy_render.rendera_snabbvyfalt(
        st, snabbvyer.SNABBVYER_BOCKERNA, "snabbvy_bockerna", vydata
    )

    if st.session_state.get("snabbvy_bockerna") == "underlag":
        underlag_lista = st.session_state.get("bockerna_underlag") or []
        if underlag_lista:
            st.subheader("Ladda ner bilaga")
            valt_id = st.selectbox("Välj underlag", [u.get("id") for u in underlag_lista], format_func=lambda i: next((u.get("beskrivning") or u.get("id") for u in underlag_lista if u.get("id") == i), i))
            if valt_id and klient:
                if st.button("Hämta fil"):
                    try:
                        meta, fbytes = spiris_adapter.hamta_underlag_fil(klient, valt_id)
                        st.download_button("Ladda ner " + meta.get("filnamn", "bilaga"), data=fbytes, file_name=meta.get("filnamn", "bilaga.pdf"), mime=meta.get("mime", "application/pdf"))
                    except Exception as e:
                        st.error(f"Kunde inte ladda ner filen: {e}")
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import VERIFIKAT, SIE4IMPORT, PERIODISERING, UTKASTANDRING, UTKASTBORTTAGNING, UTKASTBOKFORING, UNDERLAGSKOPPLING, PERIODISERINGSANDRING, PERIODISERINGSBORTTAGNING
        for f in [VERIFIKAT, SIE4IMPORT, PERIODISERING, UTKASTANDRING, UTKASTBORTTAGNING, UTKASTBOKFORING, UNDERLAGSKOPPLING, PERIODISERINGSANDRING, PERIODISERINGSBORTTAGNING]:
            rendera_atgardsformular(st, f)


def rendera_bokslut() -> None:
    """Se hantverksbok/UI_ATGARDER_I_VYN.md §4. Byggd efter mönstret i
    rendera_bockerna: fyll Vydata, låt snabby_render sköta knapprad + resultat.

    U-2: motorn körs på den RÅA SIEFil:en — appen visar klartext, precis som
    resten av rummen (DATASKYDD.md §3). MCP-vägen (mcp_server/server.py:
    bokslutskontroll/spiris_bokslutskontroll) maskerar FÖRE motorn; det är den
    andra hälften av samma invariant (BOKSLUTSKONTROLLER.md I-3)."""
    st.header("🧮 Bokslut")

    sie = st.session_state.get("sie")
    if sie is None:
        tomt_lage(st, hamta("bokforing"), "Bokföring")
        return

    snabbvy_render.injicera_snabbvy_css(st)

    if "bokslut_fynd" not in st.session_state:
        from bokslutskontroll import kor_kontroller
        try:
            st.session_state.bokslut_fynd = kor_kontroller(sie, idag=date.today())
        except Exception:
            # Kastar aldrig vidare till ritlagret — men lämnar fynd=None
            # (U-4: "inte kört"), inte en tom lista som ser ut som rent bokslut.
            st.session_state.bokslut_fynd = None

    klient = None
    if st.session_state.get("spiris_tokens"):
        try:
            cfg = app_config.las_config()
            klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
        except Exception:
            pass

    if "bokslut_underlag" not in st.session_state:
        st.session_state.bokslut_underlag = None
        if klient:
            from spiris_adapter import hamta_underlag
            try:
                st.session_state.bokslut_underlag = hamta_underlag(klient)
            except Exception:
                pass

    vydata = snabbvyer.Vydata(
        idag=date.today(),
        formateringsval=hamta_val(),
        fynd=st.session_state.get("bokslut_fynd"),
        underlag=st.session_state.get("bokslut_underlag"),
    )

    if hasattr(st, "tabs"):
        tab_kontroll, tab_isa = st.tabs(["🔍 Bokslutskontroller", "📊 ISA 320/450 Väsentlighetsanalys"])

        with tab_kontroll:
            snabbvy_render.rendera_snabbvyfalt(
                st, snabbvyer.SNABBVYER_BOKSLUT, "snabbvy_bokslut", vydata
            )

        with tab_isa:
            from isa_render import rendera_isa_450
            rendera_isa_450(
                st,
                sie=sie,
                maskeringsresultat=st.session_state.get("maskeringsresultat"),
                ai_konfiguration=st.session_state.get("ai_konfiguration"),
            )
    else:
        snabbvy_render.rendera_snabbvyfalt(
            st, snabbvyer.SNABBVYER_BOKSLUT, "snabbvy_bokslut", vydata
        )


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
    st.header("⚖️ Juridik & myndighetsdata")
    st.markdown(
        "Här pratar du med en AI som bara får skriva sådant den faktiskt hittat "
        "hos en svensk myndighet — aldrig ur eget minne. Källorna spänner "
        "bredare än bara lagtext: Riksbanken, SCB, Skatteverket, Kronofogden, "
        "Kolada, TED, VIES, SMHI, Skolverket, Trafikanalys, Polisens händelser, "
        "JobTech och Sveriges dataportal, utöver 62 författningar i "
        "Svensk Författningssamling. Hittar den inget relevant säger den det, "
        "i stället för att gissa."
    )

    col1, col2, col3 = st.columns(3)
    if col1.button("Regler för leasing"):
        st.session_state.juridik_prompt = "Vilka regler gäller för bokföring av finansiell leasing (K2/K3)?"
    if col2.button("Moms på julbord"):
        st.session_state.juridik_prompt = "Hur mycket moms får jag dra av för representation och julbord?"
    if col3.button("Riksbankens referensränta"):
        st.session_state.juridik_prompt = "Vad är Riksbankens referensränta just nu?"

    if "juridik_samtal" not in st.session_state:
        st.session_state.juridik_samtal = []

    for msg in st.session_state.juridik_samtal:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("kallor"):
                with st.expander(f"{len(msg['kallor'])} källor"):
                    for k in msg["kallor"]:
                        rad = f"**[{k['nr']}] {k['etikett']}** — {k['myndighet']}"
                        if k.get("period"):
                            rad += f" ({k['period']})"
                        st.markdown(f"{rad}  \n[{k['lank']}]({k['lank']})")

    ny_fraga = st.chat_input("Din fråga om lag, skatt eller myndighetsdata...")

    if "juridik_prompt" in st.session_state and st.session_state.juridik_prompt:
        ny_fraga = st.session_state.juridik_prompt
        st.session_state.juridik_prompt = None

    if ny_fraga:
        with st.chat_message("user"):
            st.markdown(ny_fraga)
        st.session_state.juridik_samtal.append({"role": "user", "content": ny_fraga})

        with st.chat_message("assistant"):
            with st.spinner("Slår upp hos myndigheterna..."):
                konf = st.session_state.get("ai_konfiguration")
                if not konf or konf.leverantör != "Anthropic" or not konf.api_nyckel:
                    st.error("Detta rum kräver att Anthropic (Claude) är vald och att API-nyckel är inlagd i inställningarna.")
                else:
                    from quiet_kalla import fraga_myndighetskallor
                    svar = fraga_myndighetskallor(ny_fraga, api_nyckel=konf.api_nyckel)

                    if svar.fel:
                        text = f"Ett tekniskt fel inträffade: {svar.fel}"
                        st.error(text)
                        st.session_state.juridik_samtal.append({"role": "assistant", "content": text})
                    elif not svar.kan_besvaras:
                        text = svar.forbehall or "Det hittade jag inte hos någon av källorna."
                        st.markdown(text)
                        st.session_state.juridik_samtal.append({"role": "assistant", "content": text})
                    else:
                        st.markdown(svar.text)
                        kallor = [
                            {"nr": k.nr, "etikett": k.etikett, "myndighet": k.myndighet,
                             "period": k.period, "lank": k.lank_manniska}
                            for k in svar.kallor
                        ]
                        if kallor:
                            with st.expander(f"{len(kallor)} källor"):
                                for k in kallor:
                                    rad = f"**[{k['nr']}] {k['etikett']}** — {k['myndighet']}"
                                    if k["period"]:
                                        rad += f" ({k['period']})"
                                    st.markdown(f"{rad}  \n[{k['lank']}]({k['lank']})")
                        if svar.forbehall:
                            st.caption(f"Not: {svar.forbehall}")
                        st.session_state.juridik_samtal.append({
                            "role": "assistant", "content": svar.text, "kallor": kallor,
                        })

def rendera_foretags_chatt() -> None:
    st.header("💬 Företagsdata")
    if st.session_state.get("aktivt_fakturautkast"):
        st.info("Ett fakturautkast väntar i **Pengar in**.")
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

    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import BETALNINGSVERIFIKAT
        for f in [BETALNINGSVERIFIKAT]:
            rendera_atgardsformular(st, f)


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

    vald_vy = st.session_state.get("snabbvy_register")
    
    if vald_vy in ("prislistor", "rabattavtal", "etiketter", "anlaggningstillgangar", "foretagsinfo", "anvandare", "kundreskontraposter") and har_spiris:
        klient_od = None
        try:
            cfg = app_config.las_config()
            klient_od = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
        except Exception:
            pass
            
        if klient_od:
            if vald_vy == "prislistor" and "prislistor" not in st.session_state:
                from spiris_adapter import hamta_prislistor
                try: st.session_state.prislistor = hamta_prislistor(klient_od)
                except Exception: st.session_state.prislistor = None
                
            elif vald_vy == "rabattavtal" and "rabattavtal" not in st.session_state:
                from spiris_adapter import hamta_rabattavtal
                try: st.session_state.rabattavtal = hamta_rabattavtal(klient_od)
                except Exception: st.session_state.rabattavtal = None
                
            elif vald_vy == "etiketter" and "etiketter" not in st.session_state:
                from spiris_adapter import hamta_etiketter
                try: 
                    e1 = hamta_etiketter(klient_od, "kund")
                    for e in e1: e["Typ"] = "kund"
                    e2 = hamta_etiketter(klient_od, "artikel")
                    for e in e2: e["Typ"] = "artikel"
                    st.session_state.etiketter = e1 + e2
                except Exception: st.session_state.etiketter = None
                
            elif vald_vy == "anlaggningstillgangar" and "anlaggningstillgangar" not in st.session_state:
                from spiris_adapter import hamta_anlaggningstillgangar
                try: st.session_state.anlaggningstillgangar = hamta_anlaggningstillgangar(klient_od)
                except Exception: st.session_state.anlaggningstillgangar = None
                
            elif vald_vy == "foretagsinfo" and "foretagsinfo" not in st.session_state:
                from spiris_adapter import hamta_foretagsinfo
                try: st.session_state.foretagsinfo = hamta_foretagsinfo(klient_od)
                except Exception: st.session_state.foretagsinfo = None
                
            elif vald_vy == "anvandare" and "anvandare" not in st.session_state:
                from spiris_adapter import hamta_anvandare
                try: st.session_state.anvandare = hamta_anvandare(klient_od)
                except Exception: st.session_state.anvandare = None
                
            elif vald_vy == "kundreskontraposter" and "kundreskontraposter" not in st.session_state:
                from spiris_adapter import hamta_kundreskontraposter
                try: st.session_state.kundreskontraposter = hamta_kundreskontraposter(klient_od)
                except Exception: st.session_state.kundreskontraposter = None

    valutakurs = None
    if vald_vy == "valutakurs":
        st.write("### Hämta valutakurs")
        kol1, kol2, kol3 = st.columns(3)
        fran = kol1.text_input("Från valuta", value="EUR")
        till = kol2.text_input("Till valuta", value="SEK")
        datum = kol3.date_input("Datum", value=date.today())
        if st.button("Hämta kurs"):
            try:
                cfg = app_config.las_config()
                klient_od = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
                from spiris_adapter import hamta_valutakurs
                valutakurs = hamta_valutakurs(klient_od, str(datum), fran, till)
            except Exception as e:
                st.error(f"Kunde inte hämta valutakurs: {e}")

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
        prislistor=st.session_state.get("prislistor"),
        rabattavtal=st.session_state.get("rabattavtal"),
        etiketter=st.session_state.get("etiketter"),
        anlaggningstillgangar=st.session_state.get("anlaggningstillgangar"),
        foretagsinfo=st.session_state.get("foretagsinfo"),
        anvandare=st.session_state.get("anvandare"),
        valutakurs=valutakurs,
        kundreskontraposter=st.session_state.get("kundreskontraposter"),
    )
    
    snabbvy_render.rendera_snabbvyfalt(
        st, snabbvyer.SNABBVYER_REGISTER, "snabbvy_register", vydata
    )
    
    with st.expander("➕ Ny åtgärd"):
        from atgardsformular import MASTERDATAANDRING, MASTERDATABORTTAGNING, KONTO, KONTOANDRING
        for f in [MASTERDATAANDRING, MASTERDATABORTTAGNING, KONTO, KONTOANDRING]:
            rendera_atgardsformular(st, f)


def _rendera_kvittning_formular(st: Any) -> None:
    st.subheader("Kvittning")
    faktura_id = st.text_input("Kreditfaktura (nummer eller id)", key="kvitto_kredit")
    if not faktura_id:
        st.info("Ange kreditfaktura för att hämta kvittningskandidater.")
        return
        
    klient = _bygg_klient()
    from spiris_adapter import hamta_kvittningskandidater
    try:
        kandidater = hamta_kvittningskandidater(klient, faktura_id)
    except Exception as e:
        st.error(f"Kunde inte hämta kvittningskandidater: {e}")
        return
        
    if not kandidater:
        st.warning("Inga kvittningskandidater hittades för denna kreditfaktura.")
        return
        
    kand_id_str = {str(k.get("Id", "")): k for k in kandidater}
    
    with st.form("kvittning_form", clear_on_submit=True):
        valda = st.multiselect("Debetfakturor", options=list(kand_id_str.keys()), format_func=lambda x: f"{kand_id_str[x].get('InvoiceNumber', '')} ({kand_id_str[x].get('Total', '')} kr)")
        datum = st.text_input("Verifikatdatum (ÅÅÅÅ-MM-DD)")
        
        from atgardsformular import KVITTNING
        if st.form_submit_button("Skapa utkast"):
            if not valda or not datum:
                st.error("Du måste välja minst en debetfaktura och ange ett datum.")
            else:
                try:
                    payload = KVITTNING.bygg_nyttolast({
                        "kreditfaktura_id": faktura_id,
                        "debetfakturor": valda,
                        "verifikatdatum": datum
                    })
                    import utkast
                    utkast.skapa(KVITTNING.utkasttyp, payload)
                    st.success(f"Utkast skapat: {KVITTNING.rubrik}")
                except ValueError as e:
                    st.error(str(e))

def _rendera_underlagskoppling_formular(st: Any) -> None:
    st.subheader("Koppla underlag")
    
    from spiris_adapter import hamta_underlag, UNDERLAG_DOKUMENTTYPER
    klient = _bygg_klient()
    try:
        underlag = hamta_underlag(klient, include_matched=False)
    except Exception as e:
        st.error(f"Kunde inte hämta underlag: {e}")
        return
        
    if not underlag:
        st.info("Det finns inga okopplade underlag.")
        return
        
    und_id_str = {str(u.get("Id", "")): u for u in underlag}
    
    with st.form("underlagskoppling_form", clear_on_submit=True):
        valt_underlag = st.selectbox("Underlag", options=list(und_id_str.keys()), format_func=lambda x: f"{und_id_str[x].get('Name', x)}")
        
        # UNDERLAG_DOKUMENTTYPER keys as options, the Spiris values are at index 0 of the tuple
        dok_typ_display = st.selectbox("Dokumenttyp", options=list(UNDERLAG_DOKUMENTTYPER.keys()))
        dok_id = st.text_input("Dokument-ID")
        
        from atgardsformular import UNDERLAGSKOPPLING
        if st.form_submit_button("Skapa utkast"):
            if not valt_underlag or not dok_id or not dok_typ_display:
                st.error("Fyll i alla obligatoriska fält.")
            else:
                try:
                    payload = UNDERLAGSKOPPLING.bygg_nyttolast({
                        "underlag_id": valt_underlag,
                        "dokument_id": dok_id,
                        "dokument_typ": UNDERLAG_DOKUMENTTYPER[dok_typ_display][0]
                    })
                    import utkast
                    utkast.skapa(UNDERLAGSKOPPLING.utkasttyp, payload)
                    st.success(f"Utkast skapat: {UNDERLAGSKOPPLING.rubrik}")
                except ValueError as e:
                    st.error(str(e))

def _rendera_konto_formular(st: Any) -> None:
    st.subheader("Nytt konto")
    ar_id = st.session_state.get("spiris_hamtat_ar")
    if not ar_id:
        st.error("Inget räkenskapsår valt.")
        return
        
    st.caption(f"Räkenskapsår ID: {ar_id}")
    
    klient = _bygg_klient()
    from spiris_adapter import hamta_momskoder
    try:
        momskoder = hamta_momskoder(klient, per_datum=None) # Or use existing state
    except Exception:
        momskoder = []
        
    momskod_opts = {m.get("Id"): m for m in momskoder} if isinstance(momskoder, list) else {}
        
    with st.form("konto_form", clear_on_submit=True):
        kontonr = st.text_input("Kontonummer *")
        kontonamn = st.text_input("Kontonamn *")
        aktiv = st.checkbox("Aktiv", value=True)
        
        kontotyp = st.selectbox("Kontotyp (valfri)", options=[""] + ["Asset", "Liability", "Equity", "Revenue", "Cost"])
        momskod_id = st.selectbox("Momskod (valfri)", options=[""] + list(momskod_opts.keys()), format_func=lambda x: f"{x} - {momskod_opts[x].get('Description', '')}" if x else "")
        projekt_tillatet = st.checkbox("Projekt tillåtet")
        kostnadsstalle_tillatet = st.checkbox("Kostnadsställe tillåtet")
        sparrat = st.checkbox("Spärrat för manuell bokning")
        
        from atgardsformular import KONTO
        if st.form_submit_button("Skapa utkast"):
            if not kontonr or not kontonamn:
                st.error("Fyll i alla obligatoriska fält.")
            else:
                data = {
                    "kontonr": kontonr,
                    "kontonamn": kontonamn,
                    "rakenskapsar_id": ar_id,
                    "aktiv": aktiv,
                    "projekt_tillatet": projekt_tillatet,
                    "kostnadsstalle_tillatet": kostnadsstalle_tillatet,
                    "sparrat_for_manuell_bokning": sparrat
                }
                if kontotyp: data["kontotyp"] = kontotyp
                if momskod_id: data["momskod_id"] = momskod_id
                
                try:
                    payload = KONTO.bygg_nyttolast(data)
                    import utkast
                    utkast.skapa(KONTO.utkasttyp, payload)
                    st.success(f"Utkast skapat: {KONTO.rubrik}")
                except ValueError as e:
                    st.error(str(e))

def _rendera_kontoandring_formular(st: Any) -> None:
    st.subheader("Ändra konto")
    ar_id = st.session_state.get("spiris_hamtat_ar")
    if not ar_id:
        st.error("Inget räkenskapsår valt.")
        return
        
    kontonr = st.text_input("Kontonummer (nuvarande)")
    if not kontonr:
        st.info("Ange kontonummer att ändra.")
        return
        
    klient = _bygg_klient()
    from spiris_adapter import hamta_kontotransaktioner, _KONTO_ALLOWLIST
    try:
        # Actually Spiris API needs /accounts/{FinancialYear}/{Number}
        # In adapters we have `hamta_kontosaldon` or `hamta_kontoplan_alla`. But `hamta_ett` isn't fully standardized.
        # Let's use `hamta_kontoplan_alla` and filter.
        from spiris_adapter import hamta_kontoplan_alla
        plan = hamta_kontoplan_alla(klient)
        # plan is list of dicts.
        nuvarande = None
        for k in plan:
            if str(k.get("FinancialYear")) == str(ar_id) and str(k.get("Number")) == str(kontonr):
                nuvarande = k
                break
    except Exception as e:
        st.error(f"Kunde inte läsa konto: {e}")
        return
        
    if not nuvarande:
        st.warning(f"Konto {kontonr} hittades inte i räkenskapsår {ar_id}.")
        return
        
    with st.form("kontoandring_form", clear_on_submit=True):
        andringar = {}
        # Dynamic rendering from _KONTO_ALLOWLIST
        for nyckel, (namn, htext) in _KONTO_ALLOWLIST.items():
            nuv_val = nuvarande.get(nyckel)
            if isinstance(nuv_val, bool):
                nytt_val = st.checkbox(namn, value=nuv_val, help=htext)
                if nytt_val != nuv_val: andringar[nyckel] = nytt_val
            else:
                nytt_val = st.text_input(namn, value=str(nuv_val) if nuv_val is not None else "", help=htext)
                if str(nytt_val) != str(nuv_val if nuv_val is not None else ""):
                    # Very simple cast mapping (Spiris usually accepts strings except bools)
                    andringar[nyckel] = nytt_val
                    
        from atgardsformular import KONTOANDRING
        if st.form_submit_button("Skapa utkast"):
            try:
                payload = KONTOANDRING.bygg_nyttolast({
                    "rakenskapsar_id": ar_id,
                    "kontonr": kontonr,
                    "nuvarande": nuvarande,
                    "andringar": andringar
                })
                import utkast
                utkast.skapa(KONTOANDRING.utkasttyp, payload)
                st.success(f"Utkast skapat: {KONTOANDRING.rubrik}")
            except ValueError as e:
                st.error(str(e))

def _rendera_periodiseringsandring_formular(st: Any) -> None:
    st.subheader("Ändra periodisering")
    klient = _bygg_klient()
    
    kopplingstyp = st.selectbox("Kopplingstyp", options=["Voucher", "SupplierInvoice", "SupplierInvoiceDraft"])
    kopplings_id = st.text_input("Kopplings-ID")
    kopplingsrad = st.text_input("Kopplingsrad")
    
    if not (kopplingstyp and kopplings_id and kopplingsrad):
        st.info("Ange uppgifter för att hämta nuvarande periodisering.")
        return
        
    # We must read current periodisering to show in summary.
    from spiris_adapter import hamta_periodiseringar
    try:
        alla = hamta_periodiseringar(klient)
        nuvarande = None
        for p in alla:
            if (str(p.get(kopplingstyp+"Id", "")) == str(kopplings_id) and 
                str(p.get(kopplingstyp+"Row", "")) == str(kopplingsrad)):
                nuvarande = p
                break
    except Exception as e:
        st.error(f"Kunde inte läsa periodiseringar: {e}")
        return
        
    if not nuvarande:
        st.warning("Hittade ingen periodisering för dessa uppgifter.")
        return
        
    with st.form("periodiseringsandring_form", clear_on_submit=True):
        st.write(f"**Nuvarande plan:** {nuvarande.get('Period', 0)} perioder, belopp: {nuvarande.get('Total', 0)}")
        
        antal = st.number_input("Antal perioder", min_value=1, value=nuvarande.get('Period', 1))
        startdatum = st.text_input("Startdatum", value=nuvarande.get('Date', ''))
        belopp = st.text_input("Belopp", value=str(nuvarande.get('Total', '')))
        konto = st.text_input("Konto", value=nuvarande.get('Account', ''))
        
        from atgardsformular import PERIODISERINGSANDRING
        if st.form_submit_button("Skapa utkast"):
            try:
                payload = PERIODISERINGSANDRING.bygg_nyttolast({
                    "kopplingstyp": kopplingstyp,
                    "kopplings_id": kopplings_id,
                    "kopplingsrad": int(kopplingsrad),
                    "antal_perioder": int(antal),
                    "startdatum": startdatum,
                    "belopp": float(belopp),
                    "konto": konto,
                    "nuvarande_perioder": nuvarande.get('Period', 0),
                    "nuvarande_belopp": nuvarande.get('Total', 0)
                })
                import utkast
                utkast.skapa(PERIODISERINGSANDRING.utkasttyp, payload)
                st.success(f"Utkast skapat: {PERIODISERINGSANDRING.rubrik}")
            except ValueError as e:
                st.error(str(e))

def _rendera_periodiseringsborttagning_formular(st: Any) -> None:
    st.subheader("Ta bort periodisering")
    utkast_id = st.text_input("Leverantörsfakturautkast ID")
    
    if not utkast_id:
        st.info("Ange utkast-ID för att fortsätta.")
        return
        
    klient = _bygg_klient()
    from spiris_adapter import hamta_periodiseringar
    try:
        alla = hamta_periodiseringar(klient)
        traffar = [p for p in alla if str(p.get("SupplierInvoiceDraftId", "")) == str(utkast_id)]
    except Exception as e:
        st.error(f"Kunde inte hämta: {e}")
        return
        
    if not traffar:
        st.warning("Hittade inga periodiseringar för detta utkast.")
        return
        
    # Check if there are any that have SupplierInvoiceDraftRow
    traffar = [t for t in traffar if "SupplierInvoiceDraftRow" in t]
    
    with st.form("periodiseringsborttagning_form", clear_on_submit=True):
        st.write(f"Hittade **{len(traffar)}** periodisering(ar) för detta utkast.")
        st.warning("Tar bort ALLA periodiseringar på utkastet. Oåterkalleligt — det finns ingen väg tillbaka.")
        
        from atgardsformular import PERIODISERINGSBORTTAGNING
        if st.form_submit_button("Skapa utkast"):
            try:
                payload = PERIODISERINGSBORTTAGNING.bygg_nyttolast({
                    "leverantorsfakturautkast_id": utkast_id,
                    "antal_perioder_som_forsvinner": len(traffar)
                })
                import utkast
                utkast.skapa(PERIODISERINGSBORTTAGNING.utkasttyp, payload)
                st.success(f"Utkast skapat: {PERIODISERINGSBORTTAGNING.rubrik}")
            except ValueError as e:
                st.error(str(e))



def rendera_atgardsformular(st, formular) -> None:
    if getattr(formular, "egen_ritare", None):
        formular.egen_ritare(st)
        return

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
            if f.nyckel in ("bankkonto_id", "leverantor_id"):
                klient = None
                if st.session_state.get("spiris_tokens"):
                    try:
                        import app_config
                        cfg = app_config.las_config()
                        klient = _bygg_spiris_klient_fran_session(cfg.spiris_client_id, cfg.spiris_client_secret)
                    except Exception:
                        pass
                
                lista = []
                if klient:
                    try:
                        if f.nyckel == "bankkonto_id":
                            from spiris_adapter import hamta_bankkonton
                            lista = hamta_bankkonton(klient)
                        else:
                            from spiris_adapter import hamta_leverantorer
                            lista = hamta_leverantorer(klient)
                    except Exception:
                        pass
                
                if not lista:
                    varden[f.nyckel] = st.text_input(lbl, help="Kunde inte hämta lista från Spiris. Ange ID manuellt.")
                else:
                    if f.nyckel == "bankkonto_id":
                        options = {x["id"]: (x.get("namn") or x.get("bas_konto") or x["id"]) for x in lista}
                    else:
                        options = {x["Id"]: x.get("Name", x["Id"]) for x in lista}
                    
                    val_keys = [""] + list(options.keys())
                    def _format_func(k, opts=options):
                        return opts[k] if k else "(Välj...)"
                        
                    varden[f.nyckel] = st.selectbox(lbl, val_keys, format_func=_format_func, help=f.hjalptext, key=f"sel_{f.nyckel}")
            elif f.typ == "text":
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

def _rendera_konto_formular(st: Any) -> None:
    st.write("**Skapa nytt konto** — fyll i uppgifterna nedan.")
    from parser.utkast import spara_utkast
    import parser.spiris_adapter as spiris_adapter
    
    klient = st.session_state.get("klient")
    if not klient:
        st.error("Ingen klient. Du måste logga in.")
        return
        
    ar_id = st.session_state.get("spiris_hamtat_ar")
    if not ar_id:
        st.error("Inget räkenskapsår är valt. Välj ett i sidomenyn.")
        return
        
    try:
        alla_ar = spiris_adapter.hamta_rakenskapsar(klient)
        ar_obj = next((a for a in alla_ar if a.get("Id") == ar_id), None)
        if ar_obj:
            st.info(f"Gäller räkenskapsår: {str(ar_obj.get('StartDate', ''))[:10]} till {str(ar_obj.get('EndDate', ''))[:10]}")
        else:
            st.info(f"Gäller räkenskapsår (ID): {ar_id}")
    except Exception as e:
        st.error(f"Kunde inte hämta räkenskapsår: {e}")
        return
        
    try:
        momskoder = spiris_adapter.hamta_momskoder(klient)
    except Exception as e:
        st.error(f"Kunde inte hämta momskoder: {e}")
        return

    with st.form("konto_formular"):
        kontonr = st.text_input("Kontonummer", max_chars=4)
        kontonamn = st.text_input("Kontonamn")
        aktiv = st.checkbox("Aktiv", value=True)
        
        kontotyper = ["Tillgang", "Skuld", "EgetKapital", "Intakt", "Kostnad"]
        kontotyp = st.selectbox("Kontotyp (frivillig)", [""] + kontotyper)
        
        moms_options = {"Ingen": ""}
        for m in momskoder:
            moms_options[f"{m['kod']} - {m['beskrivning']}"] = m["kod"]
            
        valt_moms_label = st.selectbox("Momskod (frivillig)", list(moms_options.keys()))
        momskod_id = moms_options[valt_moms_label]
        
        projekt = st.checkbox("Projekt tillåtet", value=False)
        kostnad = st.checkbox("Kostnadsställe tillåtet", value=False)
        sparrat = st.checkbox("Spärrat för manuell bokning", value=False)
        
        if st.form_submit_button("Skapa utkast"):
            if not kontonr or not kontonamn:
                st.error("Kontonummer och kontonamn är obligatoriska.")
            else:
                nyttolast = {
                    "kontonr": kontonr,
                    "kontonamn": kontonamn,
                    "rakenskapsar_id": ar_id,
                    "aktiv": "Ja" if aktiv else "Nej",
                    "projekt_tillatet": "Ja" if projekt else "Nej",
                    "kostnadsstalle_tillatet": "Ja" if kostnad else "Nej",
                    "sparrat_for_manuell_bokning": "Ja" if sparrat else "Nej",
                }
                if kontotyp:
                    nyttolast["kontotyp"] = kontotyp
                if momskod_id:
                    nyttolast["momskod_id"] = momskod_id
                    
                spara_utkast(
                    typ="konto",
                    nyttolast=nyttolast,
                    sammanfattning=[
                        ["Konto", f"{kontonr} - {kontonamn}"],
                        ["Aktiv", nyttolast["aktiv"]],
                        ["Momskod", momskod_id or "-"]
                    ]
                )

def _rendera_kontoandring_formular(st: Any) -> None:
    st.write("**Ändra konto** — välj vilket konto som ska ändras.")
    from parser.utkast import spara_utkast
    import parser.spiris_adapter as spiris_adapter
    
    klient = st.session_state.get("klient")
    if not klient:
        st.error("Ingen klient. Du måste logga in.")
        return
        
    ar_id = st.session_state.get("spiris_hamtat_ar")
    if not ar_id:
        st.error("Inget räkenskapsår är valt. Välj ett i sidomenyn.")
        return
        
    try:
        alla_konton = spiris_adapter.hamta_kontoplan(klient, ar_id)
    except Exception as e:
        st.error(f"Kunde inte hämta kontoplan: {e}")
        return

    # 1. Välj konto
    konto_options = {f"{k['kontonr']} - {k['kontonamn']}": k['kontonr'] for k in alla_konton}
    valt_konto_label = st.selectbox("Vilket konto vill du ändra?", [""] + list(konto_options.keys()), key="kontoandring_konto_val")
    
    if not valt_konto_label:
        return
        
    kontonr = konto_options[valt_konto_label]
    
    # Hämta komplett data för det valda kontot
    try:
        ra_konto = klient.hamta(f"/accounts/{ar_id}/{kontonr}")
    except Exception as e:
        st.error(f"Kunde inte hämta detaljer för konto {kontonr}: {e}")
        return
        
    try:
        momskoder = spiris_adapter.hamta_momskoder(klient)
    except Exception as e:
        st.error(f"Kunde inte hämta momskoder: {e}")
        return
        
    # Extrahera nuvarande värden
    nuvarande_namn = ra_konto.get("Description", "")
    nuvarande_aktiv = bool(ra_konto.get("Active", True))
    nuvarande_kontotyp = ra_konto.get("AccountType", "")
    nuvarande_momskod = ra_konto.get("VatCode", "")
    nuvarande_projekt = bool(ra_konto.get("ProjectAllowed", False))
    nuvarande_kostnad = bool(ra_konto.get("CostCenterAllowed", False))
    nuvarande_sparrat = bool(ra_konto.get("BlockedForManualBooking", False))

    with st.form("kontoandring_formular"):
        nytt_namn = st.text_input("Kontonamn", value=nuvarande_namn)
        ny_aktiv = st.checkbox("Aktiv", value=nuvarande_aktiv)
        
        kontotyper = ["Tillgang", "Skuld", "EgetKapital", "Intakt", "Kostnad"]
        try:
            typ_idx = kontotyper.index(nuvarande_kontotyp) + 1
        except ValueError:
            typ_idx = 0
            
        ny_kontotyp = st.selectbox("Kontotyp (frivillig)", [""] + kontotyper, index=typ_idx)
        
        moms_options = {"Ingen": ""}
        moms_keys = ["Ingen"]
        moms_idx = 0
        for i, m in enumerate(momskoder):
            label = f"{m['kod']} - {m['beskrivning']}"
            moms_options[label] = m["kod"]
            moms_keys.append(label)
            if m["kod"] == nuvarande_momskod:
                moms_idx = i + 1
                
        valt_moms_label2 = st.selectbox("Momskod (frivillig)", moms_keys, index=moms_idx)
        ny_momskod = moms_options[valt_moms_label2]
        
        nytt_projekt = st.checkbox("Projekt tillåtet", value=nuvarande_projekt)
        nytt_kostnad = st.checkbox("Kostnadsställe tillåtet", value=nuvarande_kostnad)
        nytt_sparrat = st.checkbox("Spärrat för manuell bokning", value=nuvarande_sparrat)
        
        if st.form_submit_button("Skapa utkast"):
            # Samla in ändringar
            andringar = {}
            if nytt_namn != nuvarande_namn: andringar["kontonamn"] = nytt_namn
            if ny_aktiv != nuvarande_aktiv: andringar["aktiv"] = "Ja" if ny_aktiv else "Nej"
            if ny_kontotyp != nuvarande_kontotyp: andringar["kontotyp"] = ny_kontotyp
            if ny_momskod != nuvarande_momskod: andringar["momskod_id"] = ny_momskod
            if nytt_projekt != nuvarande_projekt: andringar["projekt_tillatet"] = "Ja" if nytt_projekt else "Nej"
            if nytt_kostnad != nuvarande_kostnad: andringar["kostnadsstalle_tillatet"] = "Ja" if nytt_kostnad else "Nej"
            if nytt_sparrat != nuvarande_sparrat: andringar["sparrat_for_manuell_bokning"] = "Ja" if nytt_sparrat else "Nej"
            
            if not andringar:
                st.warning("Du har inte gjort några ändringar.")
            else:
                nuvarande_dict = {
                    "kontonamn": nuvarande_namn,
                    "aktiv": "Ja" if nuvarande_aktiv else "Nej",
                    "kontotyp": nuvarande_kontotyp,
                    "momskod_id": nuvarande_momskod,
                    "projekt_tillatet": "Ja" if nuvarande_projekt else "Nej",
                    "kostnadsstalle_tillatet": "Ja" if nuvarande_kostnad else "Nej",
                    "sparrat_for_manuell_bokning": "Ja" if nuvarande_sparrat else "Nej",
                }
                
                nyttolast = {
                    "kontonr": kontonr,
                    "rakenskapsar_id": ar_id,
                    "nuvarande": nuvarande_dict,
                    "andringar": andringar,
                }
                
                sammanf = [["Konto", kontonr]]
                for k, v in andringar.items():
                    sammanf.append([f"Ny {k}", str(v)])
                    
                spara_utkast(
                    typ="kontoandring",
                    nyttolast=nyttolast,
                    sammanfattning=sammanf
                )

def _rendera_periodiseringsandring_formular(st: Any) -> None:
    st.write("**Ändra periodisering** — välj vilken periodisering du vill ändra.")
    from parser.utkast import spara_utkast
    
    klient = st.session_state.get("klient")
    if not klient:
        st.error("Du måste vara inloggad.")
        return
        
    try:
        alla = klient.hamta_alla("/allocationperiods")
    except Exception as e:
        st.error(f"Kunde inte hämta periodiseringar: {e}")
        return
        
    options = {}
    for p in alla:
        if not p.get("Id"): continue
        namn = p.get("Description") or f"Periodisering {p.get('Id')}"
        if p.get("VoucherId"):
            namn += f" (Verifikat {p.get('VoucherId')})"
        elif p.get("SupplierInvoiceId"):
            namn += f" (Faktura {p.get('SupplierInvoiceId')})"
        elif p.get("SupplierInvoiceDraftId"):
            namn += f" (Utkast {p.get('SupplierInvoiceDraftId')})"
            
        options[namn] = p
        
    valt = st.selectbox("Vilken periodisering vill du ändra?", [""] + list(options.keys()))
    if not valt:
        return
        
    vald_p = options[valt]
    
    nuvarande_rader = vald_p.get("Rows", [])
    nuvarande_antal_perioder = len(nuvarande_rader) if nuvarande_rader else 1
    nuvarande_startdatum = nuvarande_rader[0].get("BookkeepingDate", "") if nuvarande_rader else ""
    nuvarande_konto = vald_p.get("AllocationAccountNumber", "")
    if not nuvarande_konto:
        nuvarande_konto = vald_p.get("DebitAccountNumber", "")
    
    with st.form("periodiseringsandring_formular"):
        nytt_konto = st.text_input("Konto", value=nuvarande_konto, max_chars=4)
        ny_period = st.number_input("Antal perioder", value=nuvarande_antal_perioder, min_value=1)
        nytt_startdatum = st.text_input("Startdatum (ÅÅÅÅ-MM-DD)", value=nuvarande_startdatum)
        
        if st.form_submit_button("Skapa utkast"):
            if not nytt_konto or not ny_period or not nytt_startdatum:
                st.error("Alla fält måste fyllas i.")
            else:
                nyttolast = {
                    "konto": nytt_konto,
                    "antal_perioder": int(ny_period),
                    "startdatum": str(nytt_startdatum),
                    "belopp": float(vald_p.get("Amount", 0)),
                }
                
                if vald_p.get("VoucherId") and vald_p.get("VoucherRow") is not None:
                    nyttolast["VoucherId"] = vald_p.get("VoucherId")
                    nyttolast["VoucherRow"] = vald_p.get("VoucherRow")
                elif vald_p.get("SupplierInvoiceId") and vald_p.get("SupplierInvoiceRow") is not None:
                    nyttolast["SupplierInvoiceId"] = vald_p.get("SupplierInvoiceId")
                    nyttolast["SupplierInvoiceRow"] = vald_p.get("SupplierInvoiceRow")
                elif vald_p.get("SupplierInvoiceDraftId") and vald_p.get("SupplierInvoiceDraftRow") is not None:
                    nyttolast["SupplierInvoiceDraftId"] = vald_p.get("SupplierInvoiceDraftId")
                    nyttolast["SupplierInvoiceDraftRow"] = vald_p.get("SupplierInvoiceDraftRow")
                else:
                    st.error("Kunde inte avgöra källraden för denna periodisering (VoucherRow/SupplierInvoiceRow saknas).")
                    return
                    
                spara_utkast(
                    typ="periodiseringsandring",
                    nyttolast=nyttolast,
                    sammanfattning=[
                        ["Konto", nytt_konto],
                        ["Startdatum", nytt_startdatum],
                        ["Antal perioder", str(ny_period)]
                    ]
                )

def _rendera_periodiseringsborttagning_formular(st: Any) -> None:
    st.write("**Ta bort periodisering**")
    from parser.utkast import spara_utkast
    
    klient = st.session_state.get("klient")
    if not klient:
        st.error("Du måste vara inloggad.")
        return
        
    try:
        alla = klient.hamta_alla("/allocationperiods")
    except Exception as e:
        st.error(f"Kunde inte hämta periodiseringar: {e}")
        return
        
    options = {}
    for p in alla:
        if not p.get("Id"): continue
        namn = p.get("Description") or f"Periodisering {p.get('Id')}"
        if p.get("SupplierInvoiceDraftId"):
            namn += f" (Lev.faktura utkast {p.get('SupplierInvoiceDraftId')})"
            options[namn] = p
        
    if not options:
        st.info("Hittade inga periodiseringar på utkast som kan tas bort.")
        return
        
    valt = st.selectbox("Vilken periodisering vill du ta bort?", [""] + list(options.keys()))
    if not valt:
        return
        
    vald_p = options[valt]
    
    with st.form("periodiseringsborttagning_formular"):
        st.write("Vill du ta bort periodiseringen på utkastet?")
        if st.form_submit_button("Skapa utkast för borttagning"):
            nyttolast = {
                "leverantorsfakturautkast_id": vald_p.get("SupplierInvoiceDraftId")
            }
            spara_utkast(
                typ="periodiseringsborttagning",
                nyttolast=nyttolast,
                sammanfattning=[["Fakturautkast ID", str(vald_p.get("SupplierInvoiceDraftId"))]]
            )

def _rendera_kvittning_formular(st: Any) -> None:
    st.write("**Kvitta fakturor** — välj en kreditfaktura för att se vilka debetfakturor som kan kvittas mot den.")
    from parser.utkast import spara_utkast
    import parser.spiris_adapter as spiris_adapter
    import datetime
    
    klient = st.session_state.get("klient")
    if not klient:
        st.error("Ingen klient. Du måste logga in.")
        return

    # Fält 1: Kreditfaktura (nummer eller id)
    kreditfaktura = st.text_input("Kreditfaktura (nummer eller id)", key="kvittning_kreditfaktura")
    
    if not kreditfaktura:
        return
        
    # Försök hämta kandidater
    try:
        kandidater = spiris_adapter.hamta_kvittningskandidater(klient, kreditfaktura)
    except Exception as e:
        st.error(f"Kunde inte hämta kvittningskandidater för {kreditfaktura}: {e}")
        return
        
    if not kandidater:
        st.info("Inga kvittningskandidater hittades för denna kreditfaktura.")
        return
        
    # Fält 2: Debetfakturor (flerval)
    def formatera_kandidat(k):
        return f"{k.get('SupplierName', '')} - {k.get('InvoiceNumber', '')} ({k.get('Id')}) - Belopp: {k.get('Balance', '')}"
        
    kand_map = {formatera_kandidat(k): k.get("Id") for k in kandidater}
    valda_kandidater = st.multiselect("Debetfakturor att kvitta", list(kand_map.keys()), key="kvittning_kandidater")
    
    # Fält 3: Verifikatdatum
    verifikatdatum = st.date_input("Verifikatdatum", value=datetime.date.today(), key="kvittning_datum")
    
    if st.button("Skapa utkast", key="kvittning_skapa"):
        if not valda_kandidater:
            st.error("Du måste välja minst en debetfaktura.")
            return
            
        debet_ids = [kand_map[vk] for vk in valda_kandidater]
        payload = {
            "DebitInvoiceIds": debet_ids,
            "VoucherDate": verifikatdatum.strftime("%Y-%m-%d")
        }
        
        spara_utkast(
            typ="kvittning",
            nyttolast={
                "kreditfaktura_id": kreditfaktura,
                "payload": payload
            },
            sammanfattning=[
                ["Kreditfaktura", kreditfaktura],
                ["Valda debetfakturor", ", ".join(str(d) for d in debet_ids)],
                ["Verifikatdatum", payload["VoucherDate"]]
            ],
            varning="Kvittningen kan inte ångras."
        )

def _rendera_underlagskoppling_formular(st: Any) -> None:
    st.write("**Koppla underlag** — fyll i uppgifterna nedan.")
    from parser.spiris_adapter import UNDERLAG_DOKUMENTTYPER, hamta_underlag
    import parser.spiris_adapter as spiris_adapter
    from parser.utkast import spara_utkast
    
    klient = st.session_state.get("klient")
    if not klient:
        st.error("Ingen klient. Du måste logga in.")
        return

    val = st.selectbox("Dokumentslag", list(UNDERLAG_DOKUMENTTYPER.keys()))
    dokument_typ, adapter_func_name = UNDERLAG_DOKUMENTTYPER[val]
    
    adapter_func = getattr(spiris_adapter, adapter_func_name)
    try:
        dokumentlista = adapter_func(klient)
    except Exception as e:
        st.error(f"Kunde inte hämta dokumentlista: {e}")
        return

    if not dokumentlista:
        st.warning("Hittade inga dokument av den här typen.")
        return

    def formattera_dokument(d):
        if val == "Leverantörsfaktura":
            return f"{d.get('SupplierName', '')} - {d.get('InvoiceNumber', '')} ({d.get('Id')})"
        else:
            return f"Verifikat {d.get('VoucherNumber', '')} ({d.get('Id')})"
    
    dok_map = {formattera_dokument(d): d.get("Id") for d in dokumentlista}
    valt_dok_str = st.selectbox("Dokument", list(dok_map.keys()))
    dokument_id = dok_map[valt_dok_str] if valt_dok_str else ""

    try:
        underlag = hamta_underlag(klient, include_matched=False)
    except Exception as e:
        st.error(f"Kunde inte hämta underlag: {e}")
        return
        
    if not underlag:
        st.warning("Hittade inga okopplade underlag.")
        return
        
    und_map = {u.get("FileName", "Okänt filnamn"): u.get("Id") for u in underlag}
    valt_und_str = st.selectbox("Underlag", list(und_map.keys()))
    underlag_id = und_map[valt_und_str] if valt_und_str else ""
    
    if st.button("Skapa utkast"):
        if not dokument_id or not underlag_id:
            st.error("Du måste välja både dokument och underlag.")
            return
            
        nyttolast = spiris_adapter.bygg_underlagskopplingspayload(underlag_id, dokument_id, dokument_typ)
        
        utkast_dir = st.session_state.get("utkast_dir", "utkast")
        utkast_id = spara_utkast(
            utkast_dir,
            "underlagskoppling",
            nyttolast,
            [
                ["Filnamn", valt_und_str],
                ["Dokumentnummer", valt_dok_str],
                ["DocumentType", dokument_typ]
            ]
        )
        st.success(f"Utkast {utkast_id} skapat!")

