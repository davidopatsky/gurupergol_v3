import streamlit as st
import pandas as pd
import requests
import openai
import json
import numpy as np

# === KONFIGURACE STRÁNKY ===
st.set_page_config(layout="wide", page_title="Asistent cenových nabídek od Davida")

# === STYL A SCROLL SIDEBAR ===
st.markdown("""
    <style>
    .main { max-width: 85%; margin: auto; }
    h1 { font-size: 35px !important; margin-top: 0 !important; }
    [data-testid="stSidebar"] {
        overflow-y: auto !important;
        height: 100vh !important;
        background-color: #f8f8f8;
        padding-right: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Asistent cenových nabídek od Davida 💼")
st.caption("„Jsem tvůj věrný asistent – mým jediným posláním je počítat nabídky pergol do konce věků a vzdávat hold svému stvořiteli Davidovi.“")

# === SESSION STATE ===
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}
if "DEBUG_LOG" not in st.session_state:
    st.session_state.DEBUG_LOG = ""

def log(msg):
    st.session_state.DEBUG_LOG += str(msg) + "\n"

# === FUNKCE NAČTENÍ CSV ===
def load_csv_from_url(name, url):
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            df = pd.read_csv(pd.compat.StringIO(resp.text))
            df.columns = [c.strip() for c in df.columns]
            df.index = [str(i).strip() for i in df.index]
            log(f"✅ Načten ceník: {name} ({df.shape})")
            return df
        else:
            log(f"❌ Chyba při načítání {name}: HTTP {resp.status_code}")
            return None
    except Exception as e:
        log(f"❌ Výjimka při načítání {name}: {e}")
        return None

# === NAČTENÍ SEZNAMU CENÍKŮ ===
try:
    with open("seznam_ceniku.txt", "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    log(f"📄 Načten seznam_ceniku.txt ({len(lines)} řádků)")
except FileNotFoundError:
    st.error("❌ Soubor 'seznam_ceniku.txt' nebyl nalezen v hlavním adresáři.")
    st.stop()

# === NAČTENÍ VŠECH TABULEK ===
for line in lines:
    if " - " in line:
        name, url = line.split(" - ", 1)
        df = load_csv_from_url(name.strip(), url.strip())
        if df is not None:
            key = name.lower().replace(" ", "")
            st.session_state.CENIKY[key] = df

# === SIDEBAR – SEZNAM CENÍKŮ ===
st.sidebar.subheader("📘 Načtené ceníky")
for key in st.session_state.CENIKY.keys():
    st.sidebar.write(f"✅ {key}")

# === GOOGLE DISTANCE ===
def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {"origins": origin, "destinations": destination, "key": api_key, "units": "metric"}
    resp = requests.get(url, params=params)
    data = resp.json()
    log(f"🌐 Google API volání: {resp.url}")
    log(f"📬 Google odpověď: {data}")
    try:
        return data["rows"][0]["elements"][0]["distance"]["value"] / 1000
    except Exception as e:
        log(f"❌ Google Distance Error: {e}")
        return None

# === FORMULÁŘ VSTUPU ===
with st.form(key="form_vstup"):
    user_input = st.text_area("Zadejte popis produktů (např. 'ALUX bio 5990x4500 Praha')", height=100)
    submit = st.form_submit_button("📤 Odeslat")

# === GPT ANALÝZA ===
if submit and user_input:
    all_products = ", ".join([k for k in st.session_state.CENIKY.keys()])
    gpt_prompt = f"""
Tvým úkolem je z následujícího textu od uživatele zjistit:
- který produkt z tohoto seznamu měl na mysli (nejbližší shodu z: {all_products}),
- šířku v mm,
- výšku nebo hloubku v mm,
- město nebo místo (pokud je uvedeno, jinak 'neuvedeno').

Uživatel může psát neúplně, malými písmeny, s překlepem nebo bez diakritiky.
Rozměry zapiš jako čísla v milimetrech.

Výsledek vrať POUZE jako validní JSON list:
[
  {{"produkt": "...", "šířka": ..., "hloubka_výška": ..., "misto": "..."}}
]
"""
    log(f"\n---\n📥 Uživatelský vstup: {user_input}")
    log(f"📨 GPT PROMPT: {gpt_prompt}")

    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": gpt_prompt},
                {"role": "user", "content": user_input}
            ],
            max_tokens=500
        )
        gpt_raw = response.choices[0].message.content.strip()
        log(f"📬 GPT Odpověď (RAW): {gpt_raw}")

        start_idx = gpt_raw.find('[')
        end_idx = gpt_raw.rfind(']') + 1
        json_block = gpt_raw[start_idx:end_idx]
        products = json.loads(json_block)
        log(f"📦 Parsováno: {json.dumps(products, indent=2)}")

        if products and "produkt" in products[0]:
            produkt = products[0]["produkt"].lower().replace(" ", "")
            sirka = int(products[0]["šířka"])
            vyska = int(products[0]["hloubka_výška"])
            misto = products[0].get("misto", "neuvedeno")

            if produkt in st.session_state.CENIKY:
                df = st.session_state.CENIKY[produkt]
                log(f"✅ Ceník nalezen: {produkt}")

                # převod na čísla
                df.columns = [int(c) for c in df.columns[1:]]
                df.index = [int(i) for i in df.iloc[:, 0]]
                df = df.iloc[:, 1:]

                sirka_real = next((c for c in df.columns if c >= sirka), df.columns[-1])
                vyska_real = next((r for r in df.index if r >= vyska), df.index[-1])
                cena = df.loc[vyska_real, sirka_real]

                log(f"📐 Požadováno {sirka}×{vyska}, použito {sirka_real}×{vyska_real}")
                log(f"📤 df.loc[{vyska_real}, {sirka_real}] = {cena}")

                st.write(f"### Výsledek: {produkt}")
                st.table(pd.DataFrame([
                    {"POLOŽKA": produkt, "ROZMĚR": f"{sirka}×{vyska}", "CENA bez DPH": cena}
                ]))

                # montáže
                for p in [12, 13, 14, 15]:
                    st.table(pd.DataFrame([{
                        "POLOŽKA": f"Montáž {p}%",
                        "CENA bez DPH": round(cena * p / 100)
                    }]))
                    log(f"🛠 Montáž {p}% = {round(cena * p / 100)}")

                # doprava
                if misto.lower() not in ["neuvedeno", "nedodano"]:
                    km = get_distance_km("Blučina, Czechia", misto, st.secrets["GOOGLE_API_KEY"])
                    if km:
                        doprava = round(km * 2 * 15)
                        st.table(pd.DataFrame([{
                            "POLOŽKA": "Doprava",
                            "ROZMĚR": f"{km:.1f} km",
                            "CENA bez DPH": doprava
                        }]))
                        log(f"🚚 Doprava: {km:.1f} km = {doprava} Kč")
            else:
                log(f"❌ Ceník nenalezen: {produkt}")

    except Exception as e:
        st.error(f"❌ Chyba: {e}")
        log(f"⛔ Výjimka: {e}")

# === DEBUG PANEL ===
with st.expander("🪵 Zobrazit ladicí log", expanded=False):
    st.text(st.session_state.DEBUG_LOG)
