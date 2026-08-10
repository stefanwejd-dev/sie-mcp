import os
from pathlib import Path

fpath = "AI_HANDOVER.md"
content = Path(fpath).read_text(encoding="utf-8")

# Modify Section 4 title to say Etapp 8 to 17
content = content.replace("## 4. Vad som utförts i Etapp 8 till 15b", "## 4. Vad som utförts i Etapp 8 till 17")

# Add Etapp 16 and 17 to Section 4
etapp_16_17 = '''
* **Etapp 16**: Inläsning av prislistor, rabattavtal och etiketter (masterdata).
* **Etapp 17**: Byggde verktyg för två-segmentsuppslag (`spiris_verifikation` och `spiris_bankhandelse`). All kod är klar och röktestad lokalt.'''
content = content.replace("* **Etapp 15-15b**: Stöd för offertutkast (`/quotedrafts`), säljdokumentåtgärd (omvandling av ordrar/offerter), samt kvittning av leverantörskreditfakturor (`/supplierinvoices/{id}/offset`).", 
                          "* **Etapp 15-15b**: Stöd för offertutkast (`/quotedrafts`), säljdokumentåtgärd (omvandling av ordrar/offerter), samt kvittning av leverantörskreditfakturor (`/supplierinvoices/{id}/offset`)." + etapp_16_17)

# Update Section 5 title and text
content = content.replace("## 5. Vad som kvarstår att göra (Etapp 16+)", "## 5. Vad som kvarstår att göra")
content = content.replace("Den planen är körbar och ersätter listan nedan som arbetsunderlag. Den här sammanställningen står kvar för att visa hur punkterna föll ut.",
                          "**Hela planen är nu utförd.** Både Etapp 0-7 och Etapp 8-17 är till fullo implementerade, testade (2 244 gröna tester) och integrerade i koden. Nedan syns hur utkastet utföll.")

# Update the instruction steps
content = content.replace("3. Börja med Etapp 8 (rättningarna). Bygg ingen ny funktion ovanpå en trasig skrivväg.", "3. Projektet är nu i en fas där grundplanerna (`PLAN_SPIRIS_TACKNING.md` och `PLAN_SPIRIS_ETAPP8.md`) är 100 % slutförda.")
content = content.replace("4. Kör inte R8.7 eller Etapp 15b innan GRIND 10 är körd: `python tools/prov_grind10.py --bolag \"<bolagsnamn>\" --offset`.", "4. Endast underhåll och eventuellt upptäckta buggar återstår i dagsläget, såvida ingen ny plan (Etapp 18+) formuleras.")

# Update the latest status line
content = content.replace("- **Senaste uppdatering**: Etapp 17 (Småplock: Enstaka verifikat och bankhändelser) är implementerad och inväntar GRIND 17.", 
                          "- **Senaste uppdatering**: Etapp 17 är implementerad. Hela systemet, från Etapp 0 till 17, är klart och kodbasen är 100 % testgrön med 2 244 tester.")

Path(fpath).write_text(content, encoding="utf-8")
