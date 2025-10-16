import streamlit as st
import pandas as pd
import json
import openai
import requests
from io import StringIO

st.set_page_config(layout="wide")

st.title("🧠 Asistent cenových nabídek od Davida")

# Session state init
if "ceniky" not in st.session_state:
    st.session_state.ceniky = {}
if "log" not in st.session_state:
    st.session_state.log = ""
if "vysledky" not in st.session_state:
    st.session_state.vysledky = []

# 🔄 Načti seznam ceníků ze souboru
seznam_path = "seznam_ceniku.txt"
try:
    with open(seznam_path, "r") as f:
        seznam_ceniku = [line.strip().split(" - ") for line in f if " - " in line]
    st.session_state.log += f"📄 Načten seznam_ceniku.txt ({len(seznam_ceniku)} položek)\n"
except Exception as e:
    st.error(f"❌ Chyba při načítání seznamu ceníků: {e}")
    st.stop()

# 🌐 Načti všechny ceníky z Google Sheets
for nazev, url in seznam_ceniku:
    try:
        response = requests.get(url)
        if response.status_code != 200:
            st.session_state.log += f"❌ Nelze stáhnout {nazev} (HTTP {response.status_code})\n"
            continue
        df = pd.read_csv(StringIO(response.text), index_col=0)
        df.columns = df.columns.astype(str)
        df.index = df.index.astype(str)
        st.session_state.ceniky[nazev.lower()] = df
        st.session_state.log += f"✅ Načten ceník: {nazev} ({df.shape})\n"
    except Exception as e:
        st.session_state.log += f"❌ Chyba při načítání {nazev}: {e}\n"

# 📥 Zadání od uživatele
with st.form("formular"):
    vstup_text = st.text_area("Zadej poptávku:", height=100)
    odeslat = st.form_submit_button("📤 Odeslat")

if odeslat and vstup_text:
    st.session_state.log += f"\n---\n📥 Uživatelský vstup: {vstup_text}\n"

    prompt = (
        "Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání. "
        "Název produktu vybírej co nejpřesněji z tohoto seznamu: " + ", ".join(st.session_state.ceniky.keys()) + ". "
        "Fráze jako 'screen', 'screenová roleta' vždy přiřaď k produktu 'screen'. "
        "Rozměry ve formátu jako 3500-250 dopočítej. "
        "Vrať POUZE validní JSON list, např. [{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}]"
    )

    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": vstup_text},
            ],
            max_tokens=1000
        )
        gpt_vystup = response.choices[0].message.content.strip()
        st.session_state.log += f"📨 GPT odpověď: {gpt_vystup}\n"

        produkty = json.loads(gpt_vystup)

        for p in produkty:
            nazev = p['produkt'].lower()
            sirka = int(p['šířka'])
            vyska = int(p['hloubka_výška'])

            df = st.session_state.ceniky.get(nazev)
            if df is None:
                st.session_state.log += f"❌ Ceník nenalezen: {nazev}\n"
                continue

            cols = sorted([int(float(c.replace(",", "."))) for c in df.columns])
            rows = sorted([int(float(r.replace(",", "."))) for r in df.index])

            col_real = next((c for c in cols if c >= sirka), cols[-1])
            row_real = next((r for r in rows if r >= vyska), rows[-1])

            st.session_state.log += f"📐 Rozměr požadovaný: {sirka}×{vyska}, použitý: {col_real}×{row_real}\n"

            try:
                cena = df.loc[str(row_real), str(col_real)]
                st.session_state.log += f"📤 Hodnota z df.loc[{row_real}, {col_real}] = {cena}\n"
                vysledek = {
                    "Produkt": nazev,
                    "Rozměr": f"{sirka}×{vyska}",
                    "Cena bez DPH": round(float(cena))
                }
                st.session_state.vysledky.append(vysledek)
            except Exception as e:
                st.session_state.log += f"❌ Chyba při zpracování: {e}\n"

    except Exception as e:
        st.session_state.log += f"❌ Výjimka při zpracování GPT: {e}\n"

# 🧾 Výpis výsledků
if st.session_state.vysledky:
    st.subheader("💶 Výsledky")
    st.dataframe(pd.DataFrame(st.session_state.vysledky))

# 📂 Debug log – rozbalovací
with st.expander("🪵 Živý log procesu"):
    st.text(st.session_state.log)

# 📊 Náhled všech ceníků
with st.expander("📂 Zobrazit všechny načtené tabulky"):
    for nazev, df in st.session_state.ceniky.items():
        st.write(f"### {nazev}")
        st.dataframe(df)
