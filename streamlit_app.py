import streamlit as st
import pandas as pd
import openai
import json
import requests
import os
from io import BytesIO
import base64

st.set_page_config(layout="wide")

# Styl
st.markdown("""
    <style>
    .main { max-width: 80%; margin: auto; }
    h1 { font-size: 45px !important; margin-top: 0 !important; }
    .stTable { background-color: #f9f9f9 !important; }
    </style>
""", unsafe_allow_html=True)

# Pozadí s průhledností
def set_background(image_path, opacity=0.2):
    with open(image_path, "rb") as img_file:
        encoded = base64.b64encode(img_file.read()).decode()
    st.markdown(f"""
        <style>
        body {{
            background-image: url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-repeat: no-repeat;
            background-attachment: fixed;
            opacity: {opacity};
        }}
        </style>
    """, unsafe_allow_html=True)

# Nastavení průhledného pozadí
set_background("grafika/pozadi_hlavni.PNG", opacity=0.2)

# Inicializace session
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

st.title("Asistent cenových nabídek od Davida")

# Načtení XLS ceníků
ceniky = {}
sheet_names = []

try:
    for file in os.listdir("ceniky"):
        if file.endswith(".xls"):
            path = os.path.join("ceniky", file)
            xls = pd.ExcelFile(path)
            for sheet in xls.sheet_names:
                df = xls.parse(sheet, index_col=0)
                df.columns = df.columns.map(lambda x: int(str(x).strip()) if str(x).strip().isdigit() else x)
                df.index = df.index.map(lambda x: int(str(x).strip()) if str(x).strip().isdigit() else x)
                ceniky[sheet.lower()] = df
                sheet_names.append(sheet)
    st.session_state.debug_history += f"\n📄 Načtené záložky: {list(ceniky.keys())}\n"
except Exception as e:
    st.error(f"❌ Chyba při načítání ceníků: {e}")
    st.stop()

# Vstup od uživatele
with st.form(key="vstupni_formular"):
    user_input = st.text_area("Zadejte popis produktů, rozměry a místo dodání:", height=100,
                              placeholder="Např. ALUX Glass 6000x2500 Brno, screen 3500x2500...")
    submit_button = st.form_submit_button(label="📤 ODESLAT")

# Google Distance
def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {'origins': origin, 'destinations': destination, 'key': api_key, 'units': 'metric'}
    response = requests.get(url, params=params)
    st.session_state.debug_history += f"\n📡 Google API Request: {response.url}\n"
    data = response.json()
    st.session_state.debug_history += f"\n📬 Google API Response:\n{json.dumps(data, indent=2)}\n"
    try:
        return data['rows'][0]['elements'][0]['distance']['value'] / 1000
    except:
        return None

if submit_button and user_input:
    debug_text = f"\n---\n📥 Uživatelský vstup:\n{user_input}\n"

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
            debug_text += f"\n📨 GPT prompt:\n{gpt_prompt}\n"

            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": gpt_prompt},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=1000
            )

            gpt_output_raw = response.choices[0].message.content.strip()
            debug_text += f"\n📬 GPT odpověď (RAW):\n{gpt_output_raw}\n"

            start_idx = gpt_output_raw.find('[')
            end_idx = gpt_output_raw.rfind(']') + 1
            gpt_output_clean = gpt_output_raw[start_idx:end_idx]
            debug_text += f"\n📦 GPT JSON blok:\n{gpt_output_clean}\n"

            products = json.loads(gpt_output_clean)
            debug_text += f"\n📤 GPT parsed výstup:\n{json.dumps(products, indent=2)}\n"

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
                    vyska_hloubka = (
                        2500 if params['hloubka_výška'] is None and "screen" in produkt_lookup
                        else int(float(params['hloubka_výška']))
                    )
                except Exception as e:
                    st.error(f"❌ Chybný rozměr: {e}")
                    debug_text += f"\n❌ Chybný rozměr: {e}\n"
                    continue

                debug_text += f"\n🔍 Produkt: {produkt_lookup}, rozměr: {sirka}×{vyska_hloubka}, místo: {misto}\n"

                if produkt_lookup not in ceniky:
                    st.error(f"❌ Nenalezen produkt/záložka: {produkt_lookup}")
                    continue

                df = ceniky[produkt_lookup]
                sloupce = sorted([int(c) for c in df.columns if isinstance(c, int)])
                radky = sorted([int(r) for r in df.index if isinstance(r, int)])

                sirka_real = next((s for s in sloupce if s >= sirka), sloupce[-1])
                vyska_real = next((v for v in radky if v >= vyska_hloubka), radky[-1])
                debug_text += f"\n📐 Vybraná velikost v matici: {sirka_real}×{vyska_real}\n"

                try:
                    cena = df.loc[vyska_real, sirka_real]
                    debug_text += f"\n💰 Cena nalezena: {cena} Kč\n"
                except Exception as e:
                    st.error(f"❌ Cena nenalezena: {e}")
                    debug_text += f"\n❌ Chyba při čtení ceny: {e}\n"
                    continue

                all_rows.append({
                    "POLOŽKA": produkt_lookup,
                    "ROZMĚR": f"{sirka} × {vyska_hloubka} mm",
                    "CENA bez DPH": round(float(cena))
                })

                if "screen" not in produkt_lookup:
                    for perc in [12, 13, 14, 15]:
                        cena_montaz = round(float(cena) * perc / 100)
                        all_rows.append({
                            "POLOŽKA": f"Montáž {perc}%",
                            "ROZMĚR": "",
                            "CENA bez DPH": cena_montaz
                        })

                if misto and misto.lower() not in ["neuvedeno", "nedodáno"]:
                    api_key = st.secrets["GOOGLE_API_KEY"]
                    distance_km = get_distance_km("Blučina, Czechia", misto, api_key)
                    if distance_km:
                        cena_doprava = round(distance_km * 2 * 15)
                        all_rows.append({
                            "POLOŽKA": "Doprava",
                            "ROZMĚR": f"{distance_km:.1f} km",
                            "CENA bez DPH": cena_doprava
                        })

            st.session_state.vysledky.insert(0, all_rows)
            debug_text += f"\n📦 Výsledná tabulka:\n{pd.DataFrame(all_rows).to_string(index=False)}\n"
            st.session_state.debug_history += debug_text

        except Exception as e:
            st.error(f"❌ Výjimka: {e}")
            st.session_state.debug_history += f"\n⛔ Výjimka: {e}\n"

# Výpis výsledků
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.dataframe(pd.DataFrame(vysledek), use_container_width=True)

# Debug panel (20 % výšky)
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 20%; overflow-y: scroll; "
    f"background-color: #f0f0f0; font-size: 10px; padding: 10px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
