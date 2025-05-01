import pandas as pd
import openai
import json
import requests

def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        'origins': origin,
        'destinations': destination,
        'key': api_key,
        'units': 'metric'
    }
    response = requests.get(url, params=params)
    data = response.json()
    try:
        distance_meters = data['rows'][0]['elements'][0]['distance']['value']
        return distance_meters / 1000
    except Exception:
        return None

def get_product_data(user_input, sheet_names, api_key):
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": (
                f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou/výškou (v mm) a místem dodání. "
                f"Název produktu vybírej co nejpřesněji z tohoto seznamu: {', '.join(sheet_names)}. "
                f"Pokud zadá uživatel 'screen', 'screenová roleta' apod., přiřaď to k 'screen'. "
                f"Pokud zadá vzorec (např. 3590-240), vypočítej výsledek a použij. "
                f"Pokud nic nenajdeš, vrať položku 'nenalezeno': true a zprávu pro uživatele."
            )},
            {"role": "user", "content": user_input}
        ],
        max_tokens=1000
    )
    content = response.choices[0].message.content.strip()
    start_idx = content.find('[')
    end_idx = content.rfind(']') + 1
    return json.loads(content[start_idx:end_idx])

def calculate_prices(cenik_path, sheet_n_
