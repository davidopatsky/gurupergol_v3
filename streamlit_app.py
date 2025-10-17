import os
import json
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ==============
# ZÁKLAD
# ==============
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – automatický výpočet montáže a dopravy")

if "LOG" not in st.session_state:
    st.session_state.LOG = []
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}
if "PRODUKTY" not in st.session_state:
    st.session_state.PRODUKTY = []

def log(msg: str): st.session_state.LOG.append(str(msg))
def show_log(): st.text_area("🪵 Live log", value="\n".join(st.session_state.LOG), height=300)

# ==============
# CENÍKY
# ==============
SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")

def read_seznam_ceniku():
    pairs = []
    with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
        for line in f.read().splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#"): continue
            m = re.match(r'^(.+?)\s*=\s*["\'](.+?)["\']$', raw)
            if m: pairs.append((m.group(1).strip(), m.group(2).strip()))
    return pairs

def fetch_csv(url: str):
    r = requests.get(url, timeout=30)
    return pd.read_csv(StringIO(r.text)) if r.status_code == 200 else None

def normalize_numeric_token(x):
    if pd.isna(x): return None
    s = str(x).replace("\xa0","").replace(" ","").replace(",",".")
    s = re.sub(r"[^\d\.]", "", s)
    try: return int(float(s))
    except: return None

def coerce_matrix(df):
    if df is None or df.empty: return None
    df2 = df.copy()
    first_col = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first_col]]
    if sum(v is not None for v in idx_try) / len(idx_try) > 0.5:
        df2.index = idx_try
        df2 = df2.drop(columns=[first_col])
    df2.columns = [normalize_numeric_token(c) for c in df2.columns]
    df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2 = df2.loc[[i for i in df2.index if i is not None],
                  [c for c in df2.columns if c is not None]]
    for c in df2.columns: df2[c] = pd.to_numeric(df2[c], errors="coerce")
    return df2

def nearest_ge(values, want):
    vals = sorted(values)
    for v in vals:
        if v >= want: return v
    return vals[-1]

def find_price(df, w, h):
    if df is None or df.empty: return None, None, None
    cols = sorted([int(c) for c in df.columns])
    rows = sorted([int(r) for r in df.index])
    use_w, use_h = nearest_ge(cols, w), nearest_ge(rows, h)
    return use_w, use_h, df.loc[use_h, use_w]

# ==============
# DOPRAVA – GOOGLE MATRIX
# ==============
def calculate_transport_cost(destination: str) -> tuple[float, float]:
    """Cena = vzdálenost × 2 × 150 Kč"""
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        origin = "Blučina, Česká republika"
        res = gmaps.distance_matrix([origin], [destination], mode="driving")
        distance_m = res["rows"][0]["elements"][0]["distance"]["value"]
        km = distance_m / 1000
        price = km * 2 * 150
        log(f"🚗 {origin} → {destination}: {km:.1f} km, {price:.0f} Kč")
        return km, price
    except Exception as e:
        log(f"❌ Chyba dopravy: {e}")
        return 0.0, 0.0

# ==============
# NAČTENÍ CENÍKŮ
# ==============
def load_all_ceniky():
    st.session_state.LOG.clear()
    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()
    for name, url in read_seznam_ceniku():
        raw = fetch_csv(url)
        if raw is None: continue
        mat = coerce_matrix(raw)
        if mat is None: continue
        st.session_state.CENIKY[name.lower()] = mat
        st.session_state.PRODUKTY.append(name)

if not st.session_state.CENIKY: load_all_ceniky()

# ==============
# FORM
# ==============
st.markdown("---")
st.subheader("📝 Zadej poptávku (produkt, rozměry, adresu)")

with st.form("calc_form"):
    user_text = st.text_area(
        "Např. ALUX Bioclimatic 6000x4500, screen 3000x2500, adresa Praha 4",
        height=100)
    submitted = st.form_submit_button("📤 ODESLAT")

if submitted and user_text.strip():
    log(f"📥 Uživatelský vstup:\n{user_text}")

    # GPT extrakce
    product_list = ", ".join(st.session_state.PRODUKTY)
    prompt = (
        "Z textu vytěž JSON se strukturou: "
        "{\"polozky\":[{\"produkt\":\"...\",\"šířka\":...,\"hloubka_výška\":...}],"
        "\"adresa\":\"...\"}. "
        f"Názvy produktů hledej mezi: {product_list}."
    )

    try:
        import openai
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role":"system","content":prompt},{"role":"user","content":user_text}],
            max_tokens=500
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE)
        parsed = json.loads(raw)
    except Exception as e:
        log(f"❌ GPT chyba: {e}")
        parsed = {}

    items = parsed.get("polozky", [])
    destination = parsed.get("adresa", "")

    # Výpočet cen
    rows = []
    total_sum = 0
    for it in items:
        try:
            produkt = str(it["produkt"]).strip()
            w, h = int(it["šířka"]), int(it["hloubka_výška"])
        except Exception:
            continue
        df = st.session_state.CENIKY.get(produkt.lower())
        if df is None: continue
        use_w, use_h, price = find_price(df, w, h)
        if pd.isna(price): continue
        total_sum += float(price)
        rows.append([produkt, f"{w}×{h}", f"{use_w}×{use_h}", f"{price:,.0f} Kč"])

    # Montáže (automaticky)
    for pct in [12, 13, 14, 15]:
        rows.append([f"Montáž {pct} %", "", "", f"{total_sum*pct/100:,.0f} Kč"])

    # Doprava
    if destination:
        dist, doprava = calculate_transport_cost(destination)
        rows.append([f"Doprava ({dist:.1f} km × 2 × 150 Kč)", "", "", f"{doprava:,.0f} Kč"])
    else:
        doprava = 0

    # Součet
    rows.append(["Celkem bez DPH", "", "", f"{total_sum + doprava:,.0f} Kč"])

    df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr požad.", "Rozměr použit.", "Cena (bez DPH)"])
    st.success("✅ Výpočet dokončen")
    st.dataframe(df_out, use_container_width=True)

st.markdown("---")
show_log()
