"""Sekretesslager — se ARCHITECTURE.md / ARCHITECTURE_tillagg_sekretesslager.md,
"Modul 3: Sekretesslager (maskering)".
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field

from domain_model import SIEFil, Verifikation
from ekonomiska_termer import ar_ekonomisk_term

# --- Lager 1: personaldimension-igenkänning --------------------------------

_PERSONALDIMENSION_MONSTER = re.compile(r"anställ|personal|medarbetare", re.IGNORECASE)

# --- Lager 2: personnummer ---------------------------------------------------
# ÅÅMMDD-XXXX / ÅÅÅÅMMDD-XXXX, samt +-variant (samordningsnummer/100+ år,
# se ARCHITECTURE_tillagg_sekretesslager.md avsnitt 7 — inte särbehandlat i v1).

_PERSONNUMMER_MONSTER = re.compile(r"(?<!\d)(\d{6}|\d{8})([-+])(\d{4})(?!\d)")

# Fynd 4 (granskning): personnummer UTAN separator. "8506151234" och
# "198506151234" skrivs ofta så i verklig bokföringstext och passerade förr rakt
# igenom. En ren siffersekvens är tvetydig (belopp, orgnr, referensnummer), så
# den maskeras ENDAST om den både har en giltig ÅÅMMDD/ÅÅÅÅMMDD-datumdel OCH en
# giltig Luhn-kontrollsiffra — dubbelkravet håller falska träffar nere.
# Organisationsnummer förkastas naturligt: deras tredje siffra är ≥ 2 (månadsdel
# ≥ 20), vilket faller på datumkontrollen.
_PERSONNUMMER_UTAN_SEP_MONSTER = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")

# --- Lager 2b (fynd 5): övriga direkt identifierande fritextmönster ----------
# Deterministiska, matematiskt/strukturellt entydiga mönster som lager 2
# (personnummer) — men för e-post, telefon, gatuadress och bankgiro/IBAN. Alla
# auto-maskeras med en TYPAD token (EPOST_n, TELEFON_n, ADRESS_n, BANKGIRO_n),
# aldrig flaggade för granskning: precis som ett personnummer är de entydigt PII
# och kräver ingen mänsklig bedömning.

_EPOST_MONSTER = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Telefon: håller sig medvetet till svenska mönster med ETT tydligt fäste — en
# ledande "0"/"+46" följt av separatorindelade grupper, ELLER ett rent
# 07-mobilnummer (10 siffror). Kravet på antingen separator eller mobilprefix
# håller nakna belopp (t.ex. "1234567890") borta, som fångas av personnummer-
# lagret om de faktiskt är personnummer.
#
# Två skärpningar (omgranskningens fynd 2) mot falska träffar som FÖRVANSKADE
# belopp/datum i AI-kontexten:
#   - Siffran efter riktnummer-nollan måste vara 1-9 (inget svenskt riktnummer
#     börjar "00") — annars åts "1 000 000 000" upp som "1 TELEFON_n".
#   - Lookbehind förbjuder även ett föregående "-" — annars matchade "07 22 000"
#     i "Perioden 2026-07 22 000 kr". Priset är att udda skrivsätt som
#     "0046 70..." inte längre fångas — rätt byte: en missad exotisk
#     telefonform är bättre än systematiskt sönderklippta belopp.
_TELEFON_MONSTER = re.compile(
    r"(?<![\d/+\-])(?:\+46[\s\-]?|0)[1-9]\d{0,2}[\s\-]\d{2,4}(?:[\s\-]?\d{2,4}){1,3}(?!\d)"
    r"|(?<![\d/+\-])07\d{8}(?!\d)"
    r"|(?<![\d/+\-])\+(?!46)\d{1,3}[\s\-]?\d{1,4}[\s\-]\d{2,4}(?:[\s\-]?\d{2,4}){0,3}(?!\d)"
)

# Gatuadress i fritext: ett versalinlett gatunamn som slutar på en vanlig
# svensk gatusuffix, följt av ett husnummer. Bolagets egen #ADRESS maskeras
# redan strukturellt (lager 1) — det här fångar adresser som dyker upp mitt i
# en transaktions-/verifikationstext ("Hyra lgh Storgatan 12").
#
# Suffixlistan breddad (omgranskningens fynd 3): allén/stigen/backen/plan/
# torg/leden/esplanaden/promenaden/platsen/kajen — "Karlaplan 5" och
# "Björkstigen 4" passerade förr. Även "Box NNN" (postbox). Alternationens
# ordning kvittar för korrekthet (regex-backtracking provar alla), men
# längre suffix står först där ett är prefix av ett annat, för läsbarhet.
# Medveten övermaskering på köpet: "Handlingsplan 2026" kan fastna — fel åt
# det säkra hållet, och \w är Unicode-medvetet så gatunamn med diakriter
# ("Linnégatan") täcks redan.
_ADRESS_MONSTER = re.compile(
    r"\b[A-ZÅÄÖ][\wÅÄÖåäö]*"
    r"(?:gatan|gata|vägen|väg|gränden|gränd|torget|torg|allén|allen|stigen|"
    r"backen|leden|esplanaden|promenaden|platsen|plan|kajen)"
    r"\s+\d{1,4}[A-Za-z]?\b"
    r"|\bBox\s+\d{1,5}\b"
)

# Bankgiro (NNN-NNNN / NNNN-NNNN) och svenskt IBAN (SE + 22 tecken). Kontonummer
# är inte PII i sig men är identifierande betalningsuppgifter som granskningen
# lyfter — och de ska aldrig behöva nå en AI.
_BANKGIRO_MONSTER = re.compile(r"(?<!\d)\d{3,4}-\d{4}(?!\d)")
_IBAN_MONSTER = re.compile(r"\bSE\d{2}(?:\s?\d){20}\b")

# Kortnummer (PAN, 13-19 siffror). Lagret maskerar redan bankgiro och IBAN med
# motiveringen att betalningsidentifierare aldrig ska behöva nå en AI — PAN är
# den starkaste av dem och saknades. Två skrivsätt tillåts: grupperat i fyror
# (kortets eget tryck) eller obrutet. Svenska belopp grupperas i TREOR, så
# fyrgruppsformen kan inte krocka med dem, och Luhn-kontrollen (från höger,
# samma som bankgiro) håller resten av falska träffar borta.
_KORTNUMMER_MONSTER = re.compile(
    r"(?<![\d.,\-])(?:\d{4}[ \-]){3}\d{1,7}(?![\d.,])"
    r"|(?<![\d.,\-])\d{13,19}(?![\d.,\-])"
)

# --- Lager 3b: versalmönster "Förnamn Efternamn" ----------------------------
# Detektorn matchar 2–3 versalinledda namnord VAR SOM HELST i texten — även
# allra först (tidigare krävdes ett föregående ord, `\S+\s+`, vilket lät ett
# namn i strängstart passera: "Xerxes Qoolio är sen"). Skillnaden mot en rå
# versalmatchning görs i två steg (se _hitta_okanda_namn):
#   1. Lager 3a (kända namn) körs FÖRE 3b och tokeniserar redan kända namn.
#   2. Ledande/avslutande EKONOMISKA ram-ord trimmas bort via
#      ekonomiska_termer (t.ex. "Kurs Erik Svensson" -> "Erik Svensson",
#      "Ingående Balans" -> inget kvar). Rena ekonomiska rubriker (alla ord i
#      stopplistan) blir därför aldrig en 3b-träff, medan ett namn intill ett
#      ram-ord ändå fångas.
# Denna detektor DELAS av fritext (flagga+blockera), kontonamn/identifierande
# fält (auto-maskera) och chatt (blockera) — igenkänningen kan inte glida isär.
#
# Stöd: 2–3 namnord i titel-/namnform, bindestreck ("Anna-Lena", "Björk-Ström")
# och apostrof ("O'Brien"). Diakriter (André/Linnéa/Renée/Müller/Ödqvist) täcks
# av teckenklasserna. Egna konstanter så versal- och gemenklassen aldrig glider
# isär mellan mönster.
#
# Medvetet UTANFÖR scope (dokumenterade restrisker): HELT VERSALA namn
# ("XERXES QOOLIO"), helt GEMENA namn ("xerxes qoolio"), initial + efternamn
# ("A. Svensson") och mononymer (ett enda namn). Ett 3-ordsnamn som föregås av
# ett icke-ekonomiskt versalord kan rapporteras som en längre fras — fail-closed
# (fortfarande blockerat/maskerat), aldrig ett läckt namn.

def _kodpunktsklass(kategori: str, slut: int = 0x10000) -> str:
    """Bygger en regex-teckenklass över ALLA kodpunkter i BMP vars Unicode-
    kategori är `kategori` ("Lu"/"Ll"), hopslagna till intervall.

    Ersätter de tidigare handskrivna, rent latinska klasserna. De gjorde
    detektorn blind för kyrilliska/grekiska namn (fail-OPEN) och gav PARTIELL
    maskering för latinska diakriter utanför listan ("Wiśniewski" ->
    "PERSON_1śniewski"). Tabellen kommer nu från stdlib:s unicodedata, inte
    från en handhållen lista som kan glida efter verkligheten. Kostnad ~10 ms
    en gång vid import."""
    intervall: list[list[int]] = []
    for kp in range(slut):
        if unicodedata.category(chr(kp)) != kategori:
            continue
        if intervall and intervall[-1][1] == kp - 1:
            intervall[-1][1] = kp
        else:
            intervall.append([kp, kp])
    return "".join(
        re.escape(chr(a)) if a == b else f"{re.escape(chr(a))}-{re.escape(chr(b))}"
        for a, b in intervall
    )


_NAMN_VERSALER = _kodpunktsklass("Lu")
_NAMN_GEMENER = _kodpunktsklass("Ll")

# Ett namnord: versal + minst ett tecken till, där bindestreck/apostrof får
# binda ihop delar ("Anna-Lena", "Björk-Ström", "O'Brien").
_NAMNORD = (
    rf"[{_NAMN_VERSALER}]"
    rf"(?:[{_NAMN_GEMENER}]|['\-][{_NAMN_VERSALER}{_NAMN_GEMENER}])+"
    rf"[{_NAMN_GEMENER}]*"
)

# 2–3 namnord i följd. Vänster lookbehind hindrar start mitt i ett längre ord.
_NAMNMONSTER = re.compile(
    rf"(?<![{_NAMN_VERSALER}{_NAMN_GEMENER}'\-])"
    rf"(?:{_NAMNORD})(?:\s+(?:{_NAMNORD})){{1,2}}"
)

_PLATS_MONSTER = re.compile(r"serie=(\S*) vernr=(\S*)")

# --- Lager 3c: skriftvakt för obedömbara skriftsystem -----------------------
# Lager 3b bygger HELT på versalinledning och är därför strukturellt blind för
# skriftsystem UTAN versal/gemen-skillnad (kinesiska, japanska, koreanska,
# arabiska, hebreiska, thailändska). Ett namn skrivet så passerade förr rakt
# igenom, oflaggat — fail-OPEN i ett lager vars princip är fail-closed.
#
# Testet är exakt, inte heuristiskt: en bokstav som varken är versal eller
# gemen tillhör per definition ett skriftsystem utan versalbegrepp, och kan
# alltså aldrig bedömas av 3b. Siffror och skiljetecken är inte bokstäver och
# berörs inte.

MOTPART_TOKENTYP = "MOTPART"


def _ar_obedombar_bokstav(tecken: str) -> bool:
    return tecken.isalpha() and not tecken.isupper() and not tecken.islower()


def _hitta_obedombar_text(text: str) -> list[str]:
    """Sammanhängande löp av bokstäver ur ett skriftsystem utan versalbegrepp.
    Returnerar unika, ordningsbevarade RÅ-strängar — samma invariant som
    _hitta_okanda_namn: de får bara användas lokalt (flaggas/maskeras)."""
    träffar: list[str] = []
    aktuell: list[str] = []
    for tecken in text:
        if _ar_obedombar_bokstav(tecken):
            aktuell.append(tecken)
            continue
        if aktuell:
            frasen = "".join(aktuell)
            if frasen not in träffar:
                träffar.append(frasen)
            aktuell = []
    if aktuell:
        frasen = "".join(aktuell)
        if frasen not in träffar:
            träffar.append(frasen)
    return träffar


def _hitta_okanda_namn(text: str) -> list[str]:
    """Delad Lager 3b-detektor för fritext, chatt, kontonamn och Spiris.

    Hittar okända versalinledda namnpar/-trippel var som helst i texten (även
    strängstart) och trimmar bort ledande/avslutande ekonomiska ram-ord. En
    ren ekonomisk rubrik (alla ord i stopplistan) ger inget kvar och blir ingen
    träff. Returnerar unika, ordningsbevarade rå-strängar — de får bara användas
    lokalt (flaggas/maskeras), aldrig skickas till en extern part."""
    träffar: list[str] = []
    for match in _NAMNMONSTER.finditer(text):
        ord_ = match.group(0).split()
        while ord_ and ar_ekonomisk_term(ord_[0]):
            ord_.pop(0)
        while ord_ and ar_ekonomisk_term(ord_[-1]):
            ord_.pop()
        if len(ord_) < 2:
            continue
        frasen = " ".join(ord_)
        if frasen not in träffar:
            träffar.append(frasen)
    return träffar


@dataclass
class Maskeringsbehov:
    plats: str
    fältnamn: str
    misstänkt_text: str
    träffkälla: str
    status: str
    # Användarens ev. manuellt justerade text ("maskera bara förnamnet").
    # Ligger i ett EGET fält i stället för att skriva över misstänkt_text:
    # (plats, fältnamn, misstänkt_text) är radens identitet när granskade
    # beslut vävs tillbaka in i behovslistan (_sla_ihop_granskade), och den
    # identiteten får inte ändras av att användaren redigerar texten.
    ersättningstext: str | None = None


def normalisera_undantag(text: str) -> str:
    """Matchningsnyckel för undantagslistan (allowlist): skiftlägesokänslig och
    med kollapsad whitespace, så att "DANSKE  DISKS" och "Danske Disks" är
    samma post. Matchningen sker ALLTID mot hela den flaggade strängen — aldrig
    som delsträng, så ett kort undantag kan inte tysta ett längre namn."""
    return " ".join(text.split()).casefold()


def _text_att_maskera(behov: Maskeringsbehov) -> str:
    """Den sträng som faktiskt ska sökas upp och ersättas: användarens
    justering om den finns, annars den flaggade texten."""
    return behov.ersättningstext or behov.misstänkt_text


@dataclass
class Maskeringsresultat:
    maskerad_siefil: SIEFil
    kodnyckel: dict[str, str]
    maskeringsbehov: list[Maskeringsbehov]
    blockerade_verifikationer: set[tuple[str, str]]
    sandningsbara_verifikationer: list[Verifikation]
    prosa_sandningsbar: str | None


class _Tokengenerator:
    """Tilldelar typade tokens (BOLAG_n, PERSON_n, ...) och håller
    kodnyckeln (token -> verkligt värde) enbart i minnet."""

    def __init__(self, befintlig_kodnyckel: dict[str, str] | None = None):
        self._kodnyckel: dict[str, str] = dict(befintlig_kodnyckel or {})
        self._token_för_värde: dict[tuple[str, str], str] = {}
        self._räknare: dict[str, int] = {}
        for token, värde in self._kodnyckel.items():
            typ, _, nr = token.rpartition("_")
            if nr.isdigit():
                self._räknare[typ] = max(self._räknare.get(typ, 0), int(nr))
                self._token_för_värde[(typ, värde)] = token

    def token_för(self, typ: str, verkligt_värde: str) -> str:
        nyckel = (typ, verkligt_värde)
        if nyckel in self._token_för_värde:
            return self._token_för_värde[nyckel]
        self._räknare[typ] = self._räknare.get(typ, 0) + 1
        token = f"{typ}_{self._räknare[typ]}"
        self._token_för_värde[nyckel] = token
        self._kodnyckel[token] = verkligt_värde
        return token

    @property
    def kodnyckel(self) -> dict[str, str]:
        return dict(self._kodnyckel)


@dataclass
class Chattmaskering:
    """Resultatet av att maskera ETT chattmeddelande före sändning till AI:n.

    text: den maskerade texten (liggare + deterministiska lager + Lager 3a).
        Säker att skicka ENDAST om `blockerad` är False.
    misstänkta_namn: okända versalmönster ("Förnamn Efternamn", Lager 3b) som
        varken liggaren eller referenslistan kunde avidentifiera. RÅ strängar —
        de finns här ENBART för lokal granskning i appen och får ALDRIG lämna
        datorn (samma invariant som Maskeringsbehov.misstänkt_text).
    """

    text: str
    misstänkta_namn: list[str] = field(default_factory=list)

    @property
    def blockerad(self) -> bool:
        """Fail-closed: finns ett okänt namn ska meddelandet inte skickas i
        klartext förrän en människa avgjort det lokalt."""
        return bool(self.misstänkta_namn)


def maskera_chattmeddelande(
    text: str,
    liggare: dict[str, str] | None = None,
    referenslista: set[str] | None = None,
) -> Chattmaskering:
    """Maskerar ETT användarmeddelande innan det skickas till AI:n (fynd B).
    Läsvägen pseudonymiserar kundens namn omsorgsfullt medan chatten förr
    skickade namn + personnummer i klartext — den här stänger det hålet.

    Fyra lager, samma ordning och motor som filvägen:
    1. Maskeringsliggaren (redan kända namn -> deras mask).
    2. Deterministiska lager (personnummer/orgnr + e-post/telefon/adress/
       bankgiro-IBAN) — entydig PII, auto-maskeras alltid.
    3. Lager 3a: den lokala namnreferenslistan (M1) — vanliga svenska namn
       auto-maskeras deterministiskt, utan att blockera.
    4. Lager 3b: ett OKÄNT versalmönster ("Förnamn Efternamn") som lager 1–3
       inte fångat FAIL-CLOSED:as (M1). Till skillnad från filvägen finns ingen
       per-verifikation-spärr här, så meddelandet flaggas `blockerad` och ska
       inte skickas i klartext — det avgörs lokalt i appen (flik Åtgärder).
       Förr passerade ett sådant namn rakt igenom; det gör det aldrig längre.

    Det ORIGINALmeddelande användaren ser lokalt påverkas inte — bara kopian som
    lämnar appen. Ren funktion, ingen delad kodnyckel behövs (meddelandet
    demaskeras aldrig)."""
    if not text:
        return Chattmaskering(text=text or "")
    tokens = _Tokengenerator()
    # 1. Maskeringsliggaren: samma pre-pass som filvägen (tillämpa_liggare).
    if liggare:
        for namn, mask in liggare.items():
            if namn and namn in text:
                text = text.replace(namn, mask)
    # 2. Deterministiska lager (personnummer + e-post/telefon/adress/bankgiro).
    text = _maskera_deterministiskt(text, tokens)
    # 3. Lager 3a: kända namn ur den lokala referenslistan auto-maskeras.
    if referenslista:
        text = _maskera_kanda_namn_i_text(text, tokens, referenslista)
    # 4. Lager 3b: okända versalnamn blockerar sändning (fail-closed). De
    #    tokeniseras INTE (det skulle förvanska legitima frågor) — i stället
    #    hålls hela meddelandet tillbaka tills en människa avgjort det lokalt.
    #    Samma delade detektor som fritext/kontonamn (kan inte glida isär).
    misstänkta = _hitta_okanda_namn(text)
    # 5. Lager 3c: text i ett skriftsystem utan versalbegrepp kan lager 3b inte
    #    bedöma. Samma fail-closed-behandling som ett okänt namn.
    misstänkta += [t for t in _hitta_obedombar_text(text) if t not in misstänkta]
    return Chattmaskering(text=text, misstänkta_namn=misstänkta)


def maskera_kontonamn(namn: str, referenslista: set[str] | None = None) -> str:
    """Fristående maskering av ETT kontonamn för de spiris_rag-rapporter som
    aggregerar saldon direkt (bygg_resultatrapport/bygg_balansrapport) utan att
    gå via maskera_siefil. De behöver bara ett sanerat visningsnamn, inte en
    delad kodnyckel — så en engångstokengenerator används. Samma fail-closed-
    logik som kontonamnen får inuti maskera_siefil (fynd A)."""
    if not namn:
        return namn
    return _maskera_identifierande_falt(namn, _Tokengenerator(), referenslista or set()) or namn


def skapa_kontonamnsmaskerare(referenslista: set[str] | None = None):
    """Maskerare för kontonamn som DELAR tokengenerator mellan anrop.

    maskera_kontonamn skapar en ny generator per anrop, så räknaren nollställs
    för varje kontonamn: tre olika personer blev alla PERSON_1/PERSON_2 och
    AI:t kunde varken skilja dem åt eller följa samma person mellan konton.
    Den som maskerar en HEL rapport ska använda den här i stället."""
    tokens = _Tokengenerator()
    referens = referenslista or set()

    def maskera(namn: str) -> str:
        if not namn:
            return namn
        return _maskera_identifierande_falt(namn, tokens, referens) or namn

    maskera.kodnyckel = lambda: tokens.kodnyckel  # type: ignore[attr-defined]
    return maskera


def innehaller_kant_personnamn(text: str, referenslista: set[str] | None = None) -> bool:
    """Sant om texten innehåller ett KÄNT personnamn (Lager 3a) eller text i
    ett obedömbart skriftsystem (Lager 3c).

    Avsedd som `ar_kanslig_namn` i reskontra_tvatt. Medvetet INTE Lager 3b:s
    versalheuristik — nästan varje svenskt bolagsnamn är två versalinledda ord
    ("Scandinavian Photo"), så 3b hade maskerat i stort sett hela reskontran
    och gjort den oanvändbar. Där finns redan org.nr-regeln som primärt skydd;
    det här är nätet för namn som "Anna Andersson AB", där bolagsform-suffixet
    annars släpper igenom en fysisk persons namn."""
    if not text:
        return False
    if _hitta_obedombar_text(text):
        return True
    mönster = _bygg_referenslope(referenslista or set())
    return bool(mönster and mönster.search(text))


def demaskera_text(text: str, kodnyckel: dict[str, str]) -> str:
    """Ersätter tokens med sina verkliga värden. Enbart för lokal visning
    — sker aldrig i eller inför ett AI-anrop."""
    if not kodnyckel:
        return text
    tokens_fallande_längd = sorted(kodnyckel, key=len, reverse=True)
    mönster = re.compile("|".join(re.escape(token) for token in tokens_fallande_längd))
    return mönster.sub(lambda match: kodnyckel[match.group(0)], text)


def _luhn_giltig(siffror: str) -> bool:
    summa = 0
    for i, tecken in enumerate(siffror):
        siffra = int(tecken)
        if i % 2 == 0:
            siffra *= 2
            if siffra > 9:
                siffra -= 9
        summa += siffra
    return summa % 10 == 0


def _luhn_giltig_fran_hoger(siffror: str) -> bool:
    """Standard-Luhn (dubbla var annan siffra från HÖGER), för bankgiro vars
    kontrollsiffra räknas så. Skild från _luhn_giltig, som dubblar från vänster
    på personnumrets fasta 10-siffrorsform."""
    summa = 0
    for i, tecken in enumerate(reversed(siffror)):
        siffra = int(tecken)
        if i % 2 == 1:
            siffra *= 2
            if siffra > 9:
                siffra -= 9
        summa += siffra
    return summa % 10 == 0


def _giltig_pnr_datumdel(siffror10: str) -> bool:
    """De sista 10 siffrorna i ett personnummer är ÅÅMMDDNNNN. Kontrollerar att
    månad (01–12) och dag (01–31) är rimliga — grovkornigt med flit: syftet är
    att skilja ett personnummer från ett godtyckligt tal (belopp, orgnr,
    referensnummer), inte att kalendervalidera exakt."""
    månad = int(siffror10[2:4])
    dag = int(siffror10[4:6])
    # Samordningsnummer (personer utan personnummer) har dagen adderad med 60,
    # alltså 61-91. Utan den grenen returnerade _identitetsnummer_tokentyp None
    # och den SEPARATORLÖSA formen lämnades omaskerad. Orgnr kan inte krocka:
    # deras månadsdel är >= 20 och faller redan på månadskontrollen.
    return 1 <= månad <= 12 and (1 <= dag <= 31 or 61 <= dag <= 91)


# Omgranskning (kontroll.md): ett aktiebolags organisationsnummer i FRITEXT
# (t.ex. "5566778899" i en transaktionstext) fångades inte — separatorlösa
# 10 siffror föll på datumkontrollen (månadsdel >= 20), och orgnr saknar
# namnkontext för Lager 3b. Svenska orgnr har en "månadsdel" (siffra 3–4) >= 20
# just eftersom inget personnummer kan ha det — det är den strukturella markören
# som skiljer orgnr från personnummer. Kombinerat med giltig Luhn är det ett
# entydigt organisationsnummer, som ska maskeras (företagsidentitet, samma
# skyddsobjekt som #ORGNR strukturellt).
_ORGNR_MANADSGRANS = 20


def _ser_ut_som_orgnr(siffror10: str) -> bool:
    return int(siffror10[2:4]) >= _ORGNR_MANADSGRANS


def _identitetsnummer_tokentyp(siffror10: str) -> str | None:
    """Avgör om ett Luhn-giltigt 10-siffrigt tal ska maskeras och med vilken
    typad token: PERSONNUMMER (giltig ÅÅMMDD-datumdel — personnummer eller
    enskild firma) eller ORGANISATIONSNUMMER (månadsdel >= 20). None om det
    varken ser ut som personnummer eller orgnr (ett tvetydigt tal som inte ska
    röras). Luhn-kontrollen görs av anroparen."""
    if _giltig_pnr_datumdel(siffror10):
        return "PERSONNUMMER"
    if _ser_ut_som_orgnr(siffror10):
        return "ORGANISATIONSNUMMER"
    return None


def är_giltigt_personnummer(kandidat: str) -> bool:
    """Sant för både separator-formen (ÅÅMMDD-XXXX / ÅÅÅÅMMDD-XXXX, ev. med `+`)
    och den separatorlösa formen (10/12 rena siffror) — så länge Luhn stämmer,
    och för den separatorlösa formen även att datumdelen är rimlig. Används av
    app_config för att aldrig tillåta ett personnummer i undantagslistan."""
    text = kandidat.strip()
    match = _PERSONNUMMER_MONSTER.fullmatch(text)
    if match:
        return _luhn_giltig((match.group(1) + match.group(3))[-10:])
    match = _PERSONNUMMER_UTAN_SEP_MONSTER.fullmatch(text)
    if match:
        siffror10 = match.group(1)[-10:]
        return _giltig_pnr_datumdel(siffror10) and _luhn_giltig(siffror10)
    return False


def _maskera_personnummer_i_text(text: str, tokens: _Tokengenerator) -> str:
    def ersätt_sep(match: re.Match) -> str:
        siffror = (match.group(1) + match.group(3))[-10:]
        if not _luhn_giltig(siffror):
            return match.group(0)
        # Separator-formen NNNNNN-NNNN med giltig Luhn maskeras ALLTID (ingen
        # datumkontroll — bakåtkompatibelt). Rätt typ väljs där den går att
        # avgöra; annars faller den tillbaka på PERSONNUMMER (aldrig omaskerad).
        typ = _identitetsnummer_tokentyp(siffror) or "PERSONNUMMER"
        return tokens.token_för(typ, match.group(0))

    def ersätt_utan_sep(match: re.Match) -> str:
        # Separatorlösa siffror är tvetydiga (belopp, referens): maskeras bara
        # om Luhn stämmer OCH formen är entydigt personnummer eller orgnr.
        siffror10 = match.group(1)[-10:]
        if not _luhn_giltig(siffror10):
            return match.group(0)
        typ = _identitetsnummer_tokentyp(siffror10)
        if typ is None:
            return match.group(0)
        return tokens.token_för(typ, match.group(0))

    text = _PERSONNUMMER_MONSTER.sub(ersätt_sep, text)
    return _PERSONNUMMER_UTAN_SEP_MONSTER.sub(ersätt_utan_sep, text)


def _maskera_typat_monster(
    text: str, tokens: _Tokengenerator, mönster: re.Pattern, tokentyp: str
) -> str:
    """Auto-maskerar varje träff på ett strukturellt entydigt mönster (e-post,
    telefon, adress, bankgiro/IBAN) med en typad token. Ingen granskning: dessa
    är lika entydigt PII/identifierande som ett personnummer."""
    return mönster.sub(lambda match: tokens.token_för(tokentyp, match.group(0)), text)


def _maskera_bankgiro_i_text(text: str, tokens: _Tokengenerator) -> str:
    """Bankgiro maskeras bara om Luhn-kontrollsiffran stämmer. Utan den fångas
    fakturanummer/datum på formen NNNN-NNNN ("2026-0456") felaktigt — samma
    dubbelkrav (mönster + kontrollsiffra) som personnummerlagret använder."""
    def ersätt(match: re.Match) -> str:
        siffror = match.group(0).replace("-", "")
        if not _luhn_giltig_fran_hoger(siffror):
            return match.group(0)
        return tokens.token_för("BANKGIRO", match.group(0))

    return _BANKGIRO_MONSTER.sub(ersätt, text)


def _maskera_deterministiskt(text: str, tokens: _Tokengenerator) -> str:
    """Alla deterministiska lager (2 + 2b) i rätt ordning — MEST SPECIFIKT FÖRST,
    så ett långt strukturerat mönster aldrig kannibaliseras av ett kortare:

    1. IBAN (SE + 22 siffror, separatorindelat) — MÅSTE gå före telefon/
       personnummer, annars åt telefon-mönstret upp IBAN:ets sifferblock och
       lämnade "SE45 5000 0000" oskyddat i klartext.
    2. Personnummer/organisationsnummer (siffror bundna av datum/orgnr-form +
       Luhn) — före telefon/bankgiro så deras siffror inte tolkas om.
    3. E-post, telefon, gatuadress, bankgiro (Luhn-gated).

    Delas av fritextmaskeringen och av maskeringen av kontonamn/sign/objekt."""
    text = _maskera_typat_monster(text, tokens, _IBAN_MONSTER, "BANKGIRO")
    text = _maskera_kortnummer_i_text(text, tokens)
    text = _maskera_personnummer_i_text(text, tokens)
    text = _maskera_typat_monster(text, tokens, _EPOST_MONSTER, "EPOST")
    text = _maskera_typat_monster(text, tokens, _TELEFON_MONSTER, "TELEFON")
    text = _maskera_typat_monster(text, tokens, _ADRESS_MONSTER, "ADRESS")
    text = _maskera_bankgiro_i_text(text, tokens)
    return text


def _maskera_kortnummer_i_text(text: str, tokens: _Tokengenerator) -> str:
    """Kortnummer maskeras bara om Luhn stämmer — samma dubbelkrav (mönster +
    kontrollsiffra) som personnummer- och bankgirolagren använder."""
    def ersätt(match: re.Match) -> str:
        siffror = re.sub(r"\D", "", match.group(0))
        if not (13 <= len(siffror) <= 19) or not _luhn_giltig_fran_hoger(siffror):
            return match.group(0)
        return tokens.token_för("KORTNUMMER", match.group(0))

    return _KORTNUMMER_MONSTER.sub(ersätt, text)


def _bygg_referenslope(referenslista: set[str]) -> re.Pattern | None:
    r"""Ett mönster som matchar ett SAMMANHÄNGANDE LÖP av kända namn.

    Två fel rättas mot den tidigare per-namn-loopen:

    1. "Anna Andersson" blev PERSON_1 PERSON_2 — en människa som två
       pseudonymer — och varje "Anna" i filen delade token med alla andra
       Anna. Ett löp tokeniseras nu som EN person, och två olika personer får
       därmed aldrig samma token.
    2. Svensk genitiv ("Anderssons hyra") passerade helt: `\b` efter namnet
       matchade inte när ett `s` följde. Ett valfritt genitiv-s ligger nu
       INNANFÖR namnalternativet, så "Lars" aldrig kan trunkeras till "Lar".

    Längsta namn först: alternationen är ordnad, så "Larsson" vinner över
    "Lars" och ett efternamn kan inte styckas av ett kortare förnamn."""
    namn = sorted((n for n in referenslista if n and n.strip()), key=len, reverse=True)
    if not namn:
        return None
    # Ett listnamn kan vara FLERORDIGT ("Anna Andersson"). Delarna binds med
    # \s+ (inte ett literalt mellanslag) så "Anna  Andersson" fortfarande
    # matchar — samma tolerans som den tidigare per-namn-loopen hade.
    alternativ = [r"\s+".join(re.escape(del_) for del_ in n.split()) for n in namn]
    ett = "(?:" + "|".join(alternativ) + r")s?"
    return re.compile(rf"\b{ett}(?:\s+{ett})*\b", re.IGNORECASE)


def _maskera_kanda_namn_i_text(text: str, tokens: _Tokengenerator, referenslista: set[str]) -> str:
    mönster = _bygg_referenslope(referenslista)
    if mönster is None:
        return text
    return mönster.sub(
        lambda match: tokens.token_för("PERSON", " ".join(match.group(0).split())), text
    )


def _flagga_okanda_namn(
    text: str,
    maskeringsbehov: list[Maskeringsbehov],
    plats: str,
    fältnamn: str,
    undantagslista: set[str],
) -> str:
    for namn in _hitta_okanda_namn(text) + _hitta_obedombar_text(text):
        # Undantagslistan är den enda fail-OPEN-mekanismen i lagret: en sträng
        # som en människa uttryckligen bedömt som icke-PII flaggas aldrig igen.
        # Den verkar ENBART här, på lager 3b:s regex-gissningar — lager 2
        # (personnummer) körs redan innan och kan därför aldrig undantas.
        if normalisera_undantag(namn) in undantagslista:
            continue
        maskeringsbehov.append(
            Maskeringsbehov(
                plats=plats,
                fältnamn=fältnamn,
                misstänkt_text=namn,
                träffkälla="regex_fallback",
                status="väntar_granskning",
            )
        )
    return text  # Maskeringsbehov blockerar sändning — texten lämnas orörd


def _maskera_fritext(
    text: str | None,
    tokens: _Tokengenerator,
    referenslista: set[str],
    maskeringsbehov: list[Maskeringsbehov],
    plats: str,
    fältnamn: str,
    undantagslista: set[str],
) -> str | None:
    if not text:
        return text
    text = _maskera_deterministiskt(text, tokens)
    text = _maskera_kanda_namn_i_text(text, tokens, referenslista)
    text = _flagga_okanda_namn(text, maskeringsbehov, plats, fältnamn, undantagslista)
    return text


def _maskera_identifierande_falt(
    text: str | None, tokens: _Tokengenerator, referenslista: set[str]
) -> str | None:
    """Maskerar ett fält som når (eller kan komma att nå) en AI men som — till
    skillnad från en verifikations fritext — INTE har någon spärr per
    verifikation att hålla tillbaka: kontonamn (fynd A), #GEN-signaturen och
    objektnamn utanför personaldimensioner (fynd/svaghet 4).

    Skillnaden mot _maskera_fritext: ett okänt versalmönster ("Förnamn
    Efternamn") AUTO-maskeras här i stället för att flaggas. Ett Maskeringsbehov
    skulle vara verkningslöst — det finns ingen verifikation att blockera, och
    att lämna ett misstänkt namn orört i ett kontonamn vore fail-OPEN, tvärtemot
    §5:s princip. Fail-closed vid en gräns som inte kan blockera betyder därför:
    maskera vid källan. Standardkontonamn ("Kassa", "Försäljning") saknar
    mönstret och lämnas orörda; bara verkligt identifierande text ("Lön Anna
    Andersson") tokeniseras."""
    if not text:
        return text
    text = _maskera_deterministiskt(text, tokens)
    text = _maskera_kanda_namn_i_text(text, tokens, referenslista)
    # Fail-closed vid en gräns som inte kan blockera: auto-maskera varje okänt
    # namn den delade 3b-detektorn hittar (samma igenkänning som fritext/chatt,
    # men här tokeniseras i stället för att flaggas). Ram-orden är redan
    # borttrimmade, så bara namnet ersätts och kringtexten bevaras.
    for namn in _hitta_okanda_namn(text):
        text = text.replace(namn, tokens.token_för("PERSON", namn))
    # Lager 3c: obedömbar skrift kan inte klassas som person eller bolag —
    # egen tokentyp i stället för att påstå något som inte är utrett.
    for löp in _hitta_obedombar_text(text):
        text = text.replace(löp, tokens.token_för(MOTPART_TOKENTYP, löp))
    return text


def _plats_för(verifikation: Verifikation) -> str:
    return f"serie={verifikation.serie} vernr={verifikation.vernr}"


def _nyckel_från_plats(plats: str) -> tuple[str, str] | None:
    match = _PLATS_MONSTER.match(plats)
    if not match:
        return None
    return (match.group(1), match.group(2))


def _finns_olost_for_nyckel(alla_behov: list[Maskeringsbehov], nyckel: tuple[str, str]) -> bool:
    return any(
        _nyckel_från_plats(behov.plats) == nyckel and behov.status == "väntar_granskning"
        for behov in alla_behov
    )


def _prosa_sandningsbar(maskerad_prosa: str | None, alla_behov: list[Maskeringsbehov]) -> str | None:
    # Fail-closed på filnivå, samma princip som blockerade_verifikationer
    # tillämpar på verifikationsnivå: prosa är inte knuten till en enskild
    # verifikation (plats för prosa-behov är alltid None via
    # _nyckel_från_plats), så den behöver sin egen spärr.
    olöst_prosa = any(
        behov.fältnamn == "prosa" and behov.status == "väntar_granskning" for behov in alla_behov
    )
    return None if olöst_prosa else maskerad_prosa


def _maskera_lager1_strukturellt(
    maskerad: SIEFil, tokens: _Tokengenerator, referenslista: set[str]
) -> None:
    fnamn = maskerad.företagsnamn
    orgnr = maskerad.orgnr
    if fnamn or orgnr:
        # Arkitektbeslut: företagsnamn och orgnr delar EN token (annars
        # läcker kopplingen mellan dem implicit). Kodnyckelns värde för den
        # delade token blir därför en kombination av båda, inte enbart det
        # ena — se konversationen om test_maskerar_foretagsnamn /
        # test_maskerar_organisationsnummer.
        if fnamn and orgnr:
            bolagsvärde = f"{fnamn} ({orgnr})"
        else:
            bolagsvärde = fnamn or orgnr
        token = tokens.token_för("BOLAG", bolagsvärde)
        if fnamn:
            maskerad.företagsnamn = token
        if orgnr:
            maskerad.orgnr = token

    if maskerad.adress is not None:
        if maskerad.adress.kontakt:
            maskerad.adress.kontakt = tokens.token_för("PERSON", maskerad.adress.kontakt)
        for fältnamn in ("utdelningsadress", "postadress", "telefon"):
            värde = getattr(maskerad.adress, fältnamn)
            if värde:
                setattr(maskerad.adress, fältnamn, tokens.token_för("ADRESS", värde))

    # #GEN-signaturen är ofta initialer men kan vara ett fullt namn på den som
    # skapade filen (svaghet 4). Initialer saknar namnmönstret och passerar; ett
    # riktigt namn/personnummer maskeras.
    maskerad.genererad_sign = _maskera_identifierande_falt(
        maskerad.genererad_sign, tokens, referenslista
    )

    for (dimensionsnr, _objektnr), objekt in maskerad.objektregister.items():
        dimension = maskerad.dimensioner.get(dimensionsnr)
        if dimension is not None and _PERSONALDIMENSION_MONSTER.search(dimension.namn):
            # Personaldimension: hela objektnamnet ÄR en fysisk person (100%).
            objekt.namn = tokens.token_för("PERSON", objekt.namn)
        else:
            # Övriga objektnamn (projekt, kostnadsställe) är sällan PII, men
            # svaghet 4 pekar på att ett namn kan gömma sig även här. Kör dem
            # genom samma identifierande-fält-maskering: standardnamn
            # ("Huvudkontor") passerar, ett dolt personnamn fångas.
            objekt.namn = _maskera_identifierande_falt(objekt.namn, tokens, referenslista)


def _ersätt_text_i_verifikation(
    maskerad: SIEFil, nyckel: tuple[str, str] | None, misstänkt_text: str, token: str
) -> None:
    if nyckel is None:
        return
    for verifikation in maskerad.verifikationer:
        if (verifikation.serie, verifikation.vernr) != nyckel:
            continue
        if verifikation.vertext and misstänkt_text in verifikation.vertext:
            verifikation.vertext = verifikation.vertext.replace(misstänkt_text, token)
        if verifikation.sign and misstänkt_text in verifikation.sign:
            verifikation.sign = verifikation.sign.replace(misstänkt_text, token)
        for transaktion in verifikation.transaktioner:
            if transaktion.transtext and misstänkt_text in transaktion.transtext:
                transaktion.transtext = transaktion.transtext.replace(misstänkt_text, token)
            if transaktion.sign and misstänkt_text in transaktion.sign:
                transaktion.sign = transaktion.sign.replace(misstänkt_text, token)


def maskera_siefil(
    sie: SIEFil,
    referenslista: set[str] | None = None,
    undantagslista: set[str] | None = None,
) -> Maskeringsresultat:
    """referenslista = namn som ALLTID maskeras (lager 3a).
    undantagslista = strängar en människa bedömt som icke-PII och som därför
    aldrig ska flaggas igen (lager 3b:s allowlist). Utelämnad undantagslista
    ger exakt tidigare beteende — allt flaggas som förut."""
    referenslista = referenslista or set()
    # Normaliseras här, en gång, så anropare kan skicka rå text utan att känna
    # till matchningsreglerna.
    undantag = {normalisera_undantag(text) for text in (undantagslista or set())}
    tokens = _Tokengenerator()
    maskerad = copy.deepcopy(sie)
    maskeringsbehov: list[Maskeringsbehov] = []

    _maskera_lager1_strukturellt(maskerad, tokens, referenslista)

    # Fynd A: kontonamn maskeras aldrig annars, och når AI:n via tre vägar
    # (haiku-kontoplanen, chattens kontosaldon, spiris_rag-rapporterna). I Visma
    # kan användaren döpa om konton fritt ("7010 Lön Anna Andersson"), så namnet
    # är osäker fritext. KontonUMret (nyckeln) rörs aldrig — det är inte PII och
    # kontomatchningen validerar mot det.
    for konto in maskerad.konton.values():
        konto.namn = _maskera_identifierande_falt(konto.namn, tokens, referenslista) or konto.namn

    for verifikation in maskerad.verifikationer:
        plats = _plats_för(verifikation)
        verifikation.vertext = _maskera_fritext(
            verifikation.vertext, tokens, referenslista, maskeringsbehov, plats, "vertext", undantag
        )
        verifikation.sign = _maskera_fritext(
            verifikation.sign, tokens, referenslista, maskeringsbehov, plats, "sign", undantag
        )
        for transaktion in verifikation.transaktioner:
            transaktion.transtext = _maskera_fritext(
                transaktion.transtext, tokens, referenslista, maskeringsbehov, plats,
                "transtext", undantag,
            )
            transaktion.sign = _maskera_fritext(
                transaktion.sign, tokens, referenslista, maskeringsbehov, plats, "sign", undantag
            )

    maskerad.prosa = _maskera_fritext(
        maskerad.prosa, tokens, referenslista, maskeringsbehov, "fil-nivå (prosa)",
        "prosa", undantag,
    )

    blockerade: set[tuple[str, str]] = set()
    for behov in maskeringsbehov:
        nyckel = _nyckel_från_plats(behov.plats)
        if nyckel is not None:
            blockerade.add(nyckel)

    sandningsbara = [
        verifikation
        for verifikation in maskerad.verifikationer
        if (verifikation.serie, verifikation.vernr) not in blockerade
    ]

    return Maskeringsresultat(
        maskerad_siefil=maskerad,
        kodnyckel=tokens.kodnyckel,
        maskeringsbehov=maskeringsbehov,
        blockerade_verifikationer=blockerade,
        sandningsbara_verifikationer=sandningsbara,
        prosa_sandningsbar=_prosa_sandningsbar(maskerad.prosa, maskeringsbehov),
    )


def _rad_nyckel(behov: Maskeringsbehov) -> tuple[str, str, str]:
    """Radens identitet vid sammanslagning. misstänkt_text ingår och är stabil
    just för att användarens redigering hamnar i ersättningstext, inte här."""
    return (behov.plats, behov.fältnamn, behov.misstänkt_text)


def _sla_ihop_granskade(
    ursprungliga: list[Maskeringsbehov], granskade: list[Maskeringsbehov]
) -> list[Maskeringsbehov]:
    """Väver in de granskade besluten i den ursprungliga behovslistan.

    Nödvändigt eftersom det finns TVÅ anropsvägar med olika semantik: UI:t
    bygger kopior via dataclasses.replace() medan testerna muterar objekten
    på plats. Utan sammanslagning såg statuskontrollen nedan bara den
    ogranskade originallistan, där allt fortfarande står som
    "väntar_granskning" — blockeringen hävdes då aldrig från UI-vägen, och
    granskade rader låg kvar i åtgärdslistan för alltid.

    Muterade-på-plats-objekt är redan identiska med sina original, så för den
    vägen är detta en no-op. Endast rader som finns i ursprungliga behålls —
    granskningen kan aldrig lägga till nya behov, bara avgöra befintliga."""
    granskad_för_nyckel: dict[tuple[str, str, str], Maskeringsbehov] = {}
    for behov in granskade:
        granskad_för_nyckel.setdefault(_rad_nyckel(behov), behov)
    return [granskad_för_nyckel.get(_rad_nyckel(behov), behov) for behov in ursprungliga]


def uppdatera_efter_granskning(
    resultat: Maskeringsresultat,
    granskade_behov: list[Maskeringsbehov],
) -> Maskeringsresultat:
    """Tar emot Maskeringsbehov där status manuellt satts till
    'godkänd_ej_pii' eller 'bekräftad_pii', och returnerar ett uppdaterat
    Maskeringsresultat där berörda verifikationer hävts från blockering.
    Vid 'bekräftad_pii' maskeras texten retroaktivt innan hävning.

    Behov som fortfarande står kvar som 'väntar_granskning' (användaren valde
    att avvakta) lämnas orörda och fortsätter blockera — returnerad
    maskeringsbehov-lista speglar exakt vad som återstår att besluta."""
    maskerad = copy.deepcopy(resultat.maskerad_siefil)
    tokens = _Tokengenerator(resultat.kodnyckel)
    blockerade = set(resultat.blockerade_verifikationer)
    sammanslagna = _sla_ihop_granskade(resultat.maskeringsbehov, granskade_behov)

    for behov in granskade_behov:
        if behov.status != "bekräftad_pii":
            continue
        text = _text_att_maskera(behov)
        token = tokens.token_för("PERSON", text)
        if behov.fältnamn == "prosa":
            if maskerad.prosa and text in maskerad.prosa:
                maskerad.prosa = maskerad.prosa.replace(text, token)
        else:
            _ersätt_text_i_verifikation(
                maskerad, _nyckel_från_plats(behov.plats), text, token
            )

    # Häv en verifikations blockering bara om INGA maskeringsbehov för samma
    # plats fortfarande väntar_granskning — kollar hela den sammanslagna
    # listan, inte bara det som skickades in i den här granskningsomgången.
    # Annars hävs en verifikation med flera flaggor så fort EN av dem
    # granskas, trots att syskon-flaggor fortfarande väntar (fail-open,
    # motsatsen till §5:s fail-closed-krav).
    berörda_nycklar = {_nyckel_från_plats(behov.plats) for behov in granskade_behov} - {None}
    for nyckel in berörda_nycklar:
        if not _finns_olost_for_nyckel(sammanslagna, nyckel):
            blockerade.discard(nyckel)

    sandningsbara = [
        verifikation
        for verifikation in maskerad.verifikationer
        if (verifikation.serie, verifikation.vernr) not in blockerade
    ]

    return Maskeringsresultat(
        maskerad_siefil=maskerad,
        kodnyckel=tokens.kodnyckel,
        maskeringsbehov=sammanslagna,
        blockerade_verifikationer=blockerade,
        sandningsbara_verifikationer=sandningsbara,
        prosa_sandningsbar=_prosa_sandningsbar(maskerad.prosa, sammanslagna),
    )
