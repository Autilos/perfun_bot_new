import os
import requests
from dotenv import load_dotenv

# Load for local testing
load_dotenv('/Users/wojciechnowak/.env')

def check_order_status(email):
    # Support both spellings just in case
    api_key = os.environ.get("SELLLASIST_API_KEY") or os.environ.get("SELLASIST_API_KEY")
    site_url = "https://perfun.sellasist.pl/api/v1"
    
    if not api_key:
        return "Błąd: Brak klucza API Sellasist w konfiguracji (SELLASIST_API_KEY)."
        
    headers = {
        "apikey": api_key,
        "Accept": "application/json"
    }
    
    # 1. Search for order by email
    endpoint = f"{site_url}/orders"
    params = {
        "email": email,
        "limit": 1,
        "sort": "date",
        "order": "desc"
    }
    
    try:
        response = requests.get(endpoint, headers=headers, params=params)
        
        # Sellasist returns 404 if no records match the filter
        if response.status_code == 404:
            return f"Nie znaleziono zamówień przypisanych do adresu: {email}"
            
        response.raise_for_status()
        data = response.json()
        
        if not data or len(data) == 0:
            return f"Nie znaleziono zamówień przypisanych do adresu: {email}"
            
        order = data[0]
        order_id = order.get('id')
        status_name = order.get('status', {}).get('name', 'Brak danych')
        date = order.get('date', 'Brak danych')
        total = order.get('total', '0.00')
        currency = order.get('payment', {}).get('currency', 'PLN')
        
        # 2. Get details for tracking info if possible
        tracking_info = ""
        try:
            detail_response = requests.get(f"{endpoint}/{order_id}", headers=headers)
            if detail_response.status_code == 200:
                detail_data = detail_response.json()
                shipments = detail_data.get('shipments', [])
                if shipments:
                    trackings = []
                    for s in shipments:
                        num = s.get('tracking_number')
                        courier = s.get('courier_name') or s.get('service') or "Kurier"
                        if num:
                            trackings.append(f"{courier}: {num}")
                    if trackings:
                        tracking_info = "\n\nWysłano przesyłkę:\n- " + "\n- ".join(trackings)
        except Exception:
            pass # Tracking is optional, don't break if fail
            
        result = (
            f"💰 Znaleziono Twoje ostatnie zamówienie nr #{order_id}:\n"
            f"📅 Data: {date}\n"
            f"📦 Status: **{status_name}**\n"
            f"💵 Kwota: {total} {currency}"
            f"{tracking_info}"
        )
        return result
        
    except Exception as e:
        return f"Błąd podczas sprawdzania statusu: {str(e)}"

if __name__ == "__main__":
    import sys
    email_to_check = sys.argv[1] if len(sys.argv) > 1 else "marcin.matuszewski@poczta.onet.pl"
    print(check_order_status(email_to_check))
