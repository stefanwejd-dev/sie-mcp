# Architecture

## SIE4-grammatik

Specifikationsreferens: SIE-gruppens *SIE filformat*, utgåva 4C (2025-08-06).
Specifikationen är upphovsrättsskyddad och ingår därför inte i kodförrådet —
den hämtas från [sie.se](https://sie.se). Avsnittshänvisningar nedan (§5.8 och
liknande) syftar på den utgåvan.

### Filstruktur — fyra block i fast ordning

```
1. Flaggpost           #FLAGGA
2. Identifikationsposter
3. Kontoplansuppgifter
4. Saldoposter / Verifikationsposter
```

Ordningen *inom* varje block är fri om inget annat anges per post.

### Fältformatering

- Fält avgränsas av ett eller flera mellanslag eller tabulatorer (ASCII 9).
- Fält *kan* omslutas av `"` (ASCII 34); det är obligatoriskt om fältet innehåller mellanslag.
- Inbäddade citattecken skrivs `\"`.
- Tomma mellanliggande fält anges som `""`. Fält efter sista värdet på raden kan utelämnas.
- Fält är positionsbestämda, inte namngivna — ordningen är semantisk.
- Belopp: punkt som decimaltecken, max 2 decimaler, negativt belopp föregås av `-`. Inget `+`.
- Datum: `ÅÅÅÅMMDD`. Period: `ÅÅÅÅMM`.
- Kontrolltecken (ASCII 0–31, 127) är förbjudna i textsträngar.

### Posttyper — obligatorium per SIE-typ

Teckenförklaring: **●** = obligatorisk, **o** = frivillig, **–** = får ej förekomma.

†  Saldoposter med nollsaldo kan utelämnas. Om ingen post har värde > 0 skrivs inga sådana poster alls.
❖  Behöver ej deklareras om de sammanfaller med reserverade standarddimensioner (1–10).

#### Identifikationsposter

| Post | Fält | 1 | 2 | 3 | 4I | 4E |
|------|------|---|---|---|----|----|
| `#FLAGGA` | `x` | ● | ● | ● | ● | ● |
| `#PROGRAM` | `programnamn version` | ● | ● | ● | ● | ● |
| `#FORMAT` | `PC8` | ● | ● | ● | ● | ● |
| `#GEN` | `datum [sign]` | ● | ● | ● | ● | ● |
| `#FNAMN` | `företagsnamn` | ● | ● | ● | ● | ● |
| `#SIETYP` | `typnr` | o | ● | ● | ● | ● |
| `#RAR` | `årsnr start slut` | ●† | ●† | ●† | o | ●† |
| `#PROSA` | `text` | o | o | o | o | o |
| `#FTYP` | `företagstyp` | o | o | o | o | o |
| `#FNR` | `företagsid` | o | o | o | o | o |
| `#ORGNR` | `orgnr [förvnr] [verknr]` | o | o | o | o | o |
| `#BKOD` | `SNI-kod` | – | o | o | o | o |
| `#ADRESS` | `kontakt utdelningsadr postadr tel` | o | o | o | o | o |
| `#TAXAR` | `år` | o | o | o | o | o |
| `#OMFATTN` | `datum` | – | – | ● | ● | o |
| `#KPTYP` | `BAS95\|BAS96\|EUBAS97\|NE2007` | o | o | o | o | o |
| `#VALUTA` | `ISO 4217-kod` | o | o | o | o | o |

#### Kontoplansuppgifter

| Post | Fält | 1 | 2 | 3 | 4I | 4E |
|------|------|---|---|---|----|----|
| `#KONTO` | `kontonr kontonamn` | ● | ● | ● | o | ● |
| `#KTYP` | `kontonr T\|S\|K\|I` | o | o | o | o | o |
| `#ENHET` | `kontonr enhet` | o | o | o | o | o |
| `#SRU` | `konto SRU-kod` | ● | ● | o | o | o |
| `#DIM` | `dimensionsnr namn` | – | – | ●❖ | o | o |
| `#UNDERDIM` | `dimensionsnr namn superdimension` | – | – | ●❖ | o | o |
| `#OBJEKT` | `dimensionsnr objektnr objektnamn` | – | – | ●❖ | o | o |

#### Saldo- och verifikationsposter

| Post | Fält | 1 | 2 | 3 | 4I | 4E |
|------|------|---|---|---|----|----|
| `#IB` | `årsnr konto saldo [kvantitet]` | – | ●† | ●† | ●† | ●† |
| `#UB` | `årsnr konto saldo [kvantitet]` | – | ●† | ●† | ●† | ●† |
| `#RES` | `årsnr konto saldo [kvantitet]` | – | ●† | ●† | ●† | ●† |
| `#OIB` | `årsnr konto {dimnr objnr} saldo [kvantitet]` | – | – | – | ●† | o |
| `#OUB` | `årsnr konto {dimnr objnr} saldo [kvantitet]` | – | – | – | ●† | o |
| `#PSALDO` | `årsnr period konto {dimnr objnr} saldo [kvantitet]` | – | – | ● | ● | o |
| `#PBUDGET` | `årsnr period konto {dimnr objnr} saldo [kvantitet]` | – | – | ● | ● | o |
| `#VER` | se nedan | – | – | – | o | o |
| `#TRANS` | se nedan | – | – | – | o | o |
| `#RTRANS` | `kontonr {objektlista} belopp [transdat] [transtext] [kvantitet] [sign]` | – | – | – | o | o |
| `#BTRANS` | `kontonr {objektlista} belopp [transdat] [transtext] [kvantitet] [sign]` | – | – | – | o | o |
| `#KSUMMA` | *(tom = start, heltal = CRC-32-värde)* | o | o | o | o | o |

### #VER — verifikationspost

```
#VER serie vernr verdatum vertext regdatum sign
{
    #TRANS ...
    #TRANS ...
}
```

| Fält | Format | Obligatorisk |
|------|--------|--------------|
| `serie` | Bokstäver A…, siffror 1…, eller alfanumerisk sträng (t.ex. `LEV1`). Tom sträng `""` tillåts vid import (4I). | Nej |
| `vernr` | Heltal. Tom sträng `""` tillåts vid import (4I). Verifikationer inom en serie ska ligga i stigande nummerordning. | Nej |
| `verdatum` | ÅÅÅÅMMDD | **Ja** |
| `vertext` | Fritext | Nej |
| `regdatum` | ÅÅÅÅMMDD — det datum verifikationen registrerades/genererades | Nej |
| `sign` | Namn, signatur eller användarid | Nej |

`{` och `}` ska stå **ensamma på var sin rad** direkt efter `#VER`-raden.

Summan av alla `belopp` inom en verifikation ska vara **noll** (dubbelsidig bokföring).

### #TRANS — transaktionsrad (underpost till #VER)

```
#TRANS kontonr {objektlista} belopp transdat transtext kvantitet sign
```

| Fält | Format | Obligatorisk |
|------|--------|--------------|
| `kontonr` | Numerisk sträng | **Ja** |
| `{objektlista}` | Parvist: `{dimnr "objnr" dimnr "objnr" …}`. Tom lista skrivs `{}` eller `{ }`. | **Ja** (listan kan vara tom) |
| `belopp` | Decimaltal med punkt. Debet = positivt, kredit = negativt. | **Ja** |
| `transdat` | ÅÅÅÅMMDD. Utelämnat ⇒ antas = `verdatum`. | Nej |
| `transtext` | Fritext | Nej |
| `kvantitet` | Decimaltal, samma tecken som belopp | Nej |
| `sign` | Namn/signatur/användarid | Nej |

`#RTRANS` (tillagd rad) och `#BTRANS` (borttagen rad) har identisk fältsyntax.
En `#RTRANS`-rad **måste** omedelbart följas av en identisk `#TRANS`-rad (bakåtkompatibilitetskrav).
Läsare som inte stödjer `#RTRANS`/`#BTRANS` ignorerar dem och läser enbart `#TRANS`-raderna.

### Dimensioner

Reserverade dimensionsnummer:

| Nr | Betydelse |
|----|-----------|
| 1 | Kostnadsställe / resultatenhet |
| 2 | Kostnadsbärare (underdimension till 1) |
| 3–5 | Reserverade |
| 6 | Projekt |
| 7 | Anställd |
| 8 | Kund |
| 9 | Leverantör |
| 10 | Faktura |
| 11–19 | Reserverade |
| 20– | Fritt disponibla |

Standarddimensioner (1–10) behöver inte deklareras med `#DIM` i typ 3-filer.

### Utbyggbarhet

- Okända etiketter **ska ignoreras** av importerande program.
- Okända extra fält sist på en rad **ska ignoreras**.
- Enbart SIE-standardens egna etiketter är tillåtna i exportfiler.

---

## Teckenkodning (beslutat)

Inläsning sker med `cp437`-avkodning enligt SIE-specens punkt 5.8. Om avkodning misslyckas eller ger uppenbart felaktiga tecken, fall tillbaka till `windows-1252`. All intern representation efter inläsning är UTF-8 (Python-standard).

---

## Felhantering v1 (beslutat)

### Princip: ingen rad försvinner tyst (skärpt 2026-06-27)

Principen gäller samtliga posttyper i SIE-filen, inte bara `#VER`/`#TRANS`/`#RTRANS`/`#BTRANS`. Varje etikett som parsern aktivt hanterar ska ha en explicit felväg: om ett obligatoriskt fält saknas eller inte går att tolka enligt grammatiken, skapas en `Tolkningsbehov`-post. Det finns ingen "tyst fallback" eller implicit `None`-tilldelning för obligatoriska fält, oavsett om posten är en verifikation eller ren metadata.

Undantag: rent frivilliga fritextfält (t.ex. `#PROSA`) har ingen "felaktig" form — all text är giltig text. Dessa behöver bara inläsning, ingen valideringsgren.

### Kaskaderegel för brutna verifikationer

Om en `#VER`-rad inte går att tolka (t.ex. saknar obligatoriskt `verdatum`) ska samtliga `#TRANS`/`#RTRANS`/`#BTRANS`-rader inom samma `{...}`-block också läggas till i `tolkningsbehov`. Fältet `kontext` på dessa rader ska hänvisa till den brutna verifikationens radnummer. De ignoreras inte bara för att föräldern var ogiltig.

### Insamlingsstrategi: hela filen alltid

Parsern läser igenom hela filen och samlar alla tolkningsbehov, i stället för att avbryta vid det första problemet. En `SIEFil` med en icke-tom `tolkningsbehov`-lista representerar en **delvis tolkad fil** som kräver mänsklig granskning innan den litas på.

### #ORGNR — tolkningsregel (beslutat)

`#ORGNR orgnr [förvnr] [verknr]` tolkas positionellt enligt SIE:s platshållarkonvention (tomma mellanfält skrivs `""`, fält efter sista värdet på raden kan utelämnas). Om radens fältantal och struktur följer konventionen tolkas den utan flaggning.

Om en rad bryter mot konventionen (t.ex. exakt 2 fält totalt, vilket är tvetydigt — saknas `förvnr` eller `verknr`?) gör parsern ett bästa-gissning utifrån fältets innehåll, men skapar **alltid** en `Tolkningsbehov`-post med `partiell_tolkning` som beskriver vad som gissades och varför. Ingen gissning får ske osynligt.

### Tomtecken-konvention (beslutat)

En explicit tom sträng `""` i ett fält är en avsiktlig platshållare enligt SIE-formatets egna fältformateringsregler (se Fältformatering ovan), inte ett fel. Den skiljer sig från ett fält som saknas helt — dvs. inga fler tokens finns kvar på raden efter etiketten. Ett obligatoriskt fält som saknas helt flaggas som `Tolkningsbehov`. Ett obligatoriskt fält som är explicit `""` flaggas **inte** — det är giltig, avsiktlig tomhet, och tolkas som tom sträng.

### Obligatoriska poster som saknas helt i filen (beslutat, avgränsat)

Utöver radnivåvalidering (ett fält på en befintlig rad är felaktigt) kontrolleras även postnivå: om en post som ska finnas i filen aldrig förekommer alls.

**Avgränsning för denna version:** kontrollen gäller enbart de fem identifikationsposter som är obligatoriska (●) i samtliga SIE-typer utan undantag: `#FLAGGA`, `#PROGRAM`, `#FORMAT`, `#GEN`, `#FNAMN`.

Saknas en av dessa helt skapas en `Tolkningsbehov`-post med:
- `radnummer = 0` — sentinelvärde, signalerar ett filnivåfel utan specifik rad
- `råtext = ""` — ingen rad att citera
- `etikett` = den saknade etiketten
- `anledning` = `"obligatorisk post <etikett> saknas helt i filen"`

**Medvetet uteslutet, kräver separat designbeslut:**

- `#SIETYP` — frivillig för typ 1, obligatorisk för typ 2–4. Om `#SIETYP` saknas helt antas typ 1 per spec (kap. 2.3), och frånvaron är då korrekt.
- `#KONTO` — obligatorisk för typ 4E, frivillig för typ 4I. Specen lagrar ingen distinktion mellan 4I och 4E i filinnehållet (se spec kap. 4.10) — `#FLAGGA` är en återimporteringsspärr, inte en typmarkör (kap. 7.4).
- Saldoposter markerade † (`#IB`, `#UB`, `#RES`, `#PBUDGET` m.fl.) — får enligt spec (5.17–5.18) utelämnas helt om saldot är noll.

### #KSUMMA — registrering och trunkeringsdetektering (beslutat, avgränsat)

`#KSUMMA` är frivillig och förekommer i par: en tom öppnande post som
signalerar att kontrollsummering är i bruk, och en avslutande post med
ett CRC-32-heltal (spec kap. 10.4–10.6).

**Avgränsning:** parsern registrerar värdet i den avslutande posten men
beräknar inte om CRC-32-summan för att verifiera filens innehåll. Skälet:
kontrollsumman skyddar mot dataförvanskning vid filöverföring/lagring —
ett scenario som blir alltmer irrelevant i takt med att projektets riktning
går mot direktkoppling till bokföringssystem (Briljant/Spiris) snarare än
SIE-fil som mellanled. En spec-trogen CRC-32-implementation kräver
dessutom en byte-exakt parallell tokenizer skild från `_tokenize`.

Parsern upptäcker dock **trunkering**: om den öppnande signalen ses men
ingen avslutande post hittas — antingen därför att en ny öppnande signal
dyker upp innan föregående stängts, eller därför att filen tar slut —
skapas en `Tolkningsbehov`-post, i linje med specens egen regel (kap.
10.6). En avslutande post utan föregående öppning flaggas också, men
värdet registreras ändå.

---

## Datamodell (FÖRSLAG — inte beslut)

> Nedanstående är ett utkast för diskussion. Inga fält är låsta. Justera fritt.

### `SIEFil`

Toppnivå-container för hela den inlästa filen.

| Fält | Typ | Källa |
|------|-----|-------|
| `sietyp` | `int` (1/2/3/4) | `#SIETYP` |
| `program` | `str` | `#PROGRAM programnamn` |
| `program_version` | `str` | `#PROGRAM version` |
| `genererad` | `date` | `#GEN datum` |
| `genererad_sign` | `str \| None` | `#GEN sign` |
| `företagsnamn` | `str` | `#FNAMN` |
| `orgnr` | `str \| None` | `#ORGNR` fält 1 |
| `förvaltningsnummer` | `str \| None` | `#ORGNR` fält 2 |
| `verksamhetsnummer` | `str \| None` | `#ORGNR` fält 3 |
| `företagsid` | `str \| None` | `#FNR` |
| `företagstyp` | `str \| None` | `#FTYP` (AB/E/HB/KB/EK/...) |
| `sni_kod` | `str \| None` | `#BKOD` |
| `taxeringsår` | `str \| None` | `#TAXAR` |
| `kontoplanstyp` | `Literal["BAS95","BAS96","EUBAS97","NE2007"] \| None` | `#KPTYP` |
| `räkenskapsår` | `dict[int, Räkenskapsår]` | `#RAR` (nyckel = årsnr: 0, -1, …) |
| `valuta` | `str` | `#VALUTA` (default `"SEK"`) |
| `omfattning` | `date \| None` | `#OMFATTN` (obligatorisk i typ 3 och 4I) |
| `konton` | `dict[str, Konto]` | `#KONTO` (nyckel = kontonr) |
| `dimensioner` | `dict[int, Dimension]` | `#DIM` / `#UNDERDIM` |
| `objektregister` | `dict[tuple[int,str], Objekt]` | `#OBJEKT` (nyckel = (dimnr, objektnr)) |
| `ingående_balanser` | `list[Saldopost]` | `#IB` |
| `utgående_balanser` | `list[Saldopost]` | `#UB` |
| `objekt_ingående_balanser` | `list[Saldopost]` | `#OIB` (obligatorisk i typ 4I) |
| `objekt_utgående_balanser` | `list[Saldopost]` | `#OUB` (obligatorisk i typ 4I) |
| `resultat` | `list[Saldopost]` | `#RES` |
| `periodsaldon` | `list[Periodsaldo]` | `#PSALDO` |
| `periodbudgetar` | `list[Periodsaldo]` | `#PBUDGET` |
| `verifikationer` | `list[Verifikation]` | `#VER` + underposter |
| `flagga` | `int` (0 eller 1) | `#FLAGGA` |
| `prosa` | `str \| None` | `#PROSA` |
| `adress` | `Adress \| None` | `#ADRESS` |
| `ksumma` | `int \| None` | `#KSUMMA` — CRC-32-värdet om checksumma finns, annars `None` |
| `tolkningsbehov` | `list[Tolkningsbehov]` | Rader som inte kunde tolkas enligt grammatiken |

