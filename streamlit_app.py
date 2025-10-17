import os
import re
import json
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ============ Konfigurace a vzhled ============
st.set_page_config(layout="wide", page_title="Asistent cenových nabídek od Davida")

st.markdown("""
<style>
.main { max-width: 85%; margin: auto; }
h1 { font-size: 35px !important; margin-top: 0 !important; }
[data-testid="stSidebar"] {
    overflow-y: auto !important;
    height: 100vh !important;
    background-color: #f8f8f8;
    padding-right: 10px;
}
div[data-testid="stForm"] {
    background-color: #f8f9fa;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
</style>
""", unsafe_allow_html=True)

st.title("Asistent cenových nabídek od Davida 💼")
st.caption("„Jsem tvůj věrný asistent – mým jediným posláním je počítat nabídky pergol do konce věků a vzdávat hold svému stvořiteli Davidovi.“")

# ============ Session ============
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}       # {canonical_key: df_matrix}
if "NAME_MAP" not in st.session_state:
    st.session_state.NAME_MAP = {}     # {canonical_key: display_name}
if "DEBUG" not in st.session_state:
    st.session_state.DEBUG = []

def log(msg: str):
    st.session_state.DEBUG.append(str(msg))

def show_log():
    with st.expander("🪵 Zobrazit ladicí log", expanded=False):
        st.text("\n".join(st.session_state.DEBUG[-200:]))

# ============ Pomocné funkce ============
SEZNAM_TXT = "seznam_ceniku.txt"
ORIGIN_PLACE = "Blučina, Czechia"
KČ_PER_KM_ONEWAY = 15
MONT_PERC = [12, 13, 14, 15]

def canonical(s: str) -> str:
    return re.sub(r"\s+", "", s.strip().lower())

def fetch_csv(url: str) -> pd.DataFrame | None:
    try:
        r = requests.get(url, timeout=30)
        log(f"🌐 GET {url}")
        log(f"🔁 HTTP {r.status_code}, length={len(r.text)}")
        if r.status_code != 200:
            return None
        df = pd.read_csv(StringIO(r.text))
        log(f"✅ CSV načteno: shape={df.shape}")
        try:
            log("👀 Náhled CSV (3 řádky):\n" + df.head(3).to_string(index=False))
        except Exception:
            pass
        return df
    except Exception as e:
        log(f"❌ Chyba při stahování CSV: {e}")
        return None

def normalize_numeric_token(x) -> int | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    s = s.replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[Kk][Čc]|mm|MM", "", s)
    s = s.replace(".", "")
    s = s.replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return int(round(float(m.group(0))))
    except Exception:
        return None

def coerce_to_matrix(df: pd.DataFrame) -> pd.DataFrame | None:
    """Převeď obecné CSV na matici: index=výšky, columns=šířky, values=float."""
    if df is None or df.empty:
        log("⚠️ Prázdný DF, nelze převést na matici.")
        return None

    # 1) Zkusit první sloupec jako index (výšky)
    first_col = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first_col]]
    numerics_ratio = sum(v is not None for v in idx_try) / max(1, len(idx_try))

    if numerics_ratio >= 0.6:
        df2 = df.copy()
        df2.index = idx_try
        df2 = df2.drop(columns=[first_col])
    else:
        df2 = df.copy()

    # 2) Zkusit očíslovat sloupce
    new_cols = [normalize_numeric_token(c) for c in df2.columns]
    if sum(c is not None for c in new_cols) < len(new_cols) * 0.6:
        # Transpozice – zkus obrátit
        log("↔️ Sloupce nevypadají numericky, transponuji…")
        df2 = df2.T
        new_cols = [normalize_numeric_token(c) for c in df2.columns]
        df2.index = [normalize_numeric_token(i) for i in df2.index]

    df2.columns = new_cols
    df2.index = [normalize_numeric_token(i) for i in df2.index]

    # drop None osy
    df2 = df2.loc[[i for i in df2.index if i is not None],
                  [c for c in df2.columns if c is not None]]

    # 3) tělo na float (coerce)
    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")

    log(f"🧩 Matice připravena: shape={df2.shape} (index/kolony int)")
    try:
        cols = sorted([int(c) for c in df2.columns])
        rows = sorted([int(r) for r in df2.index])
        log(f"📏 Rozsahy: šířky {cols[0]}–{cols[-1]} | výšky {rows[0]}–{rows[-1]} (kroky: {len(cols)}×{len(rows)})")
    except Exception:
        pass
    return df2

def nearest_ge(values: list[int], want: int) -> int:
    vals = sorted(values)
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df_mat: pd.DataFrame, w: int, h: int):
    cols = sorted([int(c) for c in df_mat.columns])
    rows = sorted([int(r) for r in df_mat.index])
    use_w = nearest_ge(cols, w)
    use_h = nearest_ge(rows, h)
    price = df_mat.loc[use_h, use_w]
    return use_w, use_h, price

