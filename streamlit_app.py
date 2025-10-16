import os
import json
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ===============================
# ZÁKLAD
# ===============================
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – s dopravou")

# Session
if "LOG" not in st.session_state:
    st.session_state.LOG = []
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}   # dict[str(lower) -> DataFrame]
if "PRODUKTY" not in st.session_state:
    st.session_state.PRODUKTY = [] # hezké názvy pro prompt

def log(msg: str):
    st.session_state.LOG.append(str(msg))

def show_log():
    st.text_area("🪵 Live log", value="\n".join(st.session_state.LOG), height=320)

# ===============================
# POMOCNÉ FUNKCE
# ===============================
SEZNAM_PATH = "seznam_ceniku.txt"
ORIGIN_PLACE = "Blučina, Czechia"
Kc_per_km_oneway = 15  # Kč / km (jednosměrně). Celkem počítáme tam+zpět → *2

def cwd_and_existence_probe():
    log(f"📂 CWD: {os.getcwd()}")
    log(f"🔎 exists('{SEZNAM_PATH}')? {os.path.exists(SEZNAM_PATH)}")

def read_seznam_ceniku():
    pairs = []
    try:
        with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        log(f"📄 Načten {SEZNAM_PATH} ({len(lines)} řádků)")
        for i, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if " - " in line:
                name, url = line.split(" - ", 1)
            elif " – " in line:
                name, url = line.split(" – ", 1)
            else:
                log(f"⚠️ Řádek {i} přeskočen (chybí ' - ' nebo ' – '): {raw}")
                continue
            name = name.strip()
            url = url.strip()
            if not name or not url:
                log(f"⚠️ Řádek {i} má prázdný název/URL: {raw}")
                continue
            pairs.append((name, url))
        log(f"✅ Zparsováno {len(pairs)} položek ze seznamu")
    except Exception as e:
        log(f"❌ Chyba při čtení '{SEZNAM_PATH}': {e}")
        st.error(f"Soubor '{SEZNAM_PATH}' chybí nebo nejde číst.")
    return pairs

def fetch_csv(url: str) -> pd.DataFrame | None:
    try:
        log(f"🌐 GET {url}")
        r = requests.get(url, timeout=30)
        log(f"🔁 HTTP {r.status_code}, {len(r.text)} znaků")
        if r.status_code != 200:
            return None
        df = pd.read_csv(StringIO(r.text))
        log(f"✅ CSV načteno: shape={df.shape}")
        log("👀 Náhled CSV (3 řádky):\n" + df.head(3).to_string(index=False))
        return df
    except Exception as e:
        log(f"❌ Chyba při stahování CSV: {e}")
        return None

def normalize_numeric_token(x) -> int | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    s = s.replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[Kk][Čc]|\s*mm|\s*MM", "", s)
    s = s.replace(".", "")
    s = s.replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        val = float(m.group(0))
        return int(round(val))
    except Exception:
        return None

def coerce_matrix(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        log("⚠️ Prázdný DF, nelze převést na matici.")
        return None
    first_col = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first_col]]
    numerics_ratio = sum(v is not None for v in idx_try) / max(1, len(idx_try))
    if numerics_ratio > 0.6:
        df2 = df.copy()
        df2.index = idx_try
        df2 = df2.drop(columns=[first_col])
    else:
        df2 = df.copy()
    new_cols = [normalize_numeric_token(c) for c in df2.columns]
    if sum(c is not None for c in new_cols) < len(new_cols) * 0.6:
        log("↔️ Sloupce nevypadají numericky, transponuji…")
        df2 = df2.T
        new_cols = [normalize_numeric_token(c) for c in df2.columns]
        df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2.columns = new_cols
    df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2 = df2.loc[[i for i in df2.index if i is not None],
                  [c for c in df2.columns if c is not None]]
    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")
    log(f"🧩 Matice připravena: shape={df2.shape}")
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

