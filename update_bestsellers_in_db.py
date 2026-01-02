import os
import requests
from datetime import datetime, timedelta
from collections import Counter
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('/Users/wojciechnowak/.env')

def update_bestsellers_in_db():
    # Credentials
    CK = os.environ.get('PERFUN_CONSUMER_KEY')
    CS = os.environ.get('PERFUN_CONSUMER_SECRET')
    URL = os.environ.get('PERFUN_SITE_URL')
    SUPABASE_URL = os.environ.get('FIRMY_SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('FIRMY_SUPABASE_KEY')
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Fetching last 100 orders to find bestsellers...")
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    endpoint = f"{URL}/wp-json/wc/v3/orders"
    params = {"after": thirty_days_ago, "per_page": 100, "status": "processing,completed"}
    
    try:
        response = requests.get(endpoint, auth=(CK, CS), params=params)
        orders = response.json()
        
        product_counts = Counter()
        for order in orders:
            for item in order.get('line_items', []):
                p_id = item.get('product_id')
                qty = item.get('quantity')
                # Skip the "Gratis" sample (ID: 15916)
                if p_id != 15916:
                    product_counts[p_id] += qty
        
        # Get Top 10 real products
        top_ids = [p_id for p_id, _ in product_counts.most_common(10)]
        print(f"Top Product IDs: {top_ids}")
        
        # Now update Supabase
        # 1. Clear bestseller tag from ALL products first (optional but safer)
        # However, it's better to just update the specific ones if we don't have many.
        # Let's just find the products in Supabase.
        
        for p_id in top_ids:
            # Find the product
            res = supabase.table('perfume_knowledge_base').select('id, name, description').eq('wp_id', p_id).execute()
            if res.data:
                record = res.data[0]
                desc = record['description']
                if "[BESTSELLER]" not in desc:
                    new_desc = desc + "\n\n[BESTSELLER]"
                    print(f"Tagging {record['name']} as Bestseller...")
                    supabase.table('perfume_knowledge_base').update({"description": new_desc}).eq('id', record['id']).execute()
                else:
                    print(f"{record['name']} is already tagged.")
            else:
                print(f"Product ID {p_id} not found in Supabase.")
                
        print("Bestsellers updated successfully in Supabase.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_bestsellers_in_db()
