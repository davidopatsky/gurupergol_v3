import os, re, json, time, requests, pandas as pd, streamlit as st
from io import StringIO
from datetime import datetime
from openai import OpenAI

# ==========================================
# KONFIGURACE
# ==========================================
st.set_page_config(page_title="Cenový asistent 3.1", layout="wide")
st.title("🧠 Cenový asistent – Full Trace Logging")

SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
ORIGIN = "Blučina, Česká republika"
TRANSPORT_RATE = 15
OPENAI_MODEL = "gpt-4o-mini"
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ==========================================
# LOGGING SYSTEM
# ==========================================
def timestamp():
    return datetime.now().strftime("[%H:%M:%S]")

def trace(category: str, message: str, level: str = "INFO"):
    """Jednotné detailní logování."""
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
        trace("ERROR", f"Chyba čtení seznamu ceníků: {e}", level="ERROR")
    return pairs

def load_ceniky():
    if "CENIKY_NACTENE" in st.session_state and st.session_state.CENIKY_NACTENE:
        trace("SYSTEM", "Ceníky již byly načteny – přeskakuji.")
        return
    st.session_state.CENIKY, st.session_state.PRODUKTY = {}, []
    pairs = read_seznam_ceniku()
    for name, url in pairs:
        start = time.time()
        trace("NETWORK", f"Stahuji ceník '{name}' z {url}")
        try:
            df = pd.read_csv(url)
            df = df.set_index(df.columns[0])
            st.session_state.CENIKY[name.lower()] = df
            st.session_state.PRODUKTY.append(name)
            trace("DATA", f"Načten {name} ({df.shape[0]}×{df.shape[1]}) za {time.time()-start:.2f}s")
        except Exception as e:
            trace("ERROR", f"Chyba načítání ceníku {name}: {e}", level="ERROR")
    st.session_state.CENIKY_NACTENE = True
    trace("SYSTEM", "Všechny ceníky načteny.")

# ==========================================
# GPT PARSER
# ==========================================
def gpt_parse_input(user_text: str, produkty: list[str]):
    trace("USER_INPUT", f"Uživatelský vstup: {user_text}")
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
    trace("GPT", f"Odesílám prompt (délka {len(prompt)} znaků)")
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": "Buď přesný JSON parser."},
                      {"role": "user", "content": prompt}],
            temperature=0
        )
        raw = completion.choices[0].message.content.strip()
        trace("GPT", f"Získána odpověď ({len(raw)} znaků)")

        # odstranění ohraničení ```json ... ```
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "").strip()

        data = json.loads(raw)
        trace("GPT", f"Úspěšně dekódován JSON: {data}")
        return data
    except Exception as e:
        trace("ERROR", f"Chyba GPT dekódování: {e}", level="ERROR")
        trace("GPT_RAW", f"Obsah: {raw if 'raw' in locals() else 'žádný výstup'}")
        return None

# ==========================================
# CENÍKOVÝ ENGINE
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
    trace("ENGINE", f"Hledám {w}×{h} v {getattr(df, 'name', 'ceníku')}")
    try:
        col_label, _ = pick_label_ge(df.columns, w)
        row_label, _ = pick_label_ge(df.index, h)
        if col_label is None or row_label is None:
            trace("ENGINE", "Nenašly se vhodné osy.", level="WARN")
            return None
        price = df.loc[row_label, col_label]
        trace("ENGINE", f"df.loc[{row_label}, {col_label}] = {price}")
        return pd.to_numeric(price, errors="coerce")
    except Exception as e:
        trace("ERROR", f"find_price: {e}", level="ERROR")
        return None

# ==========================================
# DOPRAVA
# ==========================================
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
        trace("ERROR", f"Chyba dopravy: {e}", level="ERROR")
        return 0, 0

# ==========================================
# UI
# ==========================================
init_session()
trace("SYSTEM", "Načítám ceníky při startu...")
load_ceniky()

st.markdown("---")
with st.expander("📂 Zobrazit načtené ceníky"):
    for name in st.session_state.PRODUKTY:
        st.dataframe(st.session_state.CENIKY[name.lower()], use_container_width=True)

user_text = st.text_area("Zadej poptávku", "ALUX Thermo 6000x4500, Praha")

if st.button("📤 Spočítat"):
    trace("USER_ACTION", "Klik: Spočítat")
    parsed = gpt_parse_input(user_text, st.session_state.PRODUKTY)
    if not parsed:
        st.error("GPT nerozpoznal vstup.")
        trace("ERROR", "GPT nerozpoznal vstup.", level="ERROR")
    else:
        total, rows = 0, []
        for item in parsed["polozky"]:
            produkt, w, h = item["produkt"], item["šířka"], item["hloubka_výška"]
            df = st.session_state.CENIKY.get(produkt.lower())
            if df is None:
                trace("ERROR", f"Ceník nenalezen: {produkt}", level="ERROR")
                continue
            price = find_price(df, w, h)
            if pd.isna(price):
                trace("WARN", f"Cena {produkt} {w}×{h} nenalezena", level="WARN")
                continue
            total += price
            rows.append([produkt, f"{w}×{h}", int(price)])

        for pct in [12, 13, 14, 15]:
            rows.append([f"Montáž {pct}%", "", int(total * pct / 100)])
            trace("ENGINE", f"Přidána montáž {pct}% = {int(total * pct / 100)} Kč")

        km, cost = calculate_transport(parsed.get("adresa", ""))
        rows.append([f"Doprava ({km:.1f} km)", "", cost])
        rows.append(["Celkem bez DPH", "", int(total + cost)])

        df_out = pd.DataFrame(rows, columns=["Položka", "Rozměr", "Cena (Kč)"])
        st.success("✅ Výpočet dokončen.")
        st.dataframe(df_out, use_container_width=True)
        trace("SYSTEM", "Výpočet dokončen.")

show_log_sidebar()
