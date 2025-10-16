import streamlit as st
import pandas as pd
import requests
import json
import openai

# Nastavení
st.set_page_config(layout="wide")
st.title("🧮 Cenový asistent – ALUX")

# Inicializace stavů
if "debug" not in st.session_state:
    st.session_state.debug = ""
if "ceniky" not in st.session_state:
    st.session_state.ceniky = {}
if "sheet_names" not in st.session_state:
    st.session_state.sheet_names = []

# ⏬ Načti seznam ceníků ze souboru v hlavním adresáři
debug_log = ""
try:
    with open("seznam_ceniku.txt", "r", encoding="utf-8") as f:
        radky = f.readlines()

    for radek in radky:
        if " - " not in radek:
            continue
        nazev, url = radek.strip().split(" - ", 1)
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.astype(str)
            df.index = df.index.astype(str)
            st.session_state.ceniky[nazev.strip()] = df
            st.session_state.sheet_names.append(nazev.strip())
            debug_log += f"✅ Načten ceník: {nazev.strip()} ({df.shape})\n"
        except Exception as e:
            debug_log += f"❌ Chyba při načítání {nazev.strip()}: {e}\n"
except FileNotFoundError:
    st.error("❌ Soubor `seznam_ceniku.txt` nebyl nalezen v hlavním adresáři.")
    st.stop()

# 📊 Náhled všech tabulek – rozbalovací box
with st.expander("📂 Zobrazit všechny načtené tabulky"):
    for nazev, df in st.session_state.ceniky.items():
        st.write(f"### {nazev}")
        st.dataframe(df)

# 📥 Uživatelský vstup
st.subheader("📝 Zadejte popis produktů")
prompt = st.text_area("Např. ALUX Bioclimatic 5990x4500", height=100)
odeslat = st.button("📤 Odeslat")

if odeslat and prompt.strip():
    debug_log += f"\n📥 Uživatelský vstup: {prompt.strip()}\n"

    # 🔎 Vytvoření promptu pro GPT
    gpt_prompt = (
        f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání.\n"
        f"Název produktu vybírej co nejpřesněji z tohoto seznamu: {', '.join(st.session_state.sheet_names)}.\n"
        f"Fráze jako 'screen', 'screenová roleta' vždy přiřaď k produktu 'screen'.\n"
        f"Rozměry ve formátu jako 3500-250 vždy převeď na šířku a výšku v mm.\n"
        f"Vrať POUZE validní JSON list, např. [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}]"
    )

    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": gpt_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        gpt_output_raw = response.choices[0].message.content.strip()
        debug_log += f"\n📨 GPT odpověď:\n{gpt_output_raw}\n"

        products = json.loads(gpt_output_raw)
        for item in products:
            produkt = item["produkt"]
            sirka = int(item["šířka"])
            vyska = int(item["hloubka_výška"])
            misto = item.get("misto", "")

            debug_log += f"\n📦 Požadavek: {produkt} {sirka}×{vyska} ({misto})"

            if produkt not in st.session_state.ceniky:
                debug_log += f"\n❌ Ceník nenalezen: {produkt}"
                continue

            df = st.session_state.ceniky[produkt]
            df.columns = [c.strip() for c in df.columns]
            df.index = [i.strip() for i in df.index]

            sloupce = sorted([int(float(c)) for c in df.columns if str(c).isdigit() or str(c).replace('.', '').isdigit()])
            radky = sorted([int(float(i)) for i in df.index if str(i).isdigit() or str(i).replace('.', '').isdigit()])

            sirka_real = next((x for x in sloupce if x >= sirka), sloupce[-1])
            vyska_real = next((y for y in radky if y >= vyska), radky[-1])
            debug_log += f"\n📐 Rozměr požadovaný: {sirka}×{vyska}, použitý: {sirka_real}×{vyska_real}"

            try:
                hodnota = df.loc[str(vyska_real), str(sirka_real)]
                debug_log += f"\n📤 Hodnota z df.loc[{vyska_real}, {sirka_real}] = {hodnota}"
                cena = round(float(hodnota))
                st.success(f"{produkt} {sirka_real}×{vyska_real} mm → {cena} Kč bez DPH")
            except Exception as e:
                debug_log += f"\n❌ Chyba při zpracování: {e}"
                st.error(f"Chyba při načítání ceny pro {produkt} {sirka_real}×{vyska_real}")

    except Exception as e:
        debug_log += f"\n❌ GPT výjimka: {e}"
        st.error("❌ Chyba při komunikaci s GPT nebo zpracování dat.")

# 🧾 Debug panel
with st.expander("🛠️ Debug log"):
    st.text_area("Log výpočtu", value=debug_log + "\n" + st.session_state.debug, height=300)
