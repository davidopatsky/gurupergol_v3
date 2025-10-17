import os
import json
import re
import requests
import pandas as pd
import streamlit as st
import googlemaps
from io import StringIO

# ===============================
# ZÁKLAD
# ===============================
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – automatický výpočet")

if "LOG" not in st.session_state:
    st.session_state.LOG = []
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}
if "PRODUKTY" not in st.session_state:
    st.session_state.PRODUKTY = []

def log(msg: str):
    st.session_state.LOG.append(str(msg))

def show_log():
    st.text_area("🪵 Live log", value="\n".join(st.session_state.LOG), height=320)

# ===============================
# SOUBOR SEZNAM CENÍKŮ
# ===============================
SEZNAM_PATH = os.path.join(os.path.dirname(__file__), "seznam_ceniku.txt")

def read_seznam_ceniku():
    pairs = []
    try:
        with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        log(f"📄 Načten {SEZNAM_PATH} ({len(lines)} řádků)")
        for i, line in enumerate(lines, start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            m = re.match(r'^(.+?)\s*=\s*["\'](.+?)["\']$', raw)
            if not m:
                log(f"⚠️ Řádek {i} přeskočen: {raw}")
                continue
            name, url = m.groups()
            pairs.append((name.strip(), url.strip()))
        log(f"✅ Zparsováno {len(pairs)} položek ze seznamu")
    except Exception as e:
        log(f"❌ Chyba při čtení seznamu: {e}")
        st.error(f"Soubor '{SEZNAM_PATH}' chybí nebo nejde číst.")
    return pairs

# ===============================
# FUNKCE PRO CENÍKY
# ===============================
def fetch_csv(url: str) -> pd.DataFrame | None:
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            log(f"❌ HTTP {r.status_code}")
            return None
        df = pd.read_csv(StringIO(r.text))
        return df
    except Exception as e:
        log(f"❌ Chyba při stahování CSV: {e}")
        return None

def normalize_numeric_token(x) -> int | None:
    if pd.isna(x): return None
    s = str(x).strip().replace("\xa0","").replace(" ","")
    s = re.sub(r"[Kk][Čc]|mm|MM","",s)
    s = s.replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m: return None
    try: return int(round(float(m.group(0))))
    except: return None

def coerce_matrix(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty: return None
    first_col = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first_col]]
    numerics_ratio = sum(v is not None for v in idx_try) / max(1, len(idx_try))
    df2 = df.copy()
    if numerics_ratio > 0.6:
        df2.index = idx_try
        df2 = df2.drop(columns=[first_col])
    new_cols = [normalize_numeric_token(c) for c in df2.columns]
    if sum(c is not None for c in new_cols) < len(new_cols)*0.6:
        df2 = df2.T
        new_cols = [normalize_numeric_token(c) for c in df2.columns]
        df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2.columns = new_cols
    df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2 = df2.loc[[i for i in df2.index if i is not None],
                  [c for c in df2.columns if c is not None]]
    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")
    return df2

def nearest_ge(values: list[int], want: int) -> int:
    vals = sorted(values)
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df_mat: pd.DataFrame, width: int, height: int):
    if df_mat is None or df_mat.empty:
        return None, None, None
    cols = sorted([int(c) for c in df_mat.columns])
    rows = sorted([int(r) for r in df_mat.index])
    use_w = nearest_ge(cols, width)
    use_h = nearest_ge(rows, height)
    price = df_mat.loc[use_h, use_w]
    return use_w, use_h, price

# ===============================
# DOPRAVA – GOOGLE DISTANCE MATRIX
# ===============================
def calculate_transport_cost(destination: str) -> tuple[float, float]:
    """
    Vrátí (vzdálenost_km, cena_dopravy)
    Cena = vzdálenost × 2 × 150 Kč
    """
    try:
        gmaps = googlemaps.Client(key=st.secrets["GOOGLE_API_KEY"])
        origin = "Blučina, Česká republika"
        res = gmaps.distance_matrix(origins=[origin], destinations=[destination], mode="driving")
        distance_m = res["rows"][0]["elements"][0]["distance"]["value"]
        distance_km = distance_m / 1000
        cost = distance_km * 2 * 150
        log(f"📏 Vzdálenost {distance_km:.1f} km → Doprava {cost:.0f} Kč")
        return distance_km, cost
    except Exception as e:
        log(f"❌ Chyba při výpočtu dopravy: {e}")
        return 0.0, 0.0

