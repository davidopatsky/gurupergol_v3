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
                f"Tvůj úkol: z následujícího textu vytáhni produkty s názvem, šířkou, výškou/hloubkou a místem dodání. "
                f"Vyber z: {', '.join(sheet_names)}. Pokud je 'screen', přiřaď k produktu 'screen'. "
                f"Pokud je rozměr ve formátu vzorce (např. 3590-240), spočítej výsledek. "
                f"Pokud nic nenajdeš, vrať {{'nenalezeno': true, 'zprava': 'produkt nenalezen'}}."
            )},
            {"role": "user", "content": user_input}
        ],
        max_tokens=1000
    )
    content = response.choices[0].message.content.strip()
    start_idx = content.find('[')
    end_idx = content.rfind(']') + 1
    return json.loads(content[start_idx:end_idx])

def calculate_prices(cenik_path, sheet_names, products, google_api_key):
    all_rows = []
    excel_file = pd.ExcelFile(cenik_path)
    produkt_map = {
        "alux screen": "screen", "alux screen 1": "screen", "screen": "screen",
        "screenova roleta": "screen", "screenová roleta": "screen",
        "boční screenová roleta": "screen", "boční screen": "screen"
    }

    for params in products:
        produkt = produkt_map.get(params['produkt'].strip().lower(), params['produkt'].strip().lower())
        misto = params['misto']
        sirka = int(float(params['šířka']))
        vyska_hloubka = int(float(params['hloubka_výška'])) if params['hloubka_výška'] else (2500 if 'screen' in produkt else None)

        sheet_match = next((s for s in sheet_names if s.lower() == produkt), None)
        if not sheet_match:
            sheet_match = next((s for s in sheet_names if produkt in s.lower()), None)
        if not sheet_match:
            continue

        df = pd.read_excel(cenik_path, sheet_name=sheet_match, index_col=0)
        sloupce = sorted([int(float(c)) for c in df.columns if str(c).isdigit()])
        radky = sorted([int(float(r)) for r in df.index if str(r).isdigit()])
        sirka_real = next((s for s in sloupce if s >= sirka), sloupce[-1])
        vyska_real = next((v for v in radky if v >= vyska_hloubka), radky[-1])
        cena = df.loc[vyska_real, sirka_real]

        all_rows.append({
            "POLOŽKA": produkt,
            "ROZMĚR": f"{sirka} × {vyska_hloubka} mm",
            "CENA bez DPH": round(cena)
        })

        if "screen" not in produkt:
            for perc in [12, 13, 14, 15]:
                all_rows.append({
                    "POLOŽKA": f"Montáž {perc}%",
                    "ROZMĚR": "",
                    "CENA bez DPH": round(cena * perc / 100)
                })

        if misto:
            distance_km = get_distance_km("Blučina, Czechia", misto, google_api_key)
            if distance_km:
                doprava_cena = distance_km * 2 * 15
                all_rows.append({
                    "POLOŽKA": "Doprava",
                    "ROZMĚR": f"{distance_km:.1f} km",
                    "CENA bez DPH": round(doprava_cena)
                })

    return all_rows
