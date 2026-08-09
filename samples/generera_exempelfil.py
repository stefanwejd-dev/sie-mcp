"""Genererar samples/SIE4_Exempelfil.SE — en egen SIE4-exempelfil.

Filen ersätter SIE-gruppens exempelfil, som är tredjeparts material och
därför inte får ligga i ett publikt kodförråd. Allt innehåll här är
påhittat: bolaget finns inte, orgnummret är syntetiskt och samtliga
motpartsnamn är konstruerade.

Filen är avsiktligt konstruerad så att kontotyp-vaktens facit bevaras:

  * Serie 215 har fem konton — 2150/2151/2152/2153 med typ S och 2157
    med typ T. Majoriteten blir 4/5 och 2157 flaggas av internmönstret.
  * Konto 2157 saknar helt #IB och #UB. Saldot ska bli Decimal("0").
  * Serie 208 har 2081/2086 som S och 2084/2085 som T. Röstetalet blir
    2-2, internmönstret hoppar över serien, och 2084/2085 fångas därför
    bara av referensmönstret.
  * Konto 8270 har typ I i klass 8, som är exkluderad ur referens-
    mönstret. Det ska INTE flaggas.

Balansräkningen stämmer per konstruktion: utgående balanser räknas fram
ur ingående balanser plus verifikationernas rörelser, och resultatposterna
är verifikationernas rörelser på resultatkonton. Räkenskapsårens
trialbalans går därmed alltid jämnt ut.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

UTFIL = Path(__file__).resolve().parent / "SIE4_Exempelfil.SE"

# --- Kontoplan: (kontonr, kontonamn, ktyp) ------------------------------
KONTON: list[tuple[str, str, str]] = [
    # Klass 1 — tillgångar (T)
    # 1060 bär avsiktligt ett ä: tests/test_sie4_parser.py använder kontot för
    # att skilja cp437 från windows-1252. Namnet får inte ändras.
    ("1060", "Hyresrätt", "T"),
    ("1220", "Inventarier och verktyg", "T"),
    ("1229", "Ackumulerade avskrivningar inventarier", "T"),
    ("1250", "Datorer", "T"),
    ("1259", "Ackumulerade avskrivningar datorer", "T"),
    ("1400", "Lager av råvaror och förnödenheter", "T"),
    ("1510", "Kundfordringar", "T"),
    ("1519", "Nedskrivning av kundfordringar", "T"),
    ("1630", "Avräkning skatter och avgifter", "T"),
    ("1650", "Momsfordran", "T"),
    ("1710", "Förutbetalda hyreskostnader", "T"),
    ("1910", "Kassa", "T"),
    ("1930", "Företagskonto", "T"),
    ("1940", "Placeringskonto", "T"),
    # Klass 2 — eget kapital och skulder (S), med tre avsiktliga avvikelser
    ("2081", "Aktiekapital", "S"),
    ("2084", "Överkursfond", "T"),               # avvikelse: bör vara S
    ("2085", "Uppskrivningsfond", "T"),          # avvikelse: bör vara S
    ("2086", "Reservfond", "S"),
    ("2091", "Balanserad vinst eller förlust", "S"),
    ("2150", "Ackumulerade överavskrivningar", "S"),
    ("2151", "Ack överavskrivningar immateriella anläggningstillgångar", "S"),
    ("2152", "Ack överavskrivningar byggnader och markanläggningar", "S"),
    ("2153", "Ack överavskrivningar maskiner och inventarier", "S"),
    ("2157", "Ack överavskrivningar anläggningsdjur", "T"),  # avvikelse, saknar IB/UB
    ("2350", "Långfristiga skulder till kreditinstitut", "S"),
    ("2440", "Leverantörsskulder", "S"),
    ("2510", "Skatteskulder", "S"),
    ("2610", "Utgående moms på försäljning inom Sverige", "S"),
    ("2641", "Ingående moms", "S"),
    ("2710", "Personalens källskatt", "S"),
    ("2731", "Avräkning lagstadgade sociala avgifter", "S"),
    # Klass 3 — intäkter (I)
    ("3011", "Försäljning tjänster inom Sverige", "I"),
    ("3041", "Konsultarvoden inom Sverige", "I"),
    ("3740", "Öres- och kronutjämning", "I"),
    ("3990", "Övriga rörelseintäkter", "I"),
    # Klass 4-7 — kostnader (K)
    ("4010", "Inköp av material och varor", "K"),
    ("5010", "Lokalhyra", "K"),
    ("5410", "Förbrukningsinventarier", "K"),
    ("5611", "Drivmedel för personbilar", "K"),
    ("5910", "Annonsering", "K"),
    ("6110", "Kontorsmateriel", "K"),
    ("6212", "Mobiltelefon", "K"),
    ("6540", "IT-tjänster", "K"),
    ("6570", "Bankkostnader", "K"),
    ("7010", "Löner till kollektivanställda", "K"),
    ("7210", "Löner till tjänstemän", "K"),
    ("7510", "Lagstadgade sociala avgifter", "K"),
    ("7690", "Övriga personalkostnader", "K"),
    ("7832", "Avskrivningar på inventarier och verktyg", "K"),
    ("7835", "Avskrivningar på datorer", "K"),
    # Klass 8 — exkluderad ur referensmönstret
    ("8270", "Nedskrivningar av innehav av andelar", "I"),
    ("8410", "Räntekostnader", "K"),
    ("8910", "Skatt på årets resultat", "K"),
]

SRU = {
    "1060": "7201",
    "1220": "7215", "1229": "7215", "1250": "7215", "1259": "7215",
    "1400": "7241", "1510": "7251", "1519": "7251", "1630": "7261",
    "1650": "7261", "1710": "7263", "1910": "7281", "1930": "7281",
    "1940": "7281",
    "2081": "7301", "2084": "7301", "2085": "7301", "2086": "7301",
    "2091": "7302", "2150": "7322", "2151": "7322", "2152": "7322",
    "2153": "7322", "2157": "7322", "2350": "7368",
    "2440": "7369", "2510": "7369",
    "2610": "7369", "2641": "7261", "2710": "7369", "2731": "7369",
    "3011": "7410", "3041": "7410", "3740": "7410", "3990": "7413",
    "4010": "7512", "5010": "7513", "5410": "7513", "5611": "7513",
    "5910": "7513", "6110": "7513", "6212": "7513", "6540": "7513",
    "6570": "7513", "7010": "7514", "7210": "7514", "7510": "7514",
    "7690": "7514", "7832": "7515", "7835": "7515",
    "8270": "7521", "8410": "7522", "8910": "7528",
}

# --- Ingående balanser, räkenskapsår 0 ----------------------------------
# 2091 räknas ut som utjämningspost så att ingående balans alltid summerar
# till noll, oavsett hur posterna nedan ändras.
IB_0: dict[str, str] = {
    # 1060 hålls avsiktligt litet: tillsammans med 1630 och 1710 utgör det
    # segmentet "Övriga tillgångar", som ska ligga under 5 % av balans-
    # omslutningen för tests/test_fpa_vy.py::TestInlineEtiketter.
    "1060": "60000.00",
    "1220": "900000.00", "1229": "-400000.00", "1250": "250000.00",
    "1259": "-120000.00", "1400": "300000.00", "1510": "620000.00",
    "1519": "-25000.00", "1630": "30000.00", "1650": "0.00",
    "1710": "55000.00", "1910": "12000.00", "1930": "980000.00",
    "1940": "40000.00",
    "2081": "-100000.00", "2084": "-300000.00", "2085": "-50000.00",
    "2086": "-20000.00", "2091": "0.00", "2150": "-80000.00",
    "2151": "0.00", "2152": "0.00", "2153": "-40000.00",
    "2350": "-500000.00",
    "2440": "-380000.00",
    # 2510 bär ett DEBETsaldo: en återbetalning från ett omprövat tidigare
    # taxeringsår som ännu inte betalats ut. BAS-grupp 25 blir därmed negativ
    # i balansrapporten, vilket är premissen för
    # tests/test_fpa_vy.py::TestNegativaBasgrupper.
    "2510": "250000.00", "2610": "-85000.00",
    "2641": "35000.00", "2710": "-25000.00", "2731": "-38000.00",
    # 2157 saknar avsiktligt både IB och UB.
}
IB_0["2091"] = f"{-sum(Decimal(v) for v in IB_0.values()):.2f}"

# --- Verifikationer. Varje verifikat balanserar till noll. --------------
# Motpartsnamnen är påhittade och används av sekretesslagrets tester.
VER: list[tuple[str, int, str, str, list[tuple[str, str]]]] = [
    ("A", 1, "20250107", "Bäckströms Elinstallation AB", [
        ("4010", "58400.00"), ("2641", "14600.00"), ("2440", "-73000.00")]),
    ("A", 2, "20250109", "Kundfaktura 1041 Almgren Fastigheter AB", [
        ("1510", "437500.00"), ("3011", "-350000.00"), ("2610", "-87500.00")]),
    ("A", 3, "20250114", "Hyra kvartal 1, Kvarnbergets Fastighets AB", [
        ("5010", "60000.00"), ("2641", "15000.00"), ("2440", "-75000.00")]),
    ("A", 4, "20250115", "Löneutbetalning januari", [
        ("7010", "245000.00"), ("7210", "105000.00"), ("2710", "-88000.00"),
        ("1930", "-262000.00")]),
    ("A", 5, "20250115", "Arbetsgivaravgifter januari", [
        ("7510", "109970.00"), ("2731", "-109970.00")]),
    ("A", 6, "20250120", "Inbetalning kundfaktura 1041", [
        ("1930", "437500.00"), ("1510", "-437500.00")]),
    ("A", 7, "20250131", "Betalning leverantörsskulder januari", [
        ("2440", "148000.00"), ("1930", "-148000.00")]),
    ("A", 8, "20250203", "Kundfaktura 1042 Sjölunds Bygg & Anläggning AB", [
        ("1510", "312500.00"), ("3011", "-250000.00"), ("2610", "-62500.00")]),
    ("A", 9, "20250210", "Nordvik Datorservice AB, IT-drift", [
        ("6540", "38400.00"), ("2641", "9600.00"), ("2440", "-48000.00")]),
    ("A", 10, "20250212", "Kontorsmateriel, Wikanders Pappershandel AB", [
        ("6110", "9200.00"), ("2641", "2300.00"), ("1930", "-11500.00")]),
    ("A", 11, "20250215", "Löneutbetalning februari", [
        ("7010", "245000.00"), ("7210", "105000.00"), ("2710", "-88000.00"),
        ("1930", "-262000.00")]),
    ("A", 12, "20250215", "Arbetsgivaravgifter februari", [
        ("7510", "109970.00"), ("2731", "-109970.00")]),
    ("A", 13, "20250227", "Drivmedel, Hallgrens Trafik AB", [
        ("5611", "16800.00"), ("2641", "4200.00"), ("2440", "-21000.00")]),
    ("A", 14, "20250305", "Kundfaktura 1043 Almgren Fastigheter AB", [
        ("1510", "500000.00"), ("3041", "-400000.00"), ("2610", "-100000.00")]),
    ("A", 15, "20250312", "Annonsering, Ekenbergs Mediabyrå AB", [
        ("5910", "30400.00"), ("2641", "7600.00"), ("2440", "-38000.00")]),
    ("A", 16, "20250315", "Löneutbetalning mars", [
        ("7010", "245000.00"), ("7210", "105000.00"), ("2710", "-88000.00"),
        ("1930", "-262000.00")]),
    ("A", 17, "20250315", "Arbetsgivaravgifter mars", [
        ("7510", "109970.00"), ("2731", "-109970.00")]),
    ("A", 18, "20250320", "Inbetalning kundfakturor 1042 och 1043", [
        ("1930", "812500.00"), ("1510", "-812500.00")]),
    ("A", 19, "20250331", "Momsredovisning kvartal 1", [
        ("2610", "250000.00"), ("2641", "-53300.00"), ("1930", "-196700.00")]),
    ("A", 20, "20250331", "Betald preliminär F-skatt januari-mars", [
        ("2510", "100000.00"), ("1930", "-100000.00")]),
    ("A", 21, "20250630", "Amortering företagslån", [
        ("2350", "100000.00"), ("1930", "-100000.00")]),
    # Personalskatt och arbetsgivaravgifter betalas i sin helhet under året.
    # BAS-grupp 27 blir därmed noll, vilket krävs för att övrigt-hinken i
    # finansieringsstapeln ska bli negativ (se 2510 ovan).
    ("A", 22, "20250412", "Inbetald personalskatt och arbetsgivaravgifter", [
        ("2710", "289000.00"), ("2731", "367910.00"), ("1930", "-656910.00")]),
    ("A", 23, "20251220", "Momsinbetalningar kvartal 2-4", [
        ("2610", "360000.00"), ("2641", "-132600.00"), ("1930", "-227400.00")]),
    # Enda investeringen under året. Utan den blir kassaflödesanalysens
    # investeringsavsnitt noll och testet av det innehållslöst — se
    # tests/test_spiris_rag.py::TestKassaflodeMotExempelfil.
    ("A", 24, "20250908", "Inköp av servrar, Nordvik Datorservice AB", [
        ("1250", "120000.00"), ("2641", "30000.00"), ("1930", "-150000.00")]),
    ("A", 20, "20250408", "Förbrukningsinventarier, Tegelbergs Verktyg AB", [
        ("5410", "26400.00"), ("2641", "6600.00"), ("2440", "-33000.00")]),
    ("A", 21, "20250415", "Kundfaktura 1044 Sjölunds Bygg & Anläggning AB", [
        ("1510", "375000.00"), ("3011", "-300000.00"), ("2610", "-75000.00")]),
    ("A", 22, "20250422", "Mobiltelefoni, Storviks Telekom AB", [
        ("6212", "7200.00"), ("2641", "1800.00"), ("1930", "-9000.00")]),
    ("A", 23, "20250430", "Betalning leverantörsskulder april", [
        ("2440", "215000.00"), ("1930", "-215000.00")]),
    ("A", 24, "20250514", "Inköp material, Bäckströms Elinstallation AB", [
        ("4010", "142400.00"), ("2641", "35600.00"), ("2440", "-178000.00")]),
    ("A", 25, "20250602", "Kundfaktura 1045 Lindqvist Entreprenad AB", [
        ("1510", "562500.00"), ("3041", "-450000.00"), ("2610", "-112500.00")]),
    ("A", 26, "20250618", "Bankavgifter första halvåret", [
        ("6570", "6200.00"), ("1930", "-6200.00")]),
    ("A", 27, "20250630", "Inbetalning kundfakturor 1044 och 1045", [
        ("1930", "937500.00"), ("1510", "-937500.00")]),
    ("A", 28, "20250815", "Kundfaktura 1046 Almgren Fastigheter AB", [
        ("1510", "437500.00"), ("3011", "-350000.00"), ("2610", "-87500.00")]),
    ("A", 29, "20250903", "Inköp material, Tegelbergs Verktyg AB", [
        ("4010", "196800.00"), ("2641", "49200.00"), ("2440", "-246000.00")]),
    ("A", 30, "20250930", "Personalfest, Restaurang Ekhagen AB", [
        ("7690", "17600.00"), ("2641", "4400.00"), ("1930", "-22000.00")]),
    ("A", 31, "20251015", "Kundfaktura 1047 Lindqvist Entreprenad AB", [
        ("1510", "625000.00"), ("3011", "-500000.00"), ("2610", "-125000.00")]),
    ("A", 32, "20251103", "Nedskrivning andelar i Vretens Intressenter AB", [
        ("8270", "15000.00"), ("1940", "-15000.00")]),
    ("A", 33, "20251120", "Räntekostnad företagskredit", [
        ("8410", "28400.00"), ("1930", "-28400.00")]),
    ("A", 34, "20251201", "Konstaterad kundförlust, Hedmans Måleri AB", [
        ("1519", "-18000.00"), ("3011", "18000.00")]),
    # Ingen avskrivningsverifikation. Anläggningstillgångarna är avskrivna
    # sedan tidigare år, så posten "Av- och nedskrivningar" blir noll — det
    # är premissen för tests/test_fpa_vy.py::test_nollkostnad_ger_positiv_
    # nolla_inte_minus_noll, som vaktar att en nollpost inte renderas -0,0.
    ("B", 36, "20251231", "Lagerjustering per balansdagen", [
        ("1400", "24000.00"), ("4010", "-24000.00")]),
    ("B", 37, "20251231", "Periodisering förutbetald hyra", [
        ("1710", "8000.00"), ("5010", "-8000.00")]),
    ("B", 38, "20251231", "Öres- och kronutjämning", [
        ("3740", "-1800.00"), ("1930", "1800.00")]),
    ("B", 39, "20251231", "Övriga rörelseintäkter, vidarefakturerat", [
        ("3990", "-42000.00"), ("1510", "42000.00")]),
    ("B", 40, "20251231", "Avsättning skatt på årets resultat", [
        ("8910", "196000.00"), ("2510", "-196000.00")]),
]

# --- Föregående år -----------------------------------------------------
# UB -1 är samma som IB 0 utom för 2091, som ännu inte fått årets vinst
# överförd. Trialbalansen för år -1 går då jämnt ut mot RES -1.
VINST_FOREGAENDE_AR = Decimal("420000.00")

RES_MINUS_1: dict[str, str] = {
    "3011": "-1180000.00", "3041": "-742000.00", "3740": "-1400.00",
    "3990": "-36000.00",
    "4010": "352000.00", "5010": "232000.00", "5410": "22000.00",
    "5611": "14500.00", "5910": "26000.00", "6110": "8100.00",
    "6212": "6800.00", "6540": "34000.00", "6570": "5400.00",
    "7010": "660000.00", "7210": "282000.00", "7510": "295000.00",
    "7690": "14000.00", "7832": "134000.00", "7835": "56000.00",
    "8410": "24600.00",
}


def _d(v: str) -> Decimal:
    return Decimal(v)


def _fmt(v: Decimal) -> str:
    return f"{v:.2f}"


def _citera(s: str) -> str:
    """SIE4 kräver citattecken runt fält som innehåller blanksteg."""
    return f'"{s}"' if (" " in s or not s) else s


def bygg() -> tuple[str, dict[str, Decimal], dict[str, Decimal]]:
    balanskonton = {nr for nr, _, _ in KONTON if nr[0] in "12"}

    # Aggregera verifikationernas rörelser per konto.
    rorelse: dict[str, Decimal] = defaultdict(Decimal)
    for _, _, _, _, rader in VER:
        summa = sum((_d(b) for _, b in rader), start=Decimal("0"))
        assert summa == 0, f"obalanserat verifikat: {rader} -> {summa}"
        for konto, belopp in rader:
            rorelse[konto] += _d(belopp)

    # UB 0 = IB 0 + rörelse. RES 0 = rörelse på resultatkonton.
    ub_0 = {nr: _d(IB_0[nr]) + rorelse.get(nr, Decimal("0")) for nr in IB_0}
    res_0 = {nr: rorelse[nr] for nr, _, _ in KONTON
             if nr not in balanskonton and nr in rorelse}

    # Föregående år.
    ub_minus_1 = dict(IB_0)
    ub_minus_1["2091"] = _fmt(_d(IB_0["2091"]) + VINST_FOREGAENDE_AR)
    # RES -1 justeras på skattekontot så att trialbalansen går jämnt ut.
    res_m1 = {k: _d(v) for k, v in RES_MINUS_1.items()}
    res_m1["8910"] = -VINST_FOREGAENDE_AR - sum(res_m1.values())
    # IB -1: modest avvikelse mot UB -1, med 2091 som utjämningspost.
    ib_minus_1 = {nr: _d(v) for nr, v in ub_minus_1.items()}
    for nr, delta in (("1220", "-120000.00"), ("1229", "134000.00"),
                      ("1250", "-40000.00"), ("1259", "56000.00"),
                      ("1930", "-210000.00"), ("1510", "-85000.00"),
                      ("2440", "62000.00")):
        ib_minus_1[nr] += _d(delta)
    ib_minus_1["2091"] -= sum(ib_minus_1.values())

    r: list[str] = []
    r.append("#FLAGGA 0")
    r.append("#FORMAT PC8")
    r.append("#SIETYP 4")
    r.append('#PROGRAM "sie-mcp exempelfilsgenerator" 1.0')
    r.append("#GEN 20260115")
    r.append('#FNAMN "Exempelbolaget Nordvind AB"')
    r.append('#FNR "exempelbolaget-nordvind"')
    r.append("#ORGNR 559912-3457")
    r.append('#ADRESS "Ingrid Wahlström" "Bruksgatan 14" "556 32 EXEMPELSTAD" "013-45 67 89"')
    r.append("#RAR 0 20250101 20251231")
    r.append("#RAR -1 20240101 20241231")
    r.append("#TAXAR 2026")
    r.append("#VALUTA SEK")
    r.append("#KPTYP EUBAS97")
    r.append("#DIM 1 Resultatenhet")
    r.append('#OBJEKT 1 NORD "Enhet Nord"')
    r.append('#OBJEKT 1 SYD "Enhet Syd"')

    for nr, namn, typ in KONTON:
        r.append(f"#KONTO {nr} {_citera(namn)}")
        r.append(f"#KTYP {nr} {typ}")
        r.append(f"#SRU {nr} {SRU[nr]}")

    for nr in IB_0:
        r.append(f"#IB -1 {nr} {_fmt(ib_minus_1[nr])}")
    for nr in IB_0:
        r.append(f"#UB -1 {nr} {_fmt(_d(ub_minus_1[nr]))}")
    for nr in IB_0:
        r.append(f"#IB 0 {nr} {_fmt(_d(IB_0[nr]))}")
    for nr in IB_0:
        r.append(f"#UB 0 {nr} {_fmt(ub_0[nr])}")

    for nr in sorted(res_m1):
        r.append(f"#RES -1 {nr} {_fmt(res_m1[nr])}")
    for nr in sorted(res_0):
        r.append(f"#RES 0 {nr} {_fmt(res_0[nr])}")

    # Verifikationsnumren sätts löpande per serie i listans ordning, så att
    # de förblir sammanhängande och i datumordning även när verifikationer
    # läggs till eller tas bort ovan.
    nasta_vernr: dict[str, int] = defaultdict(lambda: 1)
    for serie, _, datum, text, rader in VER:
        vernr = nasta_vernr[serie]
        nasta_vernr[serie] += 1
        r.append(f"#VER {serie} {vernr} {datum} {_citera(text)} 20260115")
        r.append("{")
        for konto, belopp in rader:
            r.append(f"   #TRANS {konto} {{}} {belopp}")
        r.append("}")

    return "\r\n".join(r) + "\r\n", ub_0, res_0


def main() -> None:
    text, ub_0, res_0 = bygg()

    # Trialbalanskontroll, år 0.
    tb = sum(ub_0.values()) + sum(res_0.values())
    assert tb == 0, f"trialbalansen går inte jämnt ut for ar 0: {tb}"

    UTFIL.write_bytes(text.encode("cp437"))

    oms = -sum(v for k, v in res_0.items() if 3000 <= int(k) <= 3799)
    resultat = -sum(res_0.values())
    balans = sum(v for k, v in ub_0.items() if 1000 <= int(k) <= 1999)
    ek = -(sum(v for k, v in ub_0.items() if 2010 <= int(k) <= 2099)
           + sum(res_0.values()))

    print(f"Skrev {UTFIL.name}: {len(text.splitlines())} rader, "
          f"{len(UTFIL.read_bytes())} byte, cp437")
    print(f"  omsattning       {oms}")
    print(f"  resultat         {resultat}")
    print(f"  balansomslutning {balans}")
    print(f"  eget_kapital     {ek}")


if __name__ == "__main__":
    main()
