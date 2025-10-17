import streamlit as st
import pandas as pd
import openai
import json
import requests
import re
from datetime import datetime

# === ZÁKLADNÍ NASTAVENÍ ===
st.set_page_config(layout="wide", page_title="Asistent cenových nabídek od Davida")

st.markdown("""
<style>
.main { max-width: 85%; margin: auto; }
h1 { font-size: 32px !important; margin-top: 0 !important; }
.subtitle { font-size: 12px; color: #777; margin-bottom: 30px; font-style: italic; }
</style>
""", unsafe_allow_html=True)

st.title("Asistent cenových nabídek od Davida")
st.markdown('<div class="subtitle">Tvůj věrný výpočetní služebník, který s radostí počítá pergoly do roztrhání těla.</div>', unsafe_allow_html=True)

# === STAVY ===
if "logs" not in st.session_state:
    st.session_state.logs = []
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}
if "NAME_MAP" not in st.session_state:
    st.session_state.NAME_MAP = {}
if "results" not in st.session_state:
    st.session_state.results = []

def log(msg: str):
    """Zápis do live logu s časem."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    st.session_state.logs.append(line)

# === LOG STARTU PROGRAMU ===
log("==== Start programu ====")

# === Načtení seznamu ceníků ===
log("Načítám seznam ceníků...")
ceniky = {}

with open("seznam_ceniku.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            log(f"⚠️ Řádek přeskočen (chybí '='): {line}")
            continue

        try:
            name, link = line.split("=", 1)
            name = name.strip()
            link = link.strip().strip('"')
            if not link.startswith("http"):
                log(f"⚠️ Neplatný odkaz u {name}: {link}")
                continue
            ceniky[name] = link
        except Exception as e:
            log(f"❌ Chyba při parsování řádku '{line}': {e}")

log(f"✅ Načten seznam_ceniku.txt ({len(ceniky)} řádků)")
        return

    loaded = []
    for line in lines:
        if "-" not in line:
            continue
        name, link = [x.strip() for x in line.split("-", 1)]
        log(f"Načítám ceník: {name} z {link}")
        try:
            df = pd.read_csv(link)
            df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
            if "Unnamed: 0" in df.columns:
                df = df.rename(columns={"Unnamed: 0": "index"}).set_index("index")

            df = df.loc[df.index.dropna()]
            df.index = pd.to_numeric(df.index, errors="coerce").dropna().astype(int)
            df.columns = pd.to_numeric(df.columns, errors="coerce")
            df = df.loc[:, ~df.columns.isna()]
            df.columns = df.columns.astype(int)

            key = re.sub(r"\s+", "", name.lower())
            st.session_state.CENIKY[key] = df
            st.session_state.NAME_MAP[key] = name
            loaded.append((name, df))
            log(f"Ceník {name} načten: {df.shape[0]} řádků, {df.shape[1]} sloupců")
        except Exception as e:
            log(f"Chyba při načítání {name}: {e}")

    # === VÝPIS DO APLIKACE ===
    if loaded:
        with st.expander("📘 Načtené ceníky (rozklikni pro zobrazení všech)", expanded=False):
            for name, df in loaded:
                st.markdown(f"#### {name} ({df.shape[0]} × {df.shape[1]})")
                st.dataframe(df, use_container_width=True)
        log("Všechny ceníky načteny a zobrazeny v expanderu.")
    else:
        st.warning("Nebyl načten žádný ceník.")
        log("Nebyl načten žádný ceník.")

load_pricelists()

# === FORMULÁŘ ===
st.subheader("Zadejte popis poptávky")
user_input = st.text_area("Např.: ALUX Bioclimatic 5990x4500 Praha", height=90)
submit = st.button("📤 ODESLAT")

# === FUNKCE ===
def find_price(df: pd.DataFrame, w: int, h: int):
    log(f"Hledám cenu v tabulce pro {w} × {h}")
    cols = sorted([int(c) for c in df.columns])
    rows = sorted([int(r) for r in df.index])
    use_w = next((c for c in cols if c >= w), cols[-1])
    use_h = next((r for r in rows if r >= h), rows[-1])
    val = df.loc[use_h, use_w]
    log(f"Vybraná buňka df.loc[{use_h}, {use_w}] = {val}")
    return use_w, use_h, val

def get_distance_km(origin, destination, api_key):
    log(f"Volám Distance Matrix API: {origin} → {destination}")
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {"origins": origin, "destinations": destination, "key": api_key, "units": "metric"}
    r = requests.get(url, params=params)
    data = r.json()
    try:
        km = data["rows"][0]["elements"][0]["distance"]["value"] / 1000
        log(f"Vzdálenost: {km} km")
        return km
    except Exception as e:
        log(f"Chyba při výpočtu vzdálenosti: {e}")
        return None

# === HLAVNÍ VÝPOČET ===
if submit and user_input:
    log("=== NOVÝ POŽADAVEK ===")
    log(f"Uživatelský vstup: {user_input}")

    available_names = [st.session_state.NAME_MAP[k] for k in st.session_state.NAME_MAP]
    gpt_prompt = f"""
