import os
import re
import datetime
import requests

# Konfiguration wird automatisch aus den GitHub Secrets geladen
WIKI_URL = os.environ.get("WIKI_URL")
WIKI_API_TOKEN = os.environ.get("WIKI_API_TOKEN")
WIKI_PAGE_ID = int(os.environ.get("WIKI_PAGE_ID", "0"))

def get_latest_reddit_codes():
    print("[*] Durchsuche Reddit nach neuen Codes...")
    url = "https://www.reddit.com/r/EscapefromTarkov/search.json?q=promo+code&sort=new&restrict_sr=on&t=week"
    
    # Individueller User-Agent umgeht die 403-Sperre von Cloud-Runnern
    headers = {
        "User-Agent": "script:eft-promo-updater:v1.1 (by /u/custom_tarkov_bot)"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        # Fallback auf alte Reddit-URL, falls die neue blockiert wird
        if response.status_code == 403:
            print("[!] Status 403 erhalten. Versuche Fallback-URL (old.reddit.com)...")
            url = "https://old.reddit.com/r/EscapefromTarkov/search.json?q=promo+code&sort=new&restrict_sr=on&t=week"
            response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"[-] Reddit-Abfrage fehlgeschlagen: HTTP Status {response.status_code}")
            return []
            
        posts = response.json().get("data", {}).get("children", [])
        found_codes = []
        ignore_list = ["TARKOV", "BSG", "BATTLESTATE", "GAME", "PATCH", "UPDATE", "NEWS", "DISCORD", "TWITCH", "REDDIT"]

        for post in posts:
            title = post.get("data", {}).get("title", "")
            body = post.get("data", {}).get("selftext", "")
            full_text = f"{title} {body}".upper()
            
            potential_codes = re.findall(r'\b[A-Z0-9-]{4,20}\b', full_text)
            for code in potential_codes:
                if code not in ignore_list and not code.isdigit():
                    found_codes.append(code)

        return list(set(found_codes))
    except Exception as e:
        print(f"[-] Fehler beim Laden von Reddit: {e}")
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
    headers = {"Authorization": f"Bearer {WIKI_API_TOKEN}"}
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
    headers = {"Authorization": f"Bearer {WIKI_API_TOKEN}"}
    res = requests.post(WIKI_URL, json={'query': mutation, 'variables': variables}, headers=headers)
    print("[+] Wiki-Update Rückmeldung:", res.json())

def main():
    if not WIKI_URL or not WIKI_API_TOKEN or WIKI_PAGE_ID == 0:
        print("[-] Fehler: Geheime Variablen (Secrets) fehlen oder wurden nicht geladen!")
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
