import streamlit as st
import pandas as pd
import openai
import json
import requests
import os
import base64

st.set_page_config(layout="wide")

# ↓ Styl pozadí, hlavičky a tabulek
st.markdown("""
    <style>
    .main { max-width: 80%; margin: auto; }
    h1 { font-size: 45px !important; margin-top: 0 !important; }
    table { background-color: #f5f5f5; }
    </style>
""", unsafe_allow_html=True)

# ↓ Funkce pro pozadí s průhledností
def set_background(image_path, opacity=0.2):
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode()
    st.markdown(
        f"""
        <style>
        body {{
            background: linear-gradient(rgba(255, 255, 255, {opacity}), rgba(255, 255, 255, {opacity})),
                        url("data:image/png;base64,{encoded}") no-repeat center center fixed;
            background-size: cover;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

set_background("grafika/pozadi_hlavni.PNG", opacity=0.2)

if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

st.title("Asistent cenových nabídek od Davida")

# ↓ Funkce pro Google Maps API

def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        'origins': origin,
        'destinations': destination,
        'key': api_key,
        'units': 'metric'
    }
    response = requests.get(url, params=params)
    st.session_state.debug_history += f"\n\ud83d\udcf1 Google API Request: {response.url}\n"
    data = response.json()
    st.session_state.debug_history += f"\n\ud83d\udcec Google API Response:\n{json.dumps(data, indent=2)}\n"
    try:
        return data['rows'][0]['elements'][0]['distance']['value'] / 1000
    except Exception as e:
        st.error(f"\u274c Chyba při získávání vzdálenosti: {e}")
        return None

# ↓ Načtení cenníků z adresáře "ceniky"
ceniky = {}
try:
    for filename in os.listdir("ceniky"):
        if filename.endswith(".csv"):
            produkt = os.path.splitext(filename)[0].strip()
            path = os.path.join("ceniky", filename)
            df = pd.read_csv(path, index_col=0, sep=";", encoding="utf-8", dtype=str)
            df = df.applymap(lambda x: float(str(x).replace('\xa0', '').replace(' ', '').replace(',', '.')) if x else float('nan'))
            df.columns = df.columns.astype(float)
            df.index = df.index.astype(float)
            ceniky[produkt.lower()] = df
            st.session_state.debug_history += f"\n✍️ Načten produkt: {produkt} ({df.shape[0]}x{df.shape[1]})\n"
except Exception as e:
    st.error(f"\u274c Chyba při načítání cenníků: {e}")
    st.stop()

sheet_names = list(ceniky.keys())

# ↓ Vstupní formulář
with st.form(key="vstupni_formular"):
    user_input = st.text_area("Zadejte popis produktů, rozměry a místo dodání:", height=100, placeholder="Např. ALUX Glass 6000x2500 Brno, screen 3500x2500...")
    submit_button = st.form_submit_button(label="\ud83d\udce4 ODESLAT")

if submit_button and user_input:
    debug_text = f"\n---\n\ud83d\udce5 Uživatelský vstup:\n{user_input}\n"
    with st.spinner("Analyzuji vstup pomocí GPT..."):
        try:
            client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            gpt_prompt = (
                f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání. "
                f"Název produktu vybírej co nejpřesněji z následujícího seznamu produktů: {', '.join(sheet_names)}. "
                f"POZOR: Pokud uživatel napíše 'screen', 'screenová roleta', 'boční screen' — vždy to přiřaď k produktu 'screen'. "
                f"Rozměry ve vzorcích (např. 3590-240) vždy spočítej. "
                f"Vrať POUZE validní JSON. Např. [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}]"
            )

            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": gpt_prompt},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=1000
            )

            gpt_output_raw = response.choices[0].message.content.strip()
            debug_text += f"\n\ud83d\udcec GPT odpověď (RAW):\n{gpt_output_raw}\n"
            start_idx = gpt_output_raw.find('[')
            end_idx = gpt_output_raw.rfind(']') + 1
            gpt_output_clean = gpt_output_raw[start_idx:end_idx]
            products = json.loads(gpt_output_clean)
            debug_text += f"\n\ud83d\udce6 GPT JSON:\n{json.dumps(products, indent=2)}\n"

            all_rows = []
            produkt_map = {
                "screen": "screen", "alux screen": "screen",
                "screenová roleta": "screen", "boční screen": "screen"
            }

            for params in products:
                produkt = params['produkt'].strip().lower()
                produkt_lookup = produkt_map.get(produkt, produkt)
                misto = params.get("misto", "")

                try:
                    sirka = int(float(params['šířka']))
                    vyska_hloubka = 2500 if params['hloubka_výška'] is None and produkt_lookup == "screen" else int(float(params['hloubka_výška']))
                except Exception as e:
                    st.error(f"\u274c Chybný rozměr: {e}")
                    debug_text += f"\n\u274c Rozměr chyba: {e}\n"
                    continue

                df = ceniky.get(produkt_lookup)
                if df is None:
                    st.error(f"\u274c Produkt '{produkt_lookup}' nebyl nalezen v cenníku.")
                    continue

                sloupce = sorted(df.columns)
                radky = sorted(df.index)
                sirka_real = next((s for s in sloupce if s >= sirka), sloupce[-1])
                vyska_real = next((v for v in radky if v >= vyska_hloubka), radky[-1])
                debug_text += f"\n\ud83d\udcca Tabulka {produkt_lookup}: použito {sirka_real} x {vyska_real}\n"

                try:
                    cena = df.loc[vyska_real, sirka_real]
                except:
                    st.error(f"\u274c Nepodařilo se získat cenu.")
                    continue

                all_rows.append({
                    "POLOŽKA": produkt_lookup,
                    "ROZMĚR": f"{sirka} x {vyska_hloubka} mm",
                    "CENA bez DPH": round(float(cena))
                })

                if "screen" not in produkt_lookup:
                    for perc in [12, 13, 14, 15]:
                        all_rows.append({
                            "POLOŽKA": f"Montáž {perc}%",
                            "ROZMĚR": "",
                            "CENA bez DPH": round(float(cena) * perc / 100)
                        })

                if misto and misto.lower() not in ["neuvedeno", "nedodáno"]:
                    distance_km = get_distance_km("Blučina, Czechia", misto, st.secrets["GOOGLE_API_KEY"])
                    if distance_km:
                        all_rows.append({
                            "POLOŽKA": "Doprava",
                            "ROZMĚR": f"{distance_km:.1f} km",
                            "CENA bez DPH": round(distance_km * 2 * 15)
                        })

            st.session_state.vysledky.insert(0, all_rows)
            debug_text += f"\n\ud83d\udcc6 Tabulka:\n{pd.DataFrame(all_rows).to_string(index=False)}\n"
            st.session_state.debug_history += debug_text

        except Exception as e:
            st.error(f"\u274c Chyba: {e}")
            st.session_state.debug_history += f"\n\u274c Chyba: {e}\n"

# ↓ Výpis výsledků
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# ↓ Debug panel
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 20%; overflow-y: scroll; "
    f"background-color: #f0f0f0; font-size: 10px; padding: 10px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)  