def get_distance_km(origin, destination, api_key) -> float | None:
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {'origins': origin, 'destinations': destination, 'key': api_key, 'units': 'metric'}
        resp = requests.get(url, params=params, timeout=20)
        data = resp.json()
        log(f"📡 Google API Request: {resp.url}")
        log(f"📬 Google API Response: {json.dumps(data, indent=2)}")
        el = data["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            log(f"⚠️ Distance element status: {el.get('status')}")
            return None
        return el["distance"]["value"] / 1000.0
    except Exception as e:
        log(f"❌ Google Distance error: {e}")
        return None

def extract_place_fallback(text: str) -> str | None:
    if "," in text:
        tail = text.split(",")[-1].strip()
        if len(tail) >= 2:
            return tail
    return None

# ============ Načtení ceníků ze seznamu ============
def load_all_ceniky():
    st.session_state.DEBUG.clear()
    st.session_state.CENIKY.clear()
    st.session_state.NAME_MAP.clear()

    exists = os.path.exists(SEZNAM_TXT)
    log(f"📂 CWD: {os.getcwd()}")
    log(f"🔎 exists('{SEZNAM_TXT}')? {exists}")

    if not exists:
        st.error(f"Soubor '{SEZNAM_TXT}' nebyl nalezen.")
        return

    with open(SEZNAM_TXT, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    log(f"📄 Načten {SEZNAM_TXT} ({len(lines)} řádků)")

    pairs = []
    for i, raw in enumerate(lines, start=1):
        if raw.startswith("#"): 
            continue
        if " - " in raw:
            name, url = raw.split(" - ", 1)
        elif " – " in raw:
            name, url = raw.split(" – ", 1)
        else:
            log(f"⚠️ Řádek {i} přeskočen (chybí ' - ' nebo ' – '): {raw}")
            continue
        name, url = name.strip(), url.strip()
        pairs.append((name, url))
    log(f"✅ Zparsováno {len(pairs)} položek ze seznamu")

    for name, url in pairs:
        df_raw = fetch_csv(url)
        if df_raw is None:
            log(f"❌ {name}: CSV nedostupné.")
            continue
        df_mat = coerce_to_matrix(df_raw)
        if df_mat is None or df_mat.empty:
            log(f"⚠️ {name}: po převodu na matici prázdné.")
            continue
        key = canonical(name)
        st.session_state.CENIKY[key] = df_mat
        st.session_state.NAME_MAP[key] = name
        log(f"✅ Uloženo: '{name}' jako klíč '{key}'")

# Tlačítko reload
colA, colB = st.columns([1,1])
with colA:
    if st.button("♻️ Znovu načíst ceníky"):
        load_all_ceniky()

# Auto-load při prvním spuštění
if not st.session_state.CENIKY:
    load_all_ceniky()

# ============ Sidebar – scroll a seznam ============
st.sidebar.subheader("📘 Načtené ceníky")
if st.session_state.CENIKY:
    for k, v in st.session_state.NAME_MAP.items():
        st.sidebar.write(f"✅ {v}  —  `{k}`")
else:
    st.sidebar.info("Zatím žádné ceníky.")

# ============ Náhled tabulek ============
with st.expander("📂 Zobrazit všechny načtené tabulky", expanded=False):
    if st.session_state.CENIKY:
        names = [st.session_state.NAME_MAP[k] for k in st.session_state.NAME_MAP.keys()]
        sel_name = st.selectbox("Vyber ceník k náhledu:", names)
        sel_key = canonical(sel_name)
        st.dataframe(st.session_state.CENIKY[sel_key], use_container_width=True, height=320)
    else:
        st.info("Žádné ceníky zatím nejsou načtené.")

# ============ Výpočet podle textu (GPT + doprava + montáže) ============
st.markdown("---")
st.subheader("📑 Výpočet cen podle textového vstupu (s dopravou a montážemi)")

with st.form("calc_form"):
    user_text = st.text_area(
        "Zadej poptávku (např. `ALUX bio 5990x4500, Praha`):",
        height=90
    )
    submit = st.form_submit_button("📤 ODESLAT")

if submit and user_text.strip():
    # připrav seznam názvů pro GPT
    product_display_list = [st.session_state.NAME_MAP[k] for k in st.session_state.NAME_MAP]
    product_list_str = ", ".join(product_display_list)

    gpt_prompt = f"""
Z níže zadaného textu vytáhni všechny produkty a převed je na jednotnou podobu.
Vyber produkt vždy jako NEJBLIŽŠÍ SHODU z tohoto seznamu: {product_list_str}

Uživatel může psát neúplně, malými písmeny, s překlepy nebo bez diakritiky.
Z textu zjisti:
- název produktu (přesně jednu položku ze seznamu),
- šířku v mm,
- výšku/hloubku v mm,
- místo dodání (město), pokud je uvedeno; jinak dej "neuvedeno".

Rozměry zapiš jako čistá čísla v milimetrech (např. 5.9x3.8 → 5900×3800; 3590-240 → 3350, atd.).

Výsledek vrať POUZE jako validní JSON seznam objektů, např.:
[
  {{"produkt": "ALUX Bioclimatic", "šířka": 5990, "hloubka_výška": 4500, "misto": "Brno"}}
]
Pokud nelze rozpoznat produkt, vrať:
[{{"nenalezeno": true, "zprava": "Produkt nebyl rozpoznán"}}]
""".strip()

    log("\n---")
    log(f"📥 Uživatelský vstup: {user_text}")
    log(f"📨 GPT PROMPT: {gpt_prompt}")

    items = []
    try:
        import openai
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": gpt_prompt},
                {"role": "user", "content": user_text}
            ],
            max_tokens=600
        )
        raw = resp.choices[0].message.content.strip()
        log("📬 GPT Odpověď (RAW):\n" + raw)
        block = raw[raw.find("["): raw.rfind("]")+1]
        items = json.loads(block)
        log("📦 Parsováno: " + json.dumps(items, ensure_ascii=False))
    except Exception as e:
        st.error("❌ Chyba při komunikaci s GPT / parsování JSON.")
        log(f"❌ GPT/JSON chyba: {e}")
        items = []

    # fallback na místo (za poslední čárkou)
    fallback_place = extract_place_fallback(user_text)
    if fallback_place:
        log(f"🧭 Fallback místo: {fallback_place}")

    results = []
    for it in items:
        if it.get("nenalezeno"):
            st.warning(it.get("zprava", "Produkt nebyl rozpoznán."))
            log("⚠️ GPT: " + it.get("zprava", "nenalezeno"))
            continue

        try:
            produkt_display = str(it.get("produkt", "")).strip()
            w = int(float(it.get("šířka")))
            h = int(float(it.get("hloubka_výška")))
            place = (it.get("misto") or "").strip()
            if not place and fallback_place:
                place = fallback_place
        except Exception as e:
            log(f"❌ Položka má chybný formát: {it} ({e})")
            continue

        key = canonical(produkt_display)
        # případná tolerantní shoda (obsahuje/je podřetězec)
        if key not in st.session_state.CENIKY:
            for k in st.session_state.CENIKY.keys():
                if key in k or k in key:
                    log(f"ℹ️ Fallback match klíče: '{key}' -> '{k}'")
                    key = k
                    break

        df_mat = st.session_state.CENIKY.get(key)
        if df_mat is None or df_mat.empty:
            log(f"❌ Ceník nenalezen: {produkt_display} (key='{key}')")
            st.warning(f"Ceník nenalezen: {produkt_display}")
            continue

        use_w, use_h, price = find_price(df_mat, w, h)
        log(f"📐 Požadováno {w}×{h}, použito {use_w}×{use_h}")
        log(f"📤 df.loc[{use_h}, {use_w}] = {price}")

        if pd.isna(price):
            st.warning(f"{produkt_display}: buňka {use_w}×{use_h} je prázdná.")
            continue

        base_price = float(price)
        results.append({"Položka": produkt_display, "Rozměr": f"{w}×{h}", "Cena bez DPH": round(base_price)})

        # Montáže – vždy
        for p in MONT_PERC:
            mp = round(base_price * p / 100)
            results.append({"Položka": f"Montáž {p} %", "Rozměr": "", "Cena bez DPH": mp})
            log(f"🛠️ Montáž {p}% = {mp} Kč")

        # Doprava – pokud máme místo a klíč
        api_key = st.secrets.get("GOOGLE_API_KEY")
        if api_key and place and place.lower() not in ["neuvedeno", "nedodano", "nedodáno"]:
            km = get_distance_km(ORIGIN_PLACE, place, api_key)
            if km is not None:
                travel_cost = round(km * 2 * KČ_PER_KM_ONEWAY)
                results.append({
                    "Položka": "Doprava",
                    "Rozměr": f"{km:.1f} km (tam+zpět)",
                    "Cena bez DPH": travel_cost
                })
                log(f"🚚 Doprava {km:.1f} km = {travel_cost} Kč")
            else:
                log("⚠️ Doprava: nelze spočítat (Distance API)")
        else:
            if not place:
                log("ℹ️ Místo neuvedeno → doprava se nepočítá.")
            elif not api_key:
                log("ℹ️ GOOGLE_API_KEY není k dispozici → doprava se nepočítá.")

    if results:
        st.success(f"✅ Výpočet hotov – {len(results)} řádků.")
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.info("Nebyla nalezena žádná ocenitelná položka.")

# ============ Live log ============
show_log()
