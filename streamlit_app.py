# Asistent cenových nabídek od Davida (verze s plným logováním a Google Sheets)

import streamlit as st
import pandas as pd
import openai
import json
import requests
import os

st.set_page_config(layout="wide")
st.title("Asistent cenových nabídek od Davida")

# ---------- 🔧 STAV ----------
if 'debug_log' not in st.session_state:
    st.session_state.debug_log = ""
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []

# ---------- 🪵 LOG FUNKCE ----------
def log(text):
    st.session_state.debug_log += str(text) + "\n"

# ---------- 📊 NAČTENÍ GOOGLE SHEET ----------
@st.cache_data
def nacti_google_sheets(url):
    try:
        df = pd.read_csv(url)
        log(f"✅ Načten Google Sheet: {url}, tvar: {df.shape}")
        return df
    except Exception as e:
        log(f"❌ Chyba při načítání Google Sheet: {e}")
        return None

# URL k veřejně sdílenému Google Sheet
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_CHUuFGLItFD-2lpokd9vOecKiY3Z93sW6rSsU2zjQnHhRIiTdRGd0DO9yhItqg/pub?output=csv"

cenik_df = nacti_google_sheets(GOOGLE_SHEET_URL)
if cenik_df is None:
    st.stop()

# ---------- 🧠 OPENAI ----------
@st.cache_resource

def init_openai():
    return openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

client = init_openai()

# ---------- 📦 GPT PARSOVÁNÍ ----------
def zpracuj_vstup(user_input, seznam_produktu):
    prompt = (
        f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání. "
        f"Název produktu vybírej co nejpřesněji z následujícího seznamu produktů: {', '.join(seznam_produktu)}. "
        f"Fráze jako 'screen', 'screenová roleta' vždy přiřaď k produktu 'screen'. "
        f"Rozměry ve formátu jako 3500-250 vždy dopočítej. "
        f"Vrať POUZE validní JSON list, např. [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}]"
    )

    log("📨 GPT PROMPT:\n" + prompt)

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input}
            ],
            max_tokens=1000
        )
        raw_output = response.choices[0].message.content.strip()
        log("📬 GPT Odpověď (RAW): " + raw_output)
        return json.loads(raw_output)
    except Exception as e:
        log(f"❌ GPT chyba: {e}")
        return []

# ---------- 📐 ZÍSKÁNÍ CENY ----------
def ziskej_cenu(df, sirka, vyska):
    try:
        cols = sorted([int(float(c)) for c in df.columns[1:]])
        df.index = df.iloc[:, 0]
        df = df.drop(df.columns[0], axis=1)
        rows = sorted([int(float(r)) for r in df.index])

        real_col = next((c for c in cols if c >= sirka), cols[-1])
        real_row = next((r for r in rows if r >= vyska), rows[-1])

        log(f"📐 Rozměr požadovaný: {sirka}×{vyska}, použitý: {real_col}×{real_row}")
        hodnota = df.loc[real_row, str(real_col)]

        if pd.isna(hodnota):
            log(f"⚠️ df.loc[{real_row}, {real_col}] = NaN")
            return None

        log(f"📤 Hodnota z df.loc[{real_row}, {real_col}] = {hodnota}")
        return float(hodnota)

    except Exception as e:
        log(f"❌ Chyba při získávání ceny: {e}")
        return None

# ---------- 🧾 FORMULÁŘ ----------
with st.form(key="formular"):
    user_input = st.text_area("Zadejte popis poptávky:", height=100)
    submit = st.form_submit_button("📤 Odeslat")

# ---------- 🚀 ZPRACOVÁNÍ ----------
produkty_list = ["screen", "ALUX Thermo", "ALUX Glass", "Alux CARBO-TRAPEZ", "Strada GLASS", "ALUX Bioclimatic", "Strada Carbo"]

if submit and user_input:
    log("---")
    log(f"📥 Uživatelský vstup: {user_input}")
    vysledky = []
    extrahovane = zpracuj_vstup(user_input, produkty_list)

    for polozka in extrahovane:
        try:
            produkt = polozka["produkt"].strip()
            sirka = int(float(polozka["šířka"]))
            vyska = int(float(polozka["hloubka_výška"]))
            log(f"🔍 Produkt: {produkt}, šířka: {sirka}, výška: {vyska}")

            cena = ziskej_cenu(cenik_df, sirka, vyska)
            if cena is None:
                log(f"❌ Cena nenalezena pro {produkt} {sirka}×{vyska}")
                continue

            vysledky.append({
                "Produkt": produkt,
                "Rozměr": f"{sirka}×{vyska}",
                "Cena bez DPH": round(cena)
            })
        except Exception as e:
            log(f"❌ Chyba při zpracování položky: {e}")

    st.session_state.vysledky.insert(0, vysledky)

# ---------- 📋 VÝSLEDKY ----------
for idx, tab in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.dataframe(pd.DataFrame(tab))

# ---------- 🐛 DEBUG PANEL ----------
st.markdown("### 🐛 Debug log")
st.text_area("Log:", st.session_state.debug_log, height=300, key="log_panel")

# 🪵 Zobrazení kompletního debug logu v aplikaci
with st.expander("🪵 DEBUG LOG", expanded=True):
    st.text_area("Detailní záznam průběhu výpočtu:", st.session_state.debug_log, height=400)
