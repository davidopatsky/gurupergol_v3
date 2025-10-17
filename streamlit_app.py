import os, re, json, time, requests, pandas as pd, streamlit as st
from io import StringIO
from datetime import datetime
from openai import OpenAI

# ==========================================
# KONFIGURACE
# ==========================================
st.set_page_config(page_title="Cenový asistent 3.2", layout="wide")
st.title("🧠 Cenový asistent – verze 3.2 (UX + montáž pod položkami)")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 15
OPENAI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ==========================================
# LOGGING
# ==========================================
def timestamp(): return datetime.now().strftime("[%H:%M:%S]")
def trace(category, message, level="INFO"):
    line = f"{timestamp()} [{level}] [{category}] {message}"
    st.session_state.LOG.append(line)
def init_session():
    if "LOG" not in st.session_state:
        st.session_state.LOG = []
    trace("SYSTEM", "=== Aplikace spuštěna ===")
def show_log_sidebar():
    with st.sidebar:
        st.markdown("### 🪵 Kompletní živý log")
        st.text_area("Log", "\n".join(st.session_state.LOG), height=600)

# ==========================================
# NAČÍTÁNÍ CENÍKŮ
# ==========================================
def read_seznam_ceniku():
    pairs = []
    try:
        with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    name, url = line.split("=", 1)
                    pairs.append((name.strip(), url.strip().strip('"')))
        trace("SYSTEM", f"Načten seznam ceníků: {len(pairs)} položek.")
    except Exception as e:
        trace("ERROR", f"Chyba čtení seznamu ceníků: {e}", "ERROR")
    return pairs

def load_ceniky():
    if "CENIKY_NACTENE" in st.session_state and st.session_state.CENIKY_NACTENE:
        trace("SYSTEM", "Ceníky již načteny – přeskakuji.")
        return
    st.session_state.CENIKY, st.session_state.PRODUKTY = {}, []
    pairs = read_seznam_ceniku()
    for name, url in pairs:
        start = time.time()
        trace("NETWORK", f"Stahuji '{name}'")
        try:
            df = pd.read_csv(url)
            df = df.set_index(df.columns[0])
            st.session_state.CENIKY[name.lower()] = df
            st.session_state.PRODUKTY.append(name)
            trace("DATA", f"Načten {name} ({df.shape[0]}×{df.shape[1]}) za {time.time()-start:.2f}s")
        except Exception as e:
            trace("ERROR", f"Chyba načítání {name}: {e}", "ERROR")
    st.session_state.CENIKY_NACTENE = True
    trace("SYSTEM", "Všechny ceníky načteny.")

# ==========================================
# GPT PARSER
# ==========================================
def gpt_parse_input(user_text: str, produkty: list[str]):
    trace("USER_INPUT", f"Vstup uživatele: {user_text}")
    prompt = f"""
    Uživatel zadal: "{user_text}".
    Toto je seznam produktů: {', '.join(produkty)}.
    Rozpoznej produkt, rozměry (v mm) a případnou adresu.
    Vrať pouze čistý JSON ve formátu:
    {{
      "polozky": [{{"produkt": "...", "šířka": ..., "hloubka_výška": ...}}],
      "adresa": "..."
    }}
    Nepiš žádný text kolem JSONu.
    """
    trace("GPT", f"Odesílám prompt ({len(prompt)} znaků)")
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": "Buď přesný JSON parser."},
                      {"role": "user", "content": prompt}],
            temperature=0
        )
        raw = completion.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "").strip()
        trace("GPT", f"Odpověď GPT ({len(raw)} znaků)")
        data = json.loads(raw)
        trace("GPT", f"Dekódován JSON: {data}")
        return data
    except Exception as e:
        trace("ERROR", f"Chyba GPT: {e}", "ERROR")
        trace("GPT_RAW", f"Obsah: {raw if 'raw' in locals() else 'žádný'}")
        return None

