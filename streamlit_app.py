import streamlit as st
import pandas as pd
import openai
import json

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

                # ... (pokračuj s načítáním ceníku a výpočty)

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
