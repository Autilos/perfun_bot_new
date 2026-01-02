import os
import json
import re
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv('/Users/wojciechnowak/.env')

# API Clients
openai_client = OpenAI(api_key=os.environ.get("OPEN_AI_API"))
supabase_url = os.environ.get("FIRMY_SUPABASE_URL")
supabase_key = os.environ.get("FIRMY_SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)

# Paths
FRAGRANTICA_DATA_PATH = "/Users/wojciechnowak/Documents/Clients/Perfun/Fragrantica - Adam/scraped_fragrantica_data.json"

def normalize_name(name):
    """Normalize perfume name for matching."""
    if not name:
        return ""
    name = name.lower()
    # Remove common words that might differ
    name = re.sub(r'\b(perfume|eau de parfum|edp|edt|eau de toilette|extrait|cologne)\b', '', name)
    # Remove special characters
    name = re.sub(r'[^a-z0-9 ]', '', name)
    # Remove extra spaces
    name = ' '.join(name.split())
    return name

def get_all_product_urls():
    """Fetch all product URLs from the sitemap."""
    print("Fetching product URLs from sitemap...")
    sitemap_url = "https://perfun.pl/product-sitemap.xml"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(sitemap_url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'xml')
        urls = [loc.text for loc in soup.find_all('loc')]
        # Filter only product URLs
        product_urls = [u for u in urls if '/produkt/' in u]
        print(f"Found {len(product_urls)} actual product URLs in sitemap (out of {len(urls)} total entries).")
        return product_urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []

def scrape_wp_product(url):
    """Scrape full product details from WordPress URL."""
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
        
        # Image
        img_meta = soup.find('meta', property='og:image')
        data['image_url'] = img_meta['content'] if img_meta else "N/A"

        # Price
        price_container = soup.select_one('p.price')
        if price_container:
            amounts = price_container.find_all('span', class_='woocommerce-Price-amount')
            if amounts:
                prices = [re.sub(r'[^\d,]', '', a.get_text()) for a in amounts]
                data['price'] = float(prices[-1].replace(',', '.'))
            else:
                data['price'] = 0.0
        else:
            data['price'] = 0.0

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
        
        # Stock status
        data['stock'] = 1 if soup.find('p', class_='in-stock') else 0
        
        return data
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def get_embedding(text):
    """Generate embedding for text using OpenAI."""
    if not text or text == "Brak opisu":
        return None
    try:
        response = openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def integrate():
    print("Loading data...")
    # Load Fragrantica data
    with open(FRAGRANTICA_DATA_PATH, 'r', encoding='utf-8') as f:
        fragrantica_data = json.load(f)
    
    # Create matching map
    frag_map = {normalize_name(item['name']): item for item in fragrantica_data}
    
    # Fetch URLs from web
    urls = get_all_product_urls()
    
    processed_count = 0
    batch_size = 10
    records_to_upload = []
    
    for url in urls:
        print(f"Processing URL: {url}")
        
        # Scrape full data from web
        scraped = scrape_wp_product(url)
        if not scraped or scraped['name'] == "N/A":
            print(f"Skipping {url} due to scraping failure.")
            continue
            
        print(f"Scraped product: {scraped['name']}")
        
        # Match with Fragrantica
        norm_name = normalize_name(scraped['name'])
        frag_match = frag_map.get(norm_name)
        
        # Combine notes
        scent_notes = []
        if scraped.get('nuty_glowy') and scraped['nuty_glowy'] != "N/A":
            scent_notes.append(f"Głowa: {scraped['nuty_glowy']}")
        if scraped.get('nuty_serca') and scraped['nuty_serca'] != "N/A":
            scent_notes.append(f"Serce: {scraped['nuty_serca']}")
        if scraped.get('nuty_bazy') and scraped['nuty_bazy'] != "N/A":
            scent_notes.append(f"Baza: {scraped['nuty_bazy']}")
            
        if frag_match and frag_match.get('notes'):
            frag_notes_raw = frag_match['notes']
            if isinstance(frag_notes_raw, list):
                scent_notes.append(f"Fragrantica Notes: {', '.join(frag_notes_raw)}")
            elif isinstance(frag_notes_raw, dict):
                frag_notes = frag_notes_raw.get('notes', {})
                if isinstance(frag_notes, list):
                     scent_notes.append(f"Fragrantica Notes: {', '.join(frag_notes)}")
                elif isinstance(frag_notes, dict):
                    if frag_notes.get('top'):
                        scent_notes.append(f"Fragrantica Top: {', '.join(frag_notes['top'])}")
                    if frag_notes.get('middle'):
                        scent_notes.append(f"Fragrantica Middle: {', '.join(frag_notes['middle'])}")
                    if frag_notes.get('base'):
                        scent_notes.append(f"Fragrantica Base: {', '.join(frag_notes['base'])}")
        
        accords_str = ""
        if frag_match and frag_match.get('accords'):
            accords = []
            for acc in frag_match['accords']:
                for k, v in acc.items():
                    # Round for readability
                    accords.append(f"{k} ({round(v, 1)}%)")
            accords_str = "Akordy: " + ", ".join(accords)
            
        # Add stats from Fragrantica
        stats_list = []
        if frag_match:
            if frag_match.get('launch_year'):
                stats_list.append(f"Rok premiery: {frag_match['launch_year']}")
            if frag_match.get('stats'):
                s = frag_match['stats']
                if s.get('longevity'): stats_list.append(f"Trwałość: {s['longevity']}/5")
                if s.get('sillage'): stats_list.append(f"Projekcja: {s['sillage']}/5")
        
        stats_str = " | ".join(stats_list) if stats_list else ""
            
        # Add attributes to description
        attrs = []
        if scraped.get('capacity'): attrs.append(f"Pojemność: {scraped['capacity']}")
        if scraped.get('concentration'): attrs.append(f"Koncentracja: {scraped['concentration']}")
        if scraped.get('gender'): attrs.append(f"Płeć: {scraped['gender']}")
        
        attr_str = " | ".join(attrs) if attrs else ""
        
        # Prepare full description for embedding and database
        full_description = scraped.get('description', "Brak opisu")
        if attr_str:
            full_description += "\n\n" + attr_str
        if stats_str:
            full_description += "\n\n" + stats_str
        if accords_str:
            full_description += "\n\n" + accords_str
            
        # Get embedding
        embedding = get_embedding(full_description)
        
        record = {
            "wp_id": scraped['wp_id'],
            "name": scraped['name'],
            "brand": frag_match['brand'] if frag_match else scraped['name'].split()[0], # Fallback brand
            "price": scraped['price'],
            "stock": scraped['stock'],
            "description": full_description,
            "scent_notes_combined": " | ".join(scent_notes) if scent_notes else "Brak danych",
            "image_url": scraped['image_url'],
            "product_url": scraped['product_url'],
            "embedding": embedding
        }
        
        records_to_upload.append(record)
        processed_count += 1
        
        if len(records_to_upload) >= batch_size:
            print(f"Uploading batch of {len(records_to_upload)}...")
            try:
                # Use upsert to handle updates
                supabase.table('perfume_knowledge_base').upsert(records_to_upload, on_conflict='wp_id').execute()
                records_to_upload = []
            except Exception as e:
                print(f"Error uploading batch: {e}")
                
        # Small delay to be polite
        time.sleep(1)

    # Final batch
    if records_to_upload:
        print(f"Uploading final batch of {len(records_to_upload)}...")
        try:
            supabase.table('perfume_knowledge_base').upsert(records_to_upload, on_conflict='wp_id').execute()
        except Exception as e:
            print(f"Error uploading final batch: {e}")

    print(f"Finished processing {processed_count} products.")

if __name__ == "__main__":
    integrate()