Z následujícího textu vytáhni produkty, šířky a výšky.
Název produktu vybírej POUZE z tohoto seznamu:
{", ".join(available_names)}

POKUD nenajdeš přesnou shodu, vrať:
[{{"nenalezeno": true, "zprava": "Produkt nebyl rozpoznán, upřesněte název."}}]

Vracíš POUZE JSON pole ve formátu:
[{{"produkt": "...", "šířka": ..., "hloubka_výška": ..., "misto": "..."}}]
    """.strip()

    log("Volám GPT pro analýzu vstupu...")
    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        gpt_response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": gpt_prompt},
                {"role": "user", "content": user_input}
            ],
            max_tokens=800
        )
        gpt_output_raw = gpt_response.choices[0].message.content.strip()
        log(f"GPT odpověď RAW: {gpt_output_raw}")

        start = gpt_output_raw.find('[')
        end = gpt_output_raw.rfind(']') + 1
        gpt_output_clean = gpt_output_raw[start:end]
        items = json.loads(gpt_output_clean)
        log(f"Parsováno JSON: {items}")

    except Exception as e:
        log(f"Chyba GPT: {e}")
        items = []

    # === ZPRACOVÁNÍ ===
    results = []
    for p in items:
        if p.get("nenalezeno"):
            log("Produkt nebyl rozpoznán, GPT žádá upřesnění.")
            continue

        product = p["produkt"]
        key = re.sub(r"\s+", "", product.lower())

        if key not in st.session_state.CENIKY:
            log(f"Ceník {product} nenalezen v seznamu.")
            continue

        df = st.session_state.CENIKY[key]
        w = int(float(p["šířka"]))
        h = int(float(p["hloubka_výška"]))
        use_w, use_h, price = find_price(df, w, h)

        if pd.isna(price):
            log(f"Chybí cena pro {w}×{h} v {product}")
            continue

        base_price = float(price)
        log(f"Základní cena: {base_price} Kč")

        rows = [{"Položka": product, "Rozměr": f"{w}×{h}", "Cena bez DPH": round(base_price)}]

        for perc in [12, 13, 14, 15]:
            rows.append({"Položka": f"Montáž {perc} %", "Rozměr": "", "Cena bez DPH": round(base_price * perc / 100)})

        place = p.get("misto", "").strip()
        if place and place.lower() not in ["neuvedeno", "nedodano"]:
            api_key = st.secrets.get("GOOGLE_API_KEY", "")
            if api_key:
                km = get_distance_km("Blučina, Czechia", place, api_key)
                if km:
                    travel_cost = round(km * 2 * 15)
                    rows.append({"Položka": "Doprava", "Rozměr": f"{km:.1f} km", "Cena bez DPH": travel_cost})
                    log(f"Doprava {km:.1f} km → {travel_cost} Kč")

        results.extend(rows)

    if results:
        df_out = pd.DataFrame(results)
        st.session_state.results.append(df_out)
        st.success("Výpočet dokončen, výsledek uložen do historie.")
    else:
        st.warning("Bez výsledků, pravděpodobně chybí shoda nebo cena.")

# === HISTORIE VÝSLEDKŮ ===
if st.session_state.results:
    st.subheader("📊 Historie výpočtů")
    for i, df in enumerate(st.session_state.results):
        st.markdown(f"**Výpočet {i+1}**")
        st.dataframe(df, use_container_width=True)

# === SIDEBAR LOG ===
with st.sidebar.expander("🧠 Log aplikace (live)", expanded=True):
    st.text("\n".join(st.session_state.logs))
