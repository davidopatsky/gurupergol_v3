import os
import json
import requests
import pandas as pd
import streamlit as st
from io import StringIO
from datetime import datetime

# ==========================================
# ZÁKLADNÍ NASTAVENÍ
# ==========================================
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – zjednodušená stabilní verze")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 15  # Kč/km, ×2 pro zpáteční cestu

# ==========================================
# SESSION + LOG
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
        st.markdown("### 🪵 Log výpočtů")
        with st.expander("Zobrazit / skrýt", expanded=False):
            st.text_area("Log", "\n".join(st.session_state.LOG), height=600)

# ==========================================
# FUNKCE PRO CENÍKY
# ==========================================
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

def fetch_csv(url: str):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            log(f"❌ {url} → HTTP {r.status_code}")
            return None
        df = pd.read_csv(StringIO(r.text))
        df = df.set_index(df.columns[0])
        log(f"✅ CSV načteno {df.shape[1]}×{df.shape[0]}")
        return df
    except Exception as e:
        log(f"❌ Chyba při načítání CSV: {e}")
        return None

def load_ceniky(force=False):
    if st.session_state.CENIKY_NACTENE and not force:
        log("📦 Ceníky už načtené – přeskakuji.")
        return

    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()

    for name, url in read_seznam_ceniku():
        df = fetch_csv(url)
        if df is None:
            continue
        st.session_state.CENIKY[name.lower()] = df
        st.session_state.PRODUKTY.append(name)
        log(f"📗 {name} načteno ({df.shape[1]}×{df.shape[0]})")

    st.session_state.CENIKY_NACTENE = True

# ==========================================
# FUNKCE PRO CENY
# ==========================================
def nearest_ge(values, want):
    vals = sorted([int(float(v)) for v in values])
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df, w, h):
    """Najde cenu podle nejbližší vyšší šířky a výšky (toleruje floaty i stringy)."""
    try:
        cols = sorted([int(float(c)) for c in df.columns])
        rows = sorted([int(float(r)) for r in df.index])

        use_w = nearest_ge(cols, w)
        use_h = nearest_ge(rows, h)

        # bezpečné načtení (někdy index/columns jsou stringy)
        price = None
        if use_h in df.index and use_w in df.columns:
            price = df.loc[use_h, use_w]
        elif str(use_h) in df.index and str(use_w) in df.columns:
            price = df.loc[str(use_h), str(use_w)]
        elif str(float(use_h)) in df.index and str(float(use_w)) in df.columns:
            price = df.loc[str(float(use_h)), str(float(use_w))]

        log(f"🔢 Cena {use_w}×{use_h} = {price}")
        return use_w, use_h, price

    except Exception as e:
        log(f"❌ Chyba ve find_price: {e}")
        return None, None, None

def calculate_transport_cost(destination: str):
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
        dist_m = res["rows"][0]["elements"][0]["distance"]["value"]
        km = dist_m / 1000
        price = int(km * 2 * TRANSPORT_RATE)
        log(f"🚗 Doprava {ORIGIN} → {destination}: {km:.1f} km → {price}")
        return km, price
    except Exception as e:
        log(f"❌ Chyba výpočtu dopravy: {e}")
        return 0.0, 0

# ==========================================
# GPT EXTRAKCE
# ==========================================
def extract_from_text(user_text: str, product_list: list[str]) -> dict:
    import openai
    client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    system_prompt = (
        "Z textu vytěž JSON ve formátu: "
        "{\"polozky\":[{\"produkt\":\"...\",\"šířka\":...,\"hloubka_výška\":...}],\"adresa\":\"...\"}. "
        f"Názvy produktů vybírej z: {', '.join(product_list)}."
    )
    log("🤖 Odesílám požadavek do GPT...")
    resp = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        max_tokens=600
    )
    raw = resp.choices[0].message.content.strip()
    try:
        parsed = json.loads(raw)
        log("✅ GPT JSON dekódován.")
    except Exception as e:
        log(f"❌ GPT JSON chyba: {e}\nRAW:\n{raw}")
        parsed = {}
    return parsed

# ==========================================
# UI A LOGIKA
# ==========================================
init_session()
load_ceniky()

# ---- Expander s načtenými ceníky ----
st.markdown("---")
with st.expander("📂 Zobrazit všechny načtené ceníky", expanded=False):
    if not st.session_state.CENIKY:
        st.warning("⚠️ Žádné ceníky nejsou načtené.")
    else:
        for name in st.session_state.PRODUKTY:
            df = st.session_state.CENIKY[name.lower()]
            st.markdown(f"### {name}")
            st.dataframe(df, use_container_width=True)

# ---- Formulář ----
st.markdown("---")
st.subheader("📝 Zadej text poptávky")
user_text = st.text_area("Např.: ALUX Thermo 6000x4500, Praha", height=100)

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
        w = int(it.get("šířka", 0))
        h = int(it.get("hloubka_výška", 0))
        df = st.session_state.CENIKY.get(produkt.lower())
        if df is None:
            log(f"❌ Nenalezen ceník: {produkt}")
            continue
        use_w, use_h, price = find_price(df, w, h)
        if price is None:
            log(f"⚠️ {produkt}: cena nenalezena.")
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

    rows.append(["Celkem bez DPH", "", "", int(total + cost)])
    df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr požad.", "Rozměr použit.", "Cena (bez DPH)"])
    st.dataframe(df_out, use_container_width=True)

# ---- Log vlevo ----
show_log_sidebar()
