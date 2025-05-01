import streamlit as st
import pandas as pd
import openai
import json
import numpy as np

# Nastavení OpenAI klienta
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("Asistent cenových nabídek od Davida")

# Načtení seznamu záložek při spuštění aplikace
cenik_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
try:
    excel_file = pd.ExcelFile(cenik_path)
    sheet_names = excel_file.sheet_names
    seznam_zalozek = ", ".join(sheet_names)
    st.success(f"✅ Načteno {len(sheet_names)} produktů.")
except Exception as e:
    st.error(f"❌ Nepodařilo se načíst seznam produktů ze souboru: {e}")
    st.stop()

# Uživatelský vstup
user_input = st.text_area("Zadejte popis produktu, rozměry a místo dodání:")

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
                            f"Tvůj úkol: extrahuj z textu přesný název produktu, šířku (v mm), hloubku nebo výšku (v mm) "
                            f"a místo dodání. Název produktu vybírej tak, aby co nejvíce odpovídal jednomu z následujících produktů: "
                            f"{seznam_zalozek}. Vrať výsledek POUZE jako platný JSON. Nepřidávej žádný úvod, žádné vysvětlení, "
                            f"žádný text okolo. Používej dvojité uvozovky kolem klíčů i hodnot. "
                            f"Formát: {{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}."
                        )},
                        {"role": "user", "content": user_input}
                    ],
                    max_tokens=500
                )

                gpt_output_raw = response.choices[0].message.content.strip()

                # Ořízneme čistý JSON blok, pokud by GPT přidalo něco navíc
                start_idx = gpt_output_raw.find('{')
                end_idx = gpt_output_raw.rfind('}') + 1
                gpt_output_clean = gpt_output_raw[start_idx:end_idx]

                params = json.loads(gpt_output_clean)
                st.write("✅ Výstup z GPT:")
                st.code(params)

                produkt = params['produkt']
                sirka = int(params['šířka'])
                vyska_hloubka = int(params['hloubka_výška'])
                misto = params['misto']

                # Načtení příslušné záložky
                df = pd.read_excel(cenik_path, sheet_name=produkt, index_col=0)
                df.columns = df.columns.astype(str)
                df.index = df.index.astype(str)

                # Převod indexů a sloupců na číselné hodnoty
                sloupce = np.array(df.columns, dtype=int)
                radky = np.array(df.index, dtype=int)

                if "ZIP" in produkt or "Screen" in produkt:
                    # Screeny – vybereme nejbližší vyšší hodnotu
                    sirka_real = min([s for s in sloupce if s >= sirka], default=max(sloupce))
                    vyska_real = min([v for v in radky if v >= vyska_hloubka], default=max(radky))
                    cena = df.loc[str(vyska_real), str(sirka_real)]
                else:
                    # Pergoly – lineární interpolace
                    df_num = df.apply(pd.to_numeric, errors='coerce')
                    sirka_real = np.interp(sirka, sloupce, sloupce)
                    vyska_real = np.interp(vyska_hloubka, radky, radky)
                    cena = np.interp(sirka, sloupce, df_num.loc[str(int(vyska_real))])  # přibližná interpolace

                st.success(f"Cena produktu: {round(cena)} Kč bez DPH")

                # Výpočet dopravy (pevná vzdálenost 100 km jako příklad)
                vzdalenost_km = 100
                doprava = vzdalenost_km * 2 * 15

                # Montáže (jen pro pergoly)
                montaze = {}
                if "ZIP" not in produkt and "Screen" not in produkt:
                    montaze = {
                        "Montáž 12%": round(cena * 0.12),
                        "Montáž 13%": round(cena * 0.13),
                        "Montáž 14%": round(cena * 0.14),
                        "Montáž 15%": round(cena * 0.15)
                    }

                # Sestavení tabulky
                tabulka = [
                    {"POLOŽKA": produkt, "ROZMĚR": f"{sirka} × {vyska_hloubka} mm", "CENA bez DPH": round(cena)},
                    {"POLOŽKA": "Doprava", "ROZMĚR": f"{vzdalenost_km} km", "CENA bez DPH": round(doprava)}
                ]

                for montaz_label, montaz_cena in montaze.items():
                    tabulka.append({"POLOŽKA": montaz_label, "ROZMĚR": "", "CENA bez DPH": montaz_cena})

                st.write("✅ **Výsledná tabulka**")
                st.table(tabulka)

            except json.JSONDecodeError as e:
                st.error(f"❌ Chyba při zpracování JSON: {e}")
                st.code(gpt_output_raw)
            except Exception as e:
                st.error(f"❌ Došlo k chybě: {e}")

# Ve spodním pravém rohu zobrazíme seznam produktů malým písmem
st.markdown(
    f"""
    <div style='position: fixed; bottom: 10px; right: 10px; font-size: 10px; color: gray; text-align: right;'>
        Seznam produktů: {seznam_zalozek}
    </div>
    """,
    unsafe_allow_html=True
)
