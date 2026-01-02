import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('/Users/wojciechnowak/.env')

url = os.environ.get("FIRMY_SUPABASE_URL")
key = os.environ.get("FIRMY_SUPABASE_KEY")

supabase = create_client(url, key)

try:
    response = supabase.table('perfume_knowledge_base').select("id", count='exact').execute()
    print(f"Total products in 'perfume_knowledge_base': {response.count}")
except Exception as e:
    print(f"Error: {e}")
