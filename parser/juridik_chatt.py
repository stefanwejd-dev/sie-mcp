import json
import anthropic
from parser import juridik_api

JURIDIK_STRIKT_PROMPT = """Du är en strikt och professionell svensk skattejurist och redovisningsexpert. 
Din ENDA uppgift är att besvara användarens frågor utifrån gällande svensk rätt och Skatteverkets ställningstaganden.

REGLER FÖR DITT SVAR:
1. Svara ALDRIG med gissningar eller "allmän kunskap" från din träningsdata.
2. Du MÅSTE använda dina verktyg för att slå upp den exakta lagtexten (SFS) eller söka i Skatteverkets Rättsliga Vägledning.
3. Du MÅSTE alltid strukturera ditt svar exakt så här:
   - **Kort Svar:** (En koncis sammanfattning på 2-8 meningar)
   - **Citat:** (Ett exakt citat ur lagen eller vägledningen)
   - **Källa:** (En klickbar Markdown-fotnot eller länk till källan du hämtade)
4. Ge inga finansiella råd gällande specifika transaktioner, utan beskriv enbart vad lagen/regeln säger generellt."""

JURIDIK_VERKTYG = [
    {
        "name": "sok_lagstiftning",
        "description": "Söker i gällande svensk lagstiftning (SFS) via Riksdagens öppna data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sokord": {"type": "string", "description": "Sökord, t.ex. 'bokföringslag'"}
            },
            "required": ["sokord"]
        }
    },
    {
        "name": "skatteverket_rattslig_vagledning",
        "description": "Skapar en söklänk till Skatteverkets ställningstaganden.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sokord": {"type": "string", "description": "Sökord, t.ex. 'representation'"}
            },
            "required": ["sokord"]
        }
    }
]

def kora_juridik_chatt(meddelanden: list[dict], api_nyckel: str, modell: str) -> str:
    if not api_nyckel:
        return "Systemfel: Ingen API-nyckel för Anthropic konfigurerad."
        
    klient = anthropic.Anthropic(api_key=api_nyckel)
    
    try:
        # Konvertera interna meddelanden till Anthropics format
        anthropic_msgs = []
        for m in meddelanden:
            if m["role"] in ["user", "assistant"]:
                anthropic_msgs.append({"role": m["role"], "content": m["content"]})
        
        response = klient.messages.create(
            model=modell,
            max_tokens=2048,
            system=JURIDIK_STRIKT_PROMPT,
            tools=JURIDIK_VERKTYG,
            messages=anthropic_msgs
        )
        
        # Om inga verktyg anropades
        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text":
                    return block.text
            return "Kunde inte tolka svaret."
            
        # Hantera verktygsanrop
        tool_results = []
        svarstext = ""
        
        for block in response.content:
            if block.type == "text":
                svarstext += block.text + "\n\n"
            elif block.type == "tool_use":
                if block.name == "sok_lagstiftning":
                    res = juridik_api.sok_svensk_lagstiftning(block.input.get("sokord", ""))
                elif block.name == "skatteverket_rattslig_vagledning":
                    res = juridik_api.skapa_lank_skatteverket(block.input.get("sokord", ""))
                else:
                    res = {"error": "Okänt verktyg"}
                    
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(res, ensure_ascii=False)
                })
                
        # Skicka tillbaka verktygsresultaten till modellen
        anthropic_msgs.append({"role": "assistant", "content": response.content})
        anthropic_msgs.append({"role": "user", "content": tool_results})
        
        slutgiltigt_svar = klient.messages.create(
            model=modell,
            max_tokens=2048,
            system=JURIDIK_STRIKT_PROMPT,
            tools=JURIDIK_VERKTYG,
            messages=anthropic_msgs
        )
        
        for block in slutgiltigt_svar.content:
            if block.type == "text":
                return svarstext + block.text
                
        return svarstext
        
    except Exception as e:
        return f"Systemfel vid anrop till juridik-agenten: {e}"
