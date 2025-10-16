import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide")

st.title("📊 Náhled všech produktových ceníků z Google Sheets")

# Testovací listy z Google Sheets (musí být publikované jako CSV)
# Formát: "název_záložky": "url_odkazu"
ceniky_google_sheets = {
    "ALUX Bioclimatic": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_CHUuFGLItFD-2lpokd9vOecKiY3Z93sW6rSsU2zjQnHhRIiTdRGd0DO9yhItqg/pub?output=csv"
    # Přidej další listy sem
    # "ALUX Thermo": "https://...",
    # "Strada GLASS": "https://..."
}

# Debug výstup (živý log)
debug_log = "\n📥 Načítání ceníků ze vzdálených CSV (Google Sheets):\n"

# Zobrazení každého ceníku
for nazev, url in ceniky_google_sheets.items():
    try:
        df = pd.read_csv(url, encoding="utf-8", sep=",")

        # Pokus o převedení všech hodnot na čísla, kde to jde
        df = df.apply(pd.to_numeric, errors='ignore')

        # Uložení do session (nepovinné)
        st.session_state[nazev] = df

        debug_log += f"✅ {nazev} – tvar: {df.shape}\n"

        with st.expander(f"📄 Náhled ceníku: {nazev} ({df.shape[0]}×{df.shape[1]})", expanded=False):
            st.dataframe(df.style.set_properties(**{
                'background-color': '#f3f3f3',
                'color': '#000000'
            }), use_container_width=True)

    except Exception as e:
        debug_log += f"❌ {nazev} – chyba: {e}\n"

# Výpis živého logu
with st.expander("🪵 Debug log načítání", expanded=True):
    st.text(debug_log)
