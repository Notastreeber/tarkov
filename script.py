import os
import re
import datetime
import requests
import feedparser

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

def get_latest_reddit_codes():
    print("[*] Durchsuche Reddit (via RSS) nach neuen Codes...")
    rss_url = "https://www.reddit.com/r/EscapefromTarkov/search.rss?q=promo+code&sort=new&restrict_sr=on&t=year"
    
    try:
        feed = feedparser.parse(rss_url, agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) EFT-Bot/2.0")
        if feed.bozo and not feed.entries:
            print(f"[-] RSS Feed konnte nicht gelesen werden: {feed.get('bozo_exception', 'Unbekannter Fehler')}")
            return []

        found_codes = []
        now = datetime.datetime.now(datetime.timezone.utc)
        one_year_ago = now - datetime.timedelta(days=365)
        ignore_list = ["TARKOV", "BSG", "BATTLESTATE", "GAME", "PATCH", "UPDATE", "NEWS", "DISCORD", "TWITCH", "REDDIT", "PROMO", "CODES", "CODE", "ESCAPE", "ARENA", "EDITION", "STEAM", "WIPE", "PVE", "PVP", "LIST"]

        for entry in feed.entries:
            published_parsed = entry.get("published_parsed")
            if published_parsed:
                pub_date = datetime.datetime(*published_parsed[:6], tzinfo=datetime.timezone.utc)
                if pub_date < one_year_ago:
                    continue

            title = entry.get("title", "")
            content = entry.get("content", [{}])[0].get("value", "") if "content" in entry else ""
            summary = entry.get("summary", "")
            
            full_text = f"{title} {content} {summary}".upper()
            potential_codes = re.findall(r'\b[A-Z0-9]{6,18}\b', full_text)
            for code in potential_codes:
                if code not in ignore_list and not code.isdigit():
                    found_codes.append(code)

        unique_codes = list(set(found_codes))
        print(f"[*] {len(unique_codes)} potenzielle Codes gefunden.")
        return unique_codes
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
    data = res.json()
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
    print("[+] Wiki-Update Server-Antwort:", res.json())

def main():
    if not WIKI_URL or not WIKI_API_TOKEN or WIKI_PAGE_ID == 0:
        print("[-] Fehler: Geheime Variablen (Secrets) fehlen oder WIKI_PAGE_ID ist 0!")
        return

    codes = get_latest_reddit_codes()
    if not codes:
        print("[*] Keine passenden Codes gefunden.")
        return

    try:
        page_data = get_wiki_page()
        current_markdown = page_data['content']
        print(f"[*] Wiki-Seite '{page_data['title']}' erfolgreich geladen ({len(current_markdown)} Zeichen).")
    except Exception as e:
        print(f"[-] Fehler beim Abrufen der Wiki-Seite: {e}")
        return
    
    added_count = 0
    updated_markdown = current_markdown

    # Flexiblerer Regex-Suchmuster für den Tabellenkopf
    table_header_pattern = r"(\| *Promo-Code *\| *Status *\| *Belohnungen / Inhalt *\|)"

    if not re.search(table_header_pattern, updated_markdown, re.IGNORECASE):
        print("[-] WARNUNG: Tabellenkopf im Wiki nicht gefunden!")
        print("    Stelle sicher, dass deine Wiki-Seite folgenden Kopf enthält:")
        print("    | Promo-Code | Status | Belohnungen / Inhalt |")
        return

    for code in codes:
        if code not in current_markdown:
            print(f"[!] Neuer Code wird angefügt: {code}")
            new_row = f"\n| `{code}` | 🟡 **UNGEPRÜFT (Auto-Add)** | *Neu auf Reddit entdeckt* |"
            
            # Fügt die Zeile direkt unter dem Tabellen-Header/Trennlinie ein
            updated_markdown = re.sub(
                r"(\| *:--- *\| *:---: *\| *:--- *\|)",
                r"\1" + new_row,
                updated_markdown,
                count=1
            )
            added_count += 1

    if added_count > 0:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updated_markdown = re.sub(r"Letzte Aktualisierung: \d{4}-\d{2}-\d{2}", f"Letzte Aktualisierung: {today}", updated_markdown)
        
        print(f"[*] Sende Update für {added_count} neue Codes an das Wiki...")
        update_wiki_page(page_data, updated_markdown)
    else:
        print("[*] Alle gefundenen Codes sind bereits im Wiki vorhanden.")

if __name__ == "__main__":
    main()
