import streamlit as st
import pandas as pd
import openai
import json
import requests
import os

# ---- VZHLED A POZADÍ ----
def set_background(image_path: str, opacity: float = 0.2):
    import base64
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background: url("data:image/png;base64,{encoded_string}") no-repeat center center fixed;
            background-size: cover;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(255,255,255,{1 - opacity});
            z-index: -1;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

set_background("grafika/pozadi_hlavni.PNG", opacity=0.2)

st.markdown("""
    <style>
    .main { max-width: 80%; margin: auto; }
    h1 { font-size: 45px !important; margin-top: 0 !important; }

    .stTextArea textarea {
        background-color: #ffffffcc !important;
        color: #000 !important;
    }

    .stButton button {
        background-color: #ffffffcc !important;
        color: #000 !important;
    }

    .stDataFrame, .css-1d391kg {
        background-color: #f0f0f0cc !important;
        color: #000;
    }
    </style>
""", unsafe_allow_html=True)

# ---- NASTAVENÍ ----
st.set_page_config(layout="wide")
st.title("Asistent cenových nabídek od Davida")

if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

# ---- FUNKCE: VZDÁLENOST ----
def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        'origins': origin,
        'destinations': destination,
        'key': api_key,
        'units': 'metric'
    }
    response = requests.get(url, params=params)
    st.session_state.debug_history += f"\n📡 Google API Request: {response.url}\n"
    data = response.json()
    st.session_state.debug_history += f"\n📬 Google API Response:\n{json.dumps(data, indent=2)}\n"
    try:
        return data['rows'][0]['elements'][0]['distance']['value'] / 1000
    except Exception as e:
        st.error(f"❌ Chyba při získávání vzdálenosti: {e}")
        return None

# ---- NAČTENÍ CENÍKŮ ----
cenik_dir = "ceniky"
ceniky = {}
sheet_names = []

try:
    for fname in os.listdir(cenik_dir):
        if fname.lower().endswith(".xls"):
            path = os.path.join(cenik_dir, fname)
            produkt = os.path.splitext(fname)[0]
            df = pd.read_excel(path, index_col=0, engine="xlrd")
            df.columns = [float(c) for c in df.columns]
            df.index = [float(i) for i in df.index]
            ceniky[produkt.lower()] = df
            sheet_names.append(produkt)
    st.session_state.sheet_names = sheet_names
    st.session_state.debug_history += f"\n📁 Načtené ceníky: {list(ceniky.keys())}\n"
except Exception as e:
    st.error(f"❌ Chyba při načítání ceníků: {e}")
    st.stop()

# ---- FORMULÁŘ ----
with st.form(key="vstupni_formular"):
    user_input = st.text_area(
        "Zadejte popis produktů, rozměry a místo dodání:",
        height=100,
        placeholder="Např. ALUX Glass 6000x2500 Brno, screen 3500x2500..."
    )
    submit_button = st.form_submit_button(label="📤 ODESLAT")

# ---- ZPRACOVÁNÍ ----
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
                f"Vrať POUZE validní JSON. Např. [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}] nebo [{{\"nenalezeno\": true, \"zprava\": \"...\"}}]."
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
            products = json.loads(gpt_output_clean)
            debug_text += f"\n📤 GPT parsed výstup:\n{json.dumps(products, indent=2)}\n"

            all_rows = []
            produkt_map = {
                "screen": "screen", "alux screen": "screen",
                "screenová roleta": "screen", "boční screen": "screen"
            }

            if products and 'nenalezeno' in products[0]:
                st.warning(products[0].get('zprava', 'Produkt nenalezen.'))
            else:
                for params in products:
                    produkt = params['produkt'].strip().lower()
                    produkt_lookup = produkt_map.get(produkt, produkt)
                    misto = params.get("misto", "")
                    try:
                        sirka = int(float(params['šířka']))
                        vyska = 2500 if params['hloubka_výška'] is None and "screen" in produkt_lookup else int(float(params['hloubka_výška']))
                    except Exception as e:
                        st.error(f"❌ Chybný rozměr: {e}")
                        continue

                    debug_text += f"\n🔍 Produkt: {produkt_lookup}, {sirka}×{vyska}, místo: {misto}\n"

                    if produkt_lookup not in ceniky:
                        st.error(f"❌ Nenalezen ceník: {produkt_lookup}")
                        continue

                    df = ceniky[produkt_lookup]
                    sirka_real = next((s for s in df.columns if s >= sirka), df.columns[-1])
                    vyska_real = next((v for v in df.index if v >= vyska), df.index[-1])
                    cena = df.loc[vyska_real, sirka_real]
                    debug_text += f"\n📐 Matice {sirka_real}x{vyska_real}, cena: {cena}\n"

                    all_rows.append({
                        "POLOŽKA": produkt_lookup,
                        "ROZMĚR": f"{sirka} × {vyska} mm",
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
                        dist_km = get_distance_km("Blučina, Czechia", misto, api_key)
                        if dist_km:
                            cena_doprava = round(dist_km * 2 * 15)
                            all_rows.append({
                                "POLOŽKA": "Doprava",
                                "ROZMĚR": f"{dist_km:.1f} km",
                                "CENA bez DPH": cena_doprava
                            })

            st.session_state.vysledky.insert(0, all_rows)
            debug_text += f"\n📦 Výsledná tabulka:\n{pd.DataFrame(all_rows).to_string(index=False)}\n"
            st.session_state.debug_history += debug_text

        except Exception as e:
            st.error(f"❌ Chyba: {e}")
            st.session_state.debug_history += f"\n⛔ Chyba: {e}\n"

# ---- VÝSLEDKY ----
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# ---- DEBUG PANEL ----
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 20%; overflow-y: scroll; "
    f"background-color: #f0f0f0; font-size: 10px; padding: 10px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
