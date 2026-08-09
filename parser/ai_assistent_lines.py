# ISA 450-analysen (Modul 1+2+4+5) och samtalsytan. Båda kräver en fungerande
# AI-konfiguration och blockeras annars tydligt — aldrig ett låtsat svar.

with flik_ai:
    st.header("🤖 AI-Assistent")
    analys_avsnitt, fraga_avsnitt = st.tabs(["Analys (ISA 450)", "Fråga om filen"])

    with analys_avsnitt:
        if sie is None or maskeringsresultat is None:
            st.info("Ladda in data i sidomenyn innan analys kan köras.")
        elif ai_konfiguration is None or ai_konfiguration.status != "modeller_hämtade":
            st.info("Ange en API-nyckel i sidomenyn så laddas modellerna, innan analys kan köras.")
        elif ai_konfiguration.vald_modell is None:
            st.info("Välj en modell i sidomenyn innan analys kan köras.")
        elif not leverantor_har_analysstod(ai_konfiguration.leverantör):
            st.warning(
                f"Analys stöds ännu inte för {ai_konfiguration.leverantör}. "
                "Modellhämtning fungerar redan, men den faktiska analysintegrationen "
                "för den här leverantören är inte byggd än."
            )
        else:
            st.caption(
                f"Analysen körs mot {ai_konfiguration.leverantör}, modell "
                f"{ai_konfiguration.vald_modell} — enligt ditt val i sidomenyn."
            )

            _v = berakna_vasentlighet(sie)

            st.subheader("Väsentlighet (Modul 1)")
            kol_o, kol_r, kol_b, kol_e = st.columns(4)
            kol_o.metric("Omsättning", formatera_kr(_v.omsattning))
            kol_r.metric("Resultat", formatera_kr(_v.resultat))
            kol_b.metric("Balansomslutning", formatera_kr(_v.balansomslutning))
            kol_e.metric("Eget kapital", formatera_kr(_v.eget_kapital))

            _std_väsentlighetstal, _std_utfall = berakna_standardtroskelvarden(_v.omsattning)
            omsattning = _v.omsattning

            st.subheader("Tröskelvärden")
            st.caption(
                "Väsentlighetstalet baseras på omsättningen, utfallsväsentligheten på "
                "väsentlighetstalet. Tänk i procent eller i kronor — systemet räknar om "
                "åt dig. Hovra över ℹ️ för förklaring; värdena styr Modul 5:s ackumulering."
            )
            inmatningslage = st.radio(
                "Inmatningsläge",
                ["Ange i Procent (%)", "Ange i Belopp (kr)"],
                horizontal=True,
            )

            # Oavsett läge slutar vi med två absoluta kr-belopp (Decimal). number_input är
            # en float-gräns (Streamlit); vi går via Decimal(str(...)) och den redan
            # testade tolka_troskelvarden när analysen körs.
            kol_vt, kol_uv = st.columns(2)
            if inmatningslage == "Ange i Procent (%)":
                with kol_vt:
                    procent_vt = st.number_input(
                        "Väsentlighetstal (%)", min_value=0.0, value=0.5, step=0.1,
                        format="%.2f", help=VASENTLIGHETSTAL_HELP,
                    )
                    väsentlighetstal_kr = belopp_fran_procent(Decimal(str(procent_vt)), omsattning)
                    st.caption(
                        f"Motsvarar: {formatera_kr(väsentlighetstal_kr)} (baserat på Omsättning)"
                    )
                with kol_uv:
                    procent_uv = st.number_input(
                        "Utfallsväsentlighet (%)", min_value=0.0, value=75.0, step=1.0,
                        format="%.1f", help=UTFALLSVASENTLIGHET_HELP,
                    )
                    utfallsväsentlighet_kr = belopp_fran_procent(
                        Decimal(str(procent_uv)), väsentlighetstal_kr
                    )
                    st.caption(
                        f"Motsvarar: {formatera_kr(utfallsväsentlighet_kr)} "
                        "(baserat på Väsentlighetstalet)"
                    )
            else:
                with kol_vt:
                    belopp_vt = st.number_input(
                        "Väsentlighetstal (kr)", min_value=0.0, value=float(_std_väsentlighetstal),
                        step=1000.0, format="%.0f", help=VASENTLIGHETSTAL_HELP,
                    )
                    väsentlighetstal_kr = Decimal(str(belopp_vt))
                    st.caption(
                        _procent_caption(
                            procent_fran_belopp(väsentlighetstal_kr, omsattning), "Omsättningen"
                        )
                    )
                with kol_uv:
                    belopp_uv = st.number_input(
                        "Utfallsväsentlighet (kr)", min_value=0.0, value=float(_std_utfall),
                        step=1000.0, format="%.0f", help=UTFALLSVASENTLIGHET_HELP,
                    )
                    utfallsväsentlighet_kr = Decimal(str(belopp_uv))
                    st.caption(
                        _procent_caption(
                            procent_fran_belopp(utfallsväsentlighet_kr, väsentlighetstal_kr),
                            "Väsentlighetstalet",
                        )
                    )

            if st.button("Kör analys"):
                try:
                    utfallsväsentlighet, väsentlighetstal = tolka_troskelvarden(
                        str(utfallsväsentlighet_kr), str(väsentlighetstal_kr)
                    )
                except TröskelvärdeFel as fel:
                    st.session_state.analys_resultat = None
                    st.error(str(fel))
                else:
                    try:
                        # Fynd A: kontoplanen som binds i haiku-anroparen (och
                        # bäddas in i varje analysanrop) ska vara MASKERAD — annars
                        # läcker omdöpta kontonamn ("Lön Anna Andersson") rakt till
                        # AI:n. Kontonr (nyckeln) är oförändrat, så valideringen står.
                        haiku_anropare = bygg_analysanropare(
                            ai_konfiguration,
                            maskeringsresultat.maskerad_siefil.konton,
                            logg=st.session_state.sessionslogg,
                        )
                    except AnalysanropareFel as fel:
                        st.session_state.analys_resultat = None
                        st.error(str(fel))
                    else:
                        st.session_state.analys_resultat = kor_analys(
                            sie, maskeringsresultat, haiku_anropare,
                            utfallsväsentlighet, väsentlighetstal,
                        )
                        # Art. 30-stöd (svaghet 3): logga metadata om AI-utflödet
                        # — tidpunkt, mottagare, datakategorier, maskeringsstatistik.
                        # Aldrig nyttolasten själv.
                        revisionslogg.logga_ai_utflode(
                            ai_konfiguration.leverantör, ai_konfiguration.vald_modell,
                            "analys",
                            datakategorier=[
                                "kontoplan", "sandningsbara_verifikationer",
                                "väsentlighetstal",
                            ],
                            maskeringsstatistik=(
                                revisionslogg.maskeringsstatistik_fran_resultat(
                                    maskeringsresultat
                                )
                            ),
                        )

        # Läs om: knapptrycket ovan kan just ha satt ETT nytt resultat eller
        # nollställt det. Frågefliken nedan läser samma variabel.
        analys_resultat = st.session_state.analys_resultat
        if analys_resultat is not None:
            if analys_resultat.felmeddelande is not None:
                st.error(analys_resultat.felmeddelande)
            else:
                st.success("Analys klar.")
                ack = analys_resultat.ackumulering
                kol1, kol2, kol3, kol4 = st.columns(4)
                kol1.metric(
                    "Nettosumma", formatera_kr(ack.summa_netto),
                    delta=ack.status_netto, delta_color="off",
                )
                kol2.metric(
                    "Bruttosumma", formatera_kr(ack.summa_brutto),
                    delta=ack.status_brutto, delta_color="off",
                )
                kol3.metric("Antal felaktigheter", ack.antal_felaktigheter)
                kol4.metric("Okänd riktning", ack.antal_okänd_riktning)

                if ack.felaktigheter:
                    st.dataframe(
                        [
                            {
                                "Källa": f.källa,
                                "Belopp": str(f.belopp),
                                "Riktning": f.riktning,
                                "Konto": f.kontonr,
                                "Kontonamn": f.kontonamn,
                                "Motivering": f.motivering,
                                "Plats": f.plats or "",
                            }
                            for f in ack.felaktigheter
                        ]
                    )
                else:
                    st.write("Inga felaktigheter identifierade.")

    with fraga_avsnitt:
        st.write(
            "Ställ frågor på svenska om bolaget och analysen. Svaren bygger bara på "
            "det som redan är känt i den här sessionen — filens översikt, och den "
            "körda ISA 450-analysen om den finns. I fil-läge besvaras varje fråga "
            "för sig (ingen historik skickas med AI:t). Kopplad till Spiris kommer "
            "assistenten även ihåg samtalet, så att den kan ställa en förtydligande "
            "flervalsfråga (t.ex. om momstyp) och slutföra uppgiften utifrån ditt svar."
        )

        if sie is None or maskeringsresultat is None:
            st.info("Ladda in data i sidomenyn för att kunna ställa frågor.")
        elif ai_konfiguration is None or ai_konfiguration.status != "modeller_hämtade":
            st.info(
                "Ange en API-nyckel i sidomenyn så laddas modellerna, för att kunna "
                "ställa frågor."
            )
        elif ai_konfiguration.vald_modell is None:
            st.info("Välj en modell i sidomenyn för att kunna ställa frågor.")
        elif not leverantor_har_samtalsstod(ai_konfiguration.leverantör):
            st.warning(
                f"Samtal stöds ännu inte för {ai_konfiguration.leverantör}. "
                "Modellhämtning fungerar redan, men samtalsintegrationen för den "
                "här leverantören är inte byggd än."
            )
        else:
            har_lyckad_analys = analys_resultat is not None and analys_resultat.felmeddelande is None
            if not har_lyckad_analys:
                st.caption(
                    "Ingen ISA 450-analys tillgänglig ännu — svaren kan bara bygga på "
                    "filens grundöversikt. Kör analysen i fliken Analys (ISA 450) för "
                    "utförligare svar."
                )
            else:
                st.caption("Svaren bygger på filens översikt och den körda ISA 450-analysen.")

                # Litet visuellt stöd: samma status_netto/status_brutto som redan
                # visas i analysfliken, bara mappade till en snabb, läsbar signal
                # här också — ingen ny beräkning.
                risksammanfattning = bygg_risksammanfattning(analys_resultat.ackumulering)
                risk_kol1, risk_kol2, risk_kol3 = st.columns(3)
                risk_kol1.metric("Netto", risksammanfattning.emoji_netto)
                risk_kol2.metric("Brutto", risksammanfattning.emoji_brutto)
                risk_kol3.metric("Granskningssignal", risksammanfattning.etikett)

            svarsläge = st.radio(
                "Svarsstil", options=SVARSLÄGEN, index=SVARSLÄGEN.index("pedagogisk"),
                horizontal=True,
            )

            st.write("Föreslagna frågor:")
            exempel_fraga: str | None = None
            for rad_start in range(0, len(FÖRESLAGNA_FRÅGOR), 3):
                rad_frågor = FÖRESLAGNA_FRÅGOR[rad_start : rad_start + 3]
                for kolumn, föreslagen_fråga in zip(st.columns(3), rad_frågor):
                    if kolumn.button(föreslagen_fråga.etikett):
                        exempel_fraga = föreslagen_fråga.fråga

            # Fas 8: "Skapa kundfaktura" — enda skriv-kapabla ytan i chatten,
            # kräver därför en live Spiris-koppling (till skillnad från
            # resten av fliken, som bara läser). Döljs helt i fil-läge.
            if datakälla == "Koppla till Spiris" and st.session_state.spiris_tokens is not None:
                if st.session_state.aktivt_fakturautkast is None and st.button(
                    "📄 Skapa kundfaktura"
                ):
                    st.session_state.aktivt_fakturautkast = {"fas": "formular"}
                    st.rerun()

            # Agentläget (Tool Calling, Fas 9) kräver en live Spiris-koppling
            # — verktygen föreslår bara Spiris-åtgärder, och utan en
            # koppling finns inget de kan leda till. I fil-läge faller
            # frågan tillbaka till den vanliga, verktygsfria chattanroparen
            # precis som innan Fas 9 fanns — och behåller DÅ det medvetna
            # engångsminnet (se samtalsflode.ställ_fraga:s docstring).
            agentlage = (
                datakälla == "Koppla till Spiris" and st.session_state.spiris_tokens is not None
            )

            # --- Fas 10, steg A: generera ett svar om senaste meddelandet i
            # historiken är ett ÄNNU obesvarat användarmeddelande.
            # samtal_senast_behandlat gör detta idempotent — se dess
            # kommentar vid session-state-initieringen för varför det krävs
            # (aktivt_fakturautkast rerunnar flera gånger på egen hand medan
            # ett utkast granskas, UTAN att lägga något nytt i historiken).
            if (
                st.session_state.samtal_historik
                and st.session_state.samtal_historik[-1].roll == "user"
                and len(st.session_state.samtal_historik) - 1
                > st.session_state.samtal_senast_behandlat
            ):
                st.session_state.samtal_senast_behandlat = (
                    len(st.session_state.samtal_historik) - 1
                )
                # Fynd B + M1: användarens meddelande maskeras (liggare +
                # deterministiska lager + Lager 3a) INNAN det når AI:t — den
                # lagrade historiken (som visas lokalt) rörs inte, bara kopian
                # som skickas iväg. Ett OKÄNT namn (Lager 3b) som inte kunde
                # avidentifieras BLOCKERAR sändningen (fail-closed): meddelandet
                # skickas aldrig i klartext, utan avgörs lokalt i fliken
                # Åtgärder. Den råa misstänkta texten lämnar aldrig datorn.
                senaste_maskering = maskera_chattmeddelande(
                    st.session_state.samtal_historik[-1].text,
                    st.session_state.maskeringsliggare,
                    st.session_state.namnreferens,
                )
                senaste_fraga = senaste_maskering.text
                kontext = bygg_saker_kontext(
                    sie, maskeringsresultat, analys_resultat,
                    reskontra=st.session_state.spiris_reskontra,
                    kundreskontra=st.session_state.spiris_kundreskontra,
                    likviditetsprognos=likviditetsprognos,
                )
                # Art. 30-stöd (svaghet 3): logga chatt-/agent-utflödets metadata
                # — men bara när något FAKTISKT lämnar datorn (ej vid blockering).
                _chatt_kategorier = ["filöversikt", "kontosaldon", "användarfråga"]
                if st.session_state.spiris_reskontra or st.session_state.spiris_kundreskontra:
                    _chatt_kategorier.append("reskontra")
                if analys_resultat is not None and analys_resultat.felmeddelande is None:
                    _chatt_kategorier.append("ackumuleringsresultat")

                def _logga_utflode() -> None:
                    revisionslogg.logga_ai_utflode(
                        ai_konfiguration.leverantör, ai_konfiguration.vald_modell,
                        "agent" if agentlage else "samtal",
                        datakategorier=_chatt_kategorier,
                        maskeringsstatistik=revisionslogg.maskeringsstatistik_fran_resultat(
                            maskeringsresultat
                        ),
                    )

                if senaste_maskering.blockerad:
                    # Fail-closed: skicka inget. Notisen får INTE innehålla det
                    # misstänkta namnet — ett assistentmeddelande återsänds till
                    # agenten i varje tur, så namnet skulle annars läcka den vägen.
                    st.session_state.samtal_historik.append(ChattMeddelande(
                        roll="assistant",
                        text=(
                            "⚠️ Meddelandet innehåller ett eller flera namn som jag "
                            "inte säkert kan avidentifiera, så det skickades inte "
                            "vidare (fail-closed). Granska namnet lokalt i fliken "
                            "🔴/🟢 Åtgärder, eller skriv om meddelandet utan namnet."
                        ),
                    ))
                elif not agentlage:
                    _logga_utflode()
                    try:
                        anropare = bygg_chattanropare(
                            ai_konfiguration, logg=st.session_state.sessionslogg
                        )
                        svar = ställ_fraga(senaste_fraga, kontext, anropare, svarsläge=svarsläge)
                    except SamtalanropareFel as fel:
                        svar = str(fel)
                    # Fil-läget har ingen tool use att luta sig mot: modellen
                    # ombeds i systemprompten svara med JSON när svaret är en
                    # lista/tabell (se svarskontrakt.KONTRAKT_INSTRUKTION).
                    # Är svaret vanlig text — eller JSON som inte följer
                    # kontraktet — ger validera_svar None och meddelandet
                    # sparas precis som förut. Ingen felruta, tyst fallback.
                    strukturerat = validera_svar(svar)
                    if strukturerat is None:
                        st.session_state.samtal_historik.append(
                            ChattMeddelande(roll="assistant", text=svar)
                        )
                    else:
                        st.session_state.samtal_historik.append(ChattMeddelande(
                            roll="assistant",
                            # Rå JSON får aldrig bli .text — den skulle visas
                            # om renderingen faller tillbaka.
                            text=text_sammanfattning(strukturerat),
                            strukturerat=strukturerat.model_dump(),
                        ))
                else:
                    _logga_utflode()
                    try:
                        anropare = bygg_agentanropare(
                            ai_konfiguration, logg=st.session_state.sessionslogg
                        )
                    except SamtalanropareFel as fel:
                        st.session_state.samtal_historik.append(
                            ChattMeddelande(roll="assistant", text=str(fel))
                        )
                    else:
                        # Fynd B + M1: maskera varje ANVÄNDARmeddelande innan hela
                        # historiken skickas om till agenten (Anthropics API är
                        # statslöst — historiken återsänds vid varje anrop, så en
                        # omaskerad rad skulle läcka i varje efterföljande tur).
                        # Ett historiskt meddelande med ett okänt namn (Lager 3b)
                        # ersätts med en neutral platshållare — det får aldrig
                        # återsändas i klartext (fail-closed även bakåt i
                        # historiken). Assistentmeddelanden är modellgenererade ur
                        # redan maskerad kontext och lämnas orörda.
                        api_meddelanden = []
                        for m in st.session_state.samtal_historik:
                            if m.roll != "user":
                                api_meddelanden.append({"roll": m.roll, "text": m.text})
                                continue
                            _mask = maskera_chattmeddelande(
                                m.text, st.session_state.maskeringsliggare,
                                st.session_state.namnreferens,
                            )
                            api_meddelanden.append({
                                "roll": m.roll,
                                "text": (
                                    "[meddelande kunde inte avidentifieras – utelämnat]"
                                    if _mask.blockerad else _mask.text
                                ),
                            })
                        agentsvar = ställ_fraga_till_agent(
                            api_meddelanden, kontext, anropare, svarsläge=svarsläge
                        )
                        if (
                            agentsvar.verktygsanrop is not None
                            and agentsvar.verktygsanrop.namn == "efterfraga_val"
                        ):
                            try:
                                valfraga = tolka_valverktygsanrop(
                                    agentsvar.verktygsanrop.indata
                                )
                            except ValueError as fel:
                                st.session_state.samtal_historik.append(ChattMeddelande(
                                    roll="assistant",
                                    text=f"⚠️ Kunde inte tolka AI:ts förfrågan: {fel}",
                                ))
                            else:
                                st.session_state.samtal_historik.append(ChattMeddelande(
                                    roll="assistant", text=valfraga.fraga,
                                    alternativ=valfraga.alternativ,
                                ))
                        elif (
                            agentsvar.verktygsanrop is not None
                            and agentsvar.verktygsanrop.namn == "presentera_strukturerat_svar"
                        ):
                            # Rent presentationsverktyg — inget utkast, ingen
                            # POST, ingen rerun. Egen gren (i stället för i
                            # kedjan nedan) för att modellens ev. kommentar och
                            # tabellen ska bli ETT meddelande, inte två bubblor.
                            strukturerat = validera_svar_dict(
                                agentsvar.verktygsanrop.indata
                            )
                            if strukturerat is None:
                                st.session_state.samtal_historik.append(ChattMeddelande(
                                    roll="assistant",
                                    text=agentsvar.text or (
                                        "⚠️ AI:t skickade ett strukturerat svar som inte "
                                        "kunde tolkas."
                                    ),
                                ))
                            else:
                                strukturerat = med_inledande_text(
                                    strukturerat, agentsvar.text
                                )
                                st.session_state.samtal_historik.append(ChattMeddelande(
                                    roll="assistant",
                                    # .text är vad agenten får se av sitt eget
                                    # svar i nästa varv (historiken återsänds)
                                    # — och fallback om renderingen fallerar.
                                    text=text_sammanfattning(strukturerat),
                                    strukturerat=strukturerat.model_dump(),
                                ))
                        else:
                            if agentsvar.text:
                                st.session_state.samtal_historik.append(
                                    ChattMeddelande(roll="assistant", text=agentsvar.text)
                                )
                            if agentsvar.verktygsanrop is None:
                                pass
                            elif agentsvar.verktygsanrop.namn == "skapa_kund":
                                try:
                                    förslag = tolka_kundverktygsanrop(
                                        agentsvar.verktygsanrop.indata
                                    )
                                except ValueError as fel:
                                    st.session_state.samtal_historik.append(ChattMeddelande(
                                        roll="assistant",
                                        text=f"⚠️ Kunde inte tolka AI:ts förslag: {fel}",
                                    ))
                                else:
                                    st.session_state.aktivt_fakturautkast = {
                                        "typ": "kund", "fas": "sok_kund",
                                        "kundnamn": förslag.kundnamn,
                                        "ar_privatperson": förslag.ar_privatperson,
                                    }
                                    st.rerun()
                            elif agentsvar.verktygsanrop.namn == "skapa_kundfaktura":
                                try:
                                    faktura_tillstand = tolka_fakturaverktygsanrop(
                                        agentsvar.verktygsanrop.indata
                                    )
                                except ValueError as fel:
                                    st.session_state.samtal_historik.append(ChattMeddelande(
                                        roll="assistant",
                                        text=f"⚠️ Kunde inte tolka AI:ts förslag: {fel}",
                                    ))
                                else:
                                    st.session_state.aktivt_fakturautkast = {
                                        "typ": "faktura", "fas": "sok_kund", **faktura_tillstand,
                                    }
                                    st.rerun()
                            else:
                                st.session_state.samtal_historik.append(ChattMeddelande(
                                    roll="assistant",
                                    text=(
                                        f"⚠️ AI:t begärde ett okänt verktyg: "
                                        f"{agentsvar.verktygsanrop.namn!r} — ignorerat."
                                    ),
                                ))

            # --- Fas 10, steg B: rendera HELA historiken via
            # st.chat_message. Ett interaktivt flerval (alternativ satt)
            # renderas bara som knappar om det är det ALLRA SISTA
            # meddelandet — annars är det redan besvarat (nästa post i
            # listan ÄR svaret).
            # Ett svar med strukturerat innehåll (fas 11) renderas av
            # chatt_renderare i stället för st.write. Går det inte att tolka
            # visas meddelandets vanliga text — samma fail-closed-princip som
            # i resten av chattkedjan.
            for i, meddelande in enumerate(st.session_state.samtal_historik):
                with st.chat_message(meddelande.roll):
                    renderat = False
                    # getattr, inte meddelande.strukturerat: ett meddelande som
                    # redan låg i session_state när koden laddades om är en
                    # instans av den GAMLA dataklassen, utan fältet (defaulten
                    # blir ett klassattribut — men bara på den nya klassen).
                    # Utan skyddet kraschar hela chatten tills processen startas
                    # om. Gamla meddelanden renderas som den text de alltid var.
                    if getattr(meddelande, "strukturerat", None):
                        renderat = rendera_strukturerat_svar(
                            meddelande.strukturerat, meddelande_index=i
                        )
                    if not renderat:
                        st.write(meddelande.text)
                    sista = i == len(st.session_state.samtal_historik) - 1
                    if sista and meddelande.alternativ:
                        _rendera_valknappar(meddelande.alternativ)

            # --- Fas 10, steg C: ny indata. st.chat_input ger inbyggd
            # autoscroll/Enter-hantering; en föreslagen fråga (ovan) räknas
            # som samma sak. BÅDA lägger bara till meddelandet i historiken
            # och kör st.rerun() — steg A ovan gör (näst gång) det faktiska
            # AI-anropet, precis som ett knapptryck i steg B:s valknappar.
            ny_fraga = st.chat_input("Din fråga")
            vald_fraga = exempel_fraga or ny_fraga
            if vald_fraga:
                st.session_state.samtal_historik.append(
                    ChattMeddelande(roll="user", text=vald_fraga)
                )
                st.rerun()

