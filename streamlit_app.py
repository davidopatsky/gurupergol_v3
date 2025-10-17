import streamlit as st
import pandas as pd
import openai
import json
import requests
import re

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

def log(msg: str):
    """Zápis do live logu."""
    st.session_state.logs.append(msg)

# === NAČTENÍ SEZNAMU CENÍKŮ ===
def load_pricelists():
    loaded = []
    try:
        with open("seznam_ceniku.txt", "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    except Exception as e:
        st.error(f"❌ Nelze načíst seznam_ceniku.txt: {e}")
        return

    log(f"📄 Načten seznam_ceniku.txt ({len(lines)} řádků)")
    for line in lines:
        if "-" not in line:
            continue
        name, link = [x.strip() for x in line.split("-", 1)]
        log(f"🌐 Načítám {name} – {link}")
        try:
            df = pd.read_csv(link)

            # očista dat
            df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
            if "Unnamed: 0" in df.columns:
                df = df.rename(columns={"Unnamed: 0": "index"}).set_index("index")

            # filtruj jen čísla v indexech a sloupcích
            df = df.loc[df.index.dropna()]
            df.index = pd.to_numeric(df.index, errors="coerce").dropna().astype(int)
            df.columns = pd.to_numeric(df.columns, errors="coerce")
            df = df.loc[:, ~df.columns.isna()]
            df.columns = df.columns.astype(int)

            key = re.sub(r"\s+", "", name.lower())
            st.session_state.CENIKY[key] = df
            st.session_state.NAME_MAP[key] = name
            log(f"✅ Ceník načten: {name} ({df.shape})")
            loaded.append((name, df))
        except Exception as e:
            log(f"❌ Chyba při načítání {name}: {e}")

    # 📘 Výpis všech ceníků v collapsible formě
    if loaded:
        st.subheader("📘 Načtené ceníky")
        for name, df in loaded:
            with st.expander(f"🔹 {name} ({df.shape[0]} řádků × {df.shape[1]} sloupců)", expanded=False):
                st.dataframe(df, use_container_width=True)
    else:
        st.warning("❗ Žádné ceníky nebyly načteny. Zkontrolujte seznam_ceniku.txt.")

load_pricelists()

# === FORMULÁŘ ===
st.subheader("Zadejte popis poptávky")
user_input = st.text_area("Např.: ALUX Bioclimatic 5990x4500 Praha", height=90)
submit = st.button("📤 ODESLAT")

# === FUNKCE VÝPOČTU ===
def find_price(df: pd.DataFrame, w: int, h: int):
    cols = sorted([int(c) for c in df.columns])
    rows = sorted([int(r) for r in df.index])
    use_w = next((c for c in cols if c >= w), cols[-1])
    use_h = next((r for r in rows if r >= h), rows[-1])
    val = df.loc[use_h, use_w]
    return use_w, use_h, val

def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {"origins": origin, "destinations": destination, "key": api_key, "units": "metric"}
    r = requests.get(url, params=params)
    data = r.json()
    try:
        km = data["rows"][0]["elements"][0]["distance"]["value"] / 1000
        return km
    except Exception:
        return None

# === HLAVNÍ LOGIKA ===
if submit and user_input:
    log(f"\n---\n📥 Uživatelský vstup: {user_input}")

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

    log(f"📨 GPT PROMPT:\n{gpt_prompt}")

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
        log(f"📬 GPT odpověď (RAW):\n{gpt_output_raw}")

        start = gpt_output_raw.find('[')
        end = gpt_output_raw.rfind(']') + 1
        gpt_output_clean = gpt_output_raw[start:end]
        items = json.loads(gpt_output_clean)
        log(f"📦 Parsováno:\n{json.dumps(items, ensure_ascii=False, indent=2)}")

    except Exception as e:
        st.error(f"❌ GPT chyba: {e}")
        log(f"❌ GPT chyba: {e}")
        items = []

    # === ZPRACOVÁNÍ PRODUKTŮ ===
    results = []

    for p in items:
        if p.get("nenalezeno"):
            st.warning(p.get("zprava"))
            log("⚠️ " + p.get("zprava"))
            continue

        product = p["produkt"]
        key = re.sub(r"\s+", "", product.lower())

        if key not in st.session_state.CENIKY:
            st.error(f"❌ Ceník nenalezen: {product}")
            log(f"❌ Ceník nenalezen: {product}")
            continue

        df = st.session_state.CENIKY[key]
        w = int(float(p["šířka"]))
        h = int(float(p["hloubka_výška"]))
        use_w, use_h, price = find_price(df, w, h)

        log(f"📐 Požadováno {w}×{h}, použito {use_w}×{use_h}, cena={price}")

        if pd.isna(price):
            st.warning(f"❌ Nenalezena cena pro {w}×{h}")
            log(f"❌ Nenalezena cena v {product}")
            continue

        base_price = float(price)
        rows = [{"Položka": product, "Rozměr": f"{w}×{h}", "Cena bez DPH": round(base_price)}]

        # Montáže 12–15 %
        for perc in [12, 13, 14, 15]:
            rows.append({
                "Položka": f"Montáž {perc} %",
                "Rozměr": "",
                "Cena bez DPH": round(base_price * perc / 100)
            })

        # Doprava
        place = p.get("misto", "").strip()
        if place and place.lower() not in ["neuvedeno", "nedodano", "nedodáno"]:
            api_key = st.secrets.get("GOOGLE_API_KEY", "")
            if api_key:
                km = get_distance_km("Blučina, Czechia", place, api_key)
                if km:
                    travel_cost = round(km * 2 * 15)
                    rows.append({"Položka": "Doprava", "Rozměr": f"{km:.1f} km", "Cena bez DPH": travel_cost})
                    log(f"🚚 Doprava {km:.1f} km = {travel_cost} Kč")

        results.extend(rows)

    # === VÝSTUP ===
    if results:
        st.success(f"✅ Hotovo ({len(results)} položek)")
        st.dataframe(pd.DataFrame(results), use_container_width=True)
        log(f"📊 Výpočet hotov – {len(results)} řádků.")
    else:
        st.warning("⚠️ Nebyl nalezen žádný výsledek.")
        log("⚠️ Výpočet selhal – žádné výsledky.")

# === LIVE LOG ===
with st.expander("🧠 Live log", expanded=True):
    st.text("\n".join(st.session_state.logs))
