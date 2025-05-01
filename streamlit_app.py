import streamlit as st
import pandas as pd
from PIL import Image
import backend

st.set_page_config(page_title="Asistent cenových nabídek", layout="wide")

# Stylování
st.markdown(
    """
    <style>
    .main {
        max-width: 80%;
        margin: auto;
    }
    h1 {
        font-size: 1.5em;  /* zmenšeno na ~50 % */
        display: inline;
        vertical-align: middle;
    }
    .small-header {
        font-size: 11px;
        color: #555;
        text-align: center;
        margin: 20px 0;  /* přidáme vertikální mezeru */
        word-wrap: break-word;  /* zajistí zalomení dlouhých řádků */
        white-space: normal;
    }
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
