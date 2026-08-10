import os
from pathlib import Path
import re

fpath = "README.md"
content = Path(fpath).read_text(encoding="utf-8")

# P3.1
old_p31 = "exponerar 54 primära verktyg över `stdio` — 37 läsande, 16 som föreslår åtgärder utan att utföra dem, och `visa_anvandarvillkor` (samt 31 domänspecifika alias, totalt 85)"
new_p31 = "exponerar 88 primära verktyg över `stdio` — 56 läsande, 31 som föreslår åtgärder utan att utföra dem, och `visa_anvandarvillkor` (samt 37 domänspecifika alias, totalt 125). Dessutom tillhandahålls 3 resurser, 1 resursmall och 5 prompter"
content = content.replace(old_p31, new_p31)

# P3.2
table_pattern = re.compile(r"\| Grupp \| Verktyg \|\n\|---\|---\|\n(?:\|.*?\|\n)+")
new_table = """Klienten (Claude Desktop e.dyl.) listar automatiskt alla verktyg när servern ansluts. Verktygen är indelade i följande logiska grupper:

* **SIE4-filer:** Beräkningar och analyser.
* **Struktur & Register:** Kontoplan, räkenskapsår, artiklar, företagsinfo, bankkonton m.m.
* **Huvudbok & Rapporter:** Saldon, transaktioner, verifikat och finansiella rapporter.
* **Reskontra & Affärsdokument:** Kund-/leverantörsreskontra, fakturor, order och offerter.
* **Moms:** Momsöversikt och rapporter.
* **Masterdata:** Prislistor, rabattavtal och etiketter.
* **Förslag (Utkastvägen):** `forbered_*`-verktyg för att skapa fakturor, bokföra, kvitta betalningar, ändra kontoplan, periodisera och hantera bokföringslås. Dessa utför ingenting, utan lägger utkast för mänsklig granskning.
* **Villkor:** `visa_anvandarvillkor` för att läsa avtalet.

"""
content = table_pattern.sub(new_table, content)

# P3.3
install_heading = "### 1. Installation\n"
new_install = install_heading + """
> **Spiris-anslutningen kräver Windows.** OAuth-sessionen skyddas med Windows
> DPAPI (per användare) och har medvetet ingen fallback på andra plattformar —
> en osäker lagring vore värre än ingen. SIE4-vägen är inte beroende av detta.
"""
content = content.replace(install_heading, new_install)

Path(fpath).write_text(content, encoding="utf-8")
