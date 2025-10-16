import streamlit as st
import pandas as pd
import requests
from io import StringIO
import os

# Nastavení stránky
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – živý výpis procesů")

# Inicializace logu
if "log" not in st.session_state:
    st.session_state.log = ""

def log(zprava: str):
    st.session_state.log += zprava + "\n"

# Cesta k souboru se seznamem ceníků
SEZNAM_CENIKU = "seznam_ceniku.txt"

# 1️⃣ Načtení seznamu ceníků
ceniky_map = {}
if not os.path.exists(SEZNAM_CENIKU):
    st.error(f"❌ Soubor `{SEZNAM_CENIKU}` neexistuje v hlavním adresáři!")
    log(f"❌ Soubor `{SEZNAM_CENIKU}` neexistuje.")
else:
    with open(SEZNAM_CENIKU, "r", encoding="utf-8") as f:
        for line in f:
            if "–" in line:
                nazev, url = line.strip().split("–", 1)
                ceniky_map[nazev.strip()] = url.strip()
                log(f"📄 Ceník nalezen: {nazev.strip()} → {url.strip()}")

# 2️⃣ Načtení CSV z Google Sheets
nactene_ceniky = {}
for produkt, url in ceniky_map.items():
    try:
        log(f"\n🌐 Načítám CSV: {produkt}")
        r = requests.get(url)
        if r.status_code != 200:
            log(f"❌ Nelze stáhnout {produkt} (HTTP {r.status_code})")
            continue
        df = pd.read_csv(StringIO(r.text), index_col=0)
        nactene_ceniky[produkt.lower()] = df
        log(f"✅ Načteno: {produkt} – {df.shape}")
    except Exception as e:
        log(f"❌ Chyba při načítání '{produkt}': {e}")

# 3️⃣ Zobrazení tabulek
with st.expander("📂 Zobrazit všechny načtené tabulky"):
    if nactene_ceniky:
        for produkt, df in nactene_ceniky.items():
            st.markdown(f"#### 📋 {produkt}")
            st.dataframe(df)
    else:
        st.info("Žádné tabulky zatím nebyly načteny.")

# 4️⃣ Živý log
st.markdown("---")
st.markdown("### 🪵 Živý výpis logu")
st.text_area("Live log", value=st.session_state.log, height=400)
