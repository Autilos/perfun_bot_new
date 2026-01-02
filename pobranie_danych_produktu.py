import requests
from bs4 import BeautifulSoup
import re
import json

def scrape_full_test_v2(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    data = {}
    
    # 1. Podstawowe
    data['nazwa'] = soup.find('h1', class_='product_title').get_text(strip=True) if soup.find('h1') else "N/A"
    data['link_produktu'] = url
    img_meta = soup.find('meta', property='og:image')
    data['link_zdjecia'] = img_meta['content'] if img_meta else "N/A"
    
    # 2. OPIS (Twój działający selektor)
    opis_div = soup.find('div', id='cgkit-tab-description')
    full_txt = ""
    if opis_div:
        for noise in opis_div.find_all(['script', 'style', 'button']):
            noise.decompose()
        full_txt = opis_div.get_text(separator=' ', strip=True)
        data['opis_pelny'] = full_txt
    else:
        data['opis_pelny'] = "Brak opisu"
    
    # 3. POPRAWIONA CENA (Obsługa wariantów i zakresów)
    # Szukamy najpierw ceny promocyjnej, potem zwykłej
    price_container = soup.select_one('p.price')
    if price_container:
        # Jeśli jest zakres (np. 14zł - 159zł), bierzemy wyższą lub czyścimy tekst
        # Wyciągamy wszystkie kwoty i bierzemy ostatnią (zazwyczaj cena główna)
        amounts = price_container.find_all('span', class_='woocommerce-Price-amount')
        if amounts:
            prices = [re.sub(r'[^\d,]', '', a.get_text()) for a in amounts]
            # Bierzemy ostatnią unikalną cenę (żeby nie brać ceny "najniższej z 30 dni")
            data['cena'] = f"{prices[-1].replace(',', '.')} zł"
        else:
            data['cena'] = "N/A"
    else:
        data['cena'] = "N/A"

    # 4. POPRAWIONE NUTY (Regex dostosowany do Twojego tekstu)
    def find_scent_notes_fixed(keyword, text):
        # Szukamy słowa "Otwarcie" itd. i bierzemy tekst do kropki
        pattern = rf"{keyword}\s+[^.]*?\s+(?:uderza|rozwijają się|tworzy|mieszanką)\s+([^.]*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match: # Drugi sposób jeśli pierwszy zawiedzie
            pattern = rf"{keyword}\s+(?:[^.]*?)\s+([^.]*)"
            match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else "N/A"
    
    data['nuty_glowy'] = find_scent_notes_fixed("Otwarcie", full_txt)
    data['nuty_serca'] = find_scent_notes_fixed("sercu", full_txt)
    data['nuty_bazy'] = find_scent_notes_fixed("Bazę", full_txt)

    # 5. Atrybuty
    rows = soup.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            val = cells[1].get_text(strip=True)
            if 'pojemność' in label: data['pojemność'] = val
            elif 'koncentracja' in label: data['koncentracja'] = val
            elif 'płeć' in label: data['płeć'] = val

    return data

# TEST
wynik = scrape_full_test_v2("https://perfun.pl/produkt/afnan-turathi-electric/")
print(json.dumps(wynik, indent=2, ensure_ascii=False))