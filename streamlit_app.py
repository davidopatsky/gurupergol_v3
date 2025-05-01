import streamlit as st
import pandas as pd
import openai
import json
import numpy as np

# Nastavení OpenAI klienta
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Layout: debug vlevo (10 %), hlavní část vpravo (90 %)
col_debug, col_main = st.columns([0.1, 0.9])

with col_debug:
    st.markdown("### 🐞 DEBUG")
    debug_text = ""

with col_main:
    st.title("Asistent cenových nabídek od Davida")

    # Načtení seznamu záložek při spuštění aplikace
    cenik_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
    try:
        excel_file = pd.ExcelFile(cenik_path)
        sheet_names = excel_file.sheet_names
        seznam_zalozek = ", ".join(sheet_names)
        debug_text += f"Načtené záložky: {sheet_names}\n"
    except Exception as e:
        st.error(f"❌ Nepodařilo se načíst seznam produktů ze souboru: {e}")
        st.stop()

    user_input = st.text_area("Zadejte popis produktů, rozměry a místo dodání:")

    if st.button("Spočítat cenu"):
        if not user_input.strip():
            st.warning("Prosím, zadejte vstupní text.")
        else:
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
                        sirka = int(float(params['šířka']))
                        vyska_hloubka = int(float(params['hloubka_výška']))
                        misto = params['misto']

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

                    st.write("✅ **Výsledná tabulka**")
                    st.table(all_rows)

                except json.JSONDecodeError as e:
                    st.error(f"❌ Chyba při zpracování JSON: {e}")
                    debug_text += f"JSONDecodeError: {e}\n"
                except Exception as e:
                    st.error(f"❌ Došlo k chybě: {e}")
                    debug_text += f"Exception: {e}\n"

    # Spodní pravý roh: seznam produktů
    st.markdown(
        f"""
        <div style='position: fixed; bottom: 10px; right: 10px; font-size: 10px; color: gray; text-align: right;'>
            Seznam produktů: {seznam_zalozek}
        </div>
        """,
        unsafe_allow_html=True
    )

# Debug výpis vlevo (10 % šířky)
with col_debug:
    st.markdown(f"<pre style='font-size: 10px; white-space: pre-wrap;'>{debug_text}</pre>", unsafe_allow_html=True)
