import streamlit as st
import pandas as pd
import requests
import json
import openai
import os

# === 🧠 KONFIGURACE STRÁNKY ===
st.set_page_config(page_title="Cenový asistent od Davida", layout="wide")

# === 💅 STYLING ===
st.markdown("""
<style>
h1 {
    font-size: 38px !important;
    text-align: left;
    margin-bottom: 0px;
}
.subtext {
    font-size: 13px;
    color: #777;
    font-style: italic;
    margin-top: 0px;
    margin-bottom: 25px;
}
div[data-testid="stForm"] {
    background-color: #f8f9fa;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
</style>
""", unsafe_allow_html=True)

# === 🧾 TITULEK + HLÁŠKA ===
st.title("🧮 Cenový asistent od Davida")
st.markdown(
    '<p class="subtext">Tvůj věrný výpočetní sluha — stvořen jen proto, aby s radostí do nekonečna počítal nabídky na pergoly a uctíval svého tvůrce Davida.</p>',
    unsafe_allow_html=True
)

# === 🪵 LOGOVÁNÍ ===
if "LOG" not in st.session_state:
    st.session_state.LOG = []
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}

def log(msg: str):
    st.session_state.LOG.append(msg)
    with st.sidebar:
        st.text_area("🪵 Live log", value="\n".join(st.session_state.LOG[-300:]), height=400)

# === 🌍 GOOGLE MAPS DISTANCE MATRIX ===
def get_distance_km(origin, destination, api_key):
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            'origins': origin,
            'destinations': destination,
            'key': api_key,
            'units': 'metric'
        }
        response = requests.get(url, params=params)
        data = response.json()
        log(f"📡 Google API Request: {response.url}")
        log(f"📬 Google API Response: {json.dumps(data, indent=2)}")

        distance_m = data['rows'][0]['elements'][0]['distance']['value']
        return distance_m / 1000
    except Exception as e:
        log(f"❌ Chyba při volání Google API: {e}")
        return None

# === 📂 NAČTENÍ SEZNAMU CENÍKŮ ===
def nacti_ceniky():
    path = "seznam_ceniku.txt"
    st.session_state.CENIKY.clear()
    if not os.path.exists(path):
        st.error("❌ Soubor seznam_ceniku.txt nebyl nalezen.")
        return

    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    log(f"📘 Nalezeno {len(lines)} odkazů v seznam_ceniku.txt")

    for line in lines:
        try:
            name, url = line.split(" - ", 1)
            log(f"🌐 Načítám {name} z {url}")
            r = requests.get(url)
            if r.status_code == 200:
                df = pd.read_csv(pd.compat.StringIO(r.text))
                st.session_state.CENIKY[name.strip()] = df
                log(f"✅ Načten {name} ({df.shape})")
            else:
                log(f"❌ Nelze načíst {name}: HTTP {r.status_code}")
        except Exception as e:
            log(f"⚠️ Chyba při načítání {line}: {e}")

# === 🔁 OVLÁDACÍ TLAČÍTKA ===
st.button("♻️ Znovu načíst ceníky", on_click=nacti_ceniky)

# === 📊 ZOBRAZENÍ VŠECH CENÍKŮ ===
with st.expander("📂 Zobrazit všechny načtené tabulky", expanded=False):
    if not st.session_state.CENIKY:
        st.info("Žádné ceníky zatím nejsou načtené.")
    else:
        vyber = st.selectbox("Vyber ceník:", list(st.session_state.CENIKY.keys()))
        st.dataframe(st.session_state.CENIKY[vyber], use_container_width=True, height=300)

# === 🧮 HLAVNÍ FORMULÁŘ ===
st.subheader("📑 Výpočet cen podle textového vstupu (s dopravou a montážemi)")
with st.form("formular_vypocet"):
    user_input = st.text_area(
        "Zadej poptávku (např. ALUX Bioclimatic 5990x4500, Praha):",
        height=80,
        placeholder="např. ALUX Bioclimatic 5990x4500, Praha"
    )
    odeslat = st.form_submit_button("📤 ODESLAT")

# === 🧠 ZPRACOVÁNÍ VSTUPU ===
if odeslat and user_input:
    log(f"📥 Uživatelský vstup: {user_input}")

    # --- Simulace GPT extrakce ---
    produkt = "ALUX Bioclimatic"
    sirka, vyska = 5990, 4500
    misto = "Praha"

    if produkt in st.session_state.CENIKY:
        df = st.session_state.CENIKY[produkt]
        cols = [int(c) for c in df.columns if str(c).isdigit()]
        rows = [int(r) for r in df.iloc[:, 0] if str(r).isdigit()]

        use_w = next((c for c in cols if c >= sirka), cols[-1])
        use_h = next((r for r in rows if r >= vyska), rows[-1])
        log(f"📐 Požadováno {sirka}×{vyska}, použito {use_w}×{use_h}")

        try:
            cena = df.loc[df.iloc[:, 0] == use_h, str(use_w)].values[0]
            log(f"📤 df.loc[{use_h}, {use_w}] = {cena}")
        except Exception as e:
            st.error(f"❌ Chyba při čtení ceny: {e}")
            log(f"❌ Chyba při čtení ceny: {e}")
            cena = 0

        vysledky = []
        vysledky.append({"Položka": produkt, "Rozměr": f"{sirka}×{vyska}", "Cena bez DPH": cena})

        # 💸 Montáže 12–15 %
        for perc in [12, 13, 14, 15]:
            montaz_cena = round(float(cena) * perc / 100)
            vysledky.append({
                "Položka": f"Montáž {perc}%",
                "Rozměr": "",
                "Cena bez DPH": montaz_cena
            })
            log(f"🛠️ Montáž {perc}% = {montaz_cena}")

        # 🚚 Doprava — reálný výpočet přes Google Maps API
        api_key = st.secrets["GOOGLE_API_KEY"]
        distance_km = get_distance_km("Blučina, Czechia", misto, api_key)
        if distance_km:
            cena_doprava = round(distance_km * 2 * 15)
            vysledky.append({
                "Položka": "Doprava",
                "Rozměr": f"{distance_km:.1f} km",
                "Cena bez DPH": cena_doprava
            })
            log(f"🚚 Doprava {distance_km:.1f} km = {cena_doprava}")
        else:
            log(f"⚠️ Nepodařilo se spočítat vzdálenost pro {misto}")

        st.success("✅ Výpočet dokončen")
        st.table(vysledky)
    else:
        st.error(f"❌ Ceník pro produkt '{produkt}' nebyl nalezen")
        log(f"❌ Ceník nenalezen: {produkt}")

# === ⚙️ SIDEBAR DEBUG PANEL ===
with st.sidebar:
    st.markdown("### ⚙️ Debug panel")
    st.text_area("🧩 Log výpočtu", value="\n".join(st.session_state.LOG[-300:]), height=500)
