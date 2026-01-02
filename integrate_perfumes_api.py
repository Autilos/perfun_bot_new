import os
import json
import re
import requests
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv
import time
from html import unescape

# Load environment variables
load_dotenv('/Users/wojciechnowak/.env')

# API Clients
openai_client = OpenAI(api_key=os.environ.get("OPEN_AI_API"))
supabase_url = os.environ.get("FIRMY_SUPABASE_URL")
supabase_key = os.environ.get("FIRMY_SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)

# WooCommerce Config
WC_CK = os.environ.get("PERFUN_CONSUMER_KEY")
WC_CS = os.environ.get("PERFUN_CONSUMER_SECRET")
WC_URL = os.environ.get("PERFUN_SITE_URL")

# Paths
FRAGRANTICA_DATA_PATH = "/Users/wojciechnowak/Documents/Clients/Perfun/Fragrantica - Adam/scraped_fragrantica_data.json"

def normalize_name(name):
    """Normalize perfume name for matching."""
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r'\b(perfume|eau de parfum|edp|edt|eau de toilette|extrait|cologne)\b', '', name)
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = ' '.join(name.split())
    return name

def clean_html(raw_html):
    """Remove HTML tags and unescape entities."""
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return unescape(cleantext).strip()

def get_embedding(text):
    """Generate embedding for text using OpenAI."""
    if not text or len(text) < 10:
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

def fetch_variations(product_id):
    """Fetch variations for a variable product to get accurate price/stock."""
    endpoint = f"{WC_URL}/wp-json/wc/v3/products/{product_id}/variations"
    try:
        response = requests.get(endpoint, auth=(WC_CK, WC_CS), params={"per_page": 100})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching variations for {product_id}: {e}")
        return []

def integrate():
    print("Loading data...")
    # Load Fragrantica data
    with open(FRAGRANTICA_DATA_PATH, 'r', encoding='utf-8') as f:
        fragrantica_data = json.load(f)
    
    # Create matching map
    frag_map = {normalize_name(item['name']): item for item in fragrantica_data}
    
    page = 1
    processed_count = 0
    batch_size = 10
    records_to_upload = []
    
    print("Starting WooCommerce API integration...")
    
    while True:
        print(f"Fetching page {page} from WooCommerce...")
        endpoint = f"{WC_URL}/wp-json/wc/v3/products"
        try:
            response = requests.get(endpoint, auth=(WC_CK, WC_CS), params={"per_page": 50, "page": page})
            response.raise_for_status()
            products = response.json()
            if not products:
                break
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
            
        for p in products:
            p_id = p['id']
            name = p['name']
            print(f"Processing: {name} (ID: {p_id})")
            
            # 1. Price and Stock
            price = float(p['price']) if p['price'] else 0.0
            stock_status = 1 if p['stock_status'] == 'instock' else 0
            
            # Handle variations for more detail
            variations_info = []
            if p['type'] == 'variable':
                vars = fetch_variations(p_id)
                for v in vars:
                    v_stock = "Na stanie" if v['stock_status'] == 'instock' else "Brak"
                    v_attr = ", ".join([f"{a['name']}: {a['option']}" for a in v['attributes']])
                    variations_info.append(f"{v_attr} - {v['price']} PLN ({v_stock})")
                    # Update price to minimum if currently 0
                    if price == 0 and v['price']:
                        price = float(v['price'])
                
            # 2. Attributes
            attrs = {}
            for attr in p['attributes']:
                attrs[attr['name']] = ", ".join(attr['options'])
            
            # 3. Clean Description
            description = clean_html(p['description']) or clean_html(p['short_description']) or "Brak opisu"
            
            # 4. Match with Fragrantica
            norm_name = normalize_name(name)
            frag_match = frag_map.get(norm_name)
            
            # Combine Scent Notes
            scent_notes = []
            # We don't have separate notes in Woo API unless they are in attributes
            # Some sites put notes in attributes. Let's check for 'Nuty'
            for attr_name, attr_val in attrs.items():
                if 'nuty' in attr_name.lower() or 'otwarcie' in attr_name.lower():
                    scent_notes.append(f"{attr_name}: {attr_val}")
            
            # From Fragrantica
            if frag_match and frag_match.get('notes'):
                raw_notes = frag_match['notes']
                if isinstance(raw_notes, list):
                    scent_notes.append(f"Fragrantica: {', '.join(raw_notes)}")
                elif isinstance(raw_notes, dict):
                    fn = raw_notes.get('notes', {})
                    if isinstance(fn, dict):
                        if fn.get('top'): scent_notes.append(f"Góra: {', '.join(fn['top'])}")
                        if fn.get('middle'): scent_notes.append(f"Serce: {', '.join(fn['middle'])}")
                        if fn.get('base'): scent_notes.append(f"Baza: {', '.join(fn['base'])}")
                    elif isinstance(fn, list):
                        scent_notes.append(f"Fragrantica: {', '.join(fn)}")

            # Accords
            accords_str = ""
            if frag_match and frag_match.get('accords'):
                acc = [f"{list(a.keys())[0]} ({round(list(a.values())[0], 1)}%)" for a in frag_match['accords']]
                accords_str = "Akordy: " + ", ".join(acc)

            # 5. Build full description for embedding
            meta_parts = []
            if attrs.get('Koncentracja'): meta_parts.append(f"Koncentracja: {attrs['Koncentracja']}")
            if attrs.get('Płeć'): meta_parts.append(f"Płeć: {attrs['Płeć']}")
            if variations_info: meta_parts.append("Dostępne warianty: " + " | ".join(variations_info))
            
            stats_list = []
            if frag_match:
                if frag_match.get('launch_year'): stats_list.append(f"Rok premiery: {frag_match['launch_year']}")
                if frag_match.get('stats'):
                    s = frag_match['stats']
                    if s.get('longevity'): stats_list.append(f"Trwałość: {s['longevity']}/5")
                    if s.get('sillage'): stats_list.append(f"Projekcja: {s['sillage']}/5")

            full_desc_for_db = description
            if meta_parts: full_desc_for_db += "\n\n" + " | ".join(meta_parts)
            if stats_list: full_desc_for_db += "\n\n" + " | ".join(stats_list)
            if accords_str: full_desc_for_db += "\n\n" + accords_str
            
            # 6. Get Embedding
            embedding = get_embedding(full_desc_for_db)
            
            record = {
                "wp_id": p_id,
                "name": name,
                "brand": frag_match['brand'] if frag_match else name.split()[0],
                "price": price,
                "stock": stock_status,
                "description": full_desc_for_db,
                "scent_notes_combined": " | ".join(scent_notes) if scent_notes else "Brak danych",
                "image_url": p['images'][0]['src'] if p['images'] else "N/A",
                "product_url": p['permalink'],
                "embedding": embedding
            }
            
            records_to_upload.append(record)
            processed_count += 1
            
            if len(records_to_upload) >= batch_size:
                print(f"Uploading batch of {len(records_to_upload)} to Supabase...")
                try:
                    supabase.table('perfume_knowledge_base').upsert(records_to_upload, on_conflict='wp_id').execute()
                    records_to_upload = []
                except Exception as e:
                    print(f"Error uploading batch: {e}")
            
            # Polite delay
            time.sleep(0.5)
            
        page += 1
        # Optional: total limit for safety during testing
        # if processed_count > 20: break

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
