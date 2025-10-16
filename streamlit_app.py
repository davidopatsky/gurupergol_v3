import streamlit as st
import pandas as pd
import openai
import json
import requests

st.set_page_config(layout="wide")

if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []

def log(msg):
    st.session_state.debug_history += f"\n{msg}"

# Nastav odkaz na Google Sheets CSV (stejný pro všechny pro testovací účely)
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_CHUuFGLItFD-2lpokd9vOecKiY3Z93sW6rSsU2zjQnHhRIiTdRGd0DO9yhItqg/pub?output=csv"

# Přiřazení produktů ke stejnému CSV (pro testování)
cenik_urls = {
    "screen": sheet_url,
    "ALUX Thermo": sheet_url,
    "ALUX Glass": sheet_url,
    "Alux CARBO-TRAPEZ": sheet_url,
    "Strada GLASS": sheet_url,
    "ALUX Bioclimatic": sheet_url,
    "Strada Carbo": sheet_url,
}

def nacti_ceniky():
    nacitene = {}
    for produkt, url in cenik_urls.items():
        try:
            df = pd.read_csv(url)
            df.columns = [c.strip() for c in df.columns]
            df.index = [i.strip() for i in df.iloc[:, 0]]
            df = df.drop(df.columns[0], axis=1)
            df.columns = [int(str(c).strip()) for c in df.columns]
            df.index = [int(str(i).strip()) for i in df.index]
            nacitene[produkt.lower()] = df
            log(f"✅ Načteno: {produkt} ({df.shape})")
        except Exception as e:
            log(f"❌ Nelze načíst {produkt}: {e}")
    return nacitene

def ziskej_cenu(df, sirka, vyska):
    try:
        cols = sorted([int(c) for c in df.columns])
        rows = sorted([int(r) for r in df.index])

        real_col = next((c for c in cols if c >= sirka), cols[-1])
        real_row = next((r for r in rows if r >= vyska), rows[-1])

        log(f"📐 Rozměr požadovaný: {sirka}×{vyska}, použitý: {real_col}×{real_row}")

        cena = df.loc[real_row, real_col]
        log(f"📤 Hodnota z df.loc[{real_row}, {real_col}] = {cena}")
        return float(cena)
    except Exception as e:
        log(f"❌ Chyba při získávání ceny: {e}")
        return None

st.title("Asistent cenových nabídek (Google Sheets verze)")

with st.form("formular"):
    vstup = st.text_area("Zadejte popis produktů:", height=100, placeholder="Např. ALUX Glass 6000x2500 Brno")
    odeslat = st.form_submit_button("📤 ODESLAT")

if odeslat and vstup:
    log(f"📥 Uživatelský vstup:\n{vstup}")

    ceniky = nacti_ceniky()

    prompt = (
        "Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), "
        "hloubkou nebo výškou (v mm) a místem dodání. Název produktu vybírej co nejpřesněji z tohoto seznamu: "
        "screen, ALUX Thermo, ALUX Glass, Alux CARBO-TRAPEZ, Strada GLASS, ALUX Bioclimatic, Strada Carbo. "
        "Fráze jako 'screen', 'screenová roleta', 'boční screen' vždy přiřaď k produktu 'screen'. "
        "Rozměry jako 3500-250 dopočítej. Vrať POUZE validní JSON: "
        "[{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}]"
    )

    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": vstup}
            ]
        )
        odpoved = response.choices[0].message.content.strip()
        log(f"📨 GPT odpověď:\n{odpoved}")

        produkty = json.loads(odpoved)
        tabulka = []

        for p in produkty:
            produkt = p['produkt'].lower()
            sirka = int(p['šířka'])
            vyska = int(p['hloubka_výška'])

            df = ceniky.get(produkt)
            if df is None:
                log(f"❌ Ceník nenalezen: {produkt}")
                continue

            cena = ziskej_cenu(df, sirka, vyska)
            if cena is not None:
                tabulka.append({
                    "Produkt": produkt,
                    "Rozměr": f"{sirka} × {vyska}",
                    "Cena bez DPH": round(cena)
                })

        st.session_state.vysledky.insert(0, tabulka)
        log(f"✅ Vygenerováno {len(tabulka)} položek")
    except Exception as e:
        log(f"❌ Chyba při zpracování: {e}")

# Výpis tabulky
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# Debug panel
st.markdown(
    "<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 25%; overflow-y: scroll; "
    "background-color: #f0f0f0; font-size: 10px; padding: 10px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
