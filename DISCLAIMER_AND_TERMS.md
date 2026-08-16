# Användarvillkor och ansvarsfriskrivning (DISCLAIMER & TERMS OF USE)

**Gäller för mjukvaran:** `sie-mcp` (SIE4-/Spiris-verktyg: MCP-server och Streamlit-klient)
**Licens:** MIT (se [LICENSE](file:///LICENSE)) — fri programvara, tillhandahålls utan ersättning
**Villkorsversion:** `2026-08-04-v4`
**Senast uppdaterat:** 2026-08-04

---

> [!CAUTION]
> **LÄS DETTA INNAN DU ANVÄNDER PROGRAMVARAN.**
> `sie-mcp` lämnar **inga garantier** och gör **inga utfästelser** — varken om att den fungerar, om att det den visar är korrekt, om att den skyddar någon uppgift, eller om att den eller din användning av den uppfyller GDPR eller annan lagstiftning.
> **Hela det juridiska ansvaret för användningen och för allt den leder till bärs av dig som använder programvaran.**
> Genom att ladda ner, installera, driftsätta eller köra `sie-mcp` godkänner du villkoren nedan i sin helhet. Godkänner du inte samtliga villkor får du inte använda programvaran.

Programvaran spärrar sig själv tills villkoren uttryckligen har godkänts, punkt för punkt, av en människa på den dator där den körs — i Streamlit-appen eller via `python parser/compliance.py --godkann`. Ett godkännande kan aldrig lämnas via MCP eller av en AI-assistent på användarens vägnar.

---

## 1. Vad programvaran är

`sie-mcp` är fri programvara med öppen källkod som laddas ner och körs helt lokalt på användarens egen dator.

- **Inga servrar, ingen tjänst.** Upphovsmännen och bidragsgivarna bakom `sie-mcp` driver inga servrar, molntjänster, databaser eller API-gateways i anslutning till programvaran, och tillhandahåller ingen drift, support, underhåll, uppdateringar eller övervakning.
- **Ingen insamling.** Programvaran sänder inga användningsloggar, felrapporter, bokföringsuppgifter, personuppgifter eller metadata till upphovsmännen.
- **BYOK (Bring Your Own Key).** All anslutning till AI-modeller (t.ex. Anthropic, OpenAI, Google, eller en lokal Ollama-modell) sker med API-nycklar som användaren själv skaffar, äger och konfigurerar lokalt.
- **BYOA (Bring Your Own Account).** All anslutning till affärs- och bokföringssystem (t.ex. Spiris/Visma eAccounting) sker via användarens egen OAuth-inloggning, användarens eget utvecklarkonto och användarens egen avtalsrelation med respektive leverantör. Användaren ansvarar för att registrera ett eget utvecklarkonto och för att följa leverantörens utvecklar- och partnervillkor.

Upphovsmännen är inte part i något avtal mellan användaren och en AI-leverantör, en systemleverantör, en klient eller någon annan.

### 1.1 Fri, öppen och icke-monetiserad — hur programvaran tillhandahålls

Följande beskriver de faktiska förhållanden under vilka `sie-mcp` tillhandahålls:

- **Ingen ersättning tas ut.** Varken för programvaran, för någon funktion i den, för uppdateringar eller för teknisk support.
- **Programvaran monetiseras inte.** Det finns ingen betalversion, ingen prenumeration, ingen premiumfunktion, ingen plattform genom vilken andra tjänster säljs, och ingen intäktsmodell av något slag knuten till programvaran.
- **Ingen personuppgiftsbehandling som villkor för användning.** Användning förutsätter inte att användaren lämnar personuppgifter till upphovsmännen. Inga personuppgifter samlas in över huvud taget.
- **Publicering sker under en fri och öppen licens** (MIT) i öppna kodförråd, där källkoden är fritt tillgänglig att använda, ändra och vidaredistribuera.
- **Upphovsmännen är inte en ekonomisk aktör.** De är inte tillverkare, komponenttillverkare, importör, distributör, auktoriserad representant eller leverantör av distributionstjänster i förhållande till programvaran, och har varken släppt ut den på marknaden, tillhandahållit den på marknaden eller tagit den i drift i den mening som avses i unionens produktlagstiftning. Att lägga upp källkod i ett öppet kodförråd utgör inte att göra en produkt tillgänglig på marknaden.

---

## 2. Inga garantier — programvaran tillhandahålls i befintligt skick

PROGRAMVARAN TILLHANDAHÅLLS "I BEFINTLIGT SKICK" ("AS IS") OCH "I MÅN AV TILLGÅNG", UTAN GARANTIER AV NÅGOT SLAG, VARE SIG UTTRYCKLIGA, UNDERFÖRSTÅDDA ELLER LAGSTADGADE.

Inga utfästelser lämnas om funktion, riktighet, fullständighet, tillförlitlighet, tillgänglighet, prestanda, säkerhet, frånvaro av fel eller lämplighet för något ändamål — allmänt eller särskilt. Användningen sker helt på användarens egen risk.

---

## 3. Resultaten kan inte antas motsvara verkligheten

> [!WARNING]
> **Ingenting som programvaran visar utgör en utsaga om faktiska förhållanden.**

Alla siffror, tabeller, sammanställningar, diagram, nyckeltal, väsentlighetstal, klassificeringar, avvikelseindikationer, prognoser, kalkyler och AI-genererade svar som `sie-mcp` producerar:

- **kan vara felaktiga, ofullständiga, missvisande, inaktuella eller helt påhittade,** och
- **kan inte antas motsvara verkligheten,** den underliggande bokföringen, användarens affärssystem, gällande redovisningsregler eller något faktiskt förhållande.

Detta gäller oavsett hur resultatet presenteras. En siffra som visas med decimaler, en tabell som ser färdig ut eller ett AI-svar som låter säkert är inte ett bevis för någonting. Språkmodeller kan producera innehåll som är rimligt formulerat men sakligt fel, och beräkningarna i programvaran bygger på tolkningar och antaganden som kan vara felaktiga för just användarens data.

**Användaren ansvarar ensam för att självständigt kontrollera och verifiera varje uppgift mot originalkällan** — bokföringen, verifikationerna, årsredovisningen och tillämpligt regelverk — innan uppgiften används, vidarebefordras, rapporteras eller läggs till grund för något beslut eller någon leverans.

---

## 4. Ingen professionell rådgivning

`sie-mcp` utgör **inte** revisionsrådgivning, redovisningsrådgivning, skatterådgivning, finansiell rådgivning eller juridisk rådgivning, och ska inte uppfattas som sådan.

- Programvaran **ersätter inte** användarens egen professionella bedömning enligt International Standards on Auditing (ISA), god revisionssed, god redovisningssed, Bokföringsnämndens allmänna råd (K2/K3), bokföringslagen, årsredovisningslagen, revisorslagen eller annan tillämplig reglering och yrkesetik.
- Hänvisningar i programvaran eller dess dokumentation till standarder och regelverk (t.ex. ISA 320, ISA 450, K2, K3) beskriver vad en beräkning är *avsedd* att efterlikna. De är inte en utfästelse om att beräkningen är korrekt, fullständig eller regelenlig, och de befriar inte användaren från att göra sin egen bedömning.
- Något uppdragsförhållande, rådgivningsförhållande eller förtroendeförhållande uppstår inte mellan användaren och upphovsmännen genom användning av programvaran.
- Skriver programvaran uppgifter till ett affärssystem ansvarar användaren ensam för att varje sådan post uppfyller bokföringslagens krav på verifikationer, och för att kontrollera posten innan den godkänns.

Användaren ansvarar ensam för sina yrkesmässiga bedömningar och för allt som levereras till användarens egna klienter, uppdragsgivare, styrelse eller myndigheter.

---

## 4a. Förslag är inte beslut — åtgärder i affärssystem

Programvaran kan låta en AI-assistent **föreslå** åtgärder i användarens affärssystem: nya kunder, kundfakturor och verifikat. Följande gäller för sådana förslag:

- **Ingenting utförs automatiskt.** Ett förslag läggs i en lokal kö och utförs först när användaren själv har granskat de verkliga uppgifterna i programvarans gränssnitt och uttryckligen godkänt dem. Programvarans MCP-server kan inte skriva till affärssystemet.
- **Ett förslag är inte ett beslut, en rekommendation eller ett utfört uppdrag.** Att programvaran föreslår en åtgärd innebär ingen bedömning av att åtgärden är riktig, lämplig eller förenlig med regelverk.
- **Förslag kan vara felaktiga på alla sätt ett AI-svar kan vara det** — fel belopp, fel konto, fel motpart, fel period, eller en åtgärd som inte borde vidtas alls. Avsnitt 3 gäller i sin helhet även här.
- **Användaren ansvarar ensam för varje åtgärd hon godkänner** och för allt som följer av den. Det omfattar att en bokförd post uppfyller bokföringslagens krav på verifikationers innehåll och ordning, att en utskickad faktura är riktig i förhållande till avtal och prestation, och att uppgifter som skrivs till affärssystemet är korrekta.
- **Ett verifikat kan inte tas bort i efterhand**, bara rättas med ett nytt verifikat. Ansvaret för räkenskaperna ligger hos den bokföringsskyldige.
- **Ett godkännande skapar som standard ett utkast i affärssystemet, inte en bokförd post.** Utkastet påverkar inte räkenskaperna förrän användaren själv bokför det i affärssystemet. Väljer användaren i stället direktbokföring vid godkännandet gäller föregående punkt fullt ut. Att ett utkast skapas fritar inte användaren från ansvaret att kontrollera uppgiften.
- Godkännandet gäller de uppgifter som visades vid granskningen. Ett förslag som är äldre än ett dygn kan inte längre godkännas, eftersom underlaget kan ha ändrats.

---

## 5. Ingen utfästelse om efterlevnad av GDPR eller annan lagstiftning

> [!CAUTION]
> **Programvaran gör inget anspråk på att uppfylla någon lagstiftning.**

`sie-mcp` lämnar ingen utfästelse, garanti eller försäkran om att programvaran — eller användarens användning av den — uppfyller dataskyddsförordningen (EU) 2016/679 (GDPR), dataskyddslagen (2018:218), krav på personuppgiftsbiträdesavtal, AI-förordningen (EU) 2024/1689, bokföringslagen (1999:1078), eller någon annan lag, förordning, standard eller föreskrift.

Att bedöma om användningen är laglig, och att säkerställa att den är det, är **helt och hållet användarens eget ansvar**. Det omfattar bland annat, utan begränsning:

1. **Roller och avtal.** Att fastställa sin egen roll som personuppgiftsansvarig eller personuppgiftsbiträde, och att teckna de personuppgiftsbiträdesavtal (Art. 28 GDPR) som krävs — både med sina egna klienter och direkt med varje AI- och systemleverantör som aktiveras under användarens eget konto.
2. **Rättslig grund.** Att säkerställa giltig rättslig grund (Art. 6 GDPR) och att hantera särskilda kategorier av personuppgifter (Art. 9) och uppgifter om lagöverträdelser (Art. 10). Bokföringstext kan avslöja sådana uppgifter indirekt.
3. **Tredjelandsöverföring.** Att fastställa en giltig överföringsmekanism (kapitel V GDPR) när data sänds till en leverantör utanför EU/EES, och att göra tillhörande riskbedömning.
4. **Konsekvensbedömning och register.** Att genomföra eventuell DPIA (Art. 35) och att föra sitt behandlingsregister (Art. 30).
5. **Säkerhet, incidenter och information.** Att uppfylla kraven på säkerhetsåtgärder (Art. 32), rutin för personuppgiftsincidenter (Art. 33/34) och informationsskyldighet gentemot registrerade (Art. 13/14).
6. **Yrkesreglering.** Att följa tillämplig yrkesreglering, tystnadsplikt och de villkor som gäller för användarens egna leverantörskonton.

[docs/DATASKYDD.md](docs/DATASKYDD.md) i projektet är ett **tekniskt underlag** som beskriver hur programvaran fungerar. Det är inte en compliance-utfästelse, inte juridisk rådgivning och inte ett bevis på att något krav är uppfyllt. Användaren ansvarar för att själv granska, verifiera och komplettera underlaget.

---

## 6. Maskeringsfunktionen är en funktion — inte ett skydd som kan förlitas på

`sie-mcp` innehåller en funktion som söker efter och ersätter namn, personnummer, organisationsnummer och vissa adressuppgifter med typade tokens (`[PERSON_1]`, `[BOLAG_1]`) innan text kan skickas vidare till en AI-modell.

> [!CAUTION]
> **Funktionen beskrivs här som en funktion, inte som ett skydd.** Den är inte fullständig, inte verifierad mot alla förekommande format, inte granskad av tredje part, och den får inte förlitas på som ett dataskydd. Personuppgifter kan nå en extern AI-leverantör i klartext, i vissa fall utan att användaren varnas och utan att något räknas i den statistik som visas.

Följande begränsningar är **kända vid tiden för denna version**. Uppräkningen är inte uttömmande — okända brister kan finnas, och funktionen kan sluta fungera som avsett vid ändrade indata, ändrade format eller ändrad omgivande kod:

- Namn i **enbart versaler** ("XERXES QOOLIO"), namn i enbart gemener, **initial + efternamn** ("A. Svensson") och **enordsnamn/mononymer** identifieras inte, utan varning.
- **Uppgifter som avslöjar särskilda kategorier** (Art. 9) eller lagöverträdelser (Art. 10) maskeras inte. Ord som "fackavgift", "sjukvård" eller "polisanmäld" passerar tillsammans med en stabil pseudonym, vilket indirekt kan peka ut en person. Detta är en medveten avgränsning: att svartlista sådana ord vore verkningslöst. Att begränsa vilka fält som alls sänds är användarens eget ansvar.
- Ett **okänt personnamn med bolagsformssuffix och giltigt organisationsnummer** ("Xerxes Qoolio AB") behandlas som juridisk person i reskontran och maskeras inte.
- **Kortnummer i vissa grupperingar** (t.ex. Amex 4-6-5) identifieras inte.
- Även när maskeringen fungerar som avsett är resultatet **pseudonymiserat, inte anonymiserat**. Pseudonymiserade uppgifter förblir personuppgifter enligt Art. 4(5) och skäl 26 GDPR. Kombinationen av en token och kringliggande transaktionstext kan indirekt röja såväl identitet som känsliga uppgifter.

Fyra tidigare dokumenterade brister — namn i icke-latinsk skrift, partiell maskering vid latinska diakriter, samordningsnummer utan separator, och reskontrans namnkontroll — är åtgärdade och regressionstestade (`tests/test_sekretess_lackprobe.py`). Att de är stängda är en observation om koden vid en viss tidpunkt, inte en garanti, och ändrar ingenting i övrigt i detta avsnitt eller i avsnitt 2, 5 och 9.

Användaren ansvarar ensam för att bedöma vilken data som är lämplig att sända, och för konsekvenserna av att sända den.

---

## 7. Programvaran beskrivs inte som säker

Ingenstans utfäster `sie-mcp` att den är säker. Programvaran är inte säkerhetsgranskad av tredje part, inte certifierad, och inte utvecklad enligt någon säkerhetsstandard.

Programvaran skriver bland annat **lokala, okrypterade loggfiler** som kan innehålla personuppgifter och den faktiska nyttolast som sänts till externa tjänster, samt lokala filer med nycklar och sessionsuppgifter. Användaren ansvarar ensam för dessa filers säkerhet, åtkomstbegränsning, säkerhetskopiering, gallring och radering, och för att bedöma om lagringen är förenlig med användarens egna krav och skyldigheter.

Termer som förekommer i den tekniska dokumentationen — såsom "fail-closed", "härdad", "vakt" eller "skyddad" — beskriver hur koden är **avsedd** att bete sig. De är inte utfästelser om att beteendet är korrekt implementerat, fullständigt eller effektivt.

---

## 8. AI-förordningen (EU 2024/1689)

`sie-mcp` publiceras utan ersättning under en fri licens för öppen källkod och tillhandahålls inte mot betalning eller som en kommersiell tjänst — se avsnitt 1.1. Programvaran omfattas därmed av undantaget för fri programvara med öppen källkod i artikel 2.12 i förordning (EU) 2024/1689.

Upphovsmännen tillhandahåller inte programvaran som ett AI-system i den mening som avses i förordningen, och avgör inte för vilket ändamål den används. Den aktör som i yrkesmässig verksamhet driftsätter eller använder programvaran — och därmed bestämmer ändamålet med användningen — ansvarar ensam för att avgöra vilka skyldigheter som gäller för den användningen och för att uppfylla dem. Det gäller även om användningen skulle innebära att systemet i användarens händer omfattas av krav som inte gäller för programvaran som sådan.

---

## 8a. Produktansvarsdirektivet (EU) 2024/2853

Upphovsmännen bakom `sie-mcp` omfattas inte av ansvar enligt Europaparlamentets och rådets direktiv (EU) 2024/2853 om skadeståndsansvar för produkter med säkerhetsbrister. Tre av varandra oberoende grunder bär var för sig den slutsatsen:

1. **Utanför direktivets tillämpningsområde (artikel 2.2).** Direktivet tillämpas inte på fri programvara med öppen källkod som utvecklas eller tillhandahålls utanför ramen för kommersiell verksamhet. `sie-mcp` tillhandahålls så — se avsnitt 1.1. Enligt skäl 14 utgör tillhandahållande av sådan programvara i öppna kodförråd inte att göra den tillgänglig på marknaden, och att utveckla eller bidra till sådan programvara utgör inte heller det.

2. **Ingen ansvarig ekonomisk aktör (artiklarna 8 och 10.1 a).** Ansvar enligt direktivet åvilar tillverkare, komponenttillverkare, importörer, auktoriserade representanter, leverantörer av distributionstjänster och distributörer som har släppt ut produkten på marknaden, tillhandahållit den på marknaden eller tagit den i drift. Upphovsmännen har inte gjort något av detta och är inte någon av dessa aktörer.

3. **Utanför de ersättningsgilla skadetyperna (artikel 6.1).** Direktivet ger rätt till ersättning endast för dödsfall och personskada, för sakskada — dock uttryckligen **inte** för egendom som uteslutande används för yrkesmässiga ändamål — samt för förstörelse eller förvanskning av data som **inte** används för yrkesmässiga ändamål. `sie-mcp` är avsett för yrkesmässig användning i redovisnings- och revisionsverksamhet. Ren förmögenhetsskada, som är den skadetyp användning av programvaran realistiskt kan ge upphov till, omfattas inte alls av direktivet.

---

## 8b. Cyberresiliensakten (EU) 2024/2847

Upphovsmännen bakom `sie-mcp` omfattas inte av skyldigheter enligt Europaparlamentets och rådets förordning (EU) 2024/2847 om övergripande cybersäkerhetskrav för produkter med digitala element.

- **Förordningen tillämpas endast på produkter som tillhandahålls på marknaden**, det vill säga levereras för distribution eller användning på unionsmarknaden inom ramen för kommersiell verksamhet (artikel 2.1, jämförd med skäl 15).
- **Programvaran monetiseras inte.** Enligt skäl 18 ska tillhandahållande av produkter med digitala element som utgör fri programvara med öppen källkod och som inte monetiseras av sin tillverkare inte anses utgöra kommersiell verksamhet. Enligt samma skäl saknar det betydelse under vilka omständigheter programvaran har utvecklats eller hur utvecklingen har finansierats, liksom att programvaran släpps i regelbundna versioner.
- **Publicering i kodförråd är inte marknadstillhandahållande.** Enligt skäl 20 utgör enbart lagring av produkter med digitala element i öppna kodförråd, inbegripet via pakethanterare eller samarbetsplattformar, inte i sig att produkten tillhandahålls på marknaden.
- **Upphovsmännen är inte förvaltare av öppen källkod** ("open-source software steward" enligt artikel 24). Den ordningen avser juridiska personer som ger varaktigt stöd åt fri programvara med öppen källkod som är avsedd för kommersiell verksamhet.

Förordningens skyldigheter är offentligrättsliga och riktar sig mot ekonomiska aktörer inom dess tillämpningsområde. De grundar inte något ansvar gentemot användare, och upphovsmännen är inte en sådan aktör.

---

## 9. Fullständig ansvarsfriskrivning

> [!CAUTION]
> **Denna friskrivning ska tolkas och tillämpas så vidsträckt som över huvud taget är möjligt.**

**9.1 Grundregel.** UPPHOVSMÄNNEN, UTVECKLARNA OCH BIDRAGSGIVARNA BAKOM `sie-mcp` ANSVARAR INTE, UNDER NÅGRA OMSTÄNDIGHETER OCH PÅ NÅGON GRUND, FÖR NÅGON SKADA, FÖRLUST, KOSTNAD, AVGIFT, SANKTION ELLER ANNAT ANSPRÅK — VARE SIG DIREKT, INDIREKT, TILLFÄLLIG, SÄRSKILD ELLER FÖLJDSKADA — SOM UPPSTÅR TILL FÖLJD AV ELLER I SAMBAND MED PROGRAMVARAN, DESS ANVÄNDNING, OFÖRMÅGAN ATT ANVÄNDA DEN, DESS RESULTAT, ELLER NÅGOT BESLUT ELLER NÅGON ÅTGÄRD SOM HELT ELLER DELVIS GRUNDATS PÅ DEN.

**9.2 Oavsett rättslig grund.** Friskrivningen gäller oberoende av vilken rättslig grund ett anspråk vilar på, och omfattar anspråk grundade på avtal, utomobligatoriskt skadestånd, vårdslöshet, grov vårdslöshet, strikt ansvar, produktansvar, garanti eller utfästelse, obehörig vinst, lagstadgat ansvar eller varje annan grund.

**9.3 Oavsett vem som framställer anspråket.** Friskrivningen gäller oavsett om anspråket framställs av användaren själv, av användarens klient eller uppdragsgivare, av en registrerad person, av en anställd, av en annan tredje man, av en tillsynsmyndighet eller av någon annan.

**9.4 Omfattning.** Friskrivningen omfattar bland annat, utan begränsning: felaktiga eller ofullständiga beräkningar; felaktiga, missvisande eller påhittade AI-svar; felaktig bokföring, kontering, periodisering eller klassificering; felaktig rapportering eller årsredovisning; felaktiga väsentlighetstal eller revisionsbedömningar; utebliven upptäckt av fel, avvikelser eller oegentligheter; förlust, förvanskning, otillgänglighet eller röjande av data eller personuppgifter; personuppgiftsincidenter; sanktionsavgifter, viten, förelägganden eller andra ingripanden från tillsynsmyndighet, däribland Integritetsskyddsmyndigheten; disciplinära åtgärder eller åtgärder från Revisorsinspektionen; avtalsbrott gentemot tredje man; anspråk från tredje man; förlorad vinst; förlorad goodwill; ökade kostnader; samt verksamhetsavbrott.

**9.5 Ingen kännedomsreservation.** Friskrivningen gäller även om upphovsmännen har underrättats om, eller borde ha insett, möjligheten av sådan skada, och även om ett angivet eller förutsatt ändamål med programvaran har förfelats.

**9.6 Skadeslöshet.** Användaren åtar sig att hålla upphovsmännen fullt skadeslösa för varje anspråk, krav, process, sanktion, kostnad och rättegångskostnad som riktas mot dem av tredje man eller myndighet till följd av eller i samband med användarens användning av programvaran.

**9.7 Maximal tillämpning och självständiga delar.** Varje del av denna friskrivning gäller självständigt och är inte beroende av att någon annan del är giltig. Skulle en domstol eller myndighet i ett enskilt fall finna att någon del inte kan göras gällande i sin fulla lydelse, ska den delen ändå tillämpas i den största utsträckning som är möjlig, och samtliga övriga delar fortsätta att gälla oförändrade och i sin helhet.

---

## 10. Användarens bekräftelse

Genom att godkänna villkoren i programvaran bekräftar användaren punkt för punkt att användaren:

1. bär hela det juridiska ansvaret för användningen och för allt den leder till,
2. accepterar att programvaran lämnar inga garantier,
3. accepterar att resultaten inte kan antas motsvara verkligheten och måste verifieras självständigt,
4. accepterar att programvaran inte utgör professionell rådgivning,
5. accepterar att programvaran inte gör anspråk på att uppfylla GDPR eller annan lagstiftning,
6. accepterar att maskeringsfunktionen är ett hjälpmedel utan garanti med kända begränsningar,
7. ansvarar själv för egna nycklar, konton och avtal (BYOK/BYOA),
8. ansvarar själv för varje åtgärd hon godkänner i sitt affärssystem, och
9. ansvarar själv för de lokala loggfiler och filer som programvaran skriver.

Den exakta lydelsen av dessa punkter finns i `parser/compliance.py` och visas i programvaran vid godkännandet. Ändras lydelsen materiellt höjs villkorsversionen, och användaren måste ta ställning på nytt.

---

## 11. Tillämplig lag och tvistlösning

- **Tillämplig lag.** På dessa villkor, och på varje tvist eller anspråk som uppstår ur eller i samband med dem eller med programvaran — oavsett om anspråket är avtalsrättsligt eller utomobligatoriskt — ska svensk rätt tillämpas, med undantag för svenska lagvalsregler som skulle leda till att annan lag tillämpas.
- **Forum.** Tvist ska prövas av svensk domstol, med Stockholms tingsrätt som första instans.
- **Kontakt före process.** Den som anser sig ha ett anspråk ska underrätta upphovsmännen skriftligen och ge dem skälig tid att bemöta det innan rättsliga åtgärder inleds.

## 12. Övrigt

- **Ändringar.** Villkoren kan ändras i nya versioner av programvaran. Den version av villkoren som följer med den kopia användaren kör är den som gäller för den kopian.
- **Ogiltighet och fortsatt giltighet.** Skulle någon bestämmelse i dessa villkor helt eller delvis inte kunna göras gällande, ska övriga bestämmelser fortsätta att gälla oförändrade, och den berörda bestämmelsen tillämpas i den största utsträckning som är möjlig så att dess syfte uppnås så långt det går. Att en bestämmelse inte kan göras gällande i ett visst fall, mot en viss part eller i en viss jurisdiktion påverkar inte dess giltighet i övrigt.
- **Ingen eftergift.** Att upphovsmännen i något fall avstår från att åberopa en bestämmelse innebär inte att rätten att åberopa den, eller någon annan bestämmelse, går förlorad.
- **Ingen support.** Programvaran tillhandahålls utan support, underhåll eller åtagande att rätta fel.
- **Övrig dokumentation.** [LICENSE](LICENSE) · [README.md](README.md) · [docs/DATASKYDD.md](docs/DATASKYDD.md) (tekniskt underlag). Dessa dokument är tekniska beskrivningar och ändrar inte ansvarsfördelningen i detta dokument. Vid motstridighet gäller detta dokument och [LICENSE](LICENSE).
