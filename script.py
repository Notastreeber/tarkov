import os
import re
import datetime
import requests

WIKI_URL = os.environ.get("WIKI_URL", "").strip()
WIKI_API_TOKEN = os.environ.get("WIKI_API_TOKEN", "").strip()

if WIKI_URL:
    if not WIKI_URL.startswith("http://") and not WIKI_URL.startswith("https://"):
        WIKI_URL = "https://" + WIKI_URL
    if not WIKI_URL.endswith("/graphql"):
        WIKI_URL = WIKI_URL.rstrip("/") + "/graphql"

raw_page_id = os.environ.get("WIKI_PAGE_ID", "0").strip().replace('"', '').replace("'", "")
try:
    WIKI_PAGE_ID = int(raw_page_id)
except ValueError:
    print(f"[-] KRITISCHER FEHLER: WIKI_PAGE_ID '{raw_page_id}' ist keine gültige Zahl!")
    WIKI_PAGE_ID = 0

def fetch_codes_from_xterotex():
    url = "https://xterotex.de/de/news/"
    print(f"[*] Durchsuche exklusiv die Quelle: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[-] Fehler beim Laden der Webseite. Statuscode: {response.status_code}")
            return []

        html_text = response.text

        # 1. Schneide den Text EXAKTLICH ab "SEASON CODES FÜR LAUNCHER" aus
        pattern_start = r"SEASON\s+CODES\s+FÜR\s+LAUNCHER.*?(?=probieren|probiert|\n|<br)"
        match_start = re.search(pattern_start, html_text, re.IGNORECASE | re.DOTALL)

        if not match_start:
            print("[-] 'SEASON CODES FÜR LAUNCHER' nicht gefunden.")
            return []

        # Nimmt alles ab der Fundstelle
        sub_text = html_text[match_start.start():]

        # Beende das Lesen, sobald die nächste H1-H6 Überschrift oder ein Footer kommt
        match_end = re.search(r"<h[1-6]|<footer", sub_text, re.IGNORECASE)
        if match_end:
            sub_text = sub_text[:match_end.start()]

        print("[+] Bereich 'SEASON CODES FÜR LAUNCHER' wurde präzise isoliert.")

        # 2. Regulärer Ausdruck:
        # Matcht entweder Standard-Codes (z.B. WIPE, PCGAMESN) ODER Formate mit Bindestrichen (z.B. 6NU9-UFK1-W2TX-89RW-M96B)
        found_raw = re.findall(r'\b[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})*\b', sub_text.upper())

        # Wörtersperre für Sätze/Anweisungen im Text
        ignore_list = {
            "SEASON", "CODES", "LAUNCHER", "MANCHE", "FUNKTIONIEREN", 
            "ANDERE", "NICHT", "SCHEINT", "VERBUGGT", "SEIN", "PROBIERT", 
            "EINFACH", "ALLE", "NEWS", "GERMAN", "DEUTSCH", "TARKOV"
        }

        valid_codes = []
        for token in found_raw:
            token = token.strip()
            # Ignoriere Sätze/Überschriften und reine Zahlen
            if token not in ignore_list and not token.isdigit():
                # Verhindert kaputte Schnipsel wie -M96B
                if not token.startswith("-") and not token.endswith("-"):
                    valid_codes.append(token)

        # Duplikate entfernen, Reihenfolge behalten
        unique_codes = list(dict.fromkeys(valid_codes))
        print(f"[*] {len(unique_codes)} exakte Codes extrahiert: {unique_codes}")
        return unique_codes

    except Exception as e:
        print(f"[-] Fehler beim Abrufen der Seite xterotex.de: {e}")
        return []

def get_wiki_page():
    query = """
    query ($id: Int!) {
      pages {
        single(id: $id) {
          content title description path locale
        }
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {WIKI_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    }
    res = requests.post(WIKI_URL, json={'query': query, 'variables': {'id': WIKI_PAGE_ID}}, headers=headers)
    data = res.json()
    if 'errors' in data:
        raise Exception(f"Wiki.js API Fehler: {data['errors']}")
    return data['data']['pages']['single']

def update_and_render_wiki_page(page_data, new_content):
    headers = {
        "Authorization": f"Bearer {WIKI_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    }

    mutation_update = """
    mutation ($id: Int!, $content: String!, $title: String!, $description: String!, $path: String!, $locale: String!) {
      pages {
        update(
          id: $id, 
          content: $content, 
          title: $title, 
          description: $description, 
          editor: "markdown", 
          isPublished: true, 
          path: $path,
          locale: $locale
        ) {
          responseResult { succeeded message }
        }
      }
    }
    """
    variables = {
        "id": WIKI_PAGE_ID,
        "content": new_content,
        "title": page_data['title'],
        "description": page_data['description'],
        "path": page_data['path'],
        "locale": page_data.get('locale', 'de')
    }
    
    res_update = requests.post(WIKI_URL, json={'query': mutation_update, 'variables': variables}, headers=headers)
    print("[+] Wiki-Update Server-Antwort:", res_update.json())

    mutation_render = """
    mutation ($id: Int!) {
      pages {
        render(id: $id) {
          responseResult { succeeded message }
        }
      }
    }
    """
    res_render = requests.post(WIKI_URL, json={'query': mutation_render, 'variables': {'id': WIKI_PAGE_ID}}, headers=headers)
    print("[+] Re-Rendering Server-Antwort:", res_render.json())

def main():
    if not WIKI_URL or not WIKI_API_TOKEN or WIKI_PAGE_ID == 0:
        print("[-] Fehler: Geheime Variablen (Secrets) fehlen oder WIKI_PAGE_ID ist 0!")
        return

    codes = fetch_codes_from_xterotex()
    if not codes:
        print("[*] Keine gültigen Codes im Zielbereich auf xterotex.de gefunden.")
        return

    try:
        page_data = get_wiki_page()
        current_markdown = page_data['content']
    except Exception as e:
        print(f"[-] Fehler beim Abrufen der Wiki-Seite: {e}")
        return
    
    added_count = 0
    updated_markdown = current_markdown

    separator_pattern = r"(\| *:\s*---+\s*\| *:\s*---+\s*:\s*\| *:\s*---+\s*\|)"

    if not re.search(separator_pattern, updated_markdown):
        print("[-] WARNUNG: Tabellen-Trennlinie im Wiki nicht gefunden!")
        return

    for code in codes:
        if code not in current_markdown:
            print(f"[!] Neuer Code angefügt: {code}")
            new_row = f"\n| `{code}` | 🟡 **UNGEPRÜFT** | *Neu entdeckt auf xterotex.de* |"
            
            updated_markdown = re.sub(
                separator_pattern,
                r"\1" + new_row,
                updated_markdown,
                count=1
            )
            added_count += 1

    if added_count > 0:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updated_markdown = re.sub(r"Letzte Aktualisierung: \d{4}-\d{2}-\d{2}", f"Letzte Aktualisierung: {today}", updated_markdown)
        
        update_and_render_wiki_page(page_data, updated_markdown)
        print(f"[+] {added_count} neue(r) Code(s) erfolgreich im Wiki eingetragen!")
    else:
        print("[*] Alle ausgelesenen Codes aus diesem Abschnitt sind bereits im Wiki vorhanden.")

if __name__ == "__main__":
    main()
