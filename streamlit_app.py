import os
import re
import json
import time
import requests
import pandas as pd
import streamlit as st
from io import StringIO
from datetime import datetime

# ==========================================
# KONFIGURACE
# ==========================================
st.set_page_config(page_title="Cenový asistent 2.2", layout="wide")
st.title("🧠 Cenový asistent – verze 2.2 (realtime log + progress bar)")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
DIST_CACHE_PATH = os.path.join(CACHE_DIR, "distance_cache.json")

ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 15  # Kč/km × 2

# ==========================================
# SESSION A LOG
# ==========================================
def init_session():
    if "LOG" not in st.session_state:
        st.session_state.LOG = []
    if "CENIKY" not in st.session_state:
        st.session_state.CENIKY = {}
    if "PRODUKTY" not in st.session_state:
        st.session_state.PRODUKTY = []
    if "CENIKY_NACTENE" not in st.session_state:
        st.session_state.CENIKY_NACTENE = False

def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")

def log(msg: str):
    entry = f"{timestamp()} {msg}"
    st.session_state.LOG.append(entry)
    st.session_state["last_log"] = entry

def show_log_sidebar():
    with st.sidebar:
        st.markdown("### 🪵 Detailní log výpočtů")
        with st.expander("Zobrazit / skrýt", expanded=False):
            st.text_area("Log", "\n".join(st.session_state.LOG), height=600)

# ==========================================
# CENÍKY (s cache)
# ==========================================
def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.mkdir(CACHE_DIR)

def read_seznam_ceniku():
    pairs = []
    try:
        with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    name, url = line.split("=", 1)
                    pairs.append((name.strip(), url.strip().strip('"')))
        log(f"✅ Seznam ceníků načten ({len(pairs)} položek).")
    except Exception as e:
        st.error(f"❌ Nelze načíst {SEZNAM_PATH}: {e}")
    return pairs

def fetch_csv_cached(name: str, url: str):
    ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, f"{name}.csv")
    start = time.time()
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, index_col=0)
        log(f"📂 {name}: načteno z cache ({df.shape[1]}×{df.shape[0]}) za {time.time()-start:.2f}s")
        return df
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            log(f"❌ {name}: HTTP {r.status_code}")
            return None
        df = pd.read_csv(StringIO(r.text))
        df.to_csv(cache_path, index=False)
        df = df.set_index(df.columns[0])
        log(f"✅ {name}: staženo ({df.shape[1]}×{df.shape[0]}) za {time.time()-start:.2f}s")
        return df
    except Exception as e:
        log(f"❌ {name}: chyba stahování {e}")
        return None

def load_ceniky(force=False):
    start_total = time.time()
    if st.session_state.CENIKY_NACTENE and not force:
        log("📦 Ceníky už načtené – přeskakuji.")
        return
    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()
    pairs = read_seznam_ceniku()

    progress = st.progress(0, text="🔄 Načítám ceníky...")
    for i, (name, url) in enumerate(pairs):
        df = fetch_csv_cached(name, url)
        if df is not None:
            st.session_state.CENIKY[name.lower()] = df
            st.session_state.PRODUKTY.append(name)
        progress.progress((i + 1) / len(pairs), text=f"📘 Načteno: {name}")
        time.sleep(0.2)
    st.session_state.CENIKY_NACTENE = True
    progress.progress(1.0, text=f"✅ Načítání dokončeno ({len(pairs)} ceníků, {time.time()-start_total:.1f}s)")
    log("🎯 Načítání ceníků dokončeno.")

# ==========================================
# VÝPOČTY
# ==========================================
def nearest_ge(values, want):
    vals = sorted([int(float(v)) for v in values if pd.notna(v)])
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df, w, h):
    try:
        cols = sorted([int(float(c)) for c in df.columns if pd.notna(c)])
        rows = sorted([int(float(r)) for r in df.index if pd.notna(r)])
        use_w = nearest_ge(cols, w)
        use_h = nearest_ge(rows, h)
        price = df.loc[use_h, use_w]
        log(f"🔢 {use_w}×{use_h} → {price}")
        return use_w, use_h, price
    except Exception as e:
        log(f"❌ find_price: {e}")
        return None, None, None

