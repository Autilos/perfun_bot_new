import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('/Users/wojciechnowak/.env')

url = os.environ.get("FIRMY_SUPABASE_URL")
key = os.environ.get("FIRMY_SUPABASE_KEY")

supabase = create_client(url, key)

try:
    response = supabase.table('perfume_knowledge_base').select("*").limit(1).order('last_updated', desc=True).execute()
    for row in response.data:
        print(f"ID: {row['id']} | Name: {row['name']}")
        print(f"Description:\n{row['description']}")
        print(f"Scent Notes: {row['scent_notes_combined']}")
        print("-" * 50)
except Exception as e:
    print(f"Error: {e}")