# ===============================
# NAČTENÍ CENÍKŮ
# ===============================
def load_all_ceniky():
    st.session_state.LOG.clear()
    pairs = read_seznam_ceniku()
    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()
    for name, url in pairs:
        raw = fetch_csv(url)
        if raw is None: continue
        mat = coerce_matrix(raw)
        if mat is None or mat.empty: continue
        st.session_state.CENIKY[name.lower()] = mat
        st.session_state.PRODUKTY.append(name)

if not st.session_state.CENIKY:
    load_all_ceniky()

# ===============================
# HLAVNÍ VÝPOČET
# ===============================
st.markdown("---")
st.subheader("📝 Textová poptávka (včetně montáže a adresy)")

with st.form("calc_form"):
    user_text = st.text_area("Zadej kompletní poptávku:", height=120,
        placeholder="např. ALUX Bioclimatic 6000x4500, screen 3000x2500, montáž 14 %, adresa Praha")
    submitted = st.form_submit_button("📤 ODESLAT")

if submitted and user_text.strip():
    log("\n---")
    log(f"📥 Uživatelský vstup:\n{user_text}")

    product_list = ", ".join(st.session_state.PRODUKTY) if st.session_state.PRODUKTY else "screen"
    system_prompt = (
        "Z následujícího textu vytěž strukturovaná data ve formátu JSON. "
        "Rozpoznej všechny položky s názvem produktu (z tohoto seznamu: "
        f"{product_list}), šířkou (mm), výškou (mm), "
        "dále položku 'montáž' (procento) a 'adresa' (text). "
        "Vrať pouze validní JSON objekt:\n"
        "{"
        "\"polozky\": [{\"produkt\":\"...\",\"šířka\":...,\"hloubka_výška\":...}], "
        "\"montáž_procent\": 12, "
        "\"adresa\": \"Praha\"}"
    )

    try:
        import openai
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role":"system","content": system_prompt},
                {"role":"user","content": user_text}
            ],
            max_tokens=800
        )
        raw = resp.choices[0].message.content.strip()
        log("📨 GPT RAW:\n" + raw)
        parsed = json.loads(raw)
    except Exception as e:
        log(f"❌ GPT chyba: {e}")
        parsed = {}

    items = parsed.get("polozky", [])
    montaz_pct = parsed.get("montáž_procent", None)
    destination = parsed.get("adresa", "")

    results = []
    for it in items:
        try:
            produkt = str(it["produkt"]).strip()
            w = int(float(it["šířka"]))
            h = int(float(it["hloubka_výška"]))
        except Exception as e:
            log(f"❌ Položka špatný formát: {it} ({e})")
            continue
        df_mat = st.session_state.CENIKY.get(produkt.lower())
        if df_mat is None:
            log(f"❌ Ceník nenalezen: {produkt}")
            continue
        use_w, use_h, price = find_price(df_mat, w, h)
        if pd.isna(price): continue
        results.append({
            "Produkt": produkt,
            "Rozměr (požadovaný)": f"{w}×{h}",
            "Rozměr (použitý)": f"{use_w}×{use_h}",
            "Cena bez DPH": float(price)
        })

    if results:
        df_results = pd.DataFrame(results)
        st.success(f"✅ Nalezeno {len(results)} položek.")
        st.dataframe(df_results, use_container_width=True)

        total_price = df_results["Cena bez DPH"].sum()

        # Montáž
        if montaz_pct:
            assembly_rates = [montaz_pct]
        else:
            assembly_rates = [12, 13, 14, 15]
        assembly_data = [
            {"Varianta montáže": f"{r} %", "Cena montáže (Kč)": round(total_price * r / 100, 2)}
            for r in assembly_rates
        ]

        # Doprava
        if destination:
            distance_km, cost_transport = calculate_transport_cost(destination)
        else:
            distance_km, cost_transport = (0.0, 0.0)
            log("⚠️ Nebyla zadána adresa – doprava přeskočena.")

        st.markdown("### 🚚 Doprava a montáž")
        st.write(f"**Adresa:** {destination or 'neuvedena'}")
        if destination:
            st.write(f"**Doprava:** {distance_km:.1f} km × 2 × 150 Kč = **{cost_transport:.0f} Kč**")
        st.dataframe(pd.DataFrame(assembly_data), use_container_width=True)

        st.markdown("---")
        st.markdown(f"**Součet produktů:** {total_price:,.0f} Kč")
        st.markdown(f"**Doprava:** {cost_transport:,.0f} Kč")
        st.markdown(f"**Celkem bez DPH:** {total_price + cost_transport:,.0f} Kč")
    else:
        st.info("Nenalezena žádná ocenitelná položka.")

# ===============================
# DEBUG PANEL
# ===============================
st.markdown("---")
st.subheader("🛠️ Debug panel")
show_log()
