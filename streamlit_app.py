import os, re, json, time, requests, pandas as pd, streamlit as st
from io import StringIO
from datetime import datetime
from openai import OpenAI

# ==========================================
# KONFIGURACE
# ==========================================
st.set_page_config(page_title="Cenový asistent 3.0", layout="wide")
st.title("🧠 Cenový asistent – verze 3.0 (GPT + ceníky)")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 15
OPENAI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ==========================================
# LOGOVÁNÍ
# ==========================================
def log(msg):
    st.session_state.LOG.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def init_session():
    if "LOG" not in st.session_state: st.session_state.LOG = []
    if "CENIKY" not in st.session_state: st.session_state.CENIKY = {}
    if "PRODUKTY" not in st.session_state: st.session_state.PRODUKTY = []
    if "CENIKY_NACTENE" not in st.session_state: st.session_state.CENIKY_NACTENE = False

# ==========================================
# NAČTENÍ CENÍKŮ
# ==========================================
def read_seznam_ceniku():
    pairs = []
    with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                name, url = line.split("=", 1)
                pairs.append((name.strip(), url.strip().strip('"')))
    log(f"✅ Seznam ceníků načten ({len(pairs)}).")
    return pairs

def load_ceniky():
    if st.session_state.CENIKY_NACTENE:
        log("📦 Ceníky už načtené – přeskakuji.")
        return
    for name, url in read_seznam_ceniku():
        df = pd.read_csv(url)
        df = df.set_index(df.columns[0])
        st.session_state.CENIKY[name.lower()] = df
        st.session_state.PRODUKTY.append(name)
        log(f"📘 {name}: načten ({df.shape[0]} řádků, {df.shape[1]} sloupců)")
    st.session_state.CENIKY_NACTENE = True

# ==========================================
# GPT PARSER
# ==========================================
def gpt_parse_input(user_text: str, produkty: list[str]):
    log("🤖 Odesílám vstup do GPT...")
    prompt = f"""
    Uživatel zadal: "{user_text}".
    Toto je seznam produktů z ceníku: {', '.join(produkty)}.
    Vyber, který produkt odpovídá, a vrať JSON s tímto formátem:
    {{
      "polozky": [{{"produkt": "...", "šířka": ..., "hloubka_výška": ...}}],
      "adresa": "..."
    }}
    Používej čísla v mm (např. 6000, 4500), ne metry.
    """
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": "Buď přesný JSON parser."},
                      {"role": "user", "content": prompt}],
            temperature=0
        )
        text = completion.choices[0].message.content.strip()
        data = json.loads(text)
        log("✅ GPT JSON úspěšně dekódován.")
        return data
    except Exception as e:
        log(f"❌ Chyba GPT: {e}")
        return None

# ==========================================
# VÝPOČET CEN
# ==========================================
def pick_label_ge(labels, want):
    numeric = pd.to_numeric(pd.Index(labels), errors="coerce")
    s = pd.Series(numeric.values, index=pd.Index(labels)).dropna()
    if s.empty: return None, None
    candidates = s[s >= want]
    if candidates.empty: label = s.idxmax()
    else: label = candidates.idxmin()
    return label, s[label]

def find_price(df, w, h):
    col_label, _ = pick_label_ge(df.columns, w)
    row_label, _ = pick_label_ge(df.index, h)
    if col_label is None or row_label is None: return None
    return df.loc[row_label, col_label]

def calculate_transport(destination):
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
        km = res["rows"][0]["elements"][0]["distance"]["value"] / 1000
        return km, int(km * 2 * TRANSPORT_RATE)
    except Exception:
        return 0, 0

# ==========================================
# UI
# ==========================================
init_session()
load_ceniky()

st.markdown("---")
with st.expander("📂 Zobrazit načtené ceníky"):
    for name in st.session_state.PRODUKTY:
        st.dataframe(st.session_state.CENIKY[name.lower()], use_container_width=True)

user_text = st.text_area("Zadej poptávku", "ALUX Thermo 6000x4500, Praha")

if st.button("📤 Spočítat"):
    st.session_state.LOG.clear()
    parsed = gpt_parse_input(user_text, st.session_state.PRODUKTY)
    if not parsed:
        st.error("GPT nerozpoznal vstup.")
    else:
        total = 0
        rows = []
        for item in parsed["polozky"]:
            produkt, w, h = item["produkt"], item["šířka"], item["hloubka_výška"]
            df = st.session_state.CENIKY.get(produkt.lower())
            if df is None:
                log(f"❌ Nenalezen ceník: {produkt}")
                continue
            price = find_price(df, w, h)
            if price is None or pd.isna(price):
                log(f"⚠️ Cena {produkt} {w}×{h} nenalezena.")
                continue
            total += float(price)
            rows.append([produkt, f"{w}×{h}", int(price)])

        for pct in [12, 13, 14, 15]:
            rows.append([f"Montáž {pct}%", "", int(total * pct / 100)])

        km, cost = calculate_transport(parsed.get("adresa", ""))
        rows.append([f"Doprava ({km:.1f} km)", "", cost])
        rows.append(["Celkem bez DPH", "", int(total + cost)])

        df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr", "Cena (Kč)"])
        st.dataframe(df_out, use_container_width=True)

st.sidebar.text_area("🪵 Log", "\n".join(st.session_state.LOG), height=500)
