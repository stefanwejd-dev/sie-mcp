import re
import urllib.request
import urllib.parse
import json


def _strip_tags(html: str) -> str:
    """Enkel taggborttagning för 'summary'-fältets <mark>-markeringar."""
    utan_taggar = re.sub(r"<[^>]+>", "", html or "")
    return re.sub(r"\s+", " ", utan_taggar).strip()


def _riksdagen_dokumentlista(sokord: str, doktyp: str, antal: int):
    """
    Ett anrop mot Riksdagens dokumentlista-API för en given doktyp.
    Returnerar None vid API-fel, annars en lista med normaliserade träffar
    (max `antal` st).

    sort=rel&sortorder=desc är avgörande — utan den sorterar API:et (i
    praktiken) på datum, och ett sökord som "representation" ger då senaste
    tillkomna dokumentet oavsett ämne istället för t.ex. Inkomstskattelagen.
    Verifierat manuellt 2026-08-10.
    """
    query = urllib.parse.quote(sokord)
    url = f"https://data.riksdagen.se/dokumentlista/?sok={query}&doktyp={doktyp}&sort=rel&sortorder=desc&utformat=json"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

    dok = data.get("dokumentlista", {}).get("dokument", [])
    if isinstance(dok, dict):
        dok = [dok]

    resultat = []
    for d in dok[:antal]:
        rm = d.get("rm", "")
        nummer = d.get("nummer", "")
        beteckning = f"{rm}:{nummer}"

        # API:et returnerar ett textutdrag ur själva dokumentet runt
        # sökordet ('summary'), inte bara titeln — det närmaste ett riktigt
        # citat vi kan komma utan att hämta och parsa hela dokumentet.
        # <mark>-taggarna runt träffordet är bara till för webbvisning,
        # strippas här.
        utdrag = _strip_tags(d.get("summary", ""))

        # dokument_url_html funkar enhetligt för alla doktyper (till
        # skillnad från den gamla, SFS-specifika riksdagen_url-mallen).
        html_url = d.get("dokument_url_html", "")
        url_full = f"https:{html_url}" if html_url else ""

        resultat.append({
            "doktyp": doktyp.upper(),
            "titel": d.get("titel", "Okänd titel"),
            "beteckning": beteckning,
            "url": url_full,
            "lagen_nu_url": f"https://lagen.nu/{beteckning}" if doktyp == "sfs" else None,
            "utdrag_ur_lagtexten": utdrag or None
        })

    return resultat


def sok_svensk_lagstiftning(sokord: str) -> dict:
    """
    Söker gällande lagtext (SFS) OCH förarbeten (propositioner + SOU) via
    Riksdagens öppna data — samma primärkälla som ferenda (lagen.nu:s
    ramverk) själv bygger på. SFS är huvudkällan för svaret; förarbetena är
    kompletterande läsning, inte grund för citatet.

    doktyp=sfs,prop,sou (kommaseparerat) testades men ignorerades av
    API:et — träffantalet blev orimligt stort (5086 mot 88 för enbart sfs),
    så varje doktyp hämtas i ett eget anrop istället.
    """
    lagstiftning = _riksdagen_dokumentlista(sokord, "sfs", 3)
    if lagstiftning is None:
        return {"status": "error", "meddelande": "Kunde inte nå Riksdagens öppna data."}

    forarbeten = (_riksdagen_dokumentlista(sokord, "prop", 2) or []) + \
                 (_riksdagen_dokumentlista(sokord, "sou", 2) or [])

    return {
        "status": "success",
        "lagstiftning": lagstiftning,
        "forarbeten": forarbeten,
        "instruktion": "SAKERHETSNOT: 'lagstiftning' (SFS) är huvudkällan för svaret — du MÅSTE länka till dess url när du hänvisar till lagen, och fältet Citat ska komma från 'utdrag_ur_lagtexten' (om det finns) i ETT av lagstiftning-träffarna, aldrig hittas på. Saknas utdrag för alla lagstiftning-träffar: säg det istället för att gissa. 'forarbeten' (propositioner/SOU) är kompletterande läsning om lagstiftarens syfte — nämn dem bara om de faktiskt är relevanta, och aldrig som ersättning för lagtexten i Citat-fältet. Klargör alltid att detta är ett automatiserat uppslag och inte utgör professionell juridisk rådgivning."
    }


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
