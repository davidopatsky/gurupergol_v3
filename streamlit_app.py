import streamlit as st
import pandas as pd
import openai
import json
import requests
from debug import log

st.set_page_config(layout="wide")

# CSS styl
with open("grafika/styles.css", "r", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Inicializace session proměnných
if "vysledky" not in st.session_state:
    st.session_state.vysledky = []
if "debug_history" not in st.session_state:
    st.session_state.debug_history = ""

st.title("Asistent cenových nabídek od Davida")

# 🔧 Funkce na výpočet vzdálenosti
def get_distance_km(origin, destination, api_key):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": api_key,
        "units": "metric"
    }
    response = requests.get(url, params=params)
    log(f"📡 Google API Request: {response.url}")
    data = response.json()
    log(f"📬 Google API Response:\n{json.dumps(data, indent=2)}")
    try:
        return data["rows"][0]["elements"][0]["distance"]["value"] / 1000
    except Exception as e:
        log(f"❌ Chyba při získávání vzdálenosti: {e}")
        return None

# 📄 Načtení ceníků
cenik_path = "ceniky/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
try:
    excel_file = pd.ExcelFile(cenik_path)
    sheet_names = excel_file.sheet_names
    st.session_state.sheet_names = sheet_names
    log(f"📄 Načtené záložky: {sheet_names}")
except Exception as e:
    st.error(f"❌ Nepodařilo se načíst Excel: {e}")
    log(f"❌ Excel load error: {e}")
    st.stop()

# 🧾 Formulář
with st.form(key="vstupni_formular"):
    user_input = st.text_area(
        "Zadejte popis produktů, rozměry a místo dodání:",
        height=100,
        placeholder="Např. ALUX Glass 6000x2500 Brno, screen 3500x2500..."
    )
    submit_button = st.form_submit_button(label="📤 ODESLAT")

# 🧠 GPT & Výpočty
if submit_button and user_input:
    log(f"\n---\n📥 Uživatelský vstup:\n{user_input}")

    with st.spinner("Analyzuji vstup pomocí GPT..."):
        try:
            client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

            with open("prompty/gpt_vstup.txt", "r", encoding="utf-8") as f:
                gpt_prompt = f.read().replace("{produkty}", ", ".join(sheet_names))
            log(f"📨 GPT prompt:\n{gpt_prompt}")

            response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": gpt_prompt},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=1000
            )

            gpt_output_raw = response.choices[0].message.content.strip()
            log(f"📬 GPT odpověď (RAW):\n{gpt_output_raw}")

            start = gpt_output_raw.find("[")
            end = gpt_output_raw.rfind("]") + 1
            gpt_output_clean = gpt_output_raw[start:end]
            log(f"📦 GPT JSON blok:\n{gpt_output_clean}")

            products = json.loads(gpt_output_clean)
            log(f"📤 GPT parsed výstup:\n{json.dumps(products, indent=2)}")

            all_rows = []

            if products and "nenalezeno" in products[0]:
                zprava = products[0].get("zprava", "Produkt nenalezen.")
                st.warning(f"❗ {zprava}")
                log(f"⚠ {zprava}")
            else:
                produkt_map = {
                    "screen": "screen", "alux screen": "screen",
                    "screenová roleta": "screen", "boční screen": "screen"
                }

                for params in products:
                    produkt = params["produkt"].strip().lower()
                    produkt_lookup = produkt_map.get(produkt, produkt)
                    misto = params.get("misto", "")

                    try:
                        sirka = int(float(params["šířka"]))
                        vyska = 2500 if params["hloubka_výška"] is None and "screen" in produkt_lookup \
                            else int(float(params["hloubka_výška"]))
                    except Exception as e:
                        st.error(f"❌ Chybný rozměr: {e}")
                        log(f"❌ Chybný rozměr: {e}")
                        continue

                    log(f"🔍 Produkt: {produkt_lookup}, Rozměry: {sirka} × {vyska}, Místo: {misto}")

                    # Vyhledání v ceníku
                    sheet_match = next((s for s in sheet_names if s.lower() == produkt_lookup), None)
                    if not sheet_match:
                        log(f"❌ Nenalezena záložka '{produkt_lookup}'")
                        continue

                    df = pd.read_excel(cenik_path, sheet_name=sheet_match, index_col=0)
                    cols = sorted([int(c) for c in df.columns if isinstance(c, (int, float))])
                    rows = sorted([int(r) for r in df.index if isinstance(r, (int, float))])

                    if not cols or not rows:
                        log(f"❌ Prázdná matice v záložce '{sheet_match}'")
                        continue

                    sirka_real = next((c for c in cols if c >= sirka), cols[-1])
                    vyska_real = next((r for r in rows if r >= vyska), rows[-1])
                    log(f"📐 Zvolená velikost: {sirka_real} × {vyska_real}")

                    try:
                        cena = df.loc[vyska_real, sirka_real]
                        log(f"💰 Cena: {cena} Kč (matice[{vyska_real}][{sirka_real}])")
                    except Exception as e:
                        log(f"❌ Chyba při čtení ceny: {e}")
                        continue

                    all_rows.append({
                        "POLOŽKA": produkt_lookup,
                        "ROZMĚR": f"{sirka} × {vyska} mm",
                        "CENA bez DPH": round(float(cena))
                    })

                    if "screen" not in produkt_lookup:
                        for perc in [12, 13, 14, 15]:
                            cena_montaz = round(float(cena) * perc / 100)
                            all_rows.append({
                                "POLOŽKA": f"Montáž {perc}%",
                                "ROZMĚR": "",
                                "CENA bez DPH": cena_montaz
                            })
                            log(f"🛠️ Montáž {perc}% = {cena_montaz} Kč")

                    if misto and misto.lower() not in ["neuvedeno", "nedodáno"]:
                        api_key = st.secrets["GOOGLE_API_KEY"]
                        distance_km = get_distance_km("Blučina, Czechia", misto, api_key)
                        if distance_km:
                            cena_doprava = round(distance_km * 2 * 15)
                            all_rows.append({
                                "POLOŽKA": "Doprava",
                                "ROZMĚR": f"{distance_km:.1f} km",
                                "CENA bez DPH": cena_doprava
                            })
                            log(f"🚚 Doprava {distance_km:.1f} km = {cena_doprava} Kč")

            st.session_state.vysledky.insert(0, all_rows)
            log(f"📦 Výsledná tabulka:\n{pd.DataFrame(all_rows).to_string(index=False)}")

        except json.JSONDecodeError as e:
            log(f"⛔ JSONDecodeError: {e}")
        except Exception as e:
            log(f"⛔ Výjimka: {e}")

# 📊 Výpis výsledků
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# 🐞 Debug log (collapsible box)
with st.expander("🪛 Debug log"):
    st.markdown("### Ladicí log")
    st.code(st.session_state.debug_history[-20000:], language="text")
