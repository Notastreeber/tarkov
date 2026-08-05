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

        # 1. HTML-Breaktags in Zeilenumbrüche umwandeln und Tags entfernen für saubere Zeilenanalyse
        clean_text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'</p>|</div>|</td>|</tr>', '\n', clean_text, flags=re.IGNORECASE)
        
        lines = clean_text.split('\n')

        found_codes = []
        inside_code_block = False

        # 2. Zeile für Zeile durchgehen
        for line in lines:
            line_str = re.sub(r'<[^>]+>', '', line).strip()  # HTML-Tags entfernen & Trimmen

            # Suche nach der Startmarkierung: Enthält "SEASON CODES" und endet/beinhaltet einen Doppelpunkt ":"
            if not inside_code_block:
                if "SEASON CODES" in line_str.upper() and ":" in line_str:
                    print(f"[+] Startzeile lokalisiert: '{line_str}'")
                    inside_code_block = True
                    continue

            # Sobald der Block aktiv ist:
            if inside_code_block:
                # Stopp-Bedingung: Erste Leerzeile oder Beginn einer neuen HTML-Struktur / Überschrift
                if not line_str or line_str.startswith("<h") or line_str.startswith("<footer"):
                    if found_codes:  # Stoppt nur, wenn bereits verarbeitete Daten vorliegen (Leerzeile nach den Codes)
                        print("[+] Ende des Code-Blocks (Leerzeile/Strukturwechsel erreicht). Stop.")
                        break
                    continue

                # Regex für Codes: Einzelne Worte (z.B. WIPE, PCGAMESN) ODER Formate mit Bindestrichen (z.B. 6NU9-UFK1-W2TX-89RW-M96B)
                code_matches = re.findall(r'\b[A-Z0-9]{4,}(?:-[A-Z0-9]{4,})*\b', line_str.upper())
                
                for code in code_matches:
                    # Filtert Fragmente mit Bindestrich am Anfang/Ende raus (z.B. -M96B)
                    if not code.startswith("-") and not code.endswith("-") and not code.isdigit():
                        found_codes.append(code)

        unique_codes = list(dict.fromkeys(found_codes))
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
        print("[*] Keine gültigen Codes im isolierten Abschnitt gefunden.")
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
