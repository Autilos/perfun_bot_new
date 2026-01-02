import os
from supabase import create_client
from dotenv import load_dotenv

# Load .env from home directory
load_dotenv('/Users/wojciechnowak/.env')

url = os.environ.get("FIRMY_SUPABASE_URL")
key = os.environ.get("FIRMY_SUPABASE_KEY")

supabase = create_client(url, key)

# Try to list tables (usually by querying public.tables or similar if accessible, 
# or just trying to query a common name like 'perfumes')
try:
    response = supabase.table('perfumes').select("*", count='exact').limit(1).execute()
    print("Table 'perfumes' exists.")
    print(f"Sample data: {response.data}")
except Exception as e:
    print(f"Error checking 'perfumes' table: {e}")

try:
    # Get all table names if possible
    res = supabase.rpc('get_tables', {}).execute()
    print(f"All tables: {res.data}")
except Exception as e:
    print(f"Error calling get_tables RPC: {e}")