def calculate_transport_cost(destination: str):
    ensure_cache_dir()
    cache = {}
    if os.path.exists(DIST_CACHE_PATH):
        try:
            with open(DIST_CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except:
            cache = {}
    if destination in cache:
        km = cache[destination]
        log(f"🚗 Doprava (cache): {destination} = {km:.1f} km")
    else:
        log(f"🛰️ Zjišťuji vzdálenost do '{destination}'...")
        try:
            import googlemaps
            gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
            res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
            dist_m = res["rows"][0]["elements"][0]["distance"]["value"]
            km = dist_m / 1000
            cache[destination] = km
            with open(DIST_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            log(f"✅ Doprava API: {destination} = {km:.1f} km")
        except Exception as e:
            log(f"❌ Chyba výpočtu dopravy: {e}")
            km = 0
    price = int(km * 2 * TRANSPORT_RATE)
    return km, price

# ==========================================
# REGEX PARSER
# ==========================================
def parse_user_text(user_text: str, products: list[str]):
    log("🔍 Analyzuji vstupní text...")
    results = []
    text = user_text.lower().replace("×", "x")
    addr_match = re.findall(r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+(?: [A-Z].*)?$", user_text)
    adresa = addr_match[-1] if addr_match else ""
    for prod in products:
        if prod.lower() in text:
            m = re.search(r"(\d+)\s*[xX]\s*(\d+)", text)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                log(f"🧩 Rozpoznán produkt: {prod} {w}×{h}")
                results.append({"produkt": prod, "šířka": w, "hloubka_výška": h})
    return {"polozky": results, "adresa": adresa}

# ==========================================
# UI
# ==========================================
init_session()
load_ceniky()

st.markdown("---")
with st.expander("📂 Zobrazit všechny načtené ceníky", expanded=False):
    if not st.session_state.CENIKY:
        st.warning("⚠️ Žádné ceníky nejsou načtené.")
    else:
        for name in st.session_state.PRODUKTY:
            df = st.session_state.CENIKY[name.lower()]
            st.markdown(f"### {name}")
            st.dataframe(df, use_container_width=True)

st.markdown("---")
st.subheader("📝 Zadej text poptávky")
user_text = st.text_area("Např.: ALUX Thermo 6000x4500, Praha", height=100)

if st.button("📤 Spočítat"):
    st.session_state.LOG.clear()
    log(f"📥 Vstup: {user_text}")

    parsed = parse_user_text(user_text, st.session_state.PRODUKTY)
    items = parsed.get("polozky", [])
    destination = parsed.get("adresa", "")

    rows, total = [], 0
    n = len(items) if items else 1
    progress = st.progress(0, text="⏳ Zahajuji výpočet...")

    for i, it in enumerate(items, start=1):
        produkt, w, h = it["produkt"], it["šířka"], it["hloubka_výška"]
        df = st.session_state.CENIKY.get(produkt.lower())
        progress.progress(i / (n + 3), text=f"⚙️ Počítám {produkt} ({i}/{n})")
        if df is None:
            log(f"❌ Nenalezen ceník: {produkt}")
            continue
        use_w, use_h, price = find_price(df, w, h)
        if price is None or pd.isna(price):
            log(f"⚠️ {produkt}: cena nenalezena.")
            continue
        total += float(price)
        rows.append([produkt, f"{w}×{h}", f"{use_w}×{use_h}", int(price)])
        time.sleep(0.2)

    # Montáže
    for j, pct in enumerate([12, 13, 14, 15], start=1):
        progress.progress((i + j) / (n + 6), text=f"🔧 Přidávám montáž {pct}%")
        rows.append([f"Montáž {pct} %", "", "", int(total * pct / 100)])
        time.sleep(0.15)

    # Doprava
    if destination:
        progress.progress(0.9, text=f"🚗 Počítám dopravu do {destination}...")
        km, cost = calculate_transport_cost(destination)
        rows.append([f"Doprava ({km:.1f} km × 2 × {TRANSPORT_RATE} Kč)", "", "", cost])
    else:
        cost = 0

    progress.progress(1.0, text="✅ Výpočet dokončen.")
    rows.append(["Celkem bez DPH", "", "", int(total + cost)])
    df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr požad.", "Rozměr použit.", "Cena (bez DPH)"])
    st.success("✅ Výpočet úspěšně dokončen.")
    st.dataframe(df_out, use_container_width=True)

show_log_sidebar()
