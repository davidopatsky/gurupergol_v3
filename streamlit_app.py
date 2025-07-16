import streamlit as st
import pandas as pd
import openai
import json
import requests
import base64
import os

st.set_page_config(layout="wide")

# === Funkce pro nastavení pozadí ===
def set_background(image_path, opacity=0.2):
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            st.markdown(f"""
                <style>
                    .stApp {{
                        background: url("data:image/png;base64,{encoded_string}");
                        background-size: cover;
                        background-repeat: no-repeat;
                        background-attachment: fixed;
                        opacity: 1;
                    }}
                    .block-container {{
                        background-color: rgba(255, 255, 255, {1 - opacity});
                        padding: 2rem;
                        border-radius: 1rem;
                    }}
                </style>
            """, unsafe_allow_html=True)
    else:
        st.warning(f"Pozadí '{image_path}' nebylo nalezeno.")

# === Styl ===
set_background("grafika/pozadi_hlavni.PNG", opacity=0.05)

st.markdown("""
    <style>
    .main { max-width: 80%; margin: auto; }
    h1 { font-size: 45px !important; margin-top: 0 !important; }
    .dataframe tbody tr th, .dataframe tbody tr td {
        background-color: #f0f0f0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# === Inicializace session ===
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

st.title("Asistent cenových nabídek od Davida")

# === Vzdálenost pomocí Google API ===
def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {'origins': origin, 'destinations': destination, 'key': api_key, 'units': 'metric'}
    response = requests.get(url, params=params)
    st.session_state.debug_history += f"\n📡 Google API Request: {response.url}\n"
    data = response.json()
    st.session_state.debug_history += f"\n📬 Google API Response:\n{json.dumps(data, indent=2)}\n"
    try:
        return data['rows'][0]['elements'][0]['distance']['value'] / 1000
    except Exception as e:
        st.error(f"❌ Chyba při získávání vzdálenosti: {e}")
        return None

# === Načti CSV ceníky z adresáře ===
cenik_dir = "ceniky"
ceniky = {}
try:
    for file in os.listdir(cenik_dir):
        if file.endswith(".csv"):
            nazev = file.rsplit(".", 1)[0].strip().lower()
            df = pd.read_csv(os.path.join(cenik_dir, file), index_col=0)
            df.columns = df.columns.astype(str)
            df.index = df.index.astype(str)
            df.columns = df.columns.astype(float)
            df.index = df.index.astype(float)
            ceniky[nazev] = df
    sheet_names = list(ceniky.keys())
    st.session_state.debug_history += f"\n📁 Načteny ceníky: {sheet_names}\n"
except Exception as e:
    st.error(f"❌ Chyba při načítání ceníků: {e}")
    st.stop()

# === Formulář ===
with st.form("formular"):
    user_input = st.text_area(
        "Zadejte popis produktů, rozměry a místo dodání:",
        height=100,
        placeholder="Např. ALUX Glass 6000x2500 Brno, screen 3500x2500..."
    )
    odeslat = st.form_submit_button("📤 ODESLAT")

if odeslat and user_input:
    debug = f"\n---\n📥 Uživatelský vstup:\n{user_input}\n"
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
            debug += f"\n📨 GPT prompt:\n{gpt_prompt}\n"
            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": gpt_prompt},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=1000
            )
            gpt_raw = response.choices[0].message.content.strip()
            debug += f"\n📬 GPT odpověď:\n{gpt_raw}\n"

            start_idx = gpt_raw.find('[')
            end_idx = gpt_raw.rfind(']') + 1
            gpt_clean = gpt_raw[start_idx:end_idx]
            produkty = json.loads(gpt_clean)
            debug += f"\n📤 Parsováno:\n{json.dumps(produkty, indent=2)}\n"

            vysledek = []

            for p in produkty:
                produkt = p['produkt'].lower()
                produkt_lookup = "screen" if "screen" in produkt else produkt
                misto = p.get("misto", "")

                sirka = int(float(p["šířka"]))
                vyska = (
                    2500 if p['hloubka_výška'] is None and "screen" in produkt_lookup
                    else int(float(p["hloubka_výška"]))
                )

                debug += f"\n🔍 {produkt_lookup}: {sirka}×{vyska}, místo: {misto}\n"

                if produkt_lookup not in ceniky:
                    debug += f"\n❌ Nenalezen ceník: {produkt_lookup}\n"
                    continue

                df = ceniky[produkt_lookup]
                cols = sorted([float(c) for c in df.columns])
                rows = sorted([float(r) for r in df.index])
                real_sirka = next((c for c in cols if c >= sirka), cols[-1])
                real_vyska = next((r for r in rows if r >= vyska), rows[-1])
                debug += f"\n📊 Tabulka: šířky={cols}, výšky={rows}\n"
                debug += f"\n📐 Použito: {real_sirka}×{real_vyska}\n"

                cena = df.loc[real_vyska, real_sirka]
                debug += f"\n💰 Cena z tabulky: {cena} Kč\n"

                vysledek.append({
                    "POLOŽKA": produkt_lookup,
                    "ROZMĚR": f"{sirka} × {vyska} mm",
                    "CENA bez DPH": round(float(cena))
                })

                if "screen" not in produkt_lookup:
                    for perc in [12, 13, 14, 15]:
                        cena_m = round(float(cena) * perc / 100)
                        vysledek.append({
                            "POLOŽKA": f"Montáž {perc}%",
                            "ROZMĚR": "",
                            "CENA bez DPH": cena_m
                        })
                        debug += f"\n🛠️ Montáž {perc}% = {cena_m} Kč\n"

                if misto and misto.lower() not in ["neuvedeno", "nedodáno"]:
                    km = get_distance_km("Blučina, Czechia", misto, st.secrets["GOOGLE_API_KEY"])
                    if km:
                        doprava = round(km * 2 * 15)
                        vysledek.append({
                            "POLOŽKA": "Doprava",
                            "ROZMĚR": f"{km:.1f} km",
                            "CENA bez DPH": doprava
                        })
                        debug += f"\n🚚 Doprava {km:.1f} km = {doprava} Kč\n"

            st.session_state.vysledky.insert(0, vysledek)
            debug += f"\n📦 Výstup:\n{pd.DataFrame(vysledek).to_string(index=False)}\n"
            st.session_state.debug_history += debug

        except Exception as e:
            st.error(f"❌ Chyba: {e}")
            st.session_state.debug_history += f"\n⛔ Výjimka: {e}\n"

# === Výstupy ===
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.dataframe(pd.DataFrame(vysledek), use_container_width=True)

# === Debug panel ===
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 20%; overflow-y: scroll; "
    f"background-color: #eeeeee; font-size: 10px; padding: 10px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
