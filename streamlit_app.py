import streamlit as st
import pandas as pd
import requests
import io

st.set_page_config(layout="wide")

st.title("🧠 Asistent cenových nabídek")

# Inicializace datových struktur
if 'df_dict' not in st.session_state:
    st.session_state.df_dict = {}
if 'debug_log' not in st.session_state:
    st.session_state.debug_log = ""

# 🧩 1. Načtení ceníků ze souboru
CENIKY_SEZNAM_PATH = "ceniky_list.txt"  # Textový soubor: název, odkaz

def nacti_ceniky():
    try:
        with open(CENIKY_SEZNAM_PATH, "r") as f:
            lines = f.readlines()
            for line in lines:
                if "," not in line:
                    continue
                nazev, url = [x.strip() for x in line.split(",", 1)]
                response = requests.get(url)
                if response.status_code == 200:
                    df = pd.read_csv(io.StringIO(response.text), index_col=0)
                    st.session_state.df_dict[nazev] = df
                    st.session_state.debug_log += f"✅ Načten ceník: {nazev} ({df.shape})\n"
                else:
                    st.session_state.debug_log += f"❌ Chyba při načítání {nazev}: {response.status_code}\n"
    except Exception as e:
        st.error(f"❌ Nelze načíst seznam ceníků: {e}")
        st.stop()

nacti_ceniky()

# 📤 2. Zadání popisu pro asistenta
with st.form("formular"):
    vstup = st.text_area("Zadejte popis produktů", height=100, placeholder="Např. ALUX Glass 6000x2500, screen 3500x2500")
    odeslat = st.form_submit_button("📤 Odeslat")

if odeslat and vstup:
    st.session_state.debug_log += f"\n📥 Uživatelský vstup: {vstup}\n"
    # ... zde by byla logika volání GPT, výpočtů, interpolací atd.

# 🧾 3. Debug log zobrazený rovnou
with st.expander("🛠️ Debug log"):
    st.text_area("Log:", st.session_state.debug_log, height=250)

# 📊 4. Náhled všech načtených tabulek – skryto ve výchozím stavu
with st.expander("📊 Náhled všech načtených ceníků (rozklikněte)"):
    for name, df in st.session_state.df_dict.items():
        st.markdown(f"#### {name}")
        st.dataframe(df, height=250)