# ==========================================
# CENÍKOVÝ ENGINE
# ==========================================
def pick_label_ge(labels, want):
    numeric = pd.to_numeric(pd.Index(labels), errors="coerce")
    s = pd.Series(numeric.values, index=pd.Index(labels)).dropna()
    if s.empty: return None, None
    candidates = s[s >= want]
    label = s.idxmax() if candidates.empty else candidates.idxmin()
    return label, s[label]

def find_price(df, w, h):
    trace("ENGINE", f"Hledám {w}×{h} v {getattr(df, 'name', 'ceníku')}")
    try:
        col_label, _ = pick_label_ge(df.columns, w)
        row_label, _ = pick_label_ge(df.index, h)
        if col_label is None or row_label is None:
            trace("ENGINE", "Osy neobsahují vhodné štítky.", "WARN")
            return None
        price = df.loc[row_label, col_label]
        trace("ENGINE", f"df.loc[{row_label}, {col_label}] = {price}")
        return pd.to_numeric(price, errors="coerce")
    except Exception as e:
        trace("ERROR", f"find_price: {e}", "ERROR")
        return None

def calculate_transport(destination):
    trace("TRANSPORT", f"Zjišťuji vzdálenost: {destination}")
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        res = gmaps.distance_matrix([ORIGIN], [destination], mode="driving")
        km = res["rows"][0]["elements"][0]["distance"]["value"] / 1000
        cost = int(km * 2 * TRANSPORT_RATE)
        trace("TRANSPORT", f"Vzdálenost {km:.1f} km → {cost} Kč")
        return km, cost
    except Exception as e:
        trace("ERROR", f"Doprava selhala: {e}", "ERROR")
        return 0, 0

# ==========================================
# UI
# ==========================================
init_session()
load_ceniky()

st.markdown("---")
with st.expander("📂 Zobrazit načtené ceníky"):
    for name in st.session_state.PRODUKTY:
        df = st.session_state.CENIKY[name.lower()]
        st.markdown(f"### 📘 {name}")
        st.caption(f"Rozměry: {df.shape[0]} výšek × {df.shape[1]} šířek")
        st.dataframe(df, use_container_width=True)

st.markdown("---")
st.subheader("📝 Zadej text poptávky (Command/Ctrl + Enter pro odeslání)")

# Formulář s podporou klávesové zkratky
with st.form("calc_form"):
    user_text = st.text_area("Např.: ALUX Thermo 6000x4500, Praha", height=100)
    submitted = st.form_submit_button("📤 ODESLAT (⌘/Ctrl + Enter)")
if submitted or (st.session_state.get("text_area_keydown", False)):
    trace("USER_ACTION", "Odeslán formulář")
    parsed = gpt_parse_input(user_text, st.session_state.PRODUKTY)
    if not parsed:
        st.error("GPT nerozpoznal vstup.")
    else:
        total, rows = 0, []
        for item in parsed["polozky"]:
            produkt, w, h = item["produkt"], item["šířka"], item["hloubka_výška"]
            df = st.session_state.CENIKY.get(produkt.lower())
            if df is None:
                trace("ERROR", f"Ceník nenalezen: {produkt}", "ERROR")
                continue
            price = find_price(df, w, h)
            if pd.isna(price):
                trace("WARN", f"Cena {produkt} {w}×{h} nenalezena", "WARN")
                continue

            total += price
            rows.append([produkt, f"{w}×{h}", int(price)])
            for pct in [12, 13, 14, 15]:
                rows.append([f"↳ Montáž {pct} %", "", int(price * pct / 100)])

        km, cost = calculate_transport(parsed.get("adresa", ""))
        rows.append([f"Doprava ({km:.1f} km)", "", cost])
        rows.append(["Celkem bez DPH", "", int(total + cost + cost)])
        df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr", "Cena (Kč)"])
        st.success("✅ Výpočet dokončen.")
        st.dataframe(df_out, use_container_width=True)

show_log_sidebar()
