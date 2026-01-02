import requests
from bs4 import BeautifulSoup
import re
import json

def scrape_wp_product(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        data = {}
        data['product_url'] = url
        
        # WP ID
        shortlink = soup.find('link', rel='shortlink')
        data['wp_id'] = int(shortlink['href'].split('p=')[1]) if shortlink and 'p=' in shortlink['href'] else None

        # Name
        data['name'] = soup.find('h1', class_='product_title').get_text(strip=True) if soup.find('h1', class_='product_title') else "N/A"
        
        # Description
        opis_div = soup.find('div', id='cgkit-tab-description')
        full_txt = ""
        if opis_div:
            for noise in opis_div.find_all(['script', 'style', 'button']):
                noise.decompose()
            full_txt = opis_div.get_text(separator=' ', strip=True)
            data['description'] = full_txt
        else:
            data['description'] = "Brak opisu"
            
        # Notes
        def find_scent_notes_fixed(keyword, text):
            # Keyword can be "Otwarcie", "sercu", "Bazę"
            pattern = rf"{keyword}\s+[^.]*?\s+(?:uderza|rozwijają się|tworzy|mieszanką)\s+([^.]*)"
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                pattern = rf"{keyword}\s+(?:[^.]*?)\s+([^.]*)"
                match = re.search(pattern, text, re.IGNORECASE)
            return match.group(1).strip() if match else "N/A"
        
        data['nuty_glowy'] = find_scent_notes_fixed("Otwarcie", full_txt)
        data['nuty_serca'] = find_scent_notes_fixed("sercu", full_txt)
        data['nuty_bazy'] = find_scent_notes_fixed("Bazę", full_txt)
        
        # Attributes
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                val = cells[1].get_text(strip=True)
                if 'pojemność' in label: data['capacity'] = val
                elif 'koncentracja' in label: data['concentration'] = val
                elif 'płeć' in label: data['gender'] = val
        
        return data
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

test_url = "https://perfun.pl/produkt/afnan-turathi-electric/"
result = scrape_wp_product(test_url)
print(json.dumps(result, indent=2, ensure_ascii=False))
