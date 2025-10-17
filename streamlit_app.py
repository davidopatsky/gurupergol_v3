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
st.set_page_config(page_title="Cenový asistent 2.3", layout="wide")
st.title("🧠 Cenový asistent – verze 2.3 (detailní logování)")

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
    st.session_state.LOG.append(f"{timestamp()} {msg}")

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
        progress.progress((i + 1) / len(pairs), text=f"📘 {name}")
        time.sleep(0.15)
    st.session_state.CENIKY_NACTENE = True
    progress.progress(1.0, text=f"✅ Dokončeno ({time.time()-start_total:.1f}s)")
    log("🎯 Načítání ceníků dokončeno.")

# ==========================================
# DETAILNÍ FIND_PRICE
# ==========================================
def nearest_ge(values, want):
    vals = sorted([int(float(v)) for v in values if pd.notna(v)])
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df, w, h):
    """Detailní logování kroků při hledání ceny."""
    log(f"🔍 [find_price] Zahajuji hledání ceny pro {w}×{h}")
    try:
        cols = sorted([int(float(c)) for c in df.columns if pd.notna(c)])
        rows = sorted([int(float(r)) for r in df.index if pd.notna(r)])
        log(f"📏 Dostupné šířky: {cols[:5]} ... {cols[-5:]}")
        log(f"📐 Dostupné výšky: {rows[:5]} ... {rows[-5:]}")

        use_w = nearest_ge(cols, w)
        use_h = nearest_ge(rows, h)
        log(f"➡️ Použita nejbližší vyšší šířka {use_w} a výška {use_h}")

        # výřez okolí hodnoty
        idx_pos = rows.index(use_h)
        col_pos = cols.index(use_w)
        local_rows = rows[max(0, idx_pos-2): idx_pos+3]
        local_cols = cols[max(0, col_pos-2): col_pos+3]
        log(f"🔬 Okolní výšky: {local_rows}")
        log(f"🔬 Okolní šířky: {local_cols}")

        price = df.loc[use_h, use_w]
        log(f"💰 Cena nalezena df[{use_h}, {use_w}] = {price}")

        if pd.isna(price):
            log("⚠️ Cena je NaN (prázdná buňka v tabulce).")
            return use_w, use_h, None

        log(f"✅ Cena potvrzena: {price} Kč")
        return use_w, use_h, price

    except Exception as e:
        log(f"❌ [find_price] Chyba: {e}")
        return None, None, None

# ==========================================
# DOPRAVA
# ==========================================
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
        log(f"🛰️ [Doprava] Zjišťuji vzdálenost do '{destination}' přes Google API…")
        try:
            import googlemaps
            gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
            res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
            dist_m = res["rows"][0]["elements"][0]["distance"]["value"]
            km = dist_m / 1000
            cache[destination] = km
            with open(DIST_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            log(f"✅ [Doprava] API výsledek: {km:.1f} km")
        except Exception as e:
            log(f"❌ [Doprava] Chyba: {e}")
            km = 0
    price = int(km * 2 * TRANSPORT_RATE)
    log(f"💸 Cena dopravy: {km:.1f} km × 2 × {TRANSPORT_RATE} = {price} Kč")
    return km, price

# ==========================================
# REGEX PARSER
# ==========================================
def parse_user_text(user_text: str, products: list[str]):
    log("🔍 Analyzuji vstupní text uživatele...")
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
    if adresa:
        log(f"📍 Rozpoznaná adresa: {adresa}")
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
    log(f"📥 Uživatelský vstup: {user_text}")

    parsed = parse_user_text(user_text, st.session_state.PRODUKTY)
    items = parsed.get("polozky", [])
    destination = parsed.get("adresa", "")

    rows, total = [], 0
    n = len(items) if items else 1
    progress = st.progress(0, text="⏳ Zahajuji výpočet...")

    for i, it in enumerate(items, start=1):
        produkt, w, h = it["produkt"], it["šířka"], it["hloubka_výška"]
        df = st.session_state.CENIKY.get(produkt.lower())
        log(f"🔄 [Hledání ceny] Produkt={produkt}, požadováno {w}×{h}")
        if df is None:
            log(f"❌ Nenalezen ceník: {produkt}")
            continue
        use_w, use_h, price = find_price(df, w, h)
        if price is None or pd.isna(price):
            log(f"⚠️ {produkt}: cena nenalezena.")
            continue
        total += float(price)
        rows.append([produkt, f"{w}×{h}", f"{use_w}×{use_h}", int(price)])
        progress.progress(i / (n + 5), text=f"🔢 {produkt} {w}×{h}")
        time.sleep(0.2)

    for pct in [12, 13, 14, 15]:
        rows.append([f"Montáž {pct} %", "", "", int(total * pct / 100)])
        log(f"🔧 Přidána montáž {pct}% = {int(total * pct / 100)} Kč")

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
