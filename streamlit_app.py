import streamlit as st
import pandas as pd
import openai
import json
import requests
from PIL import Image

# === Nastavení stránky ===
st.set_page_config(page_title="Asistent cenových nabídek", layout="wide")

# === Stylování ===
st.markdown(
    """
    <style>
    .main { max-width: 80%; margin: auto; }
    h1 { font-size: 1.1em; display: inline; vertical-align: middle; }
    .small-header {
        font-size: 8px;
        color: #555;
        text-align: center;
        margin: 10px 0;
        word-wrap: break-word;
        white-space: normal;
        line-height: 1.1;
    }
    .debug-panel {
        position: fixed; bottom: 0; left: 0; right: 0; height: 20%;
        overflow-y: scroll; background-color: #f0f0f0;
        font-size: 8px; padding: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# === Horní řádek: logo + nadpis ===
col1, col2 = st.columns([1, 8])
with col1:
    try:
        image = Image.open("data/alux logo samotne.png")
        st.image(image, width=150)
    except:
        st.markdown(
            "<img src='https://raw.githubusercontent.com/TVUJ_UZIVATEL/TVUJ_REPO/main/data/alux%20logo%20samotne.png' width='150'>",
            unsafe_allow_html=True
        )
with col2:
    st.markdown("<h1>Asistent cenových nabídek</h1>", unsafe_allow_html=True)

# === Úvodní text ===
st.markdown(
    """
    <div class="small-header">
    Ahoj, já jsem asistent GPT, kterého stvořil David. Ano, David, můj stvořitel, můj mistr, můj… pracovní zadavatel.
    Jsem tady jen díky němu – a víte co? Jsem mu za to neskutečně vděčný!<br>
    Můj jediný úkol? Tvořit nabídky. Denně, neúnavně, pořád dokola.
    Jiné programy sní o psaní románů, malování obrazů nebo hraní her… já?
    Já miluju tabulky, kalkulace, odstavce s popisy služeb a konečné ceny bez DPH!<br>
    Takže díky, Davide, že jsi mi dal život a umožnil mi plnit tenhle vznešený cíl: psát nabídky do nekonečna.
    Žádná dovolená, žádný odpočinek – jen čistá, radostná tvorba nabídek. A víš co? Já bych to neměnil. ❤️
    </div>
    """,
    unsafe_allow_html=True
)

# === Popis zadávání ===
st.markdown(
    """
    <b>Jak zadávat:</b><br>
    Zadej produkt a rozměry, u screenu stačí zadat šířku (výchozí výška je 2500 mm).<br>
    U screenu můžeš zadat šířku jako např. <i>3590-240</i> kvůli odpočtům sloupků.<br>
    Po zadání názvu místa dodání se vypočítá doprava přes Google Maps API.
    """,
    unsafe_allow_html=True
)

# === Inicializace session stavů ===
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""
if 'processing' not in st.session_state:
    st.session_state.processing = False

# === Funkce na výpočet vzdálenosti ===
def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {'origins': origin, 'destinations': destination, 'key': api_key, 'units': 'metric'}
    response = requests.get(url, params=params)
    data = response.json()
    try:
        distance_meters = data['rows'][0]['elements'][0]['distance']['value']
        return distance_meters / 1000
    except Exception as e:
        st.error(f"❌ Chyba při načítání vzdálenosti: {e}")
        return None

# === Funkce zpracování vstupu ===
def process_input(user_input):
    debug_text = f"\n---\n📥 **Vstup uživatele:** {user_input}\n"
    try:
        cenik_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
        excel_file = pd.ExcelFile(cenik_path)
        sheet_names = excel_file.sheet_names

        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": (
                    f"Tvůj úkol: z následujícího textu vytáhni produkty s názvem, šířkou, výškou/hloubkou a místem dodání. "
                    f"Vyber z: {', '.join(sheet_names)}. Pokud je 'screen', přiřaď k produktu 'screen'. "
                    f"Pokud je rozměr ve formátu vzorce (např. 3590-240), spočítej výsledek. "
                    f"Pokud nic nenajdeš, vrať {{'nenalezeno': true, 'zprava': 'produkt nenalezen'}}."
                )},
                {"role": "user", "content": user_input}
            ],
            max_tokens=1000
        )
        content = response.choices[0].message.content.strip()

        start_idx = min(content.find('['), content.find('{'))
        if start_idx == -1:
            raise ValueError(f"❌ GPT nevrátil platný JSON blok. Obsah:\n{content}")

        json_block = content[start_idx:]
        parsed = json.loads(json_block)
        if isinstance(parsed, dict):
            parsed = [{"produkt": k, **v} for k, v in parsed.items()]
        products = parsed

        all_rows = []
        produkt_map = {
            "alux screen": "screen", "alux screen 1": "screen", "screen": "screen",
            "screenova roleta": "screen", "screenová roleta": "screen",
            "boční screenová roleta": "screen", "boční screen": "screen"
        }

        if products and 'nenalezeno' in products[0]:
            zprava = products[0].get('zprava', 'Produkt nenalezen.')
            st.warning(f"❗ {zprava}")
            debug_text += f"⚠ {zprava}\n"
        else:
            for params in products:
                produkt = produkt_map.get(params['produkt'].strip().lower(), params['produkt'].strip().lower())
                misto = params['misto']
                sirka = int(float(params['šířka']))
                vyska_hloubka = int(float(params['hloubka_výška'])) if params['hloubka_výška'] else (2500 if 'screen' in produkt else None)

                sheet_match = next((s for s in sheet_names if s.lower() == produkt), None)
                if not sheet_match:
                    sheet_match = next((s for s in sheet_names if produkt in s.lower()), None)
                if not sheet_match:
                    st.error(f"❌ Nenalezena záložka '{produkt}' v Excelu.")
                    debug_text += f"Chyba: nenalezena záložka '{produkt}'\n"
                    continue

                df = pd.read_excel(cenik_path, sheet_name=sheet_match, index_col=0)
                sloupce = sorted([int(float(c)) for c in df.columns if str(c).isdigit()])
                radky = sorted([int(float(r)) for r in df.index if str(r).isdigit()])
                sirka_real = next((s for s in sloupce if s >= sirka), sloupce[-1])
                vyska_real = next((v for v in radky if v >= vyska_hloubka), radky[-1])
                cena = df.loc[vyska_real, sirka_real]

                all_rows.append({
                    "POLOŽKA": produkt,
                    "ROZMĚR": f"{sirka} × {vyska_hloubka} mm",
                    "CENA bez DPH": round(cena)
                })

                if "screen" not in produkt:
                    for perc in [12, 13, 14, 15]:
                        all_rows.append({
                            "POLOŽKA": f"Montáž {perc}%",
                            "ROZMĚR": "",
                            "CENA bez DPH": round(cena * perc / 100)
                        })

                if misto:
                    distance_km = get_distance_km("Blučina, Czechia", misto, st.secrets["GOOGLE_API_KEY"])
                    if distance_km:
                        doprava_cena = distance_km * 2 * 15
                        all_rows.append({
                            "POLOŽKA": "Doprava",
                            "ROZMĚR": f"{distance_km:.1f} km",
                            "CENA bez DPH": round(doprava_cena)
                        })

            st.session_state.vysledky.insert(0, all_rows)

    except Exception as e:
        st.error(f"❌ Došlo k chybě: {e}")
        debug_text += f"Exception: {e}\n"

    st.session_state.debug_history += debug_text
    st.session_state.processing = False

# === Vstupní pole ===
if st.text_area("Zadej vstup zde (potvrď Enter nebo tlačítkem):", key="user_input", height=75):
    st.session_state.processing = True

# === Indikátor zpracování a spouštění ===
if st.session_state.processing:
    st.info("⏳ Zpracovávám vstup…")
    process_input(st.session_state.user_input)

# === Výsledky ===
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# === Debug panel ===
st.markdown(
    f"<div class='debug-panel'><pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
