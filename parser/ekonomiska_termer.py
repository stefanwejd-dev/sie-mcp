"""ekonomiska_termer — versionsstyrd, minimal stopplista över vanliga svenska
ekonomiska/BAS-rubrikord och bokförings-ram-ord.

Används av sekretesslagrets Lager 3b för att skilja ett versalinlett namnpar
("Erik Svensson") från en ekonomisk rubrik ("Ingående Balans"), och för att
trimma bort ekonomiska ram-ord runt ett namn ("Kurs Erik Svensson" ->
"Erik Svensson", "Ingående Balans" -> inget kvar).

Två hårda designregler:
- **Deterministisk och sluten:** INGEN gitignorerad eller användarredigerbar
  extrafil i denna version. Samma indata ska ge samma säkerhetsresultat
  överallt (fritext, chatt, kontonamn, Spiris). Utbyggnad sker i senare,
  versionsstyrda ändringar — höj då VERSION.
- **Aldrig ett efternamn:** ett ord i listan får ALDRIG vara ett vanligt
  svenskt efternamn, annars skulle det tysta ett verkligt namn. Detta
  testtäcks (test_vanliga_efternamn_ar_aldrig_stoppord).

Listan är medvetet LITEN och explicit. Den täcker de vanligaste balans-/
resultatrubrikerna och de bokförings-ram-ord som ofta står omedelbart före ett
namn i verifikations-/transaktionstext.
"""

from __future__ import annotations

VERSION = 1

_STOPPORD: frozenset[str] = frozenset({
    # --- Balans- och resultatrubriker ---
    "Ingående", "Utgående", "Balans", "Balanserat", "Eget", "Kapital",
    "Bundet", "Bundna", "Fritt", "Fria", "Årets", "Resultat", "Reserver",
    "Reservfond", "Överkursfond", "Obeskattade", "Periodiseringsfond",
    # --- Periodiseringar, klasser, tillgångar/skulder ---
    "Upplupna", "Upplupet", "Förutbetalda", "Förutbetald",
    "Kostnader", "Kostnad", "Intäkter", "Intäkt",
    "Ackumulerade", "Avskrivningar", "Nedskrivningar",
    "Sociala", "Avgifter", "Kortfristiga", "Långfristiga",
    "Skulder", "Fordringar", "Anläggningstillgångar", "Omsättningstillgångar",
    "Varulager",
    # --- Skatt/moms ---
    "Moms", "Skatt", "Skatter",
    # --- Sammanställningsord ---
    "Övriga", "Övrigt", "Diverse", "Summa", "Avräkning",
    # --- Bokförings-/transaktionsram som ofta föregår ett namn ---
    "Kassa", "Bank", "Plusgiro", "Bankgiro",
    "Kurs", "Utlägg", "Insättning", "Uttag", "Betalning", "Inbetalning",
    "Utbetalning", "Faktura", "Kundfaktura", "Lön", "Swish", "Överföring",
})

_STOPPORD_CASEFOLD: frozenset[str] = frozenset(ord_.casefold() for ord_ in _STOPPORD)


def ar_ekonomisk_term(ord_: str) -> bool:
    """Sant om ordet är en känd ekonomisk term/rubrik/ram (skiftlägesokänsligt)."""
    return ord_.casefold() in _STOPPORD_CASEFOLD
