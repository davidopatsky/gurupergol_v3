import os
import json
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ==========================================
# 1️⃣ KONFIGURACE
# ==========================================
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – stabilní verze")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 150  # Kč/km × 2 směr

# ==========================================
# 2️⃣ ZÁKLADNÍ FUNKCE
# ==========================================
def log(msg: str):
    st.session_state.LOG.append(str(msg))

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

def show_log():
    st.text_area("🪵 Log", "\n".join(st.session_state.LOG), height=300)

# ==========================================
# 3️⃣ FUNKCE PRO CENÍKY
# ==========================================
def read_seznam_ceniku():
    """Načte seznam ceníků z textového souboru"""
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
    if pd.isna(x): return None
    s = str(x).replace("\xa0","").replace(" ","").replace(",",".")
    s = re.sub(r"[^\d\.]", "", s)
    try: return int(float(s))
    except: return None

def coerce_matrix(df: pd.DataFrame):
    """Převede tabulku na čitelnou matici (index = výška, columns = šířka)"""
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
        if r.status_code != 200:
            log(f"❌ {url} → HTTP {r.status_code}")
            return None
        return pd.read_csv(StringIO(r.text))
    except Exception as e:
        log(f"❌ Chyba stahování: {e}")
        return None

def load_ceniky(force=False):
    """Načte všechny ceníky (pouze jednou nebo při ručním reloadu)"""
    if st.session_state.CENIKY_NACTENE and not force:
        log("📦 Ceníky už načteny – přeskakuji.")
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

# ==========================================
# 4️⃣ GPT – EXTRAKCE INFORMACÍ
# ==========================================
def extract_from_text(user_text: str, product_list: list[str]) -> dict:
    import openai
    client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    system_prompt = (
        "Z textu vytěž JSON: {\"polozky\":[{\"produkt\":\"...\",\"šířka\":...,\"hloubka_výška\":...}],\"adresa\":\"...\"}. "
        f"Názvy produktů hledej mezi: {', '.join(product_list)}. "
        "Rozměry převáděj na mm. Adresu napiš přesně."
    )
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
    except Exception as e:
        log(f"❌ GPT JSON decode error: {e}\nRAW:\n{raw}")
        parsed = {}
    return parsed

# ==========================================
# 5️⃣ VÝPOČET
# ==========================================
def nearest_ge(values, want):
    vals = sorted(values)
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df, w, h):
    if df is None or df.empty:
        return None, None, None
    cols = sorted([int(c) for c in df.columns])
    rows = sorted([int(r) for r in df.index])
    use_w, use_h = nearest_ge(cols, w), nearest_ge(rows, h)
    return use_w, use_h, df.loc[use_h, use_w]

def calculate_transport_cost(destination: str):
    """Cena dopravy = vzdálenost × 2 × 150 Kč"""
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
        dist_m = res["rows"][0]["elements"][0]["distance"]["value"]
        km = dist_m / 1000
        price = km * 2 * TRANSPORT_RATE
        log(f"🚗 Doprava {ORIGIN} → {destination}: {km:.1f} km → {price:.0f} Kč")
        return km, price
    except Exception as e:
        log(f"❌ Chyba výpočtu dopravy: {e}")
        return 0.0, 0.0

# ==========================================
# 6️⃣ UI A LOGIKA
# ==========================================
init_session()
load_ceniky()

st.markdown("---")
st.subheader("📝 Zadej text poptávky")
user_text = st.text_area(
    "Např.: ALUX Bioclimatic 6000x4500, screen 3000x2500, adresa Praha 4",
    height=100)
if st.button("📤 Spočítat"):
    st.session_state.LOG.clear()
    log(f"📥 Vstup:\n{user_text}")

    parsed = extract_from_text(user_text, st.session_state.PRODUKTY)
    items = parsed.get("polozky", [])
    destination = parsed.get("adresa", "")

    rows = []
    total = 0

    for it in items:
        produkt = it.get("produkt", "").strip()
        w, h = int(it.get("šířka", 0)), int(it.get("hloubka_výška", 0))
        df = st.session_state.CENIKY.get(produkt.lower())
        if df is None:
            log(f"❌ Nenalezen ceník: {produkt}")
            continue
        use_w, use_h, price = find_price(df, w, h)
        if pd.isna(price): continue
        total += float(price)
        rows.append([produkt, f"{w}×{h}", f"{use_w}×{use_h}", f"{price:,.0f} Kč"])

    # Montáže
    for pct in [12, 13, 14, 15]:
        rows.append([f"Montáž {pct} %", "", "", f"{total*pct/100:,.0f} Kč"])

    # Doprava
    if destination:
        km, cost = calculate_transport_cost(destination)
        rows.append([f"Doprava ({km:.1f} km × 2 × {TRANSPORT_RATE} Kč)", "", "", f"{cost:,.0f} Kč"])
    else:
        cost = 0

    # Součet
    rows.append(["Celkem bez DPH", "", "", f"{total + cost:,.0f} Kč"])

    df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr požad.", "Rozměr použit.", "Cena (bez DPH)"])
    st.dataframe(df_out, use_container_width=True)

st.markdown("---")
show_log()
