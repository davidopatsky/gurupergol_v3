import os
import json
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO
from datetime import datetime

# ==========================================
# 1️⃣ KONFIGURACE
# ==========================================
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – detailní logování & doprava 15 Kč/km")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 15  # Kč/km (×2 pro zpáteční cestu)

# ==========================================
# 2️⃣ SESSION A LOG
# ==========================================
def init_session():
    defaults = {
        "LOG": [],
        "CENIKY": {},
        "PRODUKTY": [],
        "CENIKY_NACTENE": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def timestamp() -> str:
    return datetime.now().strftime("[%H:%M:%S]")

def log(msg: str):
    """Přidá časově označenou zprávu do logu."""
    st.session_state.LOG.append(f"{timestamp()} {msg}")

def show_log_sidebar():
    """Detailní logování v levém postranním panelu."""
    with st.sidebar:
        st.markdown("### 🪵 Debug log")
        with st.expander("Zobrazit / skrýt log", expanded=False):
            st.text_area("Log výpočtů", "\n".join(st.session_state.LOG), height=600)

# ==========================================
# 3️⃣ FUNKCE PRO CENÍKY
# ==========================================
def read_seznam_ceniku():
    pairs = []
    try:
        with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
            for i, line in enumerate(f.read().splitlines(), start=1):
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                m = re.match(r'^(.+?)\s*=\s*["\'](.+?)["\']$', raw)
                if not m:
                    log(f"⚠️ Řádek {i} ignorován: {raw}")
                    continue
                pairs.append((m.group(1).strip(), m.group(2).strip()))
        log(f"✅ Seznam ceníků načten ({len(pairs)} položek).")
    except Exception as e:
        st.error(f"❌ Nelze načíst {SEZNAM_PATH}: {e}")
    return pairs

def normalize_numeric_token(x):
    if pd.isna(x):
        return None
    s = str(x).replace("\xa0", "").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^\d\.]", "", s)
    try:
        return int(float(s))
    except:
        return None

def coerce_matrix(df: pd.DataFrame):
    if df is None or df.empty:
        return None
    df2 = df.copy()
    first_col = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first_col]]
    if sum(v is not None for v in idx_try)/len(idx_try) > 0.5:
        df2.index = idx_try
        df2 = df2.drop(columns=[first_col])
    df2.columns = [normalize_numeric_token(c) for c in df2.columns]
    df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2 = df2.loc[[i for i in df2.index if i is not None],
                  [c for c in df2.columns if c is not None]]
    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")
    return df2

def fetch_csv(url: str):
    try:
        r = requests.get(url, timeout=20)
        log(f"🌐 Načítám CSV: {url}")
        if r.status_code != 200:
            log(f"❌ {url} → HTTP {r.status_code}")
            return None
        log(f"✅ CSV staženo ({len(r.text)} znaků)")
        return pd.read_csv(StringIO(r.text))
    except Exception as e:
        log(f"❌ Chyba stahování: {e}")
        return None

def load_ceniky(force=False):
    """Načte všechny ceníky (pouze jednou nebo při ručním reloadu)."""
    if st.session_state.CENIKY_NACTENE and not force:
        log("📦 Ceníky už načtené – přeskakuji.")
        return

    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()
    pairs = read_seznam_ceniku()

    for name, url in pairs:
        df = fetch_csv(url)
        if df is None:
            log(f"❌ {name}: nelze stáhnout.")
            continue
        mat = coerce_matrix(df)
        if mat is None or mat.empty:
            log(f"⚠️ {name}: prázdný po převodu.")
            continue
        st.session_state.CENIKY[name.lower()] = mat
        st.session_state.PRODUKTY.append(name)
        log(f"✅ {name}: {mat.shape[1]} šířek × {mat.shape[0]} výšek")

    st.session_state.CENIKY_NACTENE = True
    log("🎯 Všechny ceníky načteny.")

# ==========================================
# 4️⃣ FUNKCE PRO CENY
# ==========================================
def nearest_ge(values, want):
    vals = sorted(values)
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df, w, h):
    """Vrátí (šířku, výšku, cenu) podle nejbližších vyšších hodnot."""
    if df is None or df.empty:
        log("⚠️ find_price: prázdný DF.")
        return None, None, None
    try:
        cols = [int(c) for c in df.columns if pd.notna(c) and str(c).isdigit()]
        rows = [int(r) for r in df.index if pd.notna(r) and str(r).isdigit()]
        if not cols or not rows:
            log("⚠️ find_price: DF nemá validní rozměry.")
            return None, None, None
        use_w = nearest_ge(cols, w)
        use_h = nearest_ge(rows, h)
        price = df.loc[use_h, use_w]
        log(f"🔢 Cena nalezena: {use_w}×{use_h} → {price}")
        return use_w, use_h, price
    except Exception as e:
        log(f"❌ Chyba ve find_price: {e}")
        return None, None, None

