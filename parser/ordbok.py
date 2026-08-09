"""ordbok — ett kanoniskt svenskt namn per bokföringsbegrepp.

Fönstrets ordförråd. UI-etiketter, MCP-verktygsbeskrivningar och adaptrar
hämtar alla sitt namn härifrån, så att ett begrepp byter namn på ETT ställe
och så att inget leverantörsnamn kan läcka in i gränssnittet.

Skild från ekonomiska_termer.py, som är sekretesslagrets stopplista och har
helt andra krav (deterministisk, sluten, versionsstyrd). Blanda dem inte."""

from dataclasses import dataclass, field

@dataclass(frozen=True)
class Begrepp:
    id: str
    namn: str
    forklaring: str
    kallsynonymer: dict[str, str] = field(default_factory=dict)

_ORDBOK = {
    "kundreskontra": Begrepp("kundreskontra", "Kundreskontra", "Obetalda kundfakturor och deras förfallodagar.", kallsynonymer={"spiris": "CustomerInvoices"}),
    "leverantorsreskontra": Begrepp("leverantorsreskontra", "Leverantörsreskontra", "Obetalda leverantörsfakturor och deras förfallodagar.", kallsynonymer={"spiris": "SupplierInvoices"}),
    "kundfaktura": Begrepp("kundfaktura", "Kundfaktura", "En utställd faktura till en kund."),
    "leverantorsfaktura": Begrepp("leverantorsfaktura", "Leverantörsfaktura", "En mottagen faktura från en leverantör."),
    "huvudbok": Begrepp("huvudbok", "Huvudbok", "Bokföringens alla transaktioner sorterade per konto."),
    "verifikat": Begrepp("verifikat", "Verifikat", "Bokföringshändelse.", kallsynonymer={"spiris": "Vouchers"}),
    "kontoplan": Begrepp("kontoplan", "Kontoplan", "Företagets valda konton.", kallsynonymer={"spiris": "Accounts"}),
    "kontosaldo": Begrepp("kontosaldo", "Kontosaldo", "Saldo på ett specifikt konto.", kallsynonymer={"spiris": "AccountBalances"}),
    "resultatrapport": Begrepp("resultatrapport", "Resultatrapport", "Företagets intäkter och kostnader."),
    "balansrapport": Begrepp("balansrapport", "Balansrapport", "Företagets tillgångar, eget kapital och skulder."),
    "nyckeltal": Begrepp("nyckeltal", "Nyckeltal", "Viktiga ekonomiska mätetal."),
    "kassaflode": Begrepp("kassaflode", "Kassaflöde", "In- och utbetalningar under perioden."),
    "likviditetsprognos": Begrepp("likviditetsprognos", "Likviditetsprognos", "Prognos över kortsiktig betalningsförmåga."),
    "moms": Begrepp("moms", "Moms", "Mervärdesskatt."),
    "order": Begrepp("order", "Order", "Kundbeställning.", kallsynonymer={"spiris": "Orders"}),
    "offert": Begrepp("offert", "Offert", "Erbjudande till kund.", kallsynonymer={"spiris": "Offers"}),
    "artikel": Begrepp("artikel", "Artikel", "Produkt eller tjänst som säljs eller köps.", kallsynonymer={"spiris": "Articles"}),
    "bankkonto": Begrepp("bankkonto", "Bankkonto", "Företagets bankkonto."),
    "rakenskapsar": Begrepp("rakenskapsar", "Räkenskapsår", "Företagets finansiella år.", kallsynonymer={"spiris": "FinancialYears"}),
    "vasentlighet": Begrepp("vasentlighet", "Väsentlighet", "Beloppsgräns för vad som påverkar ekonomiska beslut (ISA 320/450)."),
    "aldersanalys": Begrepp("aldersanalys", "Åldersanalys", "Analys av förfallna fakturors ålder."),
    "paminnelse": Begrepp("paminnelse", "Påminnelse", "Krav på betalning av förfallen faktura."),
    "betalningsforslag": Begrepp("betalningsforslag", "Betalningsförslag", "Förslag på leverantörsfakturor att betala."),
    "investeringskalkyl": Begrepp("investeringskalkyl", "Investeringskalkyl", "Kalkyl över framtida investeringar."),
    "bokforing": Begrepp("bokforing", "Bokföring", "Systematisk registrering av affärshändelser."),
    "kund": Begrepp("kund", "Kund", "Företagets kund."),
    "leverantor": Begrepp("leverantor", "Leverantör", "Företagets leverantör."),
    "projekt": Begrepp("projekt", "Projekt", "Projekt i bokföringen."),
    "kostnadsstalle": Begrepp("kostnadsstalle", "Kostnadsställe", "Kostnadsställe i bokföringen."),
    "referensdata": Begrepp("referensdata", "Referensdata", "Systemets referensdata."),
}

def hamta(id_: str) -> Begrepp:
    return _ORDBOK[id_]

def alla() -> tuple[Begrepp, ...]:
    return tuple(_ORDBOK.values())
