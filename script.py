import os
import re
import datetime
import requests
import feedparser

# Konfiguration aus den GitHub Secrets laden
WIKI_URL = os.environ.get("WIKI_URL", "").strip()
WIKI_API_TOKEN = os.environ.get("WIKI_API_TOKEN", "").strip()

# Formatiere die URL korrekt für GraphQL
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

def get_latest_reddit_codes():
    print("[*] Durchsuche Reddit (via RSS) nach neuen Codes...")
    
    rss_url = "https://www.reddit.com/r/EscapefromTarkov/search.rss?q=promo+code&sort=new&restrict_sr=on&t=week"
    
    try:
        feed = feedparser.parse(rss_url, agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) EFT-Bot/2.0")
        
        if feed.bozo and not feed.entries:
            print(f"[-] RSS Feed konnte nicht gelesen werden: {feed.get('bozo_exception', 'Unbekannter Fehler')}")
            return []

        found_codes = []
        ignore_list = ["TARKOV", "BSG", "BATTLESTATE", "GAME", "PATCH", "UPDATE", "NEWS", "DISCORD", "TWITCH", "REDDIT", "PROMO"]

        for entry in feed.entries:
            title = entry.get("title", "")
            content = entry.get("content", [{}])[0].get("value", "") if "content" in entry else ""
            summary = entry.get("summary", "")
            
            full_text = f"{title} {content} {summary}".upper()
            
            potential_codes = re.findall(r'\b[A-Z0-9-]{4,20}\b', full_text)
            for code in potential_codes:
                if code not in ignore_list and not code.isdigit():
                    found_codes.append(code)

        return list(set(found_codes))
    except Exception as e:
        print(f"[-] Fehler beim Verarbeiten des RSS-Feeds: {e}")
        return []

def get_wiki_page():
    query = """
    query ($id: Int!) {
      pages {
        single(id: $id) {
          content title description path
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
    
    if res.status_code != 200:
        raise Exception(f"HTTP Fehler {res.status_code}. Server-Antwort: {res.text[:200]}")
        
    try:
        data = res.json()
    except Exception:
        raise Exception(f"Antwort ist kein JSON (Status {res.status_code}): {res.text[:300]}")
        
    if 'errors' in data:
        raise Exception(f"Wiki.js API Fehler: {data['errors']}")
        
    return data['data']['pages']['single']

def update_wiki_page(page_data, new_content):
    mutation = """
    mutation ($id: Int!, $content: String!, $title: String!, $description: String!, $path: String!) {
      pages {
        update(id: $id, content: $content, title: $title, description: $description, editor: "markdown", isPublished: true, path: $path) {
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
        "path": page_data['path']
    }
    headers = {
        "Authorization": f"Bearer {WIKI_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
    }
    
    res = requests.post(WIKI_URL, json={'query': mutation, 'variables': variables}, headers=headers)
    print("[+] Wiki-Update Rückmeldung:", res.json())

def main():
    if not WIKI_URL or not WIKI_API_TOKEN or WIKI_PAGE_ID == 0:
        print("[-] Fehler: Geheime Variablen (Secrets) fehlen oder WIKI_PAGE_ID ist 0!")
        return

    codes = get_latest_reddit_codes()
    if not codes:
        print("[*] Keine neuen Codes auf Reddit gefunden.")
        return

    try:
        page_data = get_wiki_page()
        current_markdown = page_data['content']
    except Exception as e:
        print(f"[-] Fehler beim Abrufen der Wiki-Seite: {e}")
        return
    
    added_count = 0
    updated_markdown = current_markdown

    for code in codes:
        if code not in current_markdown:
            print(f"[!] Neuer Code entdeckt: {code}")
            table_header = "| Promo-Code | Status | Belohnungen / Inhalt |\n| :--- | :---: | :--- |\n"
            new_row = f"| `{code}` | 🟡 **UNGEPRÜFT (Auto-Add)** | *Neu auf Reddit entdeckt* |\n"
            
            if table_header in updated_markdown:
                updated_markdown = updated_markdown.replace(table_header, table_header + new_row)
                added_count += 1

    if added_count > 0:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updated_markdown = re.sub(r"date: \d{4}-\d{2}-\d{2}", f"date: {today}", updated_markdown)
        
        update_wiki_page(page_data, updated_markdown)
        print(f"[+] {added_count} neue(n) Code(s) erfolgreich im Wiki eingetragen!")
    else:
        print("[*] Alle gefundenen Codes existieren bereits im Wiki. Keine Aktualisierung nötig.")

if __name__ == "__main__":
    main()
