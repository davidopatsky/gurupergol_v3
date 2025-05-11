# Kompletní aplikace s rozšířeným debugem

import streamlit as st
import pandas as pd
import openai
import json
import numpy as np
import requests

# === Nastavení stránky ===
st.set_page_config(layout="wide")

# === Styl ===
st.markdown(
    """
    <style>
    .main { max-width: 80%; margin: auto; }
    </style>
    """,
    unsafe_allow_html=True
)

# === Inicializace session ===
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

st.title("Asistent cenových nabídek od Davida")

# === Funkce na výpočet vzdálenosti ===
def get_distance_km(origin, destination, api_key):
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        'origins': origin,
        'destinations': destination,
        'key': api_key,
        'units': 'metric'
    }
    response = requests.get(url, params=params)
    data = response.json()
    st.session_state.debug_history += f"📡 Volání Google API: {response.url}\n"
    st.session_state.debug_history += f"📨 Odpověď Google API: {json.dumps(data)}\n"
    try:
        distance_meters = data['rows'][0]['elements'][0]['distance']['value']
        return distance_meters / 1000
    except Exception as e:
        st.error(f"❌ Chyba při načítání vzdálenosti: {e}")
        return None

# === Načtení seznamu záložek ===
cenik_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
try:
    excel_file = pd.ExcelFile(cenik_path)
    sheet_names = excel_file.sheet_names
    st.session_state.sheet_names = sheet_names
    seznam_zalozek = ", ".join(sheet_names)
    st.session_state.debug_history += f"Načtené záložky: {sheet_names}\n"
except Exception as e:
    st.error(f"❌ Nepodařilo se načíst seznam produktů: {e}")
    st.stop()

# === Vstup ===
user_input = st.text_input("Zadejte popis produktů, rozměry a místo dodání (potvrďte Enter):")

if user_input:
    debug_text = f"\n---\n📥 Vstup uživatele: {user_input}\n"
    with st.spinner("Analyzuji vstup přes ChatGPT..."):
        try:
            client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            debug_text += "📡 Odesílám požadavek na GPT..."
"
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": (
                        f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty... Seznam: {seznam_zalozek}."
                    )},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=1000
            )
            gpt_output_raw = response.choices[0].message.content.strip()
            debug_text += f"📨 Odpověď GPT:
{gpt_output_raw}\n"
            start_idx = gpt_output_raw.find('[')
            end_idx = gpt_output_raw.rfind(']') + 1
            gpt_output_clean = gpt_output_raw[start_idx:end_idx]
            debug_text += f"📦 Parsovaný JSON blok:
{gpt_output_clean}\n"
            products = json.loads(gpt_output_clean)
            all_rows = []
            if products and 'nenalezeno' in products[0]:
                zprava = products[0].get('zprava', 'Produkt nenalezen.')
                st.warning(f"❗ {zprava}")
                debug_text += f"⚠ {zprava}\n"
                st.session_state.debug_history += debug_text
            else:
                produkt_map = {
                    "alux screen": "screen",
                    "alux screen 1": "screen",
                    "screen": "screen",
                    "screenova roleta": "screen",
                    "screenová roleta": "screen",
                    "boční screenová roleta": "screen",
                    "boční screen": "screen"
                }
                for params in products:
                    produkt = params['produkt'].strip().lower()
                    produkt_lookup = produkt_map.get(produkt, produkt)
                    misto = params['misto']
                    sirka = int(float(params['šířka']))
                    vyska = int(float(params['hloubka_výška'])) if params['hloubka_výška'] is not None else (2500 if "screen" in produkt_lookup else None)
                    debug_text += f"\n📦 Produkt: {produkt_lookup}\nZadání: šířka {sirka}, výška {vyska}, místo: {misto}\n"
                    sheet_match = next((s for s in sheet_names if s.lower() == produkt_lookup), None)
                    if sheet_match is None:
                        sheet_match = next((s for s in sheet_names if produkt_lookup in s.lower()), None)
                    debug_text += f"🔍 Nalezená záložka: {sheet_match}\n"
                    if sheet_match is None:
                        st.error(f"❌ Nenalezena záložka '{produkt_lookup}' v Excelu.")
                        debug_text += f"❌ Nenalezena záložka '{produkt_lookup}'\n"
                        continue
                    df = pd.read_excel(cenik_path, sheet_name=sheet_match, index_col=0)
                    sloupce = sorted([int(float(c)) for c in df.columns if str(c).isdigit()])
                    radky = sorted([int(float(r)) for r in df.index if str(r).isdigit()])
                    debug_text += f"📊 Šířky: {sloupce}\n📊 Výšky: {radky}\n"
                    sirka_real = next((s for s in sloupce if s >= sirka), sloupce[-1])
                    vyska_real = next((v for v in radky if v >= vyska), radky[-1])
                    debug_text += f"➡ Vybrané rozměry: {sirka_real} x {vyska_real}\n"
                    try:
                        cena = df.loc[vyska_real, sirka_real]
                        debug_text += f"💰 Cena nalezena: {cena}\n"
                    except Exception as e:
                        debug_text += f"❌ Chyba při získání ceny: {e}\n"
                        continue
                    all_rows.append({
                        "POLOŽKA": produkt_lookup,
                        "ROZMĚR": f"{sirka} × {vyska} mm",
                        "CENA bez DPH": round(cena)
                    })
                    if "screen" not in produkt_lookup:
                        for perc in [12, 13, 14, 15]:
                            montaz = round(cena * perc / 100)
                            all_rows.append({
                                "POLOŽKA": f"Montáž {perc}%",
                                "ROZMĚR": "",
                                "CENA bez DPH": montaz
                            })
                            debug_text += f"🔧 Montáž {perc}% = {montaz} Kč\n"
                    if misto:
                        api_key = st.secrets["GOOGLE_API_KEY"]
                        distance_km = get_distance_km("Blučina, Czechia", misto, api_key)
                        if distance_km:
                            doprava_cena = distance_km * 2 * 15
                            all_rows.append({
                                "POLOŽKA": "Doprava",
                                "ROZMĚR": f"{distance_km:.1f} km",
                                "CENA bez DPH": round(doprava_cena)
                            })
                            debug_text += f"🚚 Vzdálenost: {distance_km:.1f} km, Cena dopravy: {round(doprava_cena)} Kč\n"
                st.session_state.vysledky.insert(0, all_rows)
                st.session_state.debug_history += debug_text
        except json.JSONDecodeError as e:
            st.error(f"❌ Chyba při zpracování JSON: {e}")
            st.session_state.debug_history += f"JSONDecodeError: {e}\n"
        except Exception as e:
            st.error(f"❌ Došlo k chybě: {e}")
            st.session_state.debug_history += f"Exception: {e}\n"

# === Výsledky ===
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# === Debug panel ===
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 40%; overflow-y: scroll; background-color: #f0f0f0; font-size: 10px; padding: 5px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
