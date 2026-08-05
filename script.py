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

        # 1. Isolieren des Bereichs nach "SEASON CODES FÜR LAUNCHER" oder "CODES FÜR LAUNCHER"
        section_match = re.search(r"(SEASON\s+CODES\s+FÜR\s+LAUNCHER|CODES\s+FÜR\s+LAUNCHER)(.*?)(?=<h[1-6]|<footer|$)", html_text, re.IGNORECASE | re.DOTALL)
        
        target_text = ""
        if section_match:
            target_text = section_match.group(2)
            print("[+] Bereich 'SEASON CODES FÜR LAUNCHER' erfolgreich auf xterotex.de lokalisiert.")
        else:
            print("[-] Hinweis: Spezifische Überschrift nicht exakt gefunden. Durchsuche den gesamten Seiteninhalt...")
            target_text = html_text

        # 2. Regulärer Ausdruck für Tarkov Promo-Codes (Typische Formate wie H77WTXS6FFH1, 1U0MUER etc.)
        # Extrahiert alfanumerische Zeichenketten zwischen 6 und 20 Zeichen
        raw_candidates = re.findall(r'\b[A-Z0-9]{6,20}\b', target_text.upper())

        # Blacklist für Wörter/HTML-Attribute, die in Webseiten-Quelltexten vorkommen
        black_list = {
            "LAUNCHER", "SEASON", "CODES", "CODE", "NEWS", "GERMAN", "DEUTSCH",
            "TARKOV", "ESCAPE", "BATTLESTATE", "HTTP", "HTTPS", "CLASS", "STYLE",
            "DIV", "SPAN", "HREF", "SRC", "WIDTH", "HEIGHT", "COLOR", "PADDING",
            "MARGIN", "DISPLAY", "CONTAINER", "CONTENT", "FOOTER", "HEADER", "NAV"
        }

        found_codes = []
        for candidate in raw_candidates:
            # Nur Strings zulassen, die keine rein Zahlen oder reine Blacklist-Wörter sind
            if candidate not in black_list and not candidate.isdigit():
                # Mindestens ein Buchstabe und eine Zahl ODER eine typische Code-Länge
                if any(c.isdigit() for c in candidate) or len(candidate) >= 8:
                    found_codes.append(candidate)

        unique_codes = list(dict.fromkeys(found_codes))  # Behält die Reihenfolge bei und entfernt Duplikate
        print(f"[*] {len(unique_codes)} valide Codes von xterotex.de ausgelesen: {unique_codes}")
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
        print("[*] Keine gültigen Codes auf xterotex.de gefunden.")
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
            print(f"[!] Neuer Code von xterotex.de wird angefügt: {code}")
            new_row = f"\n| `{code}` | 🟡 **UNGEPRÜFT** | *Gefunden auf xterotex.de* |"
            
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
        print("[*] Alle ausgelesenen Codes von xterotex.de sind bereits im Wiki eingetragen.")

if __name__ == "__main__":
    main()