# Google Distance Matrix
def get_distance_km(origin: str, destination: str, api_key: str) -> float | None:
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin, "destinations": destination,
            "key": api_key, "units": "metric"
        }
        log(f"📡 Google API Request: {url}?origins={origin}&destinations={destination}&units=metric")
        r = requests.get(url, params=params, timeout=20)
        log(f"📬 Google API HTTP {r.status_code}")
        data = r.json()
        # pro přehlednost jen shrnutí
        try:
            summary = {
                "status": data.get("status"),
                "rows": len(data.get("rows", [])),
                "elements_status": (
                    data["rows"][0]["elements"][0].get("status")
                    if data.get("rows") and data["rows"][0].get("elements") else "?"
                )
            }
            log(f"📦 Google API Summary: {summary}")
        except Exception:
            pass
        if r.status_code != 200:
            return None
        el = data["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            log(f"⚠️ Distance element status: {el.get('status')}")
            return None
        meters = el["distance"]["value"]
        km = meters / 1000.0
        log(f"🛣️ Distance = {km:.2f} km")
        return km
    except Exception as e:
        log(f"❌ Distance API error: {e}")
        return None

def extract_place_from_input(user_text: str) -> str | None:
    # pokus: vezmi text za POSLEDNÍ čárkou
    if "," in user_text:
        tail = user_text.split(",")[-1].strip()
        # krátké validace
        if len(tail) >= 2:
            return tail
    return None

# ===============================
# NAČTENÍ CENÍKŮ
# ===============================
def load_all_ceniky():
    st.session_state.LOG.clear()
    cwd_and_existence_probe()
    pairs = read_seznam_ceniku()
    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()
    for name, url in pairs:
        raw = fetch_csv(url)
        if raw is None:
            log(f"❌ {name}: CSV nedostupné.")
            continue
        mat = coerce_matrix(raw)
        if mat is None or mat.empty:
            log(f"⚠️ {name}: po převodu na matici je DF prázdný.")
            continue
        st.session_state.CENIKY[name.lower()] = mat
        st.session_state.PRODUKTY.append(name)
        try:
            cols = sorted([int(c) for c in mat.columns])
            rows = sorted([int(r) for r in mat.index])
            log(f"📏 {name}: šířky {cols[0]}–{cols[-1]} | výšky {rows[0]}–{rows[-1]} (kroků: {len(cols)}×{len(rows)})")
        except Exception:
            pass

colA, colB = st.columns([1,1])
with colA:
    if st.button("♻️ Znovu načíst ceníky"):
        load_all_ceniky()

if not st.session_state.CENIKY:
    load_all_ceniky()

# ===============================
# NÁHLED VŠECH TABULEK
# ===============================
with st.expander("📂 Zobrazit všechny načtené tabulky"):
    if not st.session_state.CENIKY:
        st.info("Zatím nic nenalezeno – zkontroluj 'seznam_ceniku.txt' a klikni na 'Znovu načíst ceníky'.")
    else:
        for name in st.session_state.PRODUKTY:
            df = st.session_state.CENIKY.get(name.lower())
            st.markdown(f"#### {name}")
            if df is not None:
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Ceník není načten.")

# ===============================
# VÝPOČET CEN + DOPRAVA (TEXTOVÝ VSTUP)
# ===============================
st.markdown("---")
st.subheader("📝 Výpočet cen podle textového vstupu (s dopravou)")

with st.form("calc_form"):
    user_text = st.text_area(
        "Zadej poptávku (např. `ALUX Bioclimatic 5990x4500, Praha`):",
        height=100
    )
    submitted = st.form_submit_button("📤 ODESLAT")

if submitted and user_text.strip():
    log("\n---")
    log(f"📥 Uživatelský vstup:\n{user_text}")

    product_list = ", ".join(st.session_state.PRODUKTY) if st.session_state.PRODUKTY else "screen"
    system_prompt = (
        "Tvůj úkol: z následujícího textu vytáhni VŠECHNY položky s názvem produktu, šířkou (mm), výškou (mm) "
        "a MÍSTEM dodání (pokud je uvedeno). Název produktu vybírej co nejpřesněji z tohoto seznamu: "
        f"{product_list}. Fráze jako 'screen', 'screenová roleta' přiřaď k produktu 'screen'. "
        "Rozměry jako 3500-250 nejprve spočítej a výstup dej jako čistá čísla v mm. "
        "Místo vrať jako text, pokud v zadání není, dej prázdný řetězec. "
        "Vrať POUZE validní JSON list, např. "
        "[{\"produkt\":\"ALUX Bioclimatic\",\"šířka\":5990,\"hloubka_výška\":4500,\"misto\":\"Praha\"}]"
    )
    # --- GPT
    items = []
    try:
        import openai
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role":"system","content": system_prompt},
                {"role":"user","content": user_text}
            ],
            max_tokens=600
        )
        raw = resp.choices[0].message.content.strip()
        log("📨 GPT odpověď (RAW):\n" + raw)
        try:
            items = json.loads(raw)
        except Exception as e:
            log(f"❌ JSON decode chyba: {e}")
            items = []
    except Exception as e:
        log(f"❌ GPT chyba: {e}")
        items = []

    # Fallback extrakce místa z textu (za poslední čárkou), pokud GPT nedá
    fallback_place = extract_place_from_input(user_text)
    if fallback_place:
        log(f"🧭 Fallback místo z textu: {fallback_place}")

    # zpracování položek
    results = []
    for it in items:
        try:
            produkt = str(it.get("produkt", "")).strip()
            w = int(float(it.get("šířka")))
            h = int(float(it.get("hloubka_výška")))
            place = (it.get("misto") or "").strip()
            if not place and fallback_place:
                place = fallback_place
        except Exception as e:
            log(f"❌ Položka má špatný formát: {it} ({e})")
            continue

        df_mat = st.session_state.CENIKY.get(produkt.lower())
        if df_mat is None:
            log(f"❌ Ceník nenalezen: {produkt}")
            continue

        use_w, use_h, price = find_price(df_mat, w, h)
        log(f"📐 Požadováno {w}×{h}, použito {use_w}×{use_h}")
        log(f"📤 df.loc[{use_h}, {use_w}] = {price}")
        if pd.isna(price):
            st.warning(f"{produkt}: {w}×{h} → {use_w}×{use_h}: buňka je prázdná (NaN).")
            continue

        item_rows = []
        item_rows.append({
            "Položka": produkt,
            "Rozměr": f"{w}×{h}",
            "Poznámka": "",
            "Cena bez DPH": float(price)
        })

        # DOPRAVA (pokud máme místo a API KEY)
        api_key = st.secrets.get("GOOGLE_API_KEY")
        if place and api_key:
            km = get_distance_km(ORIGIN_PLACE, place, api_key)
            if km is not None:
                # tam i zpět
                travel_cost = round(km * 2 * Kc_per_km_oneway)
                item_rows.append({
                    "Položka": "Doprava",
                    "Rozměr": f"{km:.1f} km (tam+zpět)",
                    "Poznámka": f"{ORIGIN_PLACE} → {place}",
                    "Cena bez DPH": travel_cost
                })
                log(f"🚚 Doprava: {km:.1f} km → {travel_cost} Kč")
            else:
                log("⚠️ Dopravu nelze spočítat (Distance API)")
        else:
            if not place:
                log("ℹ️ Místo neuvedeno, doprava se nepočítá.")
            elif not api_key:
                log("ℹ️ Chybí GOOGLE_API_KEY, doprava se nepočítá.")

        results.extend(item_rows)

    if results:
        st.success(f"Hotovo – {len(results)} položek.")
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.info("Nebyla nalezena žádná ocenitelná položka (zkontroluj vstup nebo ceník).")

# ===============================
# DEBUG PANEL
# ===============================
st.markdown("---")
st.subheader("🛠️ Debug panel")
show_log()