### `Räkenskapsår`

| Fält | Typ |
|------|-----|
| `årsnr` | `int` |
| `start` | `date` |
| `slut` | `date` |

### `Konto`

| Fält | Typ | Källa |
|------|-----|-------|
| `kontonr` | `str` | `#KONTO` |
| `namn` | `str` | `#KONTO` |
| `typ` | `Literal["T","S","K","I"] \| None` | `#KTYP` |
| `enhet` | `str \| None` | `#ENHET` |
| `sru_koder` | `list[str]` | `#SRU` (ett konto kan ha flera) |

### `Verifikation`

| Fält | Typ | Källa |
|------|-----|-------|
| `serie` | `str \| None` | `#VER` fält 1 |
| `vernr` | `str \| None` | `#VER` fält 2 |
| `verdatum` | `date` | `#VER` fält 3 |
| `vertext` | `str \| None` | `#VER` fält 4 |
| `regdatum` | `date \| None` | `#VER` fält 5 |
| `sign` | `str \| None` | `#VER` fält 6 |
| `transaktioner` | `list[Transaktion]` | `#TRANS`-underposter |

### `Transaktion`

| Fält | Typ | Källa |
|------|-----|-------|
| `kontonr` | `str` | `#TRANS` fält 1 |
| `objektreferenser` | `dict[int, str]` | `#TRANS` objektlista — nyckel = dimnr, värde = objnr; förhindrar duplicerade dimensioner på en rad |
| `belopp` | `Decimal` | `#TRANS` fält 3 — `Decimal` för att undvika flyttalsfel |
| `transdat` | `date \| None` | `#TRANS` fält 4 (None ⇒ använd verdatum) |
| `transtext` | `str \| None` | `#TRANS` fält 5 |
| `kvantitet` | `Decimal \| None` | `#TRANS` fält 6 |
| `sign` | `str \| None` | `#TRANS` fält 7 |
| `radtyp` | `Literal["TRANS","RTRANS","BTRANS"]` | postens etikett |

### `Saldopost`

Återanvänds av `#IB`, `#UB`, `#RES`, `#OIB`, `#OUB`.

