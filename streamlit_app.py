import streamlit as st
import pandas as pd
import openai
import json
import requests
from pathlib import Path
from io import BytesIO
from PIL import Image
import base64

# 💡 Funkce pro pozadí s průhledností
def set_background(image_path, opacity=0.2):
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode()
    st.markdown(f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-repeat: no-repeat;
            background-attachment: fixed;
            opacity: {opacity};
        }}
        </style>
    """, unsafe_allow_html=True)

# 🖼️ Pozadí
set_background("grafika/pozadi_hlavni.png", opacity=0.2)

# 🧠 GPT klient
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(layout="wide")

st.markdown("""
    <style>
        h1 { font-size: 45px !important; margin-top: 0 !important; }
        .stTable {{ background-color: #f2f2f2; }}
    </style>
""", unsafe_allow_html=True)

st.title("Asistent cenových nabídek od Davida")

if 'debug' not in st.session_state:
    st.session_state.debug = ""

if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []

# 🔄 Načti všechny Excely z adresáře "ceniky"
cenik_soubory = sorted(Path("ceniky").glob("*.xls*"))
produkt_data = {}
sheet_names = []

for excel_path in cenik_soubory:
    try:
        excel = pd.ExcelFile(excel_path)
        for sheet in excel.sheet_names:
            df = excel.parse(sheet, index_col=0)
            produkt_data[sheet.lower()] = df
            sheet_names.append(sheet)
    except Exception as e:
        st.error(f"Chyba při načítání ceníku: {e}")
        st.stop()

st.markdown(f"🗂️ Načtené ceníky: {sheet_names}")

# 📤 Vstup
with st.form("formular"):
    vstup = st.text_area("Zadejte popis produktů, rozměry a místo dodání:", height=120, placeholder="Např. ALUX Glass 6000x2500 Brno, screen 3500x2500...")
    odeslat = st.form_submit_button("📤 ODESLAT")

if odeslat and vstup:
    debug = f"\n📥 Vstup: {vstup}\n"
    prompt = (
        f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání. "
        f"Název produktu vybírej co nejpřesněji z tohoto seznamu: {', '.join(sheet_names)}. "
        f"Fráze jako 'screen', 'screenová roleta' vždy přiřaď k produktu 'screen'. "
        f"Rozměry ve formátu jako 3500-250 dopočítej. "
        f"Vrať POUZE validní JSON list, např. [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}]"
    )
    debug += f"\n📨 GPT PROMPT:\n{prompt}\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": vstup}
            ],
            max_tokens=1000
        )
        obsah = response.choices[0].message.content.strip()
        debug += f"\n📬 GPT Odpověď (RAW):\n{obsah}\n"

        start, end = obsah.find("["), obsah.rfind("]") + 1
        vystup = json.loads(obsah[start:end])
        debug += f"\n📦 Parsováno:\n{json.dumps(vystup, indent=2)}\n"

        rows = []

        for polozka in vystup:
            produkt = polozka["produkt"].lower().strip()
            sirka = int(float(polozka["šířka"]))
            vyska = int(float(polozka["hloubka_výška"] or 2500))
            misto = polozka.get("misto", "")

            if produkt not in produkt_data:
                st.warning(f"Produkt {produkt} nebyl nalezen.")
                continue

            df = produkt_data[produkt]
            cols = sorted([int(c) for c in df.columns if isinstance(c, (int, float))])
            idxs = sorted([int(i) for i in df.index if isinstance(i, (int, float))])

            debug += f"\n📊 Matice: {cols} x {idxs}"

            col_real = next((c for c in cols if c >= sirka), cols[-1])
            idx_real = next((r for r in idxs if r >= vyska), idxs[-1])
            cena = df.at[idx_real, col_real]

            debug += f"\n🔍 {produkt} {sirka}×{vyska} => {col_real}×{idx_real} = {cena} Kč"

            rows.append({
                "POLOŽKA": produkt,
                "ROZMĚR": f"{sirka} × {vyska} mm",
                "CENA bez DPH": round(float(cena))
            })

        st.session_state.vysledky.insert(0, rows)

    except Exception as e:
        st.error(f"Chyba: {e}")
        debug += f"\n⛔ Výjimka: {e}"

    st.session_state.debug += debug

# 📊 Výsledky
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(pd.DataFrame(vysledek))

# 🐞 Debug
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 20%; overflow-y: scroll; background: #eee; font-size: 11px; padding: 10px;'>"
    f"<pre>{st.session_state.debug}</pre></div>",
    unsafe_allow_html=True
)
