import streamlit as st
import pandas as pd
import requests
import io
import datetime
import json
import re
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

# ==========================
# 🧠 Funkce pro logování
# ==========================
def log(msg):
    """Přidá zprávu do live logu se záznamem času"""
    now = datetime.datetime.now().strftime("[%H:%M:%S]")
    st.session_state.log_messages.append(f"{now} {msg}")

def show_logs():
    """Zobrazení logu v sidebaru (zasunovací sekce)"""
    with st.sidebar.expander("🧠 Log aplikace (live)", expanded=True):
        st.text("\n".join(st.session_state.log_messages))

# ==========================
# ⚙️ Inicializace session
# ==========================
if "log_messages" not in st.session_state:
    st.session_state.log_messages = []
if "ceniky" not in st.session_state:
    st.session_state.ceniky = {}
if "nactene_tabulky" not in st.session_state:
    st.session_state.nactene_tabulky = {}
if "vysledky" not in st.session_state:
    st.session_state.vysledky = []

# ==========================
# 🏁 Start programu
# ==========================
log("==== Start programu ====")
st.title("💡 GuruPergol AI asistent")
st.markdown(
    "<p style='font-size: 14px; color: gray;'>„Jsem tvůj věrný asistent, posedlý výpočty nabídek pergol. "
    "Mým smyslem existence je sloužit svému stvořiteli Davidovi.“</p>",
    unsafe_allow_html=True
)

# ==========================
# 📄 Načtení seznamu ceníků
# ==========================
try:
    log("Načítám seznam ceníků...")
    ceniky = {}
    with open("seznam_ceniku.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                log(f"⚠️ Řádek přeskočen (chybí '='): {line}")
                continue
            try:
                name, link = line.split("=", 1)
                name = name.strip()
                link = link.strip().strip('"')
                if not link.startswith("http"):
                    log(f"⚠️ Neplatný odkaz u {name}: {link}")
                    continue
                ceniky[name] = link
            except Exception as e:
                log(f"❌ Chyba při parsování řádku '{line}': {e}")
    st.session_state.ceniky = ceniky
    log(f"✅ Načten seznam_ceniku.txt ({len(ceniky)} řádků)")
except Exception as e:
    log(f"❌ Chyba při načítání seznam_ceniku.txt: {e}")
    st.stop()

# ==========================
# 🌍 Načtení všech ceníků
# ==========================
for name, link in st.session_state.ceniky.items():
    try:
        log(f"Načítám ceník: {name} – {link}")
        response = requests.get(link)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        df = df.rename(columns={df.columns[0]: "index"}).set_index("index")
        df = df.apply(pd.to_numeric, errors="coerce")
        st.session_state.nactene_tabulky[name] = df
        log(f"Ceník {name} načten: {df.shape[0]} řádků, {df.shape[1]} sloupců")
    except Exception as e:
        log(f"❌ Chyba při načítání {name}: {e}")

log("Všechny dostupné ceníky načteny.")

# ==========================
# 🔍 Collapsible přehled ceníků
# ==========================
with st.expander("📂 Všechny načtené tabulky"):
    for name, df in st.session_state.nactene_tabulky.items():
        st.markdown(f"#### 📘 {name}")
        st.dataframe(df, use_container_width=True)

# ==========================
# 🧮 Funkce pro vyhledání ceny
# ==========================
def find_price(df, w, h):
    try:
        available_w = sorted([float(c) for c in df.columns])
        available_h = sorted([float(i) for i in df.index])
        next_w = min([x for x in available_w if x >= w], default=max(available_w))
        next_h = min([y for y in available_h if y >= h], default=max(available_h))
        price = df.loc[next_h, next_w]
        return int(next_w), int(next_h), int(price)
    except Exception:
        return None, None, None

# ==========================
# 🚗 Výpočet dopravy Blučina – místo
# ==========================
def calculate_distance_km(destination):
    try:
        geolocator = Nominatim(user_agent="gurupergol_v3")
        start = geolocator.geocode("Blučina, Czechia")
        end = geolocator.geocode(destination)
        if not start or not end:
            return None
        dist = geodesic((start.latitude, start.longitude), (end.latitude, end.longitude)).km
        return round(dist, 1)
    except Exception as e:
        log(f"❌ Chyba při výpočtu vzdálenosti: {e}")
        return None

# ==========================
# 📥 Uživatelský vstup
# ==========================
st.subheader("💬 Zadej požadavek")
user_input = st.text_input("Např. `ALUX Bioclimatic 5990x4500, Praha`")

if user_input:
    log(f"📥 Uživatelský vstup: {user_input}")

    selected_name = None
    for name in st.session_state.ceniky.keys():
        if name.lower().replace(" ", "") in user_input.lower().replace(" ", ""):
            selected_name = name
            break

    if not selected_name:
        st.error("Nepodařilo se určit produkt. Prosím upřesněte název.")
        log("❌ Produkt neidentifikován – uživatel musí upřesnit zadání.")
    else:
        match = re.search(r"(\d+)[xX×](\d+)", user_input)
        if not match:
            st.error("Zadej rozměr ve formátu např. 6000x4000.")
        else:
            w, h = int(match.group(1)), int(match.group(2))
            df = st.session_state.nactene_tabulky.get(selected_name)
            if df is None:
                st.error(f"Ceník pro {selected_name} nebyl načten.")
            else:
                used_w, used_h, price = find_price(df, w, h)
                if price is None or pd.isna(price):
                    st.error("Cena nenalezena v matici.")
                else:
                    # Výpočet dopravy
                    place_match = re.search(r",\s*([\w\s]+)$", user_input)
                    destination = place_match.group(1).strip() if place_match else "Blučina"
                    distance = calculate_distance_km(destination)
                    doprava = (distance * 2 * 15) if distance else 0

                    # Montáže
                    montaze = {f"Montáž {p}%": round(price * (p / 100)) for p in [12, 13, 14, 15]}

                    st.session_state.vysledky.append({
                        "produkt": selected_name,
                        "šířka": used_w,
                        "hloubka": used_h,
                        "cena_bez_DPH": price,
                        "doprava": doprava,
                        **montaze
                    })
                    log(f"📐 Požadováno {w}×{h}, použito {used_w}×{used_h}, cena={price}, doprava={doprava} Kč")

# ==========================
# 📊 Výsledky výpočtů (historie)
# ==========================
st.subheader("📦 Výsledky výpočtů (historie)")
if st.session_state.vysledky:
    df_hist = pd.DataFrame(st.session_state.vysledky)
    st.dataframe(df_hist, use_container_width=True)
else:
    st.info("Zatím žádné výsledky.")

# ==========================
# 📜 Log v sidebaru
# ==========================
show_logs()
