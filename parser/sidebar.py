# All Streamlit-specifik OAuth-koreografi ligger tunt här; den testbara
# logiken (URL-bygge, kodextraktion, tokenväxling) bor i spiris_auth_vy.py.

with st.sidebar:
    st.header("Inställningar")
    rendera_verktygsrad(st)
    datakälla = st.radio(
        "Datakälla",
        ("Ladda upp lokal SIE4-fil", "Koppla till Spiris"),
        key="datakälla_val",
    )

    if datakälla != st.session_state.aktiv_datakälla:
        st.session_state.aktiv_datakälla = datakälla
        _nollstall_inlast_data()

    spiris_client_id = ""
    spiris_client_secret = ""
    if datakälla == "Koppla till Spiris":
        st.subheader("Spiris")
        # Förifyll från .env (gitignorerad) och persistera vid ändring.
        if "spiris_client_id" not in st.session_state:
            st.session_state.spiris_client_id = config.spiris_client_id
        if "spiris_client_secret" not in st.session_state:
            st.session_state.spiris_client_secret = config.spiris_client_secret
        spiris_client_id = st.text_input("Client ID", key="spiris_client_id")
        spiris_client_secret = st.text_input(
            "Client Secret", type="password", key="spiris_client_secret"
        )
        app_config.spara_om_andrad("spiris_client_id", spiris_client_id, config)
        app_config.spara_om_andrad("spiris_client_secret", spiris_client_secret, config)
        st.caption("Sparas lokalt i .env (gitignorerad) — committas aldrig.")
        if st.session_state.spiris_tokens is not None and st.button("Logga ut från Spiris"):
            st.session_state.spiris_tokens = None
            st.session_state.spiris_state = None
            _nollstall_inlast_data()
            st.rerun()

    # --- Datainhämtning ------------------------------------------------------
    st.divider()
    st.subheader("Data")

    if datakälla == "Ladda upp lokal SIE4-fil":
        uppladdad_fil = st.file_uploader("Ladda upp en SIE4-fil", type=["se", "si", "txt"])

        if uppladdad_fil is not None:
            st.caption(f"Fil: {uppladdad_fil.name}")

            # Läs och maskera BARA när filen faktiskt är ny (nytt file_id från
            # Streamlit). Samma fil kvar i uppladdaren över en omkörning (t.ex.
            # ett klick i en flik) får aldrig läsa om filen: det hade kastat bort
            # ett giltigt analysresultat OCH det granskade maskeringsresultatet,
            # och gjort varje interaktion onödigt dyr.
            if uppladdad_fil.file_id != st.session_state.behandlad_fil_id:
                st.session_state.behandlad_fil_id = uppladdad_fil.file_id
                st.session_state.analys_resultat = None
                _nollstall_samtalshistorik()
                st.session_state.datastatus_notiser = []

                with tempfile.NamedTemporaryFile(delete=False, suffix=".se") as temp:
                    temp.write(uppladdad_fil.getvalue())
                    temp_sökväg = temp.name

                inläsningsresultat = läs_och_maskera_fil(
                    temp_sökväg,
                    liggare=st.session_state.maskeringsliggare,
                    undantagslista=app_config.normaliserade_undantag(
                        st.session_state.undantagslista
                    ),
                    referenslista=st.session_state.namnreferens,
                )
                Path(temp_sökväg).unlink(missing_ok=True)

                if inläsningsresultat.felmeddelande is not None:
                    st.session_state.sie = None
                    st.session_state.maskeringsresultat = None
                    _notera("error", inläsningsresultat.felmeddelande)
                else:
                    st.session_state.sie = inläsningsresultat.sie
                    st.session_state.maskeringsresultat = inläsningsresultat.maskeringsresultat
                    _notera("success", f"Läste och maskerade {uppladdad_fil.name}.")

    elif not spiris_client_id or not spiris_client_secret:
        st.info("Ange Client ID och Client Secret ovan för att logga in mot Spiris.")

    elif st.session_state.spiris_tokens is None:
        # Inte inloggad än — generera state EN gång (överlever reruns) och
        # visa inloggningslänk + inklistringsfält.
        if st.session_state.spiris_state is None:
            st.session_state.spiris_state = generera_state()
            # PKCE-paret genereras i samma veva och överlever reruns.
            verifierare, _challenge = generera_pkce()
            st.session_state.spiris_code_verifier = verifierare
            st.session_state.spiris_code_challenge = _challenge
        auktoriserings_url = bygg_auktoriserings_url(
            spiris_client_id, REDIRECT_URI, st.session_state.spiris_state,
            code_challenge=st.session_state.get("spiris_code_challenge"),
        )
        st.markdown(f"**Steg 1.** [Logga in och godkänn åtkomst hos Spiris]({auktoriserings_url})")
        st.caption(
            "Efter godkännandet skickas du till en localhost-adress som inte laddar "
            "— det är meningen. Kopiera hela adressen ur webbläsarens adressfält."
        )
        inklistrad = st.text_input(
            "**Steg 2.** Klistra in adressen (eller bara koden):",
            key="spiris_redirect_inmatning",
        )
        if st.button("Slutför inloggning"):
            try:
                kod = extrahera_kod(inklistrad, förväntat_state=st.session_state.spiris_state)
                st.session_state.spiris_tokens = vaxla_kod_mot_token(
                    kod, spiris_client_id, spiris_client_secret,
                    code_verifier=st.session_state.spiris_code_verifier,
                )
            except SpirisAuthFel as fel:
                st.error(str(fel))
            else:
                # Rensa redirect-/kodfältet efter avslutad tokenväxling — den
                # inklistrade adressen bär en engångskod och ska inte ligga kvar.
                st.session_state.pop("spiris_redirect_inmatning", None)
                st.rerun()

    else:
        # Inloggad — välj räkenskapsår och hämta.
        st.success("Inloggad mot Spiris.")

        # B2.4-B: tunn glue. Tokens lever i session_state; persistens sker ENDAST
        # på uttrycklig begäran nedan (aldrig automatiskt). Domänlogiken (DPAPI +
        # guard + verifiering) ligger i spiris_session — här visas bara neutral,
        # tokenfri status.
        _kol_spara, _kol_ut = st.columns(2)
        if _kol_spara.button("Spara session för MCP-servern"):
            _res = spiris_session.persist_session(st.session_state.spiris_tokens)
            if _res.sparad:
                st.success("Sessionen sparades lokalt för MCP-servern.")
            else:
                st.error(f"Sessionen kunde inte sparas (status: {_res.statuskod}).")
        if _kol_ut.button("Logga ut"):
            spiris_session.radera_session()
            st.session_state.spiris_tokens = None
            st.session_state.spiris_state = None
            st.session_state.spiris_code_verifier = None
            st.session_state.spiris_code_challenge = None
            st.rerun()

        spiris_klient = SpirisKlient(
            access_token=st.session_state.spiris_tokens.access_token,
            refresh_token=st.session_state.spiris_tokens.refresh_token,
            client_id=spiris_client_id,
            client_secret=spiris_client_secret,
        )
        try:
            räkenskapsår = spiris_klient.hamta_alla("/fiscalyears")
        except SpirisKlientFel as fel:
            st.error(str(fel))
            räkenskapsår = []
        # En eventuell token-refresh under anropet ska överleva nästa rerun.
        st.session_state.spiris_tokens = SpirisTokens(
            spiris_klient.access_token, spiris_klient.refresh_token
        )

        if räkenskapsår:
            etiketter = {
                f"{str(f.get('StartDate'))[:10]} – {str(f.get('EndDate'))[:10]}": f
                for f in räkenskapsår
            }
            # Auto-välj innevarande räkenskapsår (datetime.now().year) som default.
            _labels = list(etiketter.keys())
            _innevarande = valj_rakenskapsar_for_ar(räkenskapsår, datetime.now().year)
            _default_idx = 0
            if _innevarande is not None:
                for _i, _f in enumerate(etiketter.values()):
                    if _f is _innevarande:
                        _default_idx = _i
                        break
            valt_år = st.selectbox("Räkenskapsår", _labels, index=_default_idx)
            valt = etiketter[valt_år]
            st.caption(f"Räkenskapsår-id (för MCP-verktyg): {valt['Id']}")

            # Auto-hämta + maskera så fort ett år är valt. Dedup: hämta bara en
            # gång per år-Id — vakten sätts FÖRE hämtningen så en rerun (eller ett
            # fel) aldrig utlöser en ny hämtning i loop.
            if st.session_state.spiris_hamtat_ar != valt["Id"]:
                st.session_state.spiris_hamtat_ar = valt["Id"]
                st.session_state.datastatus_notiser = []
                with st.spinner("Hämtar och maskerar data från Spiris…"):
                    try:
                        sie_rå = hamta_siefil_fran_spiris(
                            spiris_klient, valt["Id"], str(valt["EndDate"])[:10]
                        )
                    except SpirisKlientFel as fel:
                        _notera("error", str(fel))
                    else:
                        # Maskeringsminne: hoppa över redan granskade verifikat.
                        _sedda = las_maskeringsminne()
                        _antal_fore = len(sie_rå.verifikationer)
                        sie_rå = replace(
                            sie_rå,
                            verifikationer=filtrera_bort_sedda(sie_rå.verifikationer, _sedda),
                        )
                        _antal_bortfiltrerade = _antal_fore - len(sie_rå.verifikationer)
                        if _antal_bortfiltrerade:
                            _notera(
                                "caption",
                                f"{_antal_bortfiltrerade} verifikat filtrerades bort "
                                "(redan granskade enligt maskeringsminnet).",
                            )
                        st.session_state.spiris_tokens = SpirisTokens(
                            spiris_klient.access_token, spiris_klient.refresh_token
                        )
                        # Ingen omaskerad data når flikarna: samma sekretesslager
                        # och InläsningsResultat-kontrakt som filvägen. Liggaren
                        # pre-maskerar redan lärda namn innan maskera_siefil.
                        inläsningsresultat = maskera_inlast_siefil(
                            sie_rå,
                            liggare=st.session_state.maskeringsliggare,
                            undantagslista=app_config.normaliserade_undantag(
                                st.session_state.undantagslista
                            ),
                            referenslista=st.session_state.namnreferens,
                        )
                        if inläsningsresultat.felmeddelande is not None:
                            st.session_state.sie = None
                            st.session_state.maskeringsresultat = None
                            _notera("error", inläsningsresultat.felmeddelande)
                        else:
                            st.session_state.analys_resultat = None
                            _nollstall_samtalshistorik()
                            st.session_state.sie = inläsningsresultat.sie
                            st.session_state.maskeringsresultat = inläsningsresultat.maskeringsresultat
                            # Leverantörs-/kundreskontra (Fas C/D): GDPR-tvättade,
                            # var ledger fail-closed för sig.
                            try:
                                st.session_state.spiris_reskontra = hamta_reskontra(spiris_klient)
                            except SpirisKlientFel:
                                st.session_state.spiris_reskontra = None
                                _notera(
                                    "caption",
                                    "Leverantörsreskontran kunde inte hämtas "
                                    "(kräver ea:purchase-behörighet) — övrig analys "
                                    "påverkas inte.",
                                )
                            try:
                                st.session_state.spiris_kundreskontra = hamta_kundreskontra(
                                    spiris_klient
                                )
                            except SpirisKlientFel:
                                st.session_state.spiris_kundreskontra = None
                                _notera(
                                    "caption",
                                    "Kundreskontran kunde inte hämtas — övrig analys "
                                    "påverkas inte.",
                                )
                            # Betalhistorik (Fas 6b): underlag för likviditets-
                            # prognosens kundbetalbeteende. Fail-closed för sig —
                            # misslyckas den, faller bygg_likviditetsprognos
                            # tillbaka till ojusterade förfallodatum (samma som
                            # innan den här kopplingen fanns), inte en krasch.
                            try:
                                st.session_state.spiris_kundbetalhistorik = (
                                    hamta_kundbetalhistorik(spiris_klient)
                                )
                            except SpirisKlientFel:
                                st.session_state.spiris_kundbetalhistorik = None
                                _notera(
                                    "caption",
                                    "Kundernas betalhistorik kunde inte hämtas — "
                                    "likviditetsprognosen justerar då inte för "
                                    "betalbeteende.",
                                )
                            st.session_state.spiris_tokens = SpirisTokens(
                                spiris_klient.access_token, spiris_klient.refresh_token
                            )
                            _notera(
                                "success",
                                f"Hämtade och maskerade {len(sie_rå.verifikationer)} "
                                "verifikationer automatiskt från Spiris.",
                            )

            # --- Rapportperiod: FP&A-dashboarden live mot Spiris --------------
            # Datumväljaren defaultar till innevarande kalenderår; datat hämtas
            # automatiskt när perioden ändras (dedup via period-id, vakt före
            # hämtning → ingen loop). Fel/tom period fångas snyggt.
            st.markdown("**Rapportperiod**")
            _fpa_start, _fpa_slut = innevarande_ar_intervall()
            if "fpa_startdatum" not in st.session_state:
                st.session_state.fpa_startdatum = _fpa_start
            if "fpa_slutdatum" not in st.session_state:
                st.session_state.fpa_slutdatum = _fpa_slut
            fpa_startdatum = st.date_input("Startdatum", key="fpa_startdatum")
            fpa_slutdatum = st.date_input("Slutdatum", key="fpa_slutdatum")

            _period_id = (str(fpa_startdatum), str(fpa_slutdatum))
            if st.session_state.spiris_dashboard_period != _period_id:
                st.session_state.spiris_dashboard_period = _period_id
                with st.spinner("Hämtar FP&A-dashboard live från Spiris…"):
                    try:
                        _fpa_data = asyncio.run(
                            spiris_rag.hamta_dashboard(spiris_klient, *_period_id)
                        )
                    except Exception as fel:  # noqa: BLE001 — visa aldrig rå traceback
                        print(
                            f"[sie-mcp] Fel vid FP&A-hämtning från Spiris: {fel!r}",
                            file=sys.stderr,
                        )
                        st.session_state.spiris_dashboarddata = None
                        _notera_period(
                            "warning",
                            "Kunde inte hämta FP&A-data från Spiris för vald period. "
                            "Ändra datumintervallet för att försöka igen.",
                        )
                    else:
                        st.session_state.spiris_tokens = SpirisTokens(
                            spiris_klient.access_token, spiris_klient.refresh_token
                        )
                        if dashboard_saknar_data(_fpa_data):
                            st.session_state.spiris_dashboarddata = None
                            _notera_period(
                                "info",
                                "Sandboxen saknar bokförd data för vald period. Ändra "
                                "datumintervallet (t.ex. ett helt räkenskapsår).",
                            )
                        else:
                            st.session_state.spiris_dashboarddata = _fpa_data
                            _notera_period(
                                "success", "FP&A-dashboard hämtad automatiskt från Spiris."
                            )

    # --- AI-inställningar (alltid synlig, oavsett datakälla) ------------------
    # Automatiserad: när en API-nyckel finns hämtas modeller i bakgrunden (dedup
    # via ai_modeller_for → ingen loop). Leverantör, nyckel och senast valda
    # modell förifylls från .env och persisteras vid ändring.
    st.divider()
    st.subheader("AI-inställningar")

    if "ai_leverantör_val" not in st.session_state:
        st.session_state.ai_leverantör_val = (
            config.ai_leverantör if config.ai_leverantör in LEVERANTÖRER else LEVERANTÖRER[0]
        )
    vald_leverantör = st.selectbox("Leverantör", LEVERANTÖRER, key="ai_leverantör_val")

    if vald_leverantör == "Ollama":
        st.markdown("**Lokal AI (Ollama)**")
        st.caption(
            "Körs helt lokalt mot http://localhost:11434 — ingen API-nyckel, "
            "ingen data lämnar datorn. Kräver att Ollama är installerat och "
            "igång, samt att önskad modell är hämtad (kommandot nedan)."
        )
        st.caption("🔒 **100 % lokal körning — Ingen data lämnar datorn, ingen tredjelandsöverföring (GDPR-optimalt)**")
        st.markdown(
            "| Profil | Modell | Kommando | Kommentar |\n"
            "|---|---|---|---|\n"
            "| Snabb och lätt | [Phi-4-mini](https://ollama.com/library/phi4-mini) "
            "| `ollama run phi4-mini` | Enklare frågor, sammanfattning, svagare laptops |\n"
            "| Rekommenderad balans | [Qwen3 8B](https://ollama.com/library/qwen3:8b) "
            "| `ollama run qwen3:8b` | Standardval för svensk ekonomiassistans, "
            "resonemang, strukturerade svar |\n"
            "| Stabil allround | [Llama 3.1 8B](https://ollama.com/library/llama3.1:8b) "
            "| `ollama run llama3.1:8b` | Välkänt, brett ekosystem |\n"
            "| Strukturerad analys | [IBM Granite 3.2 8B](https://ollama.com/ibm/granite3.2:8b) "
            "| `ollama run ibm/granite3.2:8b` | RAG, dokumentarbete, verktygsanrop, "
            "regelstyrda flöden |\n"
            "| Kraftfull lokal analys | [Mistral-Nemo 12B](https://ollama.com/library/mistral-nemo:12b) "
            "| `ollama run mistral-nemo:12b` | Starkare datorer; 128k kontextfönster |\n"
        )
        api_nyckel = ""
    else:
        st.caption(
            f"🌐 **Molnbaserad AI (USA)** — Externa anrop sker under ditt eget avtal med "
            f"**{vald_leverantör}** (BYOK). Du ansvarar för ditt DPA och laglig grund "
            "(se [DISCLAIMER_AND_TERMS.md](file:///DISCLAIMER_AND_TERMS.md))."
        )
        if "ai_api_nyckel_val" not in st.session_state:
            st.session_state.ai_api_nyckel_val = config.ai_api_nyckel
        api_nyckel = st.text_input("API-nyckel", type="password", key="ai_api_nyckel_val")

    app_config.spara_om_andrad("ai_leverantör", vald_leverantör, config)
    app_config.spara_om_andrad("ai_api_nyckel", api_nyckel, config)

    # Auto-hämta modeller när nyckel finns (eller när leverantören inte
    # kräver någon, dvs. Ollama); vakten sätts FÖRE hämtningen.
    _kraver_nyckel = vald_leverantör != "Ollama"
    _ai_id = (vald_leverantör, api_nyckel)
    if (api_nyckel or not _kraver_nyckel) and st.session_state.ai_modeller_for != _ai_id:
        st.session_state.ai_modeller_for = _ai_id
        with st.spinner("Hämtar modeller…"):
            st.session_state.ai_konfiguration = uppdatera_med_hamtade_modeller(
                AIKonfiguration(leverantör=vald_leverantör, api_nyckel=api_nyckel)
            )
    elif not api_nyckel and _kraver_nyckel:
        st.session_state.ai_konfiguration = None
        st.session_state.ai_modeller_for = None

    ai_konfiguration = st.session_state.ai_konfiguration
    if ai_konfiguration is None:
        st.caption("Ange en API-nyckel så laddas modellerna automatiskt.")
    elif ai_konfiguration.status == "modeller_hämtade":
        _modeller = ai_konfiguration.tillgängliga_modeller
        _def_idx = _modeller.index(config.ai_vald_modell) if config.ai_vald_modell in _modeller else 0
        vald_modell = st.selectbox("Modell", _modeller, index=_def_idx)
        if vald_modell != ai_konfiguration.vald_modell:
            ai_konfiguration = replace(ai_konfiguration, vald_modell=vald_modell)
            st.session_state.ai_konfiguration = ai_konfiguration
        app_config.spara_om_andrad("ai_vald_modell", vald_modell, config)
    elif ai_konfiguration.status == "fel":
        st.error(f"Kunde inte hämta modeller: {ai_konfiguration.felmeddelande}")

    if st.button("Glöm sparade uppgifter"):
        app_config.rensa_config()
        for _k in (
            "spiris_client_id", "spiris_client_secret", "ai_leverantör_val",
            "ai_api_nyckel_val", "ai_modeller_for", "ai_konfiguration",
        ):
            st.session_state.pop(_k, None)
        st.rerun()

    _antal_larda = len(st.session_state.maskeringsliggare)
    st.caption(f"Maskeringsminne: {_antal_larda} inlärda namn (krypterat lokalt).")
    if st.button("Töm maskeringsminne"):
        app_config.tom_maskeringsliggare()
        st.session_state.maskeringsliggare = {}
        st.rerun()

    # Undantagslistan är den enda mekanismen som TYSTAR sekretesslagret. Den
    # måste därför alltid gå att inspektera och ångra — en felklickad "Ingen
    # maskering" får aldrig bli en permanent, osynlig lucka.
    _undantag = st.session_state.undantagslista
    st.caption(f"Undantagslista: {len(_undantag)} strängar flaggas aldrig (krypterat lokalt).")
    if _undantag:
        with st.expander("Visa undantagslistan"):
            for _post in _undantag:
                _kol_text, _kol_bort = st.columns([3, 1])
                _kol_text.write(_post.get("text", ""))
                if _kol_bort.button("Ta bort", key=f"ta_bort_undantag_{_post['normaliserad']}"):
                    _kvar = app_config.ta_bort_undantag(_undantag, _post["normaliserad"])
                    app_config.spara_undantagslista(_kvar)
                    st.session_state.undantagslista = _kvar
                    st.rerun()
        if st.button("Töm undantagslistan"):
            app_config.tom_undantagslista()
            st.session_state.undantagslista = []
            st.rerun()
