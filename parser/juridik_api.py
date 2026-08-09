import urllib.request
import urllib.parse
import json

def sok_svensk_lagstiftning(sokord: str) -> dict:
    """
    Söker i gällande svensk lagstiftning (SFS) via Riksdagens API.
    Returnerar de översta träffarna och länkar till lagen.
    """
    query = urllib.parse.quote(sokord)
    url = f"http://data.riksdagen.se/dokumentlista/?sok={query}&doktyp=sfs&utformat=json"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            traffar = data.get("dokumentlista", {}).get("@traffar", 0)
            dok = data.get("dokumentlista", {}).get("dokument", [])
            
            if isinstance(dok, dict):
                dok = [dok]
            
            resultat = []
            for d in dok[:3]:  # Returnera max 3 träffar i PoC
                titel = d.get("titel", "Okänd titel")
                rm = d.get("rm", "")
                nummer = d.get("nummer", "")
                sfs_beteckning = f"{rm}:{nummer}"
                
                # Riksdagens länk för läsning
                riksdagen_url = f"https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/_{d.get('id')}"
                lagen_nu_url = f"https://lagen.nu/{sfs_beteckning}"
                
                resultat.append({
                    "titel": titel,
                    "sfs": sfs_beteckning,
                    "riksdagen_url": riksdagen_url,
                    "lagen_nu_url": lagen_nu_url,
                    "sammanfattning": d.get("titel", "")
                })
                
            return {
                "status": "success",
                "traffar": traffar,
                "dokument": resultat,
                "instruktion": "SAKERHETSNOT: Du MÅSTE använda fotnötter och länka till 'riksdagen_url' eller 'lagen_nu_url' när du hänvisar till lagen. Klargör även att detta är ett automatiserat uppslag och inte utgör professionell juridisk rådgivning."
            }
            
    except Exception as e:
        return {"status": "error", "meddelande": str(e)}

def skapa_lank_skatteverket(sokord: str) -> dict:
    """
    Skatteverkets rättsliga vägledning saknar ett sök-API för fri text som vi kan 
    skrapa, men vi kan skapa en formaterad sök-länk som AI:n kan ge till användaren.
    """
    query = urllib.parse.quote(sokord)
    url = f"https://www4.skatteverket.se/rattsligvagledning/3236.html?q={query}"
    
    return {
        "status": "success",
        "sokord": sokord,
        "url": url,
        "instruktion": "SAKERHETSNOT: Eftersom Skatteverket blockerar maskinell läsning av Rättslig vägledning, måste du ge denna länk till användaren som en klickbar fotnot och uppmana dem att dubbelkolla Skatteverkets ställningstagande där."
    }