def calculate_transport_cost(destination: str):
    """Cena dopravy = vzdálenost × 2 × 15 Kč."""
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
        dist_m = res["rows"][0]["elements"][0]["distance"]["value"]
        km = dist_m / 1000
        price = int(km * 2 * TRANSPORT_RATE)
        log(f"🚗 Doprava {ORIGIN} → {destination}: {km:.1f} km → {price} Kč")
        return km, price
    except Exception as e:
        log(f"❌ Chyba výpočtu dopravy: {e}")
        return 0.0, 0

# ==========================================
# 5️⃣ GPT – EXTRAKCE INFORMACÍ
# ==========================================
def extract_from_text(user_text: str, product_list: list[str]) -> dict:
    import openai
    client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    system_prompt = (
        "Z textu vytěž JSON: {\"polozky\":[{\"produkt\":\"...\",\"šířka\":...,\"hloubka_výška\":...}],\"adresa\":\"...\"}. "
        f"Názvy produktů hledej mezi: {', '.join(product_list)}. "
        "Rozměry převáděj na mm. Adresu napiš přesně."
    )
    log("🤖 Odesílám požadavek do GPT...")
    resp = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_text}],
        max_tokens=600
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        parsed = json.loads(raw)
        log("✅ GPT JSON úspěšně dekódován.")
    except Exception as e:
        log(f"❌ GPT JSON decode error: {e}\nRAW:\n{raw}")
        parsed = {}
    return parsed

# ==========================================
# 6️⃣ UI A LOGIKA
# ==========================================
init_session()
load_ceniky()

# ---- Expander s načtenými ceníky ----
st.markdown("---")
with st.expander("📂 Zobrazit všechny načtené ceníky", expanded=False):
    if not st.session_state.CENIKY:
        st.warning("⚠️ Zatím nejsou načtené žádné ceníky. Klikni na ♻️ Znovu načíst.")
    else:
        st.success(f"✅ Načteno {len(st.session_state.CENIKY)} ceníků:")
        for name in st.session_state.PRODUKTY:
            df = st.session_state.CENIKY.get(name.lower())
            if df is None or df.empty:
                st.error(f"❌ {name}: prázdný nebo vadný ceník.")
                continue
            st.markdown(f"### {name}")
            st.dataframe(df.head(5), use_container_width=True)

# ---- Formulář ----
st.markdown("---")
st.subheader("📝 Zadej text poptávky")
user_text = st.text_area(
    "Např.: ALUX Bioclimatic 6000x4500, screen 3000x2500, adresa Praha 4",
    height=100)

if st.button("📤 Spočítat"):
    st.session_state.LOG.clear()
    log(f"📥 Uživatelský vstup:\n{user_text}")

    parsed = extract_from_text(user_text, st.session_state.PRODUKTY)
    items = parsed.get("polozky", [])
    destination = parsed.get("adresa", "")

    rows = []
    total = 0

    for it in items:
        produkt = it.get("produkt", "").strip()
        w, h = int(it.get("šířka", 0)), int(it.get("hloubka_výška", 0))
        log(f"📏 {produkt}: požadováno {w}×{h}")
        df = st.session_state.CENIKY.get(produkt.lower())
        if df is None:
            log(f"❌ Nenalezen ceník: {produkt}")
            continue
        use_w, use_h, price = find_price(df, w, h)
        if use_w is None or use_h is None or price is None or pd.isna(price):
            log(f"⚠️ {produkt}: cena nenalezena ({w}×{h})")
            continue
        total += float(price)
        rows.append([produkt, f"{w}×{h}", f"{use_w}×{use_h}", int(price)])

    # Montáže
    for pct in [12, 13, 14, 15]:
        rows.append([f"Montáž {pct} %", "", "", int(total * pct / 100)])

    # Doprava
    if destination:
        km, cost = calculate_transport_cost(destination)
        rows.append([f"Doprava ({km:.1f} km × 2 × {TRANSPORT_RATE} Kč)", "", "", cost])
    else:
        cost = 0

    # Součet
    rows.append(["Celkem bez DPH", "", "", int(total + cost)])

    df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr požad.", "Rozměr použit.", "Cena (bez DPH)"])
    st.dataframe(df_out, use_container_width=True)

# ---- Log v sidebaru ----
show_log_sidebar()
