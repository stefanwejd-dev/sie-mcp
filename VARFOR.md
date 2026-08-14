# Varför

`ARCHITECTURE.md` beskriver hur programvaran är byggd. `RISKREGISTER.md`
beskriver vad som kan gå fel i den. Det här dokumentet beskriver något som
saknades i båda: frågan om vem den är till för, och vad som hände när den
ställdes.

Det är skrivet av utvecklaren, i första person, och publicerat först som ett
inlägg 2026-08-14. Det står kvar här oredigerat i sak, eftersom en ärlig
anteckning som skrivs om i efterhand slutar vara en ärlig anteckning.

---

## Inlägget, 2026-08-14

> Har byggt sie-mcp sedan i somras. Läsande verktyg, skrivgrind,
> pseudoanonymisering före kontakt med extern LLM, sju rum, juridik-rum, lokal
> AI. Varje etapp har haft ett nummer, varje nummer har utförts. Loggboken fram
> till nu har nästan hela tiden handlat om delen som byggts klart.
>
> Det jag aldrig gjorde var att stanna och fråga vem det var till för.
>
> När jag väl gjorde det – förra veckan, framför min egen app – fanns inget bra
> svar. Balansrapport, åldersanalys, momsöversikt, likviditetsprognos,
> väsentlighet. Allt finns redan i Visma, Fortnox, Capego. Bättre, dessutom, av
> folk som gjort det betydligt längre än mig. Jag har byggt ett fönster ovanpå
> ett system som redan har fönster 😐.
>
> Det finns ett namn på det jag gjort: IKEA-effekten. En situation uppstår där
> skaparen värderar användnytta/verkliga värde högre än vad någon annan skulle
> göra – därför att skaparen även ser den kraft, det engagemang och till viss
> del den kärlek som hen har investerat i projektet. Jag byggde vidare för att
> bygget gick bra, och tog det som bevis för att riktningen var rätt – men det
> är två olika saker.
>
> En detalj i mitt bygge som fick mig att hajja till: när jag städade repot
> hittade jag att spiris kontosaldon aldrig fungerat. Den läste ett fält som
> inte finns på objektet och kastade ett fel vid varje anrop, från dagen den
> skrevs.
>
> Ett trasigt verktyg i en produkt med användare hade upptäckts på en
> förmiddag. Här upptäcktes det aldrig, för det fanns ingen som använde det.
> Avsaknaden av och inputen från reella användare blir en brist i ett eget
> projekt.
>
> Var det här tar mig vet jag inte riktigt. Jag är medveten om att jag är
> drabbad av IKEA-effekten – samtidigt är det jäkligt roligt att bygga något
> själv. Lite som att bygga en koja: man förväntar sig inte att någon annan
> någonsin kommer att vilja sätta sig i kojan, men att bygga kojan ger
> skaparglädje.
>
> Får se vad som händer.

---

## Vad som följer av det

Två saker, och de drar åt olika håll. Båda står kvar.

### Bygget fortsätter

Detta är inte ett avslut. Arbetet gick vidare samma vecka som inlägget
skrevs — bokslutskontrollerna, kontrollmotorn, bokslutsrummet. Skälet är det
som står i sista stycket ovan: bygget ger något i sig, och det räcker som skäl
så länge man är ärlig om att det är skälet.

Det som ändrades är inte takten utan vad som räknas som bevis. Att en etapp
blir klar är ett bevis på att etappen blev klar. Ingenting annat.

### Att sakna användare är en teknisk risk, inte bara en affärsmässig

`kontosaldon`-fyndet är den konkreta lärdomen, och den är generaliserbar:

**I ett projekt utan användare finns ingen kraft som upptäcker att något är
trasigt.** Test hittar det man tänkte på. Användare hittar det man inte tänkte
på. Saknas de andra måste den första bära hela lasten — och den lasten är
tyngre än den brukar vara i ett projekt med riktig trafik.

Praktiskt betyder det att metatester här inte är en hygienåtgärd utan den enda
återkopplingen som finns. Det är också förklaringen till varför två gap i den
här kodbasen kunde stå öppna länge:

* MCP-ytan växte förbi vad appen visade, därför att inget test band förmåga
  till gränssnitt.
* `parser/rum/`s vy-objekt renderades aldrig, därför att inget test följde
  kedjan hela vägen ut till `app.py`.

Båda är av samma sort som `kontosaldon`: kod som finns, ser rimlig ut, och
aldrig körs av någon. Ett test som bara kontrollerar att registret är
konsekvent med sig självt fångar ingen av dem.

Därav regeln som numera gäller i specarna: **en förmåga är inte byggd förrän
den är nåbar i den körande appen**, och metatestet ska följa hela kedjan, inte
bara sin egen ände av den.

### Den öppna frågan

Vem programvaran är till för är fortfarande obesvarat. Det är inte ett fel i
dokumentationen som ska rättas — det är ett läge som ska stå så länge det
gäller.

Den enda ändringen är att frågan nu är ställd och nedskriven, i stället för
outtalad.