| Fält | Typ |
|------|-----|
| `årsnr` | `int` |
| `kontonr` | `str` |
| `objektreferenser` | `dict[int, str]` (tom dict för #IB/#UB/#RES) |
| `saldo` | `Decimal` |
| `kvantitet` | `Decimal \| None` |

### `Periodsaldo`

Återanvänds av `#PSALDO` och `#PBUDGET`.

| Fält | Typ |
|------|-----|
| `årsnr` | `int` |
| `period` | `str` (ÅÅÅÅMM) |
| `kontonr` | `str` |
| `objektreferenser` | `dict[int, str]` |
| `saldo` | `Decimal` |
| `kvantitet` | `Decimal \| None` |

### `Adress`

| Fält | Typ | Källa |
|------|-----|-------|
| `kontakt` | `str \| None` | `#ADRESS` fält 1 |
| `utdelningsadress` | `str \| None` | `#ADRESS` fält 2 |
| `postadress` | `str \| None` | `#ADRESS` fält 3 |
| `telefon` | `str \| None` | `#ADRESS` fält 4 |

### `Tolkningsbehov`

En rad som parsern inte kunde tolka fullt ut. Samlas i `SIEFil.tolkningsbehov`.

| Fält | Typ | Innehåll |
|------|-----|----------|
| `radnummer` | `int` | 1-baserat radnummer i källfilen |
| `råtext` | `str` | Den omodifierade raden som den lästes in |
| `etikett` | `str \| None` | `#`-etiketten om den gick att identifiera, annars `None` |
| `anledning` | `str` | Beskrivning av varför raden inte kunde tolkas |
| `kontext` | `str \| None` | Fritext om sammanhanget, t.ex. `"underpost till #VER på rad 42"` vid kaskad |
| `partiell_tolkning` | `str \| None` | Om parsern hann tolka delar av innehållet innan raden behövde flyttas till tolkningsbehov, en kort textrepresentation av det som tolkades. `None` om ingen tolkning alls hann ske. Detta fält är en bekvämlighet för läsbarhet — `råtext` är fortsatt den auktoritativa, oförändrade källan. |

### `Dimension` / `Objekt`

| Klass | Fält |
|-------|------|
| `Dimension` | `dimensionsnr: int`, `namn: str`, `superdimension: int \| None` |
| `Objekt` | `dimensionsnr: int`, `objektnr: str`, `namn: str` |

---

## Väsentlighetsberäkning (Modul 1, beslutat)

Modul 1 i revisionsverktyget beräknar fyra centrala riktmärken direkt ur den
redan parsade `SIEFil`-domänmodellen. Ingen ny inläsningslogik krävs — modulen
konsumerar enbart `resultat` (`#RES`) och `utgående_balanser` (`#UB`) för
innevarande räkenskapsår.

### Kontointervall och formler

| Riktmärke | Formel | Källfält |
|---|---|---|
| **Omsättning** | Σ saldo, `#RES`-poster med konto 3000–3799 | `SIEFil.resultat` |
| **Resultat** | Σ saldo, samtliga `#RES`-poster (3000–8999) | `SIEFil.resultat` |
| **Balansomslutning** | Σ saldo, `#UB`-poster med konto 1000–1999 | `SIEFil.utgående_balanser` |
| **Eget kapital** | Σ saldo, `#UB`-poster med konto 2010–2099 **+** Σ saldo, samtliga `#RES`-poster | `SIEFil.utgående_balanser` + `SIEFil.resultat` |

Samtliga summeringar avser `årsnr == 0` (innevarande räkenskapsår).
Jämförelseår (`-1`, `-2` …) omfattas inte av Modul 1.

**Tecken (korrigerat 2026-07-01 efter empirisk verifiering i implementationen):**
SIE4 lagrar kreditsaldon (intäkter, eget kapital, skulder) som negativa tal,
men debetsaldon (tillgångar) lagras redan positivt. Det innebär att **endast**
de kreditnormala riktmärkena — omsättning, resultat, eget kapital — ska
negeras innan de presenteras för användaren.

**Balansomslutningen ska INTE negeras.** Konto 1000–1999 är debetnormalt och
redan lagrat med rätt tecken i `#UB`. Att negera den summan skulle ge en
negativ balansomslutning, vilket är fel. Detta bekräftades empiriskt mot
rådata i `SIE4_Exempelfil.SE` under implementationen — den ursprungliga
formuleringen i detta dokument var tvetydig på just den här punkten.

### Beslut: Eget kapital inkluderar årets löpande resultat (Alternativ B)

Ett SIE4-underlag som exporteras innan bokslutstransaktionen är genomförd har
ofta en obokförd differens mellan tillgångssidan och skuld-/kapitalsidan —
kontot för "Årets resultat" (typiskt `2099`) har då inte uppdaterats med
periodens `#RES`-summa. Detta är förväntat beteende för en fil som
exporteras löpande under året, inte ett filfel.

Väsentlighetsberäkningen ska spegla bolagets faktiska ställning inklusive
den löpande periodens resultat, även om det formellt inte bokförts än ännu.
Eget kapital beräknas därför som:

```
eget_kapital = summa(#UB, konto 2010–2099) + summa(#RES, samtliga konton)
```

Detta motsvarar hur en revisor i praktiken bedömer väsentlighet: mot det
förväntade helårsresultatet, inte mot ett ögonblicksbild mitt i
räkenskapsåret.

**Alternativ A (ej valt):** att enbart läsa `#UB 2010–2099` rakt av, utan att
addera `#RES`. Skulle ge en lägre, mer konservativ eget kapital-siffra som
inte reflekterar periodens intjäning. Avfärdat till förmån för Alternativ B.

### Avgränsning: enbart räkenskapsår 0

Modul 1 känner inte till eller hanterar jämförelseår. Om användaren i
framtiden vill jämföra mot föregående års utfall kräver det en separat,
uttrycklig utökning — inte en implicit bieffekt av denna modul.

### Inbyggd rimlighetskontroll (frivillig, ej krav för v1)

Som en bieffekt av dubbel bokföring gäller för en fullständigt bokförd fil:

```
summa(#UB, 1000–1999) == summa(#UB, 2000–2999) + summa(#RES, samtliga konton)
```

Håller inte likheten pekar det antingen på en fil med avvikande
bokslutsprocess eller ett datafel — värt att flagga för användaren i en
senare version, men ingen blockerande valideringsregel i Modul 1 v1.

### Facit — referensfil `SIE4_Exempelfil.SE`, räkenskapsår 0 (2025)

| Riktmärke | Belopp (kr) |
|---|---|
| Omsättning | 2 583 800,00 |
| Resultat | 428 690,00 |
| Balansomslutning | 3 457 690,00 |
| Eget kapital (Alt B) | 2 267 690,00 |

Dessa värden är facit för TDD-arbetet och kontrolleras av
`test_vasentlighet.py`.

> [!IMPORTANT]
> **Exempelfilen genereras — redigera den inte för hand.**
> `samples/SIE4_Exempelfil.SE` skrivs av `samples/generera_exempelfil.py`.
> Filen ersatte 2026-08-09 SIE-gruppens exempelfil, som är tredjeparts
> material och inte får ligga i ett publikt kodförråd. Bolaget,
> organisationsnummret och samtliga motpartsnamn är påhittade.
>
> Fem egenskaper är avsiktligt inbyggda för att testsvitens facit ska
> förbli meningsfullt, och generatorn kommenterar var och en:
> serie 215 med fyra `S` mot 2157:s `T` (internmönstrets stöd 4/5),
> serie 208 med två `S` och två `T` (oavgjort röstetal, så 2084/2085 fångas
> bara av referensmönstret), konto 2157 helt utan `#IB`/`#UB` (saldo noll,
> inte ett påhittat värde), BAS-grupp 25 med debetsaldo (premissen för
> balansstapelns nedflyttningslogik) och konto 1060 `Hyresrätt`
> (cp437-regressionen mot windows-1252).
>
> Ändra beloppen via generatorn, kör om den, och uppdatera facit ovan samt
> de assertions som slår. Balansräkningen räknas fram ur verifikationerna,
> så trialbalansen går alltid jämnt ut — generatorn hävdar det med en
> `assert`.

---

## Kontotyp-vakten (Modul 2, beslutat)

Modul 2 letar efter konton vars `#KTYP`-klassificering (T/S/K/I) sannolikt är
fel — utan att någonsin ändra dem. Modulen **föreslår enbart**; en människa
avgör alltid om avvikelsen är ett verkligt fel eller en legitim särlösning.
Samma princip som "ingen rad försvinner tyst" gäller här i sin
spegelvända form: **ingen rad ändras tyst.**

Två oberoende lager körs och slås samman. Att två lager oberoende av
varandra pekar ut samma konto är i sig ett starkare signal än om bara ett
lager gör det — precis som två oberoende revisorer som landar i samma
slutsats utan att ha pratat med varandra.

### Lager 1: Internmönster (grannjämförelse inom filen)

Kräver ingen extern referensdata — jämför bara ett kontos `#KTYP` mot sina
"grannar" i samma nummerserie, inom samma fil.

| Steg | Regel |
|---|---|
| Gruppering | Konton grupperas i **serier** = de tre första siffrorna i kontonumret (`2157` → `215`) |
| Röstningströskel | Endast serier med **minst 3** konton med satt `#KTYP` deltar |
| Majoritet | Vanligaste `#KTYP`-värdet i serien blir "förväntad typ" |
| Oavgjort | Om två eller fler typer delar högsta antalet röster → serien skippas helt, ingen flaggning |
| Konton utan `#KTYP` | Deltar varken i röstningen eller kan flaggas |
| Flaggning | Konton som avviker från majoriteten i sin serie blir en `Kontotypavvikelse` |

### Lager 2: Referensmönster (klassnivå, "Version A")

En grov tumregel baserad på BAS-kontoplanens kontoklasser (den första
siffran i kontonumret) — inte en fullständig kontonivå-uppslagning mot BAS
2020 (det är en separat, större satsning, se avsnittet "Medvetet
avgränsat" nedan).

| Kontoklass | Förväntad typ |
|---|---|
| 1 (1000–1999) | T |
| 2 (2000–2999) | S |
| 3 (3000–3999) | I |
| 4–7 (4000–7999) | K |
| 0, 8, 9 | **Exkluderad** — se avgränsning nedan |

**Dokumenterat undantag — serie 776–778 (Återföring av nedskrivningar):**
Dessa konton ligger numeriskt i kostnadsklassen (7000-talet) men är
funktionellt intäkter — en återförd nedskrivning ökar resultatet. Detta är
en etablerad BAS-konvention, inte ett källsystemsfel. Serien `776`–`778`
undantas därför från standardregeln klass 7 → K och förväntas istället
vara **I**.

### Medvetet avgränsat i v1

- **Hela kontoklass 8 exkluderas** från Lager 2. Klass 8 (finansiella
  poster och bokslutsdispositioner) splittrar sig delvis rent
  (`83x` ränteintäkter = I, `84x` räntekostnader = K, `88`–`89x`
  bokslutsdispositioner = K), men delserien `80`–`82x` ("resultat från
  andelar i företag") är genuint tvetydig på nummernivå — en resultatandel
  eller nedskrivning kan vara antingen I eller K beroende på om det rör
  sig om vinst eller förlust, vilket inte går att avgöra av kontonumret
  ensamt.
- **Känt blind spot:** konto `8270` ("Nedskrivning andel/fordran övr
  företag", kodat `I` i exempelfilen) ser ut som en möjlig avvikelse i
  samma familj som `2157` — en nedskrivning förväntas normalt vara en
  kostnad (K). Kontot fångas inte av Lager 1 (för få grannar i serien
  `827` för att nå röstningströskeln) eller Lager 2 (klass 8 exkluderad).
  Detta är ett **medvetet, dokumenterat** blind spot för v1 — inte ett
  förbiseende — och en kandidat för en framtida, mer finkornig
  klass 8-hantering.
- **Fullständig kontonivå-uppslagning mot BAS 2020 ("Version B")** är inte
  byggd. Skulle ge exakt klassificering för samtliga ~500 BAS-konton,
  inklusive klass 8 i sin helhet, men kräver strukturerad extraktion av
  hela `Kontoplan_Normal_2020.pdf` — ett separat arbetspaket.

### Datamodell (FÖRSLAG — inte beslut)

```
Kontotypavvikelse:
    kontonr: str
    kontonamn: str
    angiven_typ: str          # T, S, K eller I enligt filen
    forvantad_typ: str        # T, S, K eller I enligt det/de lager som flaggade
    lager: list[str]          # "internmonster" och/eller "referensmonster"
    stod_internmonster: str | None   # t.ex. "4/5", None om ej flaggat av Lager 1
    motivering: str           # kort, läsbar förklaring
```

Om ett konto flaggas av båda lagren returneras **en** post med
`lager = ["internmonster", "referensmonster"]`, inte två separata poster.

### Facit — referensfil `SIE4_Exempelfil.SE`

| Konto | Namn | Angiven | Förväntad | Lager |
|---|---|---|---|---|
| `2084` | Överkursfond/utgår 20060101 | T | S | referensmonster |
| `2085` | Uppskrivningsfond | T | S | referensmonster |
| `2157` | Ack överavskr anläggningsdjur | T | S | **båda** (internmonster: serie 215, stöd 4/5) |

Totalt tre unika konton flaggade. `2157` är den enda som bekräftas av båda
lagren oberoende av varandra.

---

# Modul 3: Sekretesslager (maskering) — Arkitekturbeslut

**Status:** Implementerad och testtäckt (158 tester i test_sekretesslager.py, samtliga gröna).

**Placering i byggordningen:** Måste köras på all data *innan* den når Modul 4–6
(Haiku-baserade AI-anrop) och innan något framtida externt API-anrop över huvud
taget. Sekretesslagret är en spärr, inte ett tillval.

---

## 1. Syfte och skyddsobjekt

Kravet är absolut: *inga uppgifter som går att spåra i form av
organisationsnummer, namn, personnummer eller liknande identitets- eller
organisationsbekräftande uppgifter får kommuniceras med en AI.*

Det finns två skilda skyddsobjekt som råkar kallas samma sak:

| Skyddsobjekt | Exempel | Källa i SIE4 |
|---|---|---|
| Det granskade företaget | Namn, organisationsnummer | `#FNAMN`, `#ORGNR` |
| Fysiska personer i datan | Anställda (löner), anställda med utlägg | Fritextfält, `#OBJEKT`, `#ADRESS` |

---

## 2. Riskkarta: var i SIE4-filen kan PII gömma sig?

| Post | Fält | Risktyp | Säkerhetsgrad |
|---|---|---|---|
| `#FNAMN` | företagsnamn | Företagsidentitet | 100% — strukturellt garanterat |
| `#ORGNR` | orgnr, förvnr, verknr | Företagsidentitet | 100% — strukturellt garanterat |
| `#ADRESS` | kontakt, utdelningsadr, postadr, tel | Fysisk person / organisationsidentitet | 100% — fältet *är* kontakt- och adressuppgift |
| `#OBJEKT` | objektnamn, om dimensionen är personalrelaterad (t.ex. `#DIM 7 "Anställningsnummer"`) | Fysisk person | 100% — strukturellt garanterat, kräver dimensionsigenkänning |
| `#VER` | vertext | Fritext, okänt innehåll | Osäkert |
| `#TRANS` | transtext, sign | Fritext, okänt innehåll | Osäkert — `sign` kan enligt SIE-specen *vara* ett namn |
| `#PROSA` | fri text | Fritext, okänt innehåll | Osäkert |

**Arkitekturprincip — universell skanning:** fritextfälten (`vertext`,
`transtext`, `sign`, `#PROSA`) skannas oavsett kontoklass eller verifikations-
serie. Kontoklass 7 (personalkostnader) och manuella serier för utlägg är
högriskzoner att *prioritera i test*, men de används inte som filter för vad
som skannas — annars uppstår en lucka där ett namn på fel konto slinker
igenom.

---

## 3. Lagerarkitektur

Samma princip som Kontotyp-vaktens Lager 1/Lager 2: deterministiskt först,
sannolikhetsbaserat sist.

| Lager | Källa | Säkerhetsgrad | Åtgärd vid träff |
|---|---|---|---|
| **1. Strukturell** | `#FNAMN`, `#ORGNR`, hela `#ADRESS`-posten (kontakt, utdelningsadr, postadr, tel), `#OBJEKT` under personaldimension | 100% | Auto-maskera, tilldela token direkt |
| **2. Personnummer** | Regex + kontrollsiffra (Luhn) i all fritext | ~100% — matematiskt verifierad | Auto-maskera, tilldela token direkt |
| **3a. Namn, referenslista** | Exakt/normaliserad träff mot en lokal lista över anställda | Hög — känd identitet | Auto-maskera, tilldela token direkt |
| **3b. Namn, delad detektor** | Okänt versalinlett namn i titel-/namnform (2–3 ord, bindestreck/apostrof) utan träff i referenslistan — **oavsett position** i texten (början, mitten, slut) | Låg — okänd identitet, kan vara brus | Fritext/chatt: **Maskeringsbehov** (blockerar). Kontonamn/identifierande fält: **auto-maskera** (tokeniseras lokalt) |

Lager 3a och 3b är två oberoende källor. En träff som bekräftas av båda
(namnet finns i referenslistan *och* matchar versalmönstret) är extra
tillförlitlig. En regex-only-träff (t.ex. en nyanställd som ännu inte finns i
listan) är precis den typ av gränsfall som ska stoppas för granskning, inte
gissas bort.

**Arkitektbeslut, delad Lager 3b-detektor (uppdaterad efter strängstart-fixen):**
Lager 3b är numera **en enda, deterministisk detektor** (`_hitta_okanda_namn` i
`sekretesslager.py`) som används konsekvent för **all** utgående text: SIE-
fritext, chatt, kontonamn och Spiris-/MCP-vägarna. Samma igenkänning delas av
alla vägar och kan inte glida isär mellan dem.

- **Position:** okända namn fångas i **strängstart, mitten och slut**. Det
  tidigare kravet på ett föregående ord är borttaget — ett namn allra först i en
  sträng ("Xerxes Qoolio är sen") passerar inte längre.
- **Namnform:** två till tre versalinledda namnord, med **bindestreck**
  ("Anna-Lena", "Björk-Ström") och **apostrof** ("O'Brien"). Diakriter täcks av
  teckenklasserna.
- **Falska positiva:** en liten, **versionsstyrd** ekonomisk stopplista
  (`ekonomiska_termer.py`, vanliga BAS-/bokföringsrubriker) trimmas bort från
  kandidaten före bedömning. Rena rubriker ("Ingående Balans", "Eget Kapital")
  blir därför aldrig en träff, medan ett namn intill ett ram-ord
  ("Kurs Erik Svensson" → "Erik Svensson") ändå fångas. Lager 3a körs **före**
  3b, så kända namn är redan tokeniserade när 3b bedömer texten.
- **Åtgärd per dataväg:**
  - a) **Fritext och chatt** — en osäker träff ger ett `Maskeringsbehov` och
       **blockeras fail-closed** för lokal mänsklig granskning; den råa
       misstänkta texten lämnar aldrig datorn.
  - b) **Kontonamn och andra identifierande fält** — saknar en per-verifikation-
       spärr och **auto-maskeras** därför lokalt (tokeniseras) före extern
       AI-/MCP-retur. Ett MCP-serialiseringstest bekräftar att ett okänt namn i
       strängstart från Spiris-data inte förekommer i det serialiserade svaret.

**Kvarstående avgränsningar för Lager 3b (dokumenterade restrisker, inte stöd):**
Följande namnformer fångas medvetet **inte** av detektorn i denna version. De är
dokumenterade restrisker — inget påstått stöd:

- Helt **VERSALA** namn ("XERXES QOOLIO").
- Helt **gemena** namn ("xerxes qoolio").
- **Initial + efternamn** ("A. Svensson").
- **Mononymer / enordsnamn** (ett enda namn).

Två kända, medvetna bieffekter åt det säkra hållet (fail-closed) — ingendera
läcker ett namn:

- **Möjliga falska positiva** för versala **orts-/produktnamn** som saknas i den
  ekonomiska stopplistan (blockeras/maskeras i onödan; löses lokalt en gång via
  undantagslistan).
- **Möjlig övermaskering** där ett icke-ekonomiskt versalord råkar tas med i en
  tre-ords-matchning — hela frasen maskeras/blockeras, vilket bara maskerar mer
  än nödvändigt, aldrig mindre.

**Arkitektbeslut, postadress:** hela `#ADRESS`-posten maskeras, inklusive
`utdelningsadr` och `postadr`. Ursprungligt förslag (maskera endast kontakt
+ tel, låta postadress passera) är avvisat — en gatu-/postadress kan i sig
vara organisationsbekräftande, vilket faller inom kravet "eller liknande
identitets- eller organisationsbekräftande uppgifter".

**Arkitektbeslut, gemensam bolagstoken:** `#FNAMN` och `#ORGNR` identifierar
samma juridiska person och ska tilldelas **samma** token (t.ex. `BOLAG_1`
för både namn och orgnr), inte varsin. Annars läcker kopplingen mellan de
två ändå implicit — två korrelerade men olika tokens är nästan lika
avslöjande som originalvärdena.

---

## 4. Pseudonymisering — tokendesign

**Beslut:** Reversibel maskering (pseudonymisering), inte permanent
överskrivning.

- Tokens är **typade**, inte intetsägande: `PERSON_1`, `BOLAG_1`,
  `PERSONNUMMER_1`. Detta bevarar den semantiska signal Modul 4 behöver —
  "Lön PERSON_1 juni" är fortfarande identifierbart som en lönepost, vilket
  är precis vad textmatchningsmodulen ska klassificera. Vi offrar identitet,
  inte kontext.
- **Kodnyckeln** (mappningen `token → verkligt värde`) lever **endast i
  minnet under sessionen**. Den persisteras aldrig till disk. Skälet: en
  sparad fil med `{token: verkligt namn}`-par är i sig en känslig artefakt
  som måste skyddas — samma lärdom som `.gitignore`/`GIT_TEST`-arbetet med
  äkta leverantörsfakturor.
- **Demaskering** sker enbart lokalt i appen vid visning för Stefan. Den
  sker aldrig i eller inför ett AI-anrop.
- Samma verkliga värde ska alltid ge samma token inom en session (t.ex. om
  "Anna Andersson" nämns tre gånger ska hon alltid bli `PERSON_1`, inte
  `PERSON_1`, `PERSON_4`, `PERSON_7`).
- **Beslut, demaskering av `BOLAG_n`:** eftersom `#FNAMN` och `#ORGNR`
  delar samma token (§3, "gemensam bolagstoken") kan kodnyckeln bara lagra
  **ett** värde per token — inte separata fält för namn och orgnr. Värdet
  som `kodnyckel[BOLAG_n]` demaskeras till är därför den kombinerade
  strängen `"Företagsnamn (orgnr)"`, inte två separata värden. Detta är en
  medveten konsekvens av den delade token-designen, inte ett förbiseende.

---

## 5. Maskeringsbehov — spärrmekanism

Syskon till `Tolkningsbehov`, men med motsatt riktning: `Tolkningsbehov`
fångar det som inte gick att tolka. `Maskeringsbehov` fångar det som inte
säkert gick att avidentifiera — och **blockerar sändning** tills det är löst.

| Fält | Innehåll |
|---|---|
| `plats` | Vilken post (t.ex. serie + vernr, radnummer) |
| `fältnamn` | `vertext`, `transtext`, `sign`, `PROSA` osv. |
| `misstänkt_text` | Den faktiska strängen — visas för Stefan lokalt, lämnar aldrig appen |
| `träffkälla` | I v1 alltid `regex_fallback` (Lager 3b) |
| `status` | `väntar_granskning` / `godkänd_ej_pii` / `bekräftad_pii` |

**Spärrgranularitet:** blockeringen sker per verifikation, inte per fil. Om
en `#VER` innehåller en flaggad rad hålls just den verifikationen tillbaka
från AI-anropet. Övriga verifikationer i samma bunt (Modul 4 arbetar i stora
buntar) flyter vidare som vanligt.

**Princip:** vid osäkerhet — blockera, skicka inte. Fail-closed, inte
fail-open.

---

## 6. Governance / säkerhetsanteckningar

- Referenslistan över anställda (Lager 3a) är själv en känslig fil och ska
  in i `.gitignore` från dag ett — samma disciplin som `.env` i GIT_TEST.
- Kodnyckeln (token-mappningen) får aldrig loggas, skrivas till disk, eller
  inkluderas i felmeddelanden/stacktraces som eventuellt visas eller
  delas utanför appen.

---

## 7. Avgränsningar för v1 (crawl-fas) — vad som medvetet INTE ingår

- Ingen NER-modell (maskininlärningsbaserad namnigenkänning) — kan bli
  Lager 3c i walk-fasen om regex-fallback ger för mycket brus.
- Ingen persistent kodnyckel mellan sessioner.
- Ingen automatisk upplösning av `Maskeringsbehov` — kräver alltid ett
  manuellt beslut (`godkänd_ej_pii` eller `bekräftad_pii`) av Stefan.
- Samordningsnummer (dag+60, dag 61–91) hanteras inte explicit i v1 —
  `+`-tecknet testas endast som separator för personer över 100 år, inte
  som samordningsnummer-indikator. Öppen fråga för walk-fasen.

---

## 8. Datamodell (förslag, inte slutgiltig kod)

```python
@dataclass
class Maskeringsresultat:
    maskerad_siefil: SIEFil          # eller maskerad textrepresentation
    kodnyckel: dict[str, str]        # token -> verkligt värde, session-only
    maskeringsbehov: list[Maskeringsbehov]

@dataclass
class Maskeringsbehov:
    plats: str
    fältnamn: str
    misstänkt_text: str
    träffkälla: str                  # "regex_fallback"
    status: str                      # "väntar_granskning" | "godkänd_ej_pii" | "bekräftad_pii"
```

---

## 9. Gränssnitt för granskningsflödet (tillägg efter testfasen)

Följande gränssnitt förutsätts av `test_sekretesslager.py` men var inte
explicit specificerat i tidigare version av detta dokument. Flaggas som
**förslag, inte slutgiltigt beslut** — bekräfta innan Fas 6 (spärrmekanism)
implementeras:

```python
@dataclass
class Maskeringsresultat:
    maskerad_siefil: SIEFil
    kodnyckel: dict[str, str]                         # token -> verkligt värde
    maskeringsbehov: list[Maskeringsbehov]
    blockerade_verifikationer: set[tuple[str, str]]    # (serie, vernr)
    sandningsbara_verifikationer: list[Verifikation]   # ej blockerade

def uppdatera_efter_granskning(
    resultat: Maskeringsresultat,
    granskade_behov: list[Maskeringsbehov],
) -> Maskeringsresultat:
    """Tar emot Maskeringsbehov där status manuellt satts till
    'godkänd_ej_pii' eller 'bekräftad_pii', och returnerar ett uppdaterat
    Maskeringsresultat där berörda verifikationer hävts från blockering.
    Vid 'bekräftad_pii' maskeras texten retroaktivt innan hävning."""
```

Denna utökade `Maskeringsresultat` ersätter förslaget i avsnitt 8 — avsnitt
8 kvarstår som historik över den ursprungliga, enklare designen.

---

## 10. Rättelse: testfilens första version

Den ursprungliga versionen av `test_sekretesslager.py` bestod av
`raise NotImplementedError` som hela testkroppen i varje testmetod. Detta
var ett misstag från arkitektstödets sida — sådana tester kan inte bli
gröna oavsett produktionskod, och gjorde uppgiften till Claude Code
logiskt omöjlig i kombination med "rör inte befintliga tester". Claude
Code identifierade problemet korrekt och blev tillfrågat innan vidare
arbete.

Filen är ersatt med fullständigt utskrivna assertions (arrange–act–assert),
i linje med hur `test_vasentlighet.py` och `test_kontotyp_vakt.py`
byggdes. Se den uppdaterade `test_sekretesslager.py` för fullständigt
innehåll.

---

## 11. Rättelse: fail-open-bugg i `uppdatera_efter_granskning`

Efter att Fas 1–7 rapporterats klara upptäcktes en bugg i den
implementerade `uppdatera_efter_granskning`: blockeringen för en
verifikation hävdes så fort **ett** av dess `Maskeringsbehov` granskades
och fick status `godkänd_ej_pii`/`bekräftad_pii` — utan att kontrollera om
verifikationen hade **fler**, fortfarande olösta, `Maskeringsbehov`. En
verifikation med två separata okända namn (t.ex. ett i `vertext`, ett i en
`transtext`) hävdes alltså felaktigt så snart det ena granskats, medan det
andra fortfarande väntade. Detta är motsatsen till §5:s princip
("vid osäkerhet — blockera, skicka inte. Fail-closed, inte fail-open.") och
saknade testtäckning — `TestSparrmekanism`s ursprungliga fyra tester byggde
alla på verifikationer med som mest **ett** `Maskeringsbehov`.

**Rättelse:** en verifikations blockering hävs numera bara om **inga**
kvarvarande `Maskeringsbehov` för samma plats (serie/vernr) fortfarande har
status `väntar_granskning` — kontrollerat mot hela den ursprungliga
`maskeringsbehov`-listan, inte bara de objekt som skickas in i den aktuella
granskningsomgången.

**Samma princip saknades helt för `prosa`:** `prosa` är inte knutet till en
enskild verifikation (`plats` för ett prosa-`Maskeringsbehov` motsvarar
ingen serie/vernr), så ett olöst namn i `prosa` bidrog varken till
`blockerade_verifikationer` eller till någon annan spärr — det fanns helt
enkelt ingen mekanism som sa "vänta med att skicka den här prosan".
`Maskeringsresultat` har därför fått ett nytt fält:

```python
prosa_sandningsbar: str | None   # maskerad prosa om säker att skicka, annars None
```

`None` så länge minst ett `Maskeringsbehov` med `fältnamn == "prosa"`
fortfarande har status `väntar_granskning`, annars den (eventuellt
retroaktivt maskerade) prosatexten. Samma fail-closed-princip som
`blockerade_verifikationer`, applicerad på filnivå istället för
verifikationsnivå. Detta fält utökar `Maskeringsresultat` från avsnitt 9,
som i övrigt kvarstår oförändrat.

Regressionstester tillagda i `test_sekretesslager.py` (`TestSparrmekanism`)
täcker båda scenarierna: en verifikation med två `Maskeringsbehov` där bara
det ena granskas (ska förbli blockerad) samt `prosa_sandningsbar`s
fail-closed/fail-open-beteende.

---

# Tillägg: Modul 4 — Semantisk kontomatchning

Se `ARCHITECTURE.md` för grunddatamodell (`SIEFil`, `Verifikation`,
`Transaktion`, `Konto`) och Modul 3 (`Maskeringsresultat`,
`sandningsbara_verifikationer`).

**Arkitektbeslut (bekräftade av Stefan 2026-07-02):**
- Avvikelsekontrollen jämför transaktionstext mot **specifikt konto**, inte
  bara grov kontotyp (T/S/K/I).
- Modulen **flaggar bara** avvikelser. Den föreslår aldrig ett alternativt
  konto och ändrar aldrig data. Samma försiktighetsprincip som Modul 2
  (Kontotyp-vakten).

---

## 1. Mål och avgränsning

För varje transaktion i en godkänd, avmaskerad-fri batch: bedöm om
transaktionstexten rimligen matchar det konto den är bokad på. Flagga
`avvikelse` vid tydlig mismatch, `osäker` vid tveksamma fall — aldrig
tyst till `matchning` vid osäkerhet ("ingen rad försvinner tyst",
tillämpat här på tolkning snarare än parsning).

## 2. Indatakontrakt — hård privacygräns

Modulen får **bara** ta emot `Maskeringsresultat.sandningsbara_verifikationer`.
Aldrig `SIEFil.verifikationer` direkt, aldrig en blockerad verifikation.
Detta är en invariant, inte en rekommendation — samma allvarlighetsgrad
som Modul 3:s krav att kodnyckeln aldrig persisteras.

**Arkitektbeslut, prosa (reviderat 2026-07-03):** `Maskeringsresultat.prosa_sandningsbar`
används av Modul 4 som **delad bakgrundskontext**, inte som något som
analyseras eller matchas mot ett enskilt konto — det ursprungliga
antagandet (prosa saknar koppling till ett specifikt konto) står fast.
Skillnaden är att prosan ändå kan ge Haiku värdefull kontext för hela
bunten (t.ex. en revisors kommentar om ovanliga omständigheter under
perioden), och skickas därför som ett separat, delat argument till
`haiku_anropare` — samma sträng vid varje bunt-anrop, aldrig inbäddad i
ett enskilt transaktionsunderlag. Se §5.

## 3. Textkälla per transaktion

| Källa | Roll |
|---|---|
| `transaktion.transtext` | Primär signal |
| `verifikation.vertext` | Kontext, skickas alltid med |
| `konto.namn` (från `SIEFil.konton`, opåverkat av maskering) | Vad kontot faktiskt heter, t.ex. "5611 Drivmedel personbilar" |

Saknas `transtext` helt används `vertext` ensam.

## 4. Datamodell

```python
from typing import Literal
from dataclasses import dataclass

@dataclass
class Kontobedömning:
    plats: str                 # "serie=X vernr=Y radindex=N"
    kontonr: str
    text_analyserad: str       # exakt det som skickades till Haiku
    status: Literal["matchning", "avvikelse", "osäker"]
    motivering: str | None = None
```

`radindex` behövs eftersom en verifikation kan ha flera transaktioner på
olika konton — `plats` måste peka på en specifik rad, inte bara en
verifikation.

**Arkitektbeslut, `motivering`:** behålls som fri text för granskaren,
men får **aldrig** innehålla ett konkret alternativt kontonummer — det
vore att föreslå via bakvägen, exakt det Stefan just beslutade bort.
Två skyddslager:
1. Haiku-prompten instruerar explicit: beskriv *varför* det är en
   avvikelse, föreslå aldrig ett specifikt kontonummer.
2. Wrapper-lagret validerar `motivering` mot ett enkelt mönster för
   4-siffriga tal som inte matchar `kontonr` — träff → status tvingas
   till `osäker` med `motivering` bevarad som diagnostik. Detta är en
   defensiv kontroll, inte en förväntad väg (om den träffar ofta är det
   ett tecken på att prompten behöver skärpas, inte att kontrollen ska
   tas bort).

## 5. Buntning och promptkontrakt

- Varje transaktion i en bunt får ett lokalt bunt-id (`T1`, `T2`, …),
  utan koppling till riktiga SIE-fält — bara för att matcha ihop Haikus
  svar med rätt transaktion.
- Haiku anropas med strukturerad output (tool use/JSON-schema). Fri text
  att regexparsa är för skört givet hur `osäker`-hanteringen (§6)
  fungerar.
- **Arkitektbeslut, buntstorlek:** 40 transaktioner per anrop som
  startpunkt. Justerbar empiriskt mot faktisk tokenåtgång på
  `SIE4_Exempelfil.SE` — mät innan ni låser, samma princip som
  väsentlighetsberäkningens facit-arbete.
- **Prosa-kontext (tillagt 2026-07-03):** `bedöm_transaktioner` tar en
  valfri `prosa_kontext: str | None = None`. Om satt skickas den som
  **andra argumentet** till `haiku_anropare` vid **varje** bunt-anrop —
  `haiku_anropare(bunt, prosa_kontext)`, inte bara vid det första.
  `haiku_anropare`s kontrakt ändras därmed från
  `Callable[[list[dict]], list[dict]]` till
  `Callable[[list[dict], str | None], list[dict]]`. Är `prosa_kontext`
  inte satt skickas `None` — anroparen ser alltid två argument, aldrig
  ett varierande antal.

## 6. Felhantering — `osäker` som förstaklassmedborgare

Tre situationer ska alla ge `status="osäker"`, aldrig ett tyst antagande:

1. Haikus svar saknar en post för ett bunt-id som skickades in.
2. Haikus svar är strukturellt ogiltigt (fel schema, trasig JSON).
3. `motivering` innehåller ett kontonummer som inte är det analyserade
   kontot (§4, skyddslager 2).

## 7. Funktionsgränssnitt (implementerat, se kontomatchning.py)

```python
def bygg_bunt(
    verifikationer: list[Verifikation],
    konton: dict[str, Konto],
    max_storlek: int = 40,
) -> list[list[dict]]:
    """Bygger buntar av transaktionsunderlag. Varje underlag: bunt-id,
    kontonr, kontonamn, transtext, vertext, plats."""

def tolka_haiku_svar(
    bunt: list[dict],
    haiku_svar: list[dict],
    konton: dict[str, Konto] | None = None,
) -> list[Kontobedömning]:
    """Matchar Haikus svar mot bunten via bunt-id. Saknat/trasigt/
    misstänkt svar → 'osäker', aldrig tyst 'matchning'. Med konton
    reagerar motivering-skyddet (§4) bara på tal som finns i
    kontoplanen; utan konton triggar varje fyrsiffrigt tal
    (fail-closed när belopp inte kan skiljas från konto)."""

def bedöm_transaktioner(
    sandningsbara_verifikationer: list[Verifikation],
    konton: dict[str, Konto],
    haiku_anropare: Callable[[list[dict], str | None], list[dict]],
    max_bunt_storlek: int = 40,
    prosa_kontext: str | None = None,
) -> list[Kontobedömning]:
    """Orkestrerar hela flödet. haiku_anropare injiceras för
    testbarhet — mockas i wrapper-tester, är en riktig API-klient i
    produktion. prosa_kontext är delad bakgrundskontext för hela
    batchen (§2, §5) — skickas som andra argument till haiku_anropare
    vid varje bunt-anrop, None om den inte är satt."""
```

## 8. Teststrategi — två separata lager, blandas aldrig

| Lager | Testar | Metod | Körs |
|---|---|---|---|
| Wrapper-logik | Buntbygge, svarsparsning, `osäker`-fallback, motivering-skyddet, att blockerade verifikationer aldrig når en bunt | Mockad `haiku_anropare`, ingen riktig API-nyckel | Alltid, i vanlig pytest-svit |
| Träffsäkerhets-facit | Faktisk matchningskvalitet | ~15–20 kurerade rätt/fel-par ur `SIE4_Exempelfil.SE`, riktigt Haiku-anrop | Manuellt/sällan, separat process |

Wrapper-testerna avgör om koden är korrekt. Facit-testerna avgör om
prompten är bra. Olika typer av "rätt", ska inte dela testfil eller
CI-status.

## 9. Öppna punkter kvar att bekräfta

- ~~§2 prosa-antagandet~~ **Avgjord 2026-07-03:** se §2 — prosa används
  som delad bakgrundskontext.
- ~~§4 motivering-skyddets exakta tröskelvärde~~ **Avgjord 2026-07-02:**
  ett fyrsiffrigt tal i `motivering` räknas som avvikande kontonummer
  bara om det finns i den faktiska kontoplanen (`SIEFil.konton`). Skälet:
  transaktionsbelopp i SEK är rutinmässigt fyrsiffriga ("Beloppet 2340 kr
  är ovanligt högt") och skulle med det råa 4-siffersmönstret nedgradera
  legitima avvikelse-flaggor till `osäker` i onödan. Utan tillgänglig
  kontoplan (`konton=None` i `tolka_haiku_svar`) gäller det strikta
  beteendet — varje fyrsiffrigt tal triggar — eftersom belopp då inte kan
  skiljas från konto (fail-closed). Regressionstest:
  `test_motivering_med_belopp_flaggas_inte_som_avvikande_konto`.

---

# ARCHITECTURE — tillägg: MCP-brygga (Modul 1 + Modul 2 + Spiris-RAG)

**Status (uppdaterad 2026-08-06, se även "Nuvarande systemöversikt och
utvecklingsstatus" längst ned i detta dokument för hela projektets status):**
implementerad och verifierad, men VÄXT VÄSENTLIGT sedan v1 nedan skrevs.
`mcp_server/server.py` exponerar numera **54** primära verktyg (samt 31 alias, totalt 85):

| Grupp | Antal | Vad |
|---|---|---|
| Fil-baserade (Modul 1/2) | 2 | `berakna_vasentlighet`, `granska_kontotyper` |
| Spiris, läsande (§3b) | 38 | struktur, huvudbok, rapporter, reskontra, motpartsregister |
| Förslag (§3c) | 4 | `forbered_kund/kundfaktura/verifikat`, `kontrollera_utkast` |
| Juridik (PoC) | 2 | `sok_lagstiftning`, `skatteverket_rattslig_vagledning` |
| Villkor | 1 | `visa_anvandarvillkor` — alltid anropbart |

**Noll skrivande verktyg.** `forbered_*` skriver ingenting — se §3c.

Allt testat grönt i `tests/test_mcp_server.py`, `test_mcp_lasande_bredd.py`,
`test_mcp_villkorssparr.py`, `test_utkast.py`, `test_sekretess_lackprobe.py`
och `test_spiris_session.py`.

**Villkorsspärr (2026-08-03).** Varje verktyg utom `visa_anvandarvillkor`
är fail-closed bakom `compliance.ar_compliance_godkand()`. Godkännande kan
ALDRIG ske via MCP — mottagaren i andra änden är en AI, och en AI får inte
acceptera juridiskt ansvar för människan som kör den. Tre metatester bevakar
att inget nytt verktyg kan glömmas bort (spärrtest, säkerhetsnot,
lagergränsen mot `spiris_adapter`).

**Säkerhetshärdning för marknadslansering (Paket A–C, 2026-08-03):**
- **Pseudonymisering, inte anonymisering** — typade tokens (`PERSON_1`, `BOLAG_1`), demaskering enbart lokalt.
- **Sökvägsvakt (Allowlist/fail-closed):** Filbaserade MCP-verktyg (`berakna_vasentlighet`, `granska_kontotyper`) valideras nu mot en tillåten katalogslista via `SIE_MCP_SIE_KATALOGER` (`_tillaten_siefil`), vilket förhindrar otillåten filläsning utanför explicit godkända mappar.
- **ACL-härdad non-synkad lagring:** All state, liggare, session och sessionslogg skrivs till per-användare non-synkad profilmapp (`%LOCALAPPDATA%\sie-mcp`) och härdas med restriktiva filbehörigheter (Windows icacls / chmod 700) vid processuppstart (`saker_lagring.initiera_lagring()`).

## §1 Syfte och avgränsning

Detta är den första riktiga MCP-servern i sie-mcp. Den gjorde ursprungligen
bara Modul 1 (Väsentlighetsberäkning) och Modul 2 (Kontotyp-vakten)
anropsbara för en AI-klient (Claude Desktop, Claude Code, eller annan
MCP-kompatibel klient) — mot en lokal SIE4-fil.

Det är fortfarande en **tunn integrationsnivå** — ingen ny analyslogik
skrivs i serverlagret. All beräkningslogik finns redan, testad, i respektive
modul (`vasentlighet.py`, `kontotyp_vakt.py`) eller i `spiris_rag.py` (den
async hämtnings-/maskeringslogiken bakom de fem nya verktygen). Serverlagret
gör tre saker och inget mer: tar emot indata, anropar befintlig logik,
paketerar om resultatet till ett stabilt, förutsägbart svarsschema.

**Medvetet avgränsat bort, ursprungligt v1-beslut — reviderat 2026-07-19:**

- ~~Modul 3, 4, 5, 6 exponeras INTE ännu.~~ **Delvis inaktuellt:** Modul 3
  (sekretesslagret/maskeringen) körs numera INUTI varje Spiris-RAG-verktyg
  (§3b) — all data som lämnar MCP-servern mot Spiris-vägen är redan maskerad
  eller blockerad, exakt samma motor som Streamlit-appens Sektion 3. Modul 4
  (kontomatchning), Modul 5 (ISA 450-ackumulering) och SKRIVfunktionerna
  (`skapa_kund`/`skapa_kundfaktura`, se Fas 5–9 nedan) är fortfarande INTE
  exponerade som MCP-verktyg — de finns bara i Streamlit-appen (`app.py`).
- ~~Ingen sessionstillstånd.~~ **Fortfarande sant för de fil-baserade
  verktygen** (varje anrop parsar filen på nytt). **Gäller INTE
  Spiris-verktygen:** de bygger en `SpirisKlient` ur en persisterad,
  fristående session (`spiris_session.py`, se §2b) som överlever mellan
  MCP-anrop — annars vore ett OAuth-flöde per verktygsanrop orimligt.
- Endast stdio-transport (lokal process som en AI-klient startar och pratar
  med via stdin/stdout). Ingen HTTP/remote-driftsättning ännu.
- Ingen autentisering av MCP-klienten själv — irrelevant för en lokal
  stdio-process som bara du själv startar på din egen maskin. Spiris-sidan
  HAR autentisering (OAuth2, §2b) — de två är oberoende av varandra.

## §2 Beroende (arkitektbeslut, godkänt och implementerat)

Officiella MCP Python SDK:t, stabila v1.x-grenen:

```
pip install "mcp[cli]"
```

Import: `from mcp.server.fastmcp import FastMCP`

**Medvetet valt bort:**

- Det fristående `fastmcp`-paketet (PrefectHQ, v3.x) — bredare funktionsyta
  (OpenAPI-generering, proxying, OpenTelemetry) som är överkurs för två
  verktyg, och ett tredjepartsberoende snarare än det officiella SDK:et.
- v2.0-beta av det officiella SDK:et — byter namn på huvudklassen till
  `MCPServer`, målsatt stabil release 2026-07-27/28. För nära i tid för att
  lita på i ett skarpt läge nu.

v1.x är uttryckligen märkt "recommended for production" av SDK-teamet
självt, och är den variant flest etablerade tutorials och Claude Code-
integrationsguider bygger mot idag.

## §2b Spiris-session i MCP-servern (tillägg 2026-07-19)

MCP-servern är en fristående process från Streamlit-appen och kan därför
INTE återanvända appens `st.session_state.spiris_tokens`. Den bygger i
stället sin egen `SpirisKlient` via `spiris_session.py`:

- **Credentials** (`SPIRIS_CLIENT_ID`/`SPIRIS_CLIENT_SECRET`) läses ur
  miljövariabler, inte ur `.env` — MCP-serverns process startas av
  MCP-klienten (Claude Desktop/Code), inte av `streamlit run`, så samma
  `.env`-inläsningsväg som `app_config.py` använder gäller inte här.
- **Tokens** (access + refresh) läses ur en lokal, gitignorerad
  `.spiris_session.json` i arbetskatalogen. Filen skrivs tillbaka efter
  varje anrop (`spara_session`) så en automatisk token-refresh persisteras
  — MCP-servern är annars stateless mellan anrop.
- **Bootstrap är manuell (känd lucka):** det finns i dagsläget INGET
  MCP-verktyg eller skript som genomför själva OAuth2-inloggningen och
  skapar `.spiris_session.json` första gången. Filen måste skapas
  utanför MCP-flödet — i praktiken genom att låna access-/refresh-token
  från ett lyckat inloggningsförsök i Streamlit-appens egen OAuth-flöde
  (`spiris_auth_vy.py`, Sektion 1) och skriva dem till filen för hand.
  En egen `spiris_logga_in`-liknande MCP-verktygsflagga är en rimlig
  framtida förbättring men är inte byggd.
- **Fail-closed:** saknas credentials i miljön ELLER en giltig
  `.spiris_session.json` höjs `SpirisSessionFel`, som varje Spiris-verktyg
  (§3b) fångar och omvandlar till ett tydligt `info`-fält i svaret —
  aldrig en krasch mot MCP-klienten.
- **JSON-säkerhet:** `json_sakert(...)` konverterar rekursivt `Decimal` till
  `float` innan ett svar serialiseras — JSON saknar en Decimal-typ, och
  detta är den enda platsen i hela kedjan där precisionen medvetet släpps
  (presentationsgränsen mot LLM:en, inte mot någon beräkning).

## §3 Verktyg som exponeras

| Verktyg | Indata | Utdata |
|---|---|---|
| `berakna_vasentlighet` | `sokvag: str` — absolut sökväg till en SIE4-fil | se schema nedan |
| `granska_kontotyper` | `sokvag: str` — absolut sökväg till en SIE4-fil | se schema nedan |

**`berakna_vasentlighet`-svar:**

```python
{
    "vasentlighet": {
        "omsattning": float,
        "resultat": float,
        "balansomslutning": float,
        "eget_kapital": float,
    } | None,
    "tolkningsbehov_antal": int,
    "fel": str | None,
}
```

**`granska_kontotyper`-svar:**

```python
{
    "avvikelser": [
        {
            "konto": str,
            "kontonamn": str,
            "forvantad_typ": str,
            "faktisk_typ": str,
            "lager": list[str],   # "internmonster" och/eller "referensmonster"
            "stod": str | None,   # t.ex. "4/5", endast för internmönster
            "motivering": str,
        },
        ...
    ] | None,
    "tolkningsbehov_antal": int,
    "fel": str | None,
}
```

**Reviderat 2026-07-02:** ursprunglig version exponerade inte `kontonamn`
eller `motivering`, trots att `Kontotypavvikelse` redan genererar båda.
En AI-klient som ska förklara en flaggad avvikelse för användaren behövde
kunna säga *varför*, inte bara *att* — inte bara kontonumret utan namnet
på kontot, och den redan färdigformulerade motiveringstexten från
kontotyp_vakt.py. Båda fälten hämtas rakt av från `Kontotypavvikelse`,
ingen ny logik.

Samma kontrakt i båda: om `fel` är satt är huvudnyckeln (`vasentlighet` /
`avvikelser`) alltid `None`. Ett verktyg lyckas helt eller misslyckas
tydligt — aldrig en tyst delvis retur som ser ut som en fullständig ett.

## §3b Spiris-verktyg (tillägg 2026-07-19) — live data, inte en fil

Fem `async`-verktyg, alla byggda ovanpå `spiris_rag.py` (§2b bygger
klienten, `_kor_spiris_verktyg`-omslaget i `mcp_server/server.py` sköter
själva anropskoreografin). Till skillnad från §3:s fil-verktyg tar dessa
INGEN sökväg — de pratar direkt mot Spiris/Visma eAccounting REST API v2
med den persisterade sessionen.

| Verktyg | Indata | Vad den gör |
|---|---|---|
| `spiris_kontosaldon` | `rakenskapsar_id: str, tom_datum: str` (yyyy-mm-dd) | Ackumulerat utgående saldo (YTD) per konto. Rent aggregat — inget blockeras. |
| `spiris_kontotransaktioner` | `rakenskapsar_id: str, kontonr: str` | Maskerade transaktionsrader för ETT konto. Blockerade verifikationer (olösta maskeringsbehov) utesluts. |
| `spiris_sok_verifikationer` | `rakenskapsar_id: str, sokterm: str` | RAG-sökning i MASKERAD vertext/transtext bland sändningsbara verifikationer. |
| `spiris_resultatrapport` | `start_datum: str, slut_datum: str` | Strukturerad BAS-resultatrapport (samma `bygg_resultatrapport`-motor som Streamlit-dashboarden). |
| `spiris_balansrapport` | `per_datum: str` | Strukturerad BAS-balansräkning (samma `bygg_balansrapport`-motor). |

**Gemensamt svarsenvelope** för de tre RAG-verktygen (kontosaldon,
kontotransaktioner, sök) — `spiris_rag._envelope`:

```python
{
    "data": list[dict],       # de faktiska posterna, redan maskerade
    "antal_exkluderade": int, # blockerade poster pga olösta maskeringsbehov
    "info": str,               # människoläsbar sammanfattning av ovanstående
}
```

`spiris_resultatrapport`/`spiris_balansrapport` returnerar i stället
rapport-dictarna rakt av (samma form som `fpa_motor.bygg_resultatrapport`/
`bygg_balansrapport` — se Rapporter-fliken i Streamlit-appen) eftersom de
är aggregat (saldon + kontonamn). **Anm. (2026-08-04):** formuleringen
"utan PII" ovan var för stark — kontonamn KAN bära personuppgifter (ett
konto kan döpas om fritt i Visma, "7010 Lön Anna Andersson"), och de körs
därför genom `skapa_kontonamnsmaskerare` med EN delad tokengenerator per
rapport. Rapporterna bär sedan paket A även `sakerhetsnot`, av samma skäl:
ett kontonamn är angriparstyrd text. Det är transaktionsradsverktyget
(`spiris_kontotransaktioner`) och sökverktyget som därutöver hanterar
fritext och därför även BLOCKERAR olösta verifikat.

**Fail-closed på tre nivåer**, alla fångade av `_kor_spiris_verktyg`:
1. Ingen giltig Spiris-session (§2b) → `{"data": [], "antal_exkluderade": 0, "info": "Ingen Spiris-session: <orsak>"}`.
2. Ett API- eller nätverksfel under själva hämtningen → loggas till stderr, `{"data": [], "antal_exkluderade": 0, "info": "Fel vid hämtning från Spiris."}` — aldrig rå exception-text till klienten.
3. En lyckad hämtning sparar ALLTID tillbaka en ev. refreshad token
   (`finally: spara_session(klient)`), oavsett om anropet i övrigt
   lyckades eller misslyckades.

**Inte exponerat än:** `spiris_rag.hamta_kassaflodesanalys` och
`spiris_rag.hamta_dashboard` (används idag bara internt av Streamlit-
appens FP&A-flik) samt likviditetsprognosen (`fpa_motor.
bygg_likviditetsprognos`, med moms-händelsen sedan 2026-07-19 — se
huvuddokumentets statusavsnitt) har inga MCP-verktyg alls ännu.
SKRIVfunktionerna (`skapa_kund`/`skapa_kundfaktura`) är av design
INTE exponerade som MCP-verktyg — de kräver ett mänskligt "Godkänn och
Skicka" i Streamlit-appens UI (Human-in-the-Loop, se statusavsnittet) som
inte har någon MCP-motsvarighet, och bör inte få en förrän ett likvärdigt
godkännande-steg finns för ett rent verktygsanrop.

---

## §3c Förslagsverktyg (tillägg 2026-08-04) — föreslå, aldrig utföra

**Problemet.** MCP-servern ska kunna hjälpa till med kunder, kundfakturor och
verifikat, men projektets bärande invariant är att varje skrivning mot ett
affärssystem passerar ett mänskligt "Godkänn och skicka". Över MCP finns
ingen sådan yta: mottagaren i andra änden är en AI.

**Det förkastade alternativet.** MCP-protokollet har `elicitation`
(`Context.elicit`), som var förstahandsförslaget. Det duger INTE som grind:
specen säger uttryckligen att en agentklient får besvara en elicitation
*automatiskt* i stället för att fråga användaren. En grind som kan passeras av
samma modell som lade förslaget är ingen grind.

**Elicitation används däremot som tidig sammanfattning** (S2-D,
`_visa_tidig_sammanfattning`): stödjer klienten det visas förslagets faktiska
värden redan när `forbered_*` anropas. Verkan är avsiktligt ASYMMETRISK och
testad i båda riktningar:

| Svar från klienten | Följd |
|---|---|
| `decline` / `cancel` / nej | Inget utkast skapas — elicitation kan STOPPA |
| `accept` / ja | Utkast skapas med `utfort: False` — elicitation kan INTE godkänna |
| Stöd saknas eller fel uppstår | Flödet fortsätter oförändrat (fail-OPEN) |

Fail-OPEN är rätt här just för att detta inte är ett säkerhetssteg: det finns
ingenting att fail-closa, och motsatsen vore att låta en klientegenskap tysta
funktionen. `ctx` injiceras av FastMCP och ingår inte i verktygets schema —
klientmodellen kan varken se eller sätta det (testat).

**Konstruktionen.**

```
AI föreslår  ->  utkast i lokal kö  ->  människan granskar i appen  ->  appen POSTar
                 (parser/utkast.py)     (verkliga värden, Åtgärder)
                 MCP skriver aldrig
```

MCP-servern behåller därmed **noll skrivförmåga**. Den kan skapa ett förslag;
den kan aldrig utföra det. `mcp_server/server.py` får inte ens referera
`skapa_kund`, `skapa_kundfaktura`, `bekrafta_for_sandning` eller
`markera_skickat` — statiskt testat i `test_utkast.py`.

**Fyra fail-closed-kontroller i `bekrafta_for_sandning`**, alla obligatoriska:

1. Utkastet finns.
2. Status är `vantar` (dubbelsändningsskydd).
3. Det är inte äldre än 24 timmar — underlaget i Spiris kan ha ändrats.
4. **SHA-256 över den kanoniserade nyttolasten stämmer.** Det människan såg är
   exakt det som skickas; en ändrad utkastfil ger vägran, inte tyst avvikelse.

**Uppslagningar sker vid utförandet, inte vid förslaget.** Kund-id och
artikel-id är levande Spiris-data som kan ha ändrats sedan förslaget lades.
Hashbindningen skyddar användarens BESLUT (vem, vad, hur mycket) — inte de
tekniska id:n beslutet översätts till. Kunduppslaget är fail-closed på namn:
två träffar ger fel, inte en gissning.

**Utkastfilerna bär omaskerade verkliga värden.** Det måste de — det är
payloaden som ska POSTas och som människan ska granska. Skyddet är
lagringsplatsen (ACL-härdad `state_dir()`), 24-timmarsgallringen som omfattar
även skickade utkast, och sökvägsvakten på `utkast_id` (som kommer från en AI).
Se `DATASKYDD.md` 2.3.1 (E-33–E-36) och `RISKREGISTER.md` R-12/R-13.

**Sandbox-verifierat (2026-08-04).** Hela kedjan körd skarpt mot Visma:
verifikat A31 i testbolaget "X Sandbox", återläst genom
`spiris_sok_verifikationer` och `spiris_kontotransaktioner`. Verifieringen
avslöjade två fältnamnsbuggar (`VoucherText`/`NumberSeries`) som samtliga 1651
tester missade — inget test påstod något om payloadens innehåll. Fältnamnen är
nu låsta med `_FangarKlient`-tester. **Momsvägen (`VatCodeId`) är oprövad.**


---

## §3d Snabbvyer (tillägg 2026-08-04) — deterministiska, utan AI

Ett fält med knappar högst upp i Rapporter-fliken. En knapp väljer en vy som
ersätter flikens ordinarie innehåll; samma knapp igen, eller "✕ Stäng", tar
tillbaka den.

**Bärande designbeslut: vyerna anropar aldrig en AI.** "Visa mina förfallna
kundfakturor" är en filtrering och en sortering. Att skicka den frågan till en
språkmodell ger latens, kostnad, dataegress till en AI-leverantör och risk för
hallucinerade siffror — utan en enda fördel. Ett statiskt test underkänner
`snabbvyer.py` om den importerar ett AI-lager. Följden: **snabbvyerna fungerar
utan AI-nyckel**, och AI:n behåller det den är bra på (varför-frågor,
uppföljning, resonemang).

Skiktningen följer projektets vanliga mönster: `snabbvyer.py` är UI-fri och
returnerar `Snabbvyresultat` (nyckeltal + sektioner + tabellblock);
`snabbvy_render.py` ritar. Tabell-HTML återanvänds från `chatt_renderare.py`,
beräkningarna från `fpa_motor.py`.

### Påminnelse- och betalningsförslag: kundens EGET mönster

Den enda vyn med egen logik värd att beskriva. Absoluta dagar säger lite — en
kund som alltid betalar 12 dagar sent är inte ett problem på dag 5, medan en
kund som alltid betalar i tid och nu är 5 dagar sen är en tidig varningssignal
som en vanlig reskontralista missar helt.

| Nivå | Villkor |
|---|---|
| 🔴 Röd | `dagar_forsent > kundens snitt + PAMINNELSE_MARGINAL_DAGAR` |
| 🟡 Gul | Förfallen, men inom kundens mönster |

Marginalen (3 dagar) finns för att en kund som normalt betalar 12 dagar sent
annars blir röd på dag 13 — utan den blir hela listan röd varje dag. **Kund utan
känd betalhistorik hamnar i RÖD** och märks "okänt — ny kund" (arkitektbeslut
B1): en ny kund som inte betalar är värd att kontakta, och att tyst lägga den i
gult vore att dölja den. Rangordning inom varje grupp: `belopp × dagar över
mönstret`, så en stor faktura som precis brutit mönstret hamnar över en liten
som är kroniskt sen.

Skarpt exempel ur sandboxen: en kund som normalt betalar **12,7 dagar i
förskott** och nu är 65 dagar sen ligger 77,7 dagar över sitt mönster — en
större avvikelse än en kund som är 117 dagar sen men alltid är det.

### Klartext lokalt

Vyerna visar **riktiga motpartsnamn**. Det är en direkt följd av att
maskeringsgränsen flyttades till egressen (se `DATASKYDD.md` §3): en kundlista
där den största kunden heter "Fiktiv Kund 3" är oanvändbar, och användaren är
personuppgiftsansvarig för uppgifter hon redan ser i sitt affärssystem.
Maskeringen sker i `reskontra_tvatt.maskera_for_egress`, vid varje väg ut ur
datorn — aldrig på skärmen.

**Anm. om typkontrollen där:** `maskera_for_egress` avgör post-typ med
`type(post).__name__` i stället för `isinstance`. Streamlit kan ladda om en
modul mellan omkörningar, varvid klassidentiteten byts och `isinstance` mot den
nyimporterade klassen fallerar för objekt skapade av den gamla. Felläget var
fail-closed (AttributeError, alltså ett fångat fel — ingen läcka), men
strängjämförelsen överlever omladdningen.


## §4 Felhantering

Samma princip som resten av projektet, applicerad på serverlagret:
**inget oväntat undantag får propagera okontrollerat till MCP-klienten.**

- Saknad fil, oläsbar fil, eller ett totalt parse-haveri → fångas, `fel`
  fylls i med ett begripligt meddelande, huvudnyckeln blir `None`.
- Parsning som lyckas men genererar `tolkningsbehov`-poster (redan
  befintlig mekanism i parsern) → `fel` är `None`, men
  `tolkningsbehov_antal` > 0 så att klienten kan varna användaren om att
  underlaget inte var 100 % entydigt.
- Oväntade interna undantag (buggar) → fångas i en sista `except Exception`,
  loggas till stderr (aldrig till stdout — det stör MCP-protokollets
  JSON-RPC-ström), och returneras som ett generiskt `fel`.

## §5 Filstruktur

```
mcp_server/
    server.py              # 54 primära verktyg + 31 alias + FastMCP-instansiering
parser/
    spiris_session.py       # MCP-serverns EGEN Spiris-session (§2b) — delar
                             # inget med Streamlit-appens session_state
    spiris_rag.py            # async hämtning+maskering bakom §3b-verktygen
    utkast.py                # lokal kö för FÖRESLAGNA skrivningar (§3c) —
                             # hashbunden, 24 h livslängd, godkänns i appen
    snabbvyer.py             # deterministiska ett-klicks-vyer (UI-fri, ingen AI)
    snabbvy_render.py        # Streamlit-rendering av snabbvyfältet
    formatering.py           # universell sifferformatering
    formatering_ui.py        # sidomenyns formateringsval
.spiris_session.json         # gitignorerad, MCP-serverns persisterade tokens
tests/
    test_mcp_server.py       # integrationstester mot exempelfilen + fejkad Spiris-klient
    test_spiris_session.py   # sessionshanteringen i isolering
```

## §6 Testning

Fil-verktygen (§3) testas som integrationstester mot `SIE4_Exempelfil.SE`
med redan kända facit-värden (samma siffror som Modul 1 och Modul 2:s egna
testsviter använder) — inga mockar, exempelfilen är liten och snabb att
parsa på riktigt. Spiris-verktygen (§3b) och sessionshanteringen (§2b)
testas mot en injicerad fejk-klient (samma mönster som `test_spiris_
adapter.py`/`test_spiris_rag.py`) — aldrig en riktig nätverksanrop eller
riktiga credentials i testsviten.

## §7 Driftsättning och lokal test

1. Rök-test direkt i terminalen: `python mcp_server/server.py` ska starta
   utan fel och vänta tyst på stdin (Ctrl+C för att avsluta).
2. Registrera i Claude Code (kör i projektmappen):
   ```
   claude mcp add sie-mcp -- python /full/sökväg/till/mcp_server/server.py
   ```
   Använd absolut sökväg — den spawnade processens arbetskatalog är inte
   garanterat projektroten.
3. Ny Claude Code-session i samma projekt, testa med naturligt språk:
   *"Använd sie-mcp för att beräkna väsentlighet för SIE4_Exempelfil.SE
   och lista sedan alla kontotyp-avvikelser."*
4. `/mcp` inuti sessionen visar anslutningsstatus om något strular.
5. **För Spiris-verktygen (§3b):** sätt `SPIRIS_CLIENT_ID`/
   `SPIRIS_CLIENT_SECRET` i miljön INNAN Claude Code startar servern (en
   redan körande MCP-serverprocess läser inte om miljövariabler), och se
   till att en giltig `.spiris_session.json` finns i den katalog servern
   startas från (§2b — manuell bootstrap tills vidare).

**Känd Windows-fallgrop:** sätt `PYTHONUNBUFFERED=1` om servern verkar
hänga utan att svara — Python buffrar annars stdout, och MCP-klienten kan
stå och vänta på ett svar som redan finns i bufferten men inte skickats.

---

# Nuvarande systemöversikt och utvecklingsstatus (tillägg, 2026-07-19)

Allt ovanför denna punkt är den historiska beslutsloggen — fortsatt korrekt
för de algoritmer/regler den beskriver, men skriven medan projektet bara
var en SIE4-parser plus fyra fristående analysmoduler. Sedan dess har
projektet vuxit till en fullständig Streamlit-app med en live Spiris/Visma
eAccounting-koppling (läsning OCH skrivning), en Tool-Calling AI-agent, och
en egen FP&A-dashboard — utöver den ursprungliga MCP-servern. Det här
avsnittet beskriver **hela systemet som det faktiskt ser ut idag**,
grundat i en genomgång av `parser/` (73 moduler plus 13 i `parser/rum/`), `app.py` och
`mcp_server/server.py`. Testsviten: **2096 tester, samtliga gröna** (plus ett som hoppas över: ett fail-closed-fall som bara gäller icke-Windows)
(`pytest tests/`).

## 0. Kodförrådet startades om 2026-08-09 inför publicering

Projektet utvecklades lokalt i 135 commits innan det gjordes publikt. Den
historiken kunde inte följa med: den innehöll tredjeparts upphovsrättsskyddat
referensmaterial — rättskällor, redovisningslitteratur, SIE-gruppens
filformatsspecifikation, BAS-kontoplanen, en leverantörs avtalsvillkor och
akademiska artiklar om gränssnittsdesign — och en commit är permanent.

Kodförrådet byggdes därför om från ren mark med en **allowlist**: bara filer
som aktivt lagts till finns här. Det är avsiktligt inte en blocklist, eftersom
en blocklist kräver att man har hittat allt farligt, medan en allowlist bara
kräver att man vet vad som ska med.

Detta ingår därför **inte** i kodförrådet, utan ligger lokalt hos utvecklaren:
rättskällorna och specifikationerna (som i stället citeras med källhänvisning),
arbetsanteckningar, interna genomförandespecifikationer, engångsskript från
tidigare ombyggnader och verktygen för demoinspelning. `.gitignore` förbjuder
blankt PDF, kalkylblad och Office-dokument — det finns i dag ingen legitim
sådan fil i förrådet, så förbudet kostar ingenting och fångar misstaget innan
det blir permanent.

`HISTORIK.md` bevarar samtliga 135 commit-rubriker. De är projektets egna
meningar och kan återges; det är diffarna och referensmaterialet som inte kan.

`.gitattributes` finns av en konkret anledning: `samples/SIE4_Exempelfil.SE`
är cp437-kodad med CRLF enligt SIE-specifikationen, och utan `*.SE -text`
normaliserar git radsluten till LF. En klon på Linux eller macOS hade då fått
en fil som avviker från det format parsern finns för att läsa.

## 1. Två gränssnitt, en delad kärna

```
parser/  — 73 moduler (+13 i rum/), UI-fria, testbara utan Streamlit- eller
           MCP-runtime (domänmodell, analysmotorer, Spiris-klient,
           AI-lager, FP&A)
  │
  ├── app.py               Streamlit-app (huvudprodukten)
  │                         5 flikar, Human-in-the-Loop-UI, egen
  │                         session_state, hela skriv-vägen mot Spiris
  │
  └── mcp_server/server.py  MCP-server
                             54 primära verktyg (§1–§3c ovan) + 31 alias, stdio,
                             egen fristående Spiris-session (§2b),
                             villkorsspärr, noll skrivförmåga
```

Båda gränssnitten konsumerar SAMMA `parser/`-bibliotek och samma
domänmodell (`SIEFil`/`Konto`/`Verifikation`/`Transaktion`/`Saldopost`) —
ingen logik är duplicerad mellan dem. De skiljer sig åt i vad de exponerar:
`app.py` har allt (inklusive skrivfunktionerna och hela FP&A-dashboarden,
gated bakom mänskligt godkännande i UI:t), MCP-servern har en medvetet
smalare, läsorienterad delmängd (§1–§3b ovan).

## 2. Modulöversikt (`parser/`)

| Modul | Rader | Ansvar | Status |
|---|---|---|---|
| `sie4_parser.py` | 832 | SIE4-grammatiken (se toppen av detta dokument) | Stabil |
| `domain_model.py` | 135 | Dataclasses: `SIEFil`, `Konto`, `Verifikation`, `Transaktion`, `Saldopost` m.fl. | Stabil |
| `vasentlighet.py` | 47 | Modul 1 — väsentlighetsberäkning | Stabil |
| `kontotyp_vakt.py` | 151 | Modul 2 — kontotyp-vakten | Stabil |
| `sekretesslager.py` | 428 | Modul 3 — maskering, tvåvägs HITL-beslut, undantagslista (allowlist) | Stabil |
| `kontomatchning.py` | 223 | Modul 4 — semantisk kontomatchning (Haiku-bunt) | Stabil |
| `ackumulering.py` | 156 | Modul 5 — ISA 450-ackumulering | Stabil |
| `haiku_klient.py` | 147 | Riktig Anthropic-integration bakom Modul 4 | Stabil |
| `masking_memory.py` | 59 | Lokalt minne över redan granskade verifikat (ej krypterat — bär ingen PII) | Stabil |
| `app_config.py` | 351 | `.env` + tre krypterade `.enc`-lager (§6 nedan) | Aktiv |
| `app_vy.py` | 628 | Filinläsning, maskeringsgranskning, fakturautkast, AI-verktygstolkning, fuzzy kundsökning | Aktiv |
| `ai_konfiguration.py` | 175 | Leverantörsoberoende modellhämtning | Stabil |
| `ai_adapter.py` | 122 | Fabrik: bygger rätt analys-/chatt-/agentanropare per leverantör | Stabil |
| `analysflode.py` | 163 | Orkestrerar Modul 1+2+4+5 till "Analys (ISA 450)"-fliken | Stabil |
| `chatt_klient.py` | 363 | Pedagogisk chatt + Tool-Calling-agent (§5 nedan) | Aktiv |
| `samtalsflode.py` | 356 | AI-kontextbygge + multi-turn-historik (Fas 10) | Aktiv |
| `spiris_klient.py` | 232 | HTTP/OAuth-lager mot Spiris REST API v2 — alla fyra verben (GET/POST/PUT/DELETE) genom EN refresh-väg | Aktiv |
| `spiris_auth_vy.py` | 143 | Testbara OAuth2-hjälpare för Streamlit-inloggningen | Stabil |
| `spiris_adapter.py` | 685 | Spiris-JSON → domänmodell, reskontra, kontering, ROT, fakturapayload | Aktiv |
| `spiris_rag.py` | 245 | Async hämtning+maskering, delas av MCP-servern och FP&A-dashboarden | Stabil |
| `spiris_session.py` | 91 | MCP-serverns egen, fristående Spiris-session (§2b) | Stabil |
| `reskontra_tvatt.py` | 195 | GDPR-tvätt av leverantörs-/kundreskontra | Stabil |
| `fpa_motor.py` | 1098 | Rena FP&A-motorer: P&L, balans, nyckeltal, kassaflöde, what-if, kapitalstack/WACC, likviditetsprognos (+moms) | Aktiv |
| `fpa_vy.py` | 1641 | Glue SIEFil/Spiris-data → FP&A-rendering, all display-config | Aktiv |
| `fpa_dashboard.py` | 1100 | Streamlit-rendering av hela Rapporter-fliken | Aktiv |
| `navigering.py` | 184 | Flikstruktur, åtgärdsbadge (inkl. väntande utkast), sticky-CSS | Stabil |
| `snabbvyer.py` | 576 | **Deterministiska ett-klicks-vyer** (reskontra, åldersanalys, påminnelse-/betalningsförslag). UI-fri, anropar ALDRIG en AI | Aktiv |
| `snabbvy_render.py` | 158 | Streamlit-rendering av snabbvyfältet: knapprad, färgnivåer, sektioner | Aktiv |
| `formatering.py` | 28 | Universell sifferformatering (decimaler, tusentalsavgränsare) | Aktiv |
| `formatering_ui.py` | 46 | Sidomenyns formateringsval | Aktiv |
| `utkast.py` | 292 | Lokal kö för FÖRESLAGNA skrivningar (§3c) — hashbunden, 24 h | Aktiv |
| `bokslutskontroll/` | — | **Paket** (undantag från flat-fil-mönstret, se B-6 i hantverksboken). Deterministiskt kontrollskikt `SIEFil -> list[Fynd]` — lager 1 i `hantverksbok/BOKSLUTSPROGRAMMET.md`. Grupp A (K-01–K-06, K-13, K-15) och grupp B (K-07–K-10) klara; grupp C (K-11, K-12, K-14) och MCP-verktyget återstår. Detaljerad status i `hantverksbok/BOKSLUTSKONTROLLER.md`. | Under uppbyggnad |

"Aktiv" = förändrad under de senaste utvecklingsomgångarna (Spiris-
skrivvägen, AI-agenten, likviditetsprognosen); "Stabil" = oförändrad sedan
respektive modul först testtäcktes.

## 3. Streamlit-appen (`app.py`) — åtta-rums-modellen

**Uppdaterat 2026-08-06.** Rubriken har hetat "sju-rums-modellen" ett tag,
men det här avsnittet beskrev fram till nu fortfarande den tidigare
femflikarsversionen (Datastatus/Åtgärder/Rapporter/Investeringskalkyl/
AI-Assistent) — den byttes ut i sin helhet i `4bd1bde` ("Slutför Fas 1-7"),
utan att arkitekturdokumentet hann med. Nedan är den FAKTISKA strukturen.

`app.py` är en tunn koreograf (< 200 rader): sidkonfiguration, villkorsspärr,
sidopanelens inställningar och datakälleval, och sist `st.navigation(sidor)`
+ `pg.run()`. All faktisk rendering ligger i `parser/rum_render.py` (en
funktion per rum) och `parser/rum/` (rumsdefinitionerna/metadata som
`st.Page` pekar mot). Toppnavigeringen (`position="top"`) listar numera åtta rum:

- **🏠 Översikt** (`rendera_oversikt`, default-sida) — datakälla, antal
  verifikationer, tolknings-/maskeringsbehov, sändningsbara/blockerade
  verifikationer, en notisyta och utflödesloggen. Passiv, ingen interaktion.
- **✅/🔴 Beslut** (`rendera_beslut`, fliktiteln byts dynamiskt till en
  åtgärdsstatus-badge via `navigering.bygg_atgardsstatus`) — allt som
  kräver ett mänskligt beslut i EN vy: maskeringsgranskningen (Modul 3, tre
  val per rad — maskera / **ingen maskering** / avvakta, där "ingen
  maskering" sparas i den krypterade undantagslistan så strängen aldrig
  flaggas igen), obehandlade verifikationsavvikelser (Modul 2/4), väntande
  MCP-utkast (`utkast.py`, Steg 2 — "Godkänn och Skicka") och hela
  kundfaktura-/kundskapandeflödet (`_rendera_fakturautkast`). Badgen är röd
  så länge något väntar.
- **📥 Pengar in** (`rendera_pengar_in`) — kundreskontrans snabbvyer
  (`snabbvyer.SNABBVYER_KUND`): utestående, förfallna, åldersanalys,
  påminnelseförslag i två nivåer. Räknar lokalt, ingen AI-latens/-egress.
- **📤 Pengar ut** (`rendera_pengar_ut`) — motsvarande för leverantörs-
  reskontran (`SNABBVYER_LEVERANTOR`): utestående, förfallna, åldersanalys,
  betalningsförslag.
- **📚 Böckerna** (`rendera_bockerna`) — under konstruktion (Fas 2 i
  omdesignplanen; verifikatsökning och momsöversikt är inte byggda än).
- **📊 Rapporter & analys** (`rendera_rapporter`) — de färdigbyggda FP&A-
  rapporterna (`st.session_state.rapportunderlag`: resultat, balans,
  nyckeltal, kassaflöde, likviditetsprognos) via
  `fpa_dashboard.rendera_rapporter`. Kund-/leverantörssnabbvyerna som
  tidigare låg här flyttade till Pengar in/Pengar ut i samma omdesign.
- **📈 Investeringskalkyl** (`rendera_investeringskalkyl`) — what-if-
  simulering (en eller flera finansieringskällor samtidigt via kapitalstack
  + WACC), staplad kapitalstapelfigur (Sankey borttaget), narrativt lager.
- **⚖️ Juridik & Skatt** (`rendera_juridik`) — ett helt fristående chatrum, hårdstyrt (via en separat Anthropic-klient i `juridik_chatt.py`) att enbart svara utifrån gällande svensk rätt och Skatteverkets ställningstaganden. Använder SFS- och SKV-verktygen (`juridik_api.py`) och tillåter inga gissningar. Avlastar kognitivt genom förifyllning ("Regler för leasing" etc).
  **Villkorsspärren gäller även juridikverktygen.** De registrerades utan spärr och kunde därmed skicka en AI-formulerad sökterm till `data.riksdagen.se` innan någon människa godkänt villkoren; `test_alla_registrerade_verktyg_har_ett_sparrtest` fångade det. Spärren är pålagd på båda, med ett test som verifierar att den ligger FÖRE nätverksanropet. Att verktyget inte läser bokföring är inget skäl till undantag: ett utflöde är ett utflöde oavsett mottagare, och undantag som motiveras med "just det här är ofarligt" urholkar regeln ett verktyg i taget. Transporten är dock fortfarande okrypterad HTTP via `urllib` i stället för projektets `httpx`-mönster — se RISKREGISTER **R-16**, öppen.

AI-chatten (tidigare en egen flik) är nu ett genomgående lager snarare än
ett eget rum — se `assistentpanel`/`_rendera_utflodeslogg` i respektive
rum och §5 nedan för agent-/fil-lägena.

**Efterhandsrättelser (2026-08-05, `c154cbb`):** omdesignen (`4bd1bde`)
lämnade fyra körvägar trasiga vid faktisk användning — en saknad import
(`bygg_oversikt`), ett formateringsobjekt byggt som fel typ (`dict` i
stället för `Formateringsval`, kraschade alla åtta reskontrasnabbvyer),
en Rapporter-funktion som refererade namn ur ett scope som inte längre
fanns (kvarleva från när koden låg inline i den gamla monolitiska appen),
och en saknad `datetime`-import i kundfaktura-godkännandet. Samtliga
rättade och verifierade.
**Lärdom:** ingen av dessa fångades av enhetstestsviten — bara körning i
riktig Streamlit-runtime (`streamlit.testing.v1.AppTest`) avslöjade dem. Det
mönstret har upprepats flera gånger i projektet: enhetstester som inte
instansierar runtime missar precis de fel som en användare möter först.

## 4. Spiris/Visma eAccounting-integrationen

- **OAuth2** Authorization Code-flöde (`spiris_auth_vy.py`), `redirect_uri
  = https://localhost:44300/callback`. Tokens lagras i Streamlit-appens
  `session_state` (aldrig på disk) — MCP-serverns motsvarande session
  (§2b) är helt separat.
- **Läsning:** `/companysettings`, `/accounts`, `/vouchers`,
  `/accountbalances`, `/suppliers`, `/supplierinvoices`, `/customers`,
  `/customerinvoices`, `/fiscalyears`, `/articleaccountcodings`,
  `/articles`.
- **Skrivning** (`spiris_adapter.skapa_kund`/`skapa_kundfaktura`, POST mot
  `/customers`/`/customerinvoices`): ALDRIG direkt från en analys eller
  ett AI-verktygsanrop — alltid bakom ett explicit mänskligt
  "Godkänn och Skicka" i UI:t (Human-in-the-Loop).
- **Utkastvägen är standard sedan Steg 4** (`utfor_utkast(..., mal=MAL_UTKAST)`):
  ett godkänt verifikat eller en godkänd kundfaktura går som standard till
  Spiris utkastköer (`/voucherdrafts`, `/customerinvoicedrafts`), inte rakt in
  i räkenskaperna. Skälet är oåterkallelighet — ett bokfört verifikat kan
  enligt bokföringslagen 5 kap. bara rättas med ett nytt, och en bokförd
  faktura kan mejlas till mottagaren. Ett utkast går att ändra (PUT) och ta
  bort (DELETE), och befordras via `/convert` av människan i Spiris eget
  gränssnitt. **`/convert` exponeras aldrig över MCP** — befordran är
  bokföringsakten. Direktbokföring (`MAL_BOKFOR`) finns kvar som ett
  uttryckligt val i Åtgärder-vyn, med varning.
  `mal` ligger MEDVETET utanför den hashbundna nyttolasten: hashen binder VAD
  som skrivs (konton, belopp, datum, mottagare), inte VART det levereras —
  samma resonemang som för uppslagning av kund-id och artikel-id.
- **Mottagargrinden för utåtriktade åtgärder (Steg 4c/5).** Kundfakturans
  livscykelåtgärder — mejla (`/email`), påminna (`/paymentreminders`),
  registrera betalning (`/payments`) och makulera (`/void`) — har INGEN
  utkastmotsvarighet i Spiris. Utkastvägen ovan går alltså inte att använda för
  de två som når en tredje man.

  Barriären är i stället att `utfor_utkast` vägrar utföra en typ i
  `UTATRIKTADE_TYPER` utan argumentet `granskad_mottagare`. Skälet är konkret:
  Vismas `EmailApi.Email` är VALFRITT, och utelämnas det mejlar Spiris till
  kundens registrerade adress — till någon ingen människa granskat. AI:n kan
  dessutom per konstruktion inte se adressen, eftersom `hamta_kunder` (Steg 2)
  aldrig hämtar `EmailAddress`.

  Adressen hämtas därför lokalt i godkännandevyn med
  `hamta_utskicksgranskning` — den enda funktionen i `spiris_adapter` som
  medvetet returnerar en e-postadress och ett omaskerat kundnamn — visas för
  människan, och skickas sedan tillbaka in som det granskade värdet. Den sätts
  EXPLICIT i payloaden, så att "det som visades" och "det som skickades" är
  samma sträng och inte två oberoende uppslag. Saknas adress spärras knappen.

  `hamta_utskicksgranskning` får aldrig nås från `mcp_server/server.py` eller
  `parser/spiris_rag.py`. Det bevakas statiskt via AST i
  `tests/test_utatriktade_atgarder.py`, som också verifierar att detektorn
  faktiskt fäller när en sådan import finns.

  Steg 5b utvidgade grinden till offert- och orderutskick samt e-faktura.
  Varken `QuoteApi` eller `OrderApi` bär en e-postadress, så mottagaren slås
  upp via dokumentets `CustomerId`; för e-faktura hämtas den registrerade
  AutoInvoice-mottagaren (`/customers/{id}/autoinvoicerecipients`) och visas
  som "Namn (elektronisk adress)". Vyn frågar bara
  `hamta_granskad_mottagare(klient, typ, nyttolast)` — vilken
  granskningsfunktion varje typ kräver är adapterns kunskap, inte vyns, och
  ett metatest kräver att VARJE typ i `UTATRIKTADE_TYPER` har en väg.

  **Kreditering ingår inte.** `/customerinvoices/{id}/credit` har ett tomt
  path-objekt i Spiris OpenAPI-spec — ingen dokumenterad metod, samma
  tillstånd som `dryrun`-endpointsen. Att gissa fram verb och kropp för en
  åtgärd som skapar en kreditfaktura mot en riktig kund vore precis den sortens
  gissning kodbasen är byggd för att undvika.

  Kedjeåtgärderna (godkänn offert, konvertera, slutför, makulera order) når
  ingen tredje man och omfattas därför INTE av mottagargrinden — men de ändrar
  dokumentens tillstånd oåterkalleligt och kräver ett godkänt utkast. De styrs
  av en hårdkodad tabell `_SALJDOKUMENTATGARDER`; en kombination som inte står
  där utförs aldrig. `offert/godkann` är det första stället i kodbasen som
  faktiskt använder klientens PUT (`uppdatera`), som tillkom i Steg 1.
- **Klientens verb** (`spiris_klient.py`): `hamta_alla`/`hamta_en` (GET),
  `skicka` (POST), `uppdatera` (PUT) och `ta_bort` (DELETE) går alla genom
  `_anrop_med_refresh` — EN plats som äger kontraktet "401 → en refresh →
  exakt ett retry → annars fail-closed". Tidigare fanns den mekaniken i två
  kopior (`_get_med_refresh`/`_post_med_refresh`); med fyra verb hade det
  blivit fyra kopior av ett säkerhetskontrakt som kan glida isär.
  `Content-Type` sätts bara när det finns en kropp — en GET eller DELETE
  ska inte påstå att den skickar JSON (låst av `TestVerbHygien`).
  `uppdatera`/`ta_bort` tillkom 2026-08-05 och är **medvetet oanvända**:
  förmågan finns, men ingen kodväg leder fram till dem förrän Steg 7 (se
  §4b).
- **Konteringsmotor:** föreslår BAS-konton utifrån fakturatyp (byggmoms →
  3231; juridisk/fysisk person → 3041 arbete / 3051 material), med
  ROT-flaggning (`RotReducedInvoicingType`/`RotPropertyType`/`Persons`)
  verifierad mot en riktig sandbox-POST. Fakturarader kräver `ArticleId`
  (inte ett direkt kontofält) — löses via `/articleaccountcodings`.
- **Självlärande konteringsminne:** när en faktura godkänns sparas
  kundens namn + valda kontering krypterat (`konteringsminne.enc`); nästa
  faktura för samma kund pre-fylls automatiskt.
- **Fuzzy kundsökning** (`app_vy.sok_lika_kunder`, `difflib`): innan en ny
  kund skapas jämförs namnet mot befintliga kunder (fångar t.ex.
  "Karl"/"Carl"-varianter). Gränssnittet erbjuder ALDRIG en fritext-
  motfråga här — bara knappval (befintlig kandidat / skapa ny / avbryt).

## 4b. Spiris-täckning och utbyggnadsplanen (tillägg 2026-08-05)

### Var vi står

Kodbasen anropar **18 distinkta endpoints** av Spiris 272 paths (228
dokumenterade operationer enligt
`https://eaccountingapi.vismaonline.com/openapi/v2.json`) — ca 7 % av ytan.
Spiris fördelning: 113 GET, 62 POST, 32 PUT, 21 DELETE.

Målbilden är att `sie-mcp` ska fungera som ett *fönster ovanpå* affärssystemet:
så mycket som möjligt av det som går att göra i Spiris ska gå att göra här, så
att friktionen vid ett systembyte faller — användaren behåller sitt fönster
och byter bara adaptern under.

### Två saker som ser ut som luckor men inte är det

1. **Filtrering och sortering fungerar redan.** `hamta_alla`/`hamta_en` tar
   `params` och slår ihop dem med `$page`; `$filter`, `$sortby` och
   `$pagesize` är alltså tillgängliga — bara oanvända. Bygg inget stöd.
2. **PDF och SIE4-export är inte binära.** `/sie4export/{från}/{till}` och
   `/customerinvoices/{id}/pdf` returnerar JSON (`DocumentApi` med
   `TemporaryUrl`, respektive `InvoiceUrlApi` med `Url`). `hamta_en` klarar
   dem. Nedladdningen från den temporära URL:en sker mot ett annat värdnamn
   utan bearer-token och hör inte hemma i `SpirisKlient`.

### Åtta steg

| Steg | Innehåll | Status |
|---|---|---|
| 1 | Klientverb: PUT + DELETE | **Klar 2026-08-05** |
| 2 | Läsbredd: kunder, leverantörer, projekt, kostnadsställen, kontosaldo, referensdata | **Klar 2026-08-05** |
| 3 | Bankavstämning (`/banktransactions` matched/unmatched) | **Klar 2026-08-05** |
| 4 | Utkast i Spiris (`/voucherdrafts`, `/customerinvoicedrafts`) som standardväg | **Klar 2026-08-06** |
| 5 | Kundfakturans livscykel: mejla, påminnelse, betalning, makulering | **Klar 2026-08-06** |
| 5b | Offert- och orderkedjan + e-faktura (kreditering utgår, se nedan) | **Klar 2026-08-06** |
| 6 | Inköp + attest: leverantörsfakturautkast, attest, leverantörsbetalning | **Klar 2026-08-06** |
| 7 | Masterdata-ändring och borttagning (read-modify-write) | **Klar 2026-08-06** |
| 8 | SIE4 in/ut: export till lokal fil, import via beskrivet utkast | **Klar 2026-08-06** |

**Alla åtta stegen är genomförda på MCP-sidan. Användargränssnittet har inte
följt med.** Godkännandesidan är komplett — alla 16 utkasttyper renderas i
rummet Beslut med destinationsval och mottagarvisning — men nio läsförmågor
saknar vy helt, rum 5 "Böckerna" renderar fortfarande bara
`st.info("under konstruktion")`, och av 16 utkasttyper går bara 2 (`kund`,
`kundfaktura`) att initiera från appen. De övriga 14 kan bara föreslås av
AI-assistenten.

Den asymmetrin drar åt fel håll i förhållande till R-13: grinden håller, men
initiativet har flyttat till AI:n. Ett förslag på elva rum i fyra grupper
finns framtaget men är ännu inte beslutat.

**Sandbox-rökprov 2026-08-06 (läsvägar, steg 2–5b):** alla 19 endpoints
svarade, inget fält saknades, alla adapterfunktioner kördes live utan fel, och
egressprovet mot fältallowlistorna hittade noll läckor. Ett verkligt fynd
åtgärdades: `Number` är None på 3 av 5 offerter/ordrar, så uppslag på enbart
nummer gjorde onumrerade dokument oåtkomliga.

**Skrivprov samma dag (utkastformer, allt raderat):** `/voucherdrafts` och
`/customerinvoicedrafts` skapades via de riktiga kodvägarna, fälten kom
identiska tillbaka, läsvägen `spiris_verifikatutkast` hittade utkastet med
GUID-id intakt, och Steg 1:s `ta_bort` kördes skarpt för första gången.

Provet avförde Steg 4:s flaggade osäkerhet — `ReversedConstructionServices
VatFree=False` och ett utelämnat fält ger identiskt resultat — men avslöjade
ett ALLVARLIGARE och äldre fel: **byggmomsvägen ger inte omvänd
skattskyldighet.** Konto 3231 väljer bara artikelkodning, och 3041/3231 löses
ut till samma artikel; momsen kräver att kunden är flaggad OCH att radflaggan
sätts. En byggmomsfaktura debiterar i dag 25 % moms som inte ska debiteras.
Felet finns på både utkastvägen och den skarpa vägen och härrör från Fas 7.
**R-15 är åtgärdat och verifierat mot levande sandbox** (byggmoms → moms
0,00 / total 1000,00; vanlig faktura → 250,00 / 1250,00). Tre delar:

- `BYGGMOMSKONTON` **härleds ur `_KONTERINGSTABELL`** i stället för att
  hårdkodas — ändras tabellen följer mängden med, annars hade en ändring av
  byggmomskontot tyst kopplat bort momshanteringen igen.
- Radflaggan `ReversedConstructionServicesVatFree` sätts **per rad** ur den
  granskade radens kontonr. Den är det enda som utlöser omvänd
  skattskyldighet; fakturanivåns `ReverseChargeOnConstructionServices` är
  HÄRLEDD ur kunden och går inte att sätta (mätt: skickat `True` för en
  oflaggad kund kom tillbaka som `False`).
- Två fail-closed-grindar i `utfor_utkast`: en **oflaggad kund vägras** med ett
  besked som säger vad användaren ska göra, och **byggmoms kan inte
  direktbokföras** — `CustomerInvoiceRowApi` saknar fältet helt, så momsen
  hade ofrånkomligen blivit 25 %.

Den sista punkten är värd att notera: byggmoms går bara via utkastvägen. Steg
4:s beslut att göra utkast till standard visade sig alltså vara det enda sättet
att fakturera byggmoms korrekt. Regressionsskydd i `tests/test_byggmoms.py`.

- **Inköp och attest (Steg 6).** Leverantörsfakturor går till
  `/supplierinvoicedrafts` av samma skäl som kundfakturor — `/convert`
  exponeras aldrig, och ett AST-test bevakar att ingen av de tre utkastköerna
  befordras från koden.

  **Attest bär en dold utåtriktad väg.** `ApprovalApi` har `RejectionMessage`
  och `RejectionMessageReceivers`: ett avslag kan alltså SKICKA ETT MEDDELANDE
  till namngivna mottagare. Adaptern fyller aldrig i de fälten — ett avslag
  härifrån är en statusändring, inte ett utskick. Behövs ett meddelande skriver
  människan det i Spiris, där hon ser vem som får det.

  Tre saker som sandbox-provet 2026-08-06 rättade och som specen inte säger:

  1. **`TotalAmount` är i praktiken obligatoriskt** på ett
     leverantörsfakturautkast. Utan det avvisar Spiris med *"The amount on
     standard account 2440, recievables is not equal with
     TotalAmountBaseCurrency"*. Beloppet härleds medvetet INTE ur raderna — det
     är fakturans nominella belopp enligt leverantören.
  2. **`RemainingAmount` är NEGATIVT på leverantörsfakturor** (och på
     kundkreditfakturor). `bygg_betalningspayload` jämförde tidigare rakt mot
     värdet, vilket gjorde VARJE delbetalning av en leverantörsskuld till en
     fullbetalning — 500 kr mot 1 000 kr i skuld räknades som fullt betald,
     eftersom 500 > −1 000. Jämförelsen sker nu på beloppens storlek.
  3. **`hamta_leverantorsfakturor` saknade `id`** — tredje gången samma
     felklass, efter `hamta_bankkonton` (Steg 3) och `hamta_offerter`
     (sandbox-fyndet). Ett verktyg som inte exponerar sin identifierare är
     oanropbart, och det syns inte i något test.

- **Masterdata (Steg 7).** **PUT NOLLAR UTELÄMNADE FÄLT.** Sandbox-mätt
  2026-08-06 på en egen testkund: en PUT med bara de obligatoriska fälten satte
  `EmailAddress`, `InvoiceAddress1`, `Telephone` och `Note` till `None`. (En
  helt partiell PUT — bara `Id` och `Name` — avvisas dessutom med 400.) Steg
  1:s docstring påstod detta; nu är det mätt.

  Det gör **read-modify-write obligatoriskt**, och kopplar ihop med
  integritetsdesignen på ett skarpt sätt: `hamta_kunder` hämtar med flit aldrig
  e-post, telefon eller adress, så en AI kan inte förse oss med dem. En naiv
  uppdatering hade därför raderat precis de fält AI:n aldrig fick läsa. Det
  nuvarande objektet hämtas i stället LOKALT vid utförandet, ändringarna läggs
  ovanpå, och hela objektet skrivs tillbaka.

  **Ändringsallowlisten** (`_MASTERDATA`) är lika viktig som läsallowlisten:
  utan den kunde ett AI-förslag sätta vilket fält som helst i ett objekt
  människan bara ombetts godkänna en namnändring på.

  `omvand_byggmoms` på en kund gör R-15:s förutsättning åtkomlig, men har en
  egen: Spiris avvisar flaggan med *"VatNumber can not be null or empty when
  using ReverseChargeOnConstructionServices"*. En förhandskontroll gör det
  svaret begripligt. `vatnummer` är MEDVETET inte ändringsbart — för en enskild
  firma är det härlett ur innehavarens personnummer.

  **Borttagning** finns bara för kund, leverantör och bankkonto. Artiklar och
  projekt saknar DELETE i Spiris och inaktiveras i stället — rimligt, eftersom
  de refereras från historiska poster.

- **SIE4 in och ut (Steg 8).** Två åtgärder med motsatt riskprofil, och de
  behandlas därefter.

  **Exporten är läsande men bär systemets största läckrisk.** En SIE4-fil
  innehåller hela bokföringen i klartext — varje motpartsnamn, varje
  verifikationstext, möjligen personnummer — och ingenting av det passerar
  maskeringen. Filens innehåll når därför aldrig ett MCP-verktyg: adaptern
  laddar ner till en ACL-härdad katalog under `state_dir()` och returnerar
  bara `filnamn`, `sokvag`, `storlek_byte` och period. Inte heller Spiris
  `TemporaryUrl` lämnas ut — den är en bärarnyckel till samma innehåll.

  **Exporten saknar `#KTYP`.** Sandbox-verifierat: filen går att läsa tillbaka
  med `parse_sie4` (32 verifikationer, 234 konton), men samtliga 234 konton kom
  utan kontotyp. Modul 2 (`kontotyp_vakt`) kan alltså inte arbeta på en
  Spiris-export — vakten hoppar över `typ=None`, vilket är fail-closed men gör
  analysen tom. Kontotyper får man via LIVE-vägen (`hamta_kontoplan`, som läser
  `Type` ur `/accounts`).

  **Importen är den mest ingripande skrivningen i hela API:t** — den kan skriva
  in en hel bokföring, ingående balanser och ett årsavslut i ett levande bolag,
  utan utkastform och utan ångerväg. Två grindar följer: AI:n kan aldrig
  LEVERERA en fil, bara peka ut en sökväg under en katalog användaren själv
  konfigurerat (`_tillaten_siefil`); och sammanfattningen människan godkänner
  räknas fram ur FILEN med projektets egen SIE4-läsare, inte ur AI:ns
  beskrivning. En base64-blob är inte något en människa kan granska.

  Alla fyra importflaggorna är avstängda som standard. `EndYearAdjustment`
  utför ett årsavslut och `ImportOpeningBalance` skriver ingående balanser —
  den som vill ha dem får begära dem uttryckligen.

Utskicken och kedjeåtgärderna är fortfarande oprövade: de går inte att köra
utan att lämna spår.

Steg 3–8 specificeras **ett i taget**, efter att föregående steg gett facit mot
en riktig sandbox. Skälet är kodbasens egen historik: specen har haft fel förr
(`Type` för svenska bolag, `VoucherText` inte `Description`, `/quotes` inte
`/offers`, `Amount` vs `TotalAmount`), och detaljspecar skrivna på gissningar
får en auktoritetston som är svår att värja sig mot.

### Arbetsdelning efter risk

Integrationen byggs stegvis, och arbetet delas efter **risk** snarare än efter
mängd. Det som kan läcka personuppgifter eller skriva i ett skarpt affärssystem
specificeras i förväg, i detalj, innan en rad kod skrivs:

| Specificeras i förväg | Byggs mot given specifikation |
|---|---|
| Fältallowlists per endpoint | Adapterfunktioner enligt given allowlist |
| Allt som rör `sekretesslager`, `reskontra_tvatt`, `utkast` | `spiris_rag`-omslag, MCP-verktygsdeklarationer |
| Alla skrivvägar | Läsverktyg |
| Guardrail-tester skrivna i förväg | Tester för normalbeteendet |

Testsviten är kontrollkanalen: guardrail-testet skrivs före funktionen det
vaktar, så att en väg som saknar sin spärr aldrig hinner bli grön.

**Den svåraste regeln är fältallowlisten.** `/customers` returnerar 66 fält
inklusive kontaktpersoners namn och mobilnummer, adresser, IBAN och
ROT-fastighetsbeteckning; `/suppliers` returnerar bankkonto, clearing, IBAN,
bankgiro och plusgiro. Ett felaktigt hämtat fält fångas normalt **inte** av
något test — det finns tester för att rätt fält finns, inga för att fel fält
saknas. Steg 2:s uppgift 2.8 rättar det för de tre registren genom att låsa
nyckeluppsättningen med `assert set(rad.keys()) == FÖRVÄNTADE_NYCKLAR`
(likhet, inte delmängd).

## 5. AI-lagret

Två skilda anropar-kontrakt, medvetet separata (se `chatt_klient.py`s
moduldocstring):

| | `skapa_verklig_chattanropare` | `skapa_agentanropare` (Fas 9–10) |
|---|---|---|
| Läge | Fil-läge (ingen Spiris) | Spiris-kopplat |
| Minne | Inget — varje fråga isolerad | Fullt: hela konversationshistoriken skickas om vid varje anrop |
| Verktyg | Inga | `skapa_kund`, `skapa_kundfaktura`, `efterfraga_val` |
| Kontrakt | `Callable[[str, str], str]` | `Callable[[list[dict[str,str]], str], AgentSvar]` |

**`efterfraga_val`** (Fas 10) löser problemet där agenten fastnade i
textbaserade frågeloopar: saknas information för ett obligatoriskt fält
anropar AI:t detta verktyg (fråga + 2–5 alternativ) i stället för att
skriva en fritextfråga. Gränssnittet (`app.py`) renderar alternativen som
`st.button()` direkt under meddelandet, plus ett permanent "Skriv
eget..."-textfält. Ett klick lägger till valet i historiken och kör
`st.rerun()` — nästa AI-anrop får hela den växande historiken och kan
därmed slutföra den ursprungliga uppgiften i stället för att fråga om
samma sak igen. All indata sker via `st.chat_input()`, all historik
renderas via `st.chat_message()`.

## 6. Sekretess och kryptering — sammanfattning

Tre lokala, krypterade lager (`app_config.py`), alla Fernet med **samma**
nyckel (`SIE_MCP_FERNET_KEY` i den gitignorerade `.env`):

| Fil | Innehåll |
|---|---|
| `mask_dict.enc` | Maskeringsliggaren — inlärda namn→token-mappningar |
| `allowlist.enc` | Undantagslistan — strängar manuellt godkända som "ej PII" |
| `konteringsminne.enc` | Kund → senast godkända konteringsmönster |

`masking_memory.json` (redan granskade verifikat-ID:n) ligger MEDVETET
okrypterad — den bär ingen PII, bara `serie#vernr`-referenser.

## 7. Teststatus

**Uppdaterat 2026-08-06: 2005 gröna, 1 skip, 0 fail av 2006 insamlade**
(`pytest tests -q`). Ingen riktig API-nyckel eller nätverksanrop i
testsviten — Anthropic- och Spiris-klienter injiceras alltid som fejkar.

Föregående notering ("1773 gröna, 1 fail") avsåg
`test_alla_registrerade_verktyg_har_ett_sparrtest`, som föll när Fas 6:s
aliasverktyg registrerades utan att undantas i testets täckningsmängd.
Aliaserna är rena en-radsdelegerare och täcks implicit av respektive
`spiris_*`-test; undantaget är nu uttryckligt i testet. De 17 övriga nya
testerna kommer från Steg 1 nedan.
Skrivvägarna (`skapa_kund`/`skapa_kundfaktura`, ROT-fälten, fakturaradernas
`ArticleId`-uppslagning) är dessutom verifierade mot en RIKTIG Spiris-
sandbox (live POST, sedan verifierade fältnamn hårdkodade i
`spiris_adapter.py`) — se kommentarer i modulen för exakt vilka fält som
bekräftats så.

**Den enda kvarstående röda:**
`test_mcp_villkorssparr.py::test_alla_registrerade_verktyg_har_ett_sparrtest`
— en metatest vars allowlist (`SPIRIS_ARGUMENT`) aldrig kompletterades när
de 22 Spiris-läsverktygen från Steg 1/Steg 3 lades till. **Verifierat manuellt
att det INTE är en verklig lucka:** samtliga 22 går genom den delade
`_kor_spiris_verktyg`, som kontrollerar `_villkor_godkanda()` fail-closed
före all åtkomst (`mcp_server/server.py` rad ~324–330, med en kommentar som
uttryckligen säger detta). Det metatestet saknar bara sin egen
regressionstäckning, vilket är en öppen punkt.
(Före `c154cbb` gick testsviten dessutom inte ens att SAMLA IN —
`tests/test_snabbvyer.py` refererade en konstant som togs bort i `4bd1bde`
utan att testfilen uppdaterades. Rättat i samma commit.)

## 8. Kända begränsningar / öppna punkter

- **MCP-serverns Spiris-bootstrap är manuell** (§2b) — `.spiris_session.json`
  måste skapas för hand tills ett eget inloggningsverktyg byggs.
- **MCP exponerar inte** Modul 4/5, skrivfunktionerna, kassaflödesanalysen,
  hela dashboard-kompositionen eller likviditetsprognosen — bara det som
  listas i §3/§3b. Allt annat finns bara i `app.py`.
- **Ny-kund-adressfälten** (`Address1`/`ZipCode`/`City` i
  `app_vy.bygg_ny_kund_payload`) är INTE verifierade mot en riktig
  sandbox-POST, till skillnad från kundens övriga fält
  (`Name`/`IsPrivatePerson`/`CorporateIdentityNumber`) och hela
  fakturaflödet. Bästa nuvarande gissning utifrån Visma-API:ts
  namnkonvention på andra endpoints — flaggat i koden.
- **ROT — `Persons`-arrayens personnummer** har aldrig kunnat testas mot
  en riktig privatpersons-testkund i sandboxen (ingen sådan fanns
  tillgänglig) — dokumenterat, oförändrat gap.
- **Momsberäkningen** (`fpa_vy.momssaldo_fran_sie`) föredrar konto 2650
  men faller tillbaka på att summera hela intervallet 2610–2649 om 2650
  saknar saldo — en approximation, inte en fullständig BAS-momskonto-
  klassificering. Förfallodagen antas alltid vara den 12:e i månaden
  (`fpa_motor.nasta_momsforfallodag`), oavsett bolagsstorlek eller
  bankdags-förskjutning vid helg.


## Tillägg: Utökad rumsmodell (Etapp 4)

Användargränssnittet (`app.py` och `parser/rum_render.py`) har utökats från den ursprungliga sju-rums-modellen till 11 rum, fördelade i fem logiska huvudgrupper via `st.navigation`. Detta chunking-mönster minskar den kognitiva belastningen och låter UI:t växa i takt med att MCP-servern får fler förmågor.

### Gruppering
- **Dagen:** Översikt, Beslut
- **Pengar:** Pengar in, Pengar ut, Bank
- **Bokföring:** Böckerna, Register
- **Analys:** Rapporter, Investeringskalkyl, Juridik & Skatt
- **Data:** Data in/ut

### Juridik & Skatt (Hårdstyrd Agent)
Ett av de nya rummen, **Juridik & Skatt**, isolerar en specialiserad AI-agent (`parser/juridik_chatt.py`) med en hårdstyrd systemprompt. Denna agent får endast tillgång till juridiska uppslag (t.ex. `sok_lagstiftning` och `skatteverket_rattslig_vagledning`) och kan inte läsa företagets bokföringsdata. Detta etablerar en stark systemgräns: användaren vet att agenten här inne endast tillämpar gällande rätt, och svaren standardiseras till (1) kort svar på 2-8 meningar, (2) lagcitat, och (3) källhänvisning.

### SIE4-export (Data in/ut)
Verktyget erbjuder nu fullständig export till SIE4 direkt från UI:t i rummet **Data in/ut**. Eftersom exporter enbart innebär läsning av data skickas dessa inte till utkastkön (som hanterar skrivningar), utan genereras och laddas ned direkt via ett dedikerat nedladdningsflöde.



### Omstrukturering av AI-chattar och svarslägen (Etapp 5)
Under rummet "AI-chattar" har AI-fokuserade rum samlats.
1. **AI Juridik & Skatt**: Hårdstyrd agent utan tillgång till företagsdata, tidigare under Analys.
2. **Företagsdata**: En kontextmedveten chatt (har tillgång till SIE-datan) som svarar enligt användarens valda personlighet ("Kort", "Pedagogisk", "Analytisk"). Personlighetsinstruktionerna ("svarslägen") har designats för att **alltid använda AI:ns fulla intelligens och fulla underlag**, och begränsar endast tonalitet och formatering för att aldrig strypa AI:ns analytiska förmåga.

### Register-bugg och State Management (2026-08-06)
Efter Etapp 2 upptäcktes buggar där 'Register'-rummet antingen hängde eller visade tomma tabeller ('Antal 0') trots aktiva datakällor. Felet låg i en tyst krasch under initieringen av Spiris-klienten (felaktigt metodanrop ladda() istället för las_config()) kombinerat med ett stavfel i state-variabeln (spiris_token istället för spiris_tokens). Eftersom felen svaldes (xcept Exception: pass) blev klient=None, vilket ledde till att registren antingen cachades som tomma listor [] eller varnade. Genom att tvinga fram ett loggat fel och korrigera variabelnamnen har state-hanteringen för Spiris-klienten blivit robust.

---

# Tillägg 2026-08-10 — täckning, distribution och startblocksinvarianten

Det här avsnittet är skrivet efter Etapp 0–17 i `PLAN_SPIRIS_TACKNING.md` och
`PLAN_SPIRIS_ETAPP8.md`, samt publiceringsförberedelserna i
`PLAN_INFOR_PUBLICERING.md`. Det **ersätter** delar av §4b, §7 och §8 — se
punkt 6 sist.

## 1. Spiris-täckningen efter Etapp 0–17

Mätt mot `https://eaccountingapi.vismaonline.com/openapi/v2.json`:

| Mått | Värde |
|---|---|
| Anropbara sökvägar i specen (normaliserade) | 161 |
| Sökvägar `spiris_adapter.py` rör | **91** |
| Täckning | **57 %** |

Måttet är *sökvägar*, inte operationer, och är därför inte direkt jämförbart
med de 31 % **operationer** som mättes 2026-08-09 i
`ARKITEKTUR_SPIRIS_TACKNING.md`. Riktningen är däremot entydig: transportlagret
har fått OData-filtrering, 429-hantering och binärhämtning; utkastvägen är hel
(skapa → läsa → ändra → radera → bokföra); periodiseringar, bilagor,
kontoplansunderhåll, bokföringslås, ROT/RUT, kvittning, offertutkast,
prislistor och etiketter finns.

MCP-ytan är nu **125 verktyg, 3 resurser, 1 resursmall och 5 prompter**.
Resurser och prompter fanns inte alls före Etapp 6.

Medvetet ej byggt, med skäl i `PLAN_SPIRIS_ETAPP8.md` avsnitt 3:
`/messagethreads`, `/appstore`, `/partnerresourcelinks`, `/banks`,
`/backgrounds`, `POST /quotes`, `POST /orders`, samt de fyra operationer som
enligt specens egna beskrivningar inte finns för svenska bolag — däribland
`POST /paymentvoucher` (endast norska och nederländska bolag).

## 2. Startblocksinvarianten

`mcp_server/server.py` hade fram till 2026-08-10 sitt startblock mitt i filen:

```python
if __name__ == "__main__":
    mcp.run()
```

`mcp.run()` återvänder aldrig. Allt som definierades efter anropet
registrerades därför **bara vid import** — alltså i testsviten — och aldrig när
servern faktiskt kördes. Uppmätt före rättningen: **62 av 125 verktyg** nådde
en klient. De 63 som föll bort var i praktiken hela utfallet av Etapp 8–17,
samtliga domänalias och båda juridikverktygen.

Invarianten, som gäller framåt:

> **Startblocket ligger sist i `server.py`.** Ett verktyg, en resurs eller en
> prompt som definieras under det anropet är osynlig för varje riktig klient,
> och testsviten blir grön ändå.

Regressionsskyddet är `tests/test_mcp_startblock.py` (3 tester): modulen körs
med `runpy` under namnet `__main__` med `FastMCP.run` ersatt, och antalet
registrerade verktyg, resurser och prompter i det ögonblicket jämförs med
antalet efter full körning. Talen ska vara lika.

## 3. Mönstret: grön svit, trasig produkt

Startblocket är det tredje felet av samma slag på kort tid:

| Fel | Varför sviten missade det |
|---|---|
| Periodiseringens skrivväg saknade gren i `utfor_utkast` | Testerna prövade `forbered_*`, aldrig vägen från godkännande till Spiris |
| `forbered_underlagskoppling` gick förbi villkorsspärren | Metatestet listade verktyget som täckt utan att pröva spärren |
| Startblocket | Testerna **importerar** modulen; guarden hoppas då över |

Samtliga tre fanns i en helt grön svit. Slutsatsen är inte att fler enhetstester
behövs, utan att sviten mäter fel sak i tre avseenden: den kör aldrig servern
som en klient gör, den följer aldrig en åtgärd hela vägen från utkast till
Spiris, och en metatests täckningsmängd kan tystas i stället för att uppfyllas.

Rökproven mot sandbox täcker API-anropen. Ingen grind har hittills täckt
**processen** — att starta servern och räkna vad en klient faktiskt ser. Den
grinden bör införas i kommande planer.

## 4. Distributionsfrågan — öppen

En arkitekturfråga som saknar svar, och som avgör vem produkten är till för.

Spiris eAccounting-API behandlar klienter som *konfidentiella*: token-växlingen
kräver `client_secret` (se `spiris_auth_vy.vaxla_kod_mot_token`). En hemlighet
kan inte hållas hemlig i ett program som installeras hos användaren och
publiceras som öppen källkod. Det ger tre möjliga modeller:

| Modell | Registrering | Server hos oss? | Friktion |
|---|---|---|---|
| **BYOK (nuvarande, N1)** | Varje användare | Nej | Hög — användaren måste bli Visma-utvecklare och ansöka om produktionsåtkomst |
| Broker | Quiet Numbers | Ja — ser tokens och data | Låg |
| Publik klient | Quiet Numbers | Nej | Låg — **men kräver Vismas medgivande** |

Jämförelsen med marknaden 2026-08-10: Vismas **egen** MCP (`mcp.spiris.se`)
löser det genom en separat auktorisationsserver (`auth.mcp.spiris.se`) med
`token_endpoint_auth_methods_supported: ["none"]`, PKCE och dynamisk
klientregistrering — alltså publika klienter utan hemlighet. `fellow-spiris`
löser det med en broker. `spiris-rust` är ett bibliotek och skjuter frågan
vidare. **Ingen löser det som en lokalt installerad app med användarens egna
uppgifter.**

Att Visma behövde bygga en ny auktorisationsserver för sin egen MCP är den
starkaste indikationen på att `identity.vismaonline.com` inte tillåter publika
klienter.

Konsekvens så länge frågan är obesvarad: sandbox fungerar för alla, men
**produktionsdata kräver att varje användare själv ansöker hos Visma**. Det
begränsar målgruppen till den som är beredd att göra det — och gör
maskeringen, utkastgrinden och det lokala utförandet till produktens skäl att
finnas, inte dess bekvämlighet.

Frågan ställs till `api@spiris.se` tillsammans med ansökan om
produktionsåtkomst.

## 5. Installationsarkitekturen — planerad, ej byggd

`ARKITEKTUR_INSTALLATION.md` och `PLAN_INSTALLATION.md` beskriver hur de tolv
stegen från nedladdning till fungerande MCP ska bli fyra: per-användarinstaller
utan UAC, guiden som ett nytt rum i Streamlit-appen, lokal OAuth-lyssnare i
stället för manuell URL-inklistring, och automatisk inskrivning i
`claude_desktop_config.json` med säkerhetskopia.

Ingenting av det är byggt. Etapp A är dessutom spärrad av en kontrollfråga:
godtar Spiris registreringsformulär `http://localhost` som callback, eller
krävs `https`? Att en giltig session finns i dag bevisar att **https-varianten
fungerar** — den öppna frågan gäller bara om http vore enklare.

## 6. Vad ovanstående ersätter

- **§4b** beskriver åttastegsplanen från 2026-08-05. Den är genomförd; punkt 1
  ovan är den aktuella lägesbilden.
- **§7 Teststatus** anger 2005 gröna per 2026-08-06. Aktuellt: **2394 gröna,
  1 skip** per 2026-08-10.
- **§8** påstår att MCP-serverns Spiris-bootstrap är manuell och att
  kassaflödesanalys och likviditetsprognos inte exponeras. Båda är
  inaktuella — sessionen skapas via appens inloggning och sparas DPAPI-skyddad
  som `secrets\.spiris_session`, och båda verktygen finns.
