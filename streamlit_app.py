import streamlit as st
import pandas as pd
import openai
import json
import numpy as np

# Nastavení OpenAI klienta
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Inicializace historie v session
if 'vysledky' not in st.session_state:
    st.session_state.vysledky = []

if 'debug_history' not in st.session_state:
    st.session_state.debug_history = ""

st.set_page_config(layout="wide")
st.title("Asistent cenových nabídek od Davida")

# Načtení seznamu záložek při spuštění aplikace
cenik_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
try:
    excel_file = pd.ExcelFile(cenik_path)
    sheet_names = excel_file.sheet_names
    seznam_zalozek = ", ".join(sheet_names)
    st.session_state.debug_history += f"Načtené záložky: {sheet_names}\n"
except Exception as e:
    st.error(f"❌ Nepodařilo se načíst seznam produktů ze souboru: {e}")
    st.stop()

user_input = st.text_area("Zadejte popis produktů, rozměry a místo dodání:")

if st.button("Spočítat cenu"):
    if not user_input.strip():
        st.warning("Prosím, zadejte vstupní text.")
    else:
        debug_text = f"\n---\n📥 **Vstup uživatele:** {user_input}\n"
        with st.spinner("Analyzuji vstup přes ChatGPT..."):
            try:
                # Dotaz na GPT-4-turbo
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": (
                            f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, "
                            f"šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání. Název produktu vybírej "
                            f"tak, aby co nejvíce odpovídal jednomu z následujících produktů: {seznam_zalozek}. "
                            f"Vrať výsledek POUZE jako platný JSON seznam položek. Nepřidávej žádný úvod ani "
                            f"vysvětlení. Formát: [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}, ...]."
                        )},
                        {"role": "user", "content": user_input}
                    ],
                    max_tokens=1000
                )

                gpt_output_raw = response.choices[0].message.content.strip()
                debug_text += f"GPT RAW odpověď:\n{gpt_output_raw}\n"

                # Ořízneme JSON blok
                start_idx = gpt_output_raw.find('[')
                end_idx = gpt_output_raw.rfind(']') + 1
                gpt_output_clean = gpt_output_raw[start_idx:end_idx]
                debug_text += f"GPT čistý JSON blok:\n{gpt_output_clean}\n"

                products = json.loads(gpt_output_clean)
                all_rows = []

                for params in products:
                    produkt = params['produkt']
                    misto = params['misto']

                    # Ověření a převod šířky
                    try:
                        sirka = int(float(params['šířka']))
                    except (ValueError, TypeError):
                        st.error(f"❌ Nedostatečné zadání nebo chybí rozměr (šířka) pro produkt {produkt}")
                        continue

                    # Ověření a převod výšky/hloubky
                    if params['hloubka_výška'] is None:
                        if "ZIP" in produkt or "Screen" in produkt:
                            vyska_hloubka = 2500  # výchozí hodnota pro screeny
                            debug_text += f"Použita výchozí výška pro screen: {vyska_hloubka} mm\n"
                        else:
                            st.error(f"❌ Nedostatečné zadání nebo chybí rozměr (výška/hloubka) pro produkt {produkt}")
                            continue
                    else:
                        try:
                            vyska_hloubka = int(float(params['hloubka_výška']))
                        except (ValueError, TypeError):
                            st.error(f"❌ Nedostatečné zadání nebo chybí rozměr (výška/hloubka) pro produkt {produkt}")
                            continue

                    debug_text += f"\nZpracovávám produkt: {produkt}, {sirka}×{vyska_hloubka}, místo: {misto}\n"

                    # Načti příslušnou záložku
                    df = pd.read_excel(cenik_path, sheet_name=produkt, index_col=0)

                    # Vyčistíme sloupce (šířky)
                    sloupce_ciste = []
                    for col in df.columns:
                        try:
                            sloupce_ciste.append(int(float(col)))
                        except (ValueError, TypeError):
                            continue
                    sloupce = np.array(sloupce_ciste)

                    # Vyčistíme indexy (výšky/hloubky)
                    radky_ciste = []
                    for idx in df.index:
                        try:
                            radky_ciste.append(int(float(idx)))
                        except (ValueError, TypeError):
                            continue
                    radky = np.array(radky_ciste)

                    debug_text += f"Čisté šířky: {sloupce}\nČisté výšky/hloubky: {radky}\n"

                    if "ZIP" in produkt or "Screen" in produkt:
                        # Screeny – nejbližší vyšší hodnoty
                        sirka_real = min([s for s in sloupce if s >= sirka], default=max(sloupce))
                        vyska_real = min([v for v in radky if v >= vyska_hloubka], default=max(radky))
                        cena = df.loc[str(vyska_real), str(sirka_real)]
                        debug_text += f"Vybraná šířka: {sirka_real}, výška: {vyska_real}, cena: {cena}\n"
                    else:
                        # Pergoly – lineární interpolace
                        df_num = df.apply(pd.to_numeric, errors='coerce')
                        df_num.index = pd.to_numeric(df_num.index, errors='coerce')
                        nejblizsi_vyska = min(radky, key=lambda x: abs(x - vyska_hloubka))
                        vyska_row = df_num.loc[nejblizsi_vyska]
                        cena = np.interp(sirka, sloupce, vyska_row)
                        debug_text += f"Interpolovaná cena: {cena}\n"

                    all_rows.append({
                        "POLOŽKA": produkt,
                        "ROZMĚR": f"{sirka} × {vyska_hloubka} mm",
                        "CENA bez DPH": round(cena)
                    })

                    # Montáže (jen pro pergoly)
                    if "ZIP" not in produkt and "Screen" not in produkt:
                        montaze = {
                            "Montáž 12%": round(cena * 0.12),
                            "Montáž 13%": round(cena * 0.13),
                            "Montáž 14%": round(cena * 0.14),
                            "Montáž 15%": round(cena * 0.15)
                        }
                        for montaz_label, montaz_cena in montaze.items():
                            all_rows.append({
                                "POLOŽKA": montaz_label,
                                "ROZMĚR": "",
                                "CENA bez DPH": montaz_cena
                            })

                # Připravíme výsledek jako text do debug panelu
                result_text = "\n".join([f"{row['POLOŽKA']}: {row['ROZMĚR']} → {row['CENA bez DPH']} Kč"
                                         for row in all_rows])
                debug_text += f"\n📤 **Výsledek aplikace:**\n{result_text}\n---\n"

                # Uložíme výsledek nahoru do historie
                st.session_state.vysledky.insert(0, all_rows)
                st.session_state.debug_history += debug_text

            except json.JSONDecodeError as e:
                st.error(f"❌ Chyba při zpracování JSON: {e}")
                st.session_state.debug_history += f"JSONDecodeError: {e}\n"
            except Exception as e:
                st.error(f"❌ Došlo k chybě: {e}")
                st.session_state.debug_history += f"Exception: {e}\n"

# Zobrazení historie výsledků (nejnovější nahoře)
for idx, vysledek in enumerate(st.session_state.vysledky):
    st.write(f"### Výsledek {len(st.session_state.vysledky) - idx}")
    st.table(vysledek)

# Debug panel dole (vodorovně)
# Debug panel dole (vodorovně, zvětšený na 35 % výšky)
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 35%; overflow-y: scroll; "
    f"background-color: #f0f0f0; font-size: 10px; padding: 5px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)

