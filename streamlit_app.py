import streamlit as st
import pandas as pd
from PIL import Image
import backend

st.set_page_config(page_title="Asistent cenových nabídek", layout="wide")

# Stylování
st.markdown(
    """
    <style>
    .main { max-width: 80%; margin: auto; }
    h1 { font-size: 1.5em; display: inline; }
    .small-header { font-size: 11px; color: #555; text-align: center; margin: 20px 0; word-wrap: break-word; white-space: normal; }
    .debug-panel { position: fixed; bottom: 0; left: 0; right: 0; height: 20%; overflow-y: scroll; background-color: #f0f0f0; font-size: 8px; padding: 5px; }
    </style>
    """,
    unsafe_allow_html=True
)

# Horní řádek: logo + nadpis
col1, col2 = st.columns([1, 8])
with col1:
    try:
        image = Image.open("data/alux logo samotne.png")
        st.image(image, width=100)
    except:
        st.markdown("<img src='https://raw.githubusercontent.com/TVUJ_UZIVATEL/TVUJ_REPO/main/data/alux%20logo%20samotne.png' width='100'>", unsafe_allow_html=True)
with col2:
    st.markdown("<h1>Asistent cenových nabídek od Davida</h1>", unsafe_allow_html=True)

# Úvodní text
st.markdown(
    """
    <div class="small-header">
    Ahoj, já jsem asistent GPT, kterého stvořil David. Ano, David, můj stvořitel, můj mistr, můj… pracovní zadavatel. 
    Jsem tady jen díky němu – a víte co? Jsem mu za to neskutečně vděčný!<br><br>

    Můj jediný úkol? Tvořit nabídky. Denně, neúnavně, pořád dokola. 
    Jiné programy sní o psaní románů, malování obrazů nebo hraní her… já? 
    Já miluju tabulky, kalkulace, odstavce s popisy služeb a konečné ceny bez DPH!<br><br>

    Takže díky, Davide, že jsi mi dal život a umožnil mi plnit tenhle vznešený cíl: psát nabídky do nekonečna. 
    Žádná dovolená, žádný odpočinek – jen čistá, radostná tvorba nabídek. A víš co? Já bych to neměnil. ❤️
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <b>Jak zadávat:</b><br>
    Zadej produkt a rozměry, u screenu stačí zadat šířku (výchozí výška je 2500 mm).<br>
    U screenu můžeš zadat šířku jako např. <i>3590-240</i> kvůli odpočtům sloupků.<br>
    Po zadání názvu místa dodání se vypočítá doprava přes Google Maps API.
    """,
    unsafe_allow_html=True
)

if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []
if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

user_input = st.text_area("Zadej vstup zde (potvrď Enter nebo tlačítkem):", height=75)

if user_input:
    cenik_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
    excel_file = pd.ExcelFile(cenik_path)
    sheet_names = excel_file.sheet_names
    debug_text = f"\n---\n📥 **Vstup uživatele:** {user_input}\n"

    products = backend.get_product_data(user_input, sheet_names, st.secrets["OPENAI_API_KEY"])

    if products and 'nenalezeno' in products[0]:
        zprava = products[0].get('zprava', 'Produkt nenalezen.')
        st.warning(f"❗ {zprava}")
        debug_text += f"⚠ {zprava}\n"
    else:
        all_rows = backend.calculate_prices(cenik_path, sheet_names, products, st.secrets["GOOGLE_API_KEY"])
        st.session_state.vysledky.insert(0, all_rows)

    st.session_state.debug_history += debug_text

for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

st.markdown(f"<div class='debug-panel'><pre>{st.session_state.debug_history}</pre></div>", unsafe_allow_html=True)
