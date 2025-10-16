import streamlit as st
import pandas as pd
import openai
import json
import requests
import os

st.set_page_config(layout="wide")

# --- INIT ---
st.title("Asistent cenových nabídek od Davida")
st.markdown("## 🔧 Zadání parametrů a výpočet cen")

# --- DEBUG STORAGE ---
if "debug_log" not in st.session_state:
    st.session_state.debug_log = ""

def log(text):
    st.session_state.debug_log += str(text) + "\n"

# --- CONFIG ---
SEZNAM_SOUBORU = "seznam_ceniku.txt"  # format: Nazev - https://link

# --- FUNKCE: Načtení všech ceníků ze seznamu ---
def load_all_price_sheets():
    df_dict = {}
    try:
        with open(SEZNAM_SOUBORU, "r") as f:
            lines = f.readlines()
            for line in lines:
                if " - " in line:
                    name, url = line.strip().split(" - ", 1)
                    df = pd.read_csv(url)
                    df.columns = df.columns.astype(str)
                    df.index = df.iloc[:, 0]
                    df = df.drop(df.columns[0], axis=1)
                    df_dict[name.strip()] = df
                    log(f"✅ Načten ceník: {name.strip()} {df.shape}")
    except Exception as e:
        log(f"❌ Chyba při načítání ceníků: {e}")
    return df_dict

ceniky = load_all_price_sheets()

# --- ZOBRAZENÍ TABULEK V EXPANDERU ---
with st.expander("📊 Náhled všech načtených ceníků"):
    for name, df in ceniky.items():
        st.markdown(f"#### {name}")
        st.dataframe(df)

# --- VSTUP OD UŽIVATELE ---
user_input = st.text_area("Zadejte popis produktů, rozměry a místo dodání:",
                          placeholder="Např. ALUX Glass 6000x2500 Brno")
if st.button("📤 ODESLAT"):
    log("\n---\n📥 Uživatelský vstup:")
    log(user_input)

    # --- GPT PROMPT ---
    gpt_prompt = (
        f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), "
        f"hloubkou nebo výškou (v mm) a místem dodání. Název produktu vybírej co nejpřesněji z tohoto seznamu: "
        f"{', '.join(ceniky.keys())}. Fráze jako 'screen', 'screenová roleta' vždy přiřaď k produktu 'screen'. "
        f"Rozměry ve formátu jako 3500-250 dopočítej. Vrať POUZE validní JSON list, např. "
        f"[{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}]"
    )

    log("\n📨 GPT PROMPT:")
    log(gpt_prompt)

    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": gpt_prompt},
                {"role": "user", "content": user_input}
            ],
            max_tokens=1000
        )
        gpt_output = response.choices[0].message.content.strip()
        log("\n📬 GPT odpověď:")
        log(gpt_output)

        data = json.loads(gpt_output)

        for zaznam in data:
            produkt = zaznam["produkt"].strip()
            sirka = int(float(zaznam["šířka"]))
            vyska = int(float(zaznam["hloubka_výška"]))
            log(f"\n📐 Rozměr požadovaný: {sirka}×{vyska}")

            if produkt not in ceniky:
                log(f"❌ Ceník nenalezen: {produkt}")
                continue

            df = ceniky[produkt]
            cols = [int(float(c)) for c in df.columns]
            rows = [int(float(r)) for r in df.index]

            sirka_real = next((x for x in cols if x >= sirka), cols[-1])
            vyska_real = next((y for y in rows if y >= vyska), rows[-1])
            log(f"📐 Použitý rozměr: {sirka_real}×{vyska_real}")

            try:
                hodnota = df.loc[str(vyska_real)][str(sirka_real)]
                log(f"📤 Hodnota z df.loc[{vyska_real}, {sirka_real}] = {hodnota}")
                cena = float(str(hodnota).replace(" ", "").replace(",", "."))
                st.success(f"{produkt} {sirka}×{vyska} mm = {int(cena)} Kč bez DPH")
            except Exception as e:
                log(f"❌ Chyba při zpracování: {e}")

    except Exception as e:
        log(f"❌ GPT chyba: {e}")

# --- DEBUG LOG ---
st.markdown("## 🐞 Debug log")
st.text_area("Log výpočtu", value=st.session_state.debug_log, height=400)
