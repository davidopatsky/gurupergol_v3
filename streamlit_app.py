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
    st.session_state.sheet_names = sheet_names  # uložíme do session
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
                # Dotaz na GPT-4-turbo s aktuálními názvy záložek
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": (
                            f"Tvůj úkol: z následujícího textu vytáhni VŠECHNY produkty, každý se svým názvem, šířkou (v mm), hloubkou nebo výškou (v mm) a místem dodání. "
                            f"Název produktu vybírej co nejpřesněji z následujícího seznamu produktů: {seznam_zalozek}. "
                            f"Pokud uživatel napíše jakoukoli z těchto frází: 'screen', 'screenová roleta', 'boční screen', 'boční screenová roleta' — VŽDY přiřaď jako název produktu 'screen' bez ohledu na pravopis nebo variantu."
                            f"Pokud žádný produkt neodpovídá, vrať položku s klíčem 'nenalezeno': true a zprávou pro uživatele, že produkt nebyl nalezen a je třeba upřesnit název. "
                            f"Vrať výsledek POUZE jako platný JSON seznam položek. Nepřidávej žádný úvod ani vysvětlení. "
                            f"Formát: [{{\"produkt\": \"...\", \"šířka\": ..., \"hloubka_výška\": ..., \"misto\": \"...\"}}] nebo [{{\"nenalezeno\": true, \"zprava\": \"produkt nenalezen, prosím o upřesnění názvu produktu\"}}]."
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

                if products and 'nenalezeno' in products[0]:
                    zprava = products[0].get('zprava', 'Produkt nenalezen.')
                    st.warning(f"❗ {zprava}")
                    debug_text += f"⚠ {zprava}\n"
                    st.session_state.debug_history += debug_text
                else:
                    # Mapování aliasů na záložky
                    produkt_map = {
                        "alux screen": "screen",
                        "alux screen 1": "screen",
                        "screen": "screen",
                        "screenova roleta": "screen",
                        "screenová roleta": "screen",
                        "boční screenová roleta": "screen",
                        "boční screen": "screen"
                    }

                    for params in products:
                        produkt = params['produkt'].strip().lower()
                        produkt_lookup = produkt_map.get(produkt, produkt)
                        misto = params['misto']

                        # Ověření a převod šířky
                        try:
                            sirka = int(float(params['šířka']))
                        except (ValueError, TypeError):
                            st.error(f"❌ Nedostatečné zadání nebo chybí rozměr (šířka) pro produkt {produkt}")
                            continue

                        # Ověření a převod výšky/hloubky
                        if params['hloubka_výška'] is None:
                            if "zip" in produkt_lookup or "screen" in produkt_lookup:
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

                        debug_text += f"\nZpracovávám produkt: {produkt_lookup}, {sirka}×{vyska_hloubka}, místo: {misto}\n"

                        # Najdeme správnou záložku
                        sheet_match = next((s for s in st.session_state.sheet_names if s.lower() == produkt_lookup), None)
                        if sheet_match is None:
                            sheet_match = next((s for s in st.session_state.sheet_names if produkt_lookup in s.lower()), None)

                        if sheet_match is None:
                            st.error(f"❌ Nenalezena záložka '{produkt_lookup}' v Excelu. Zkontrolujte názvy.")
                            debug_text += f"Chyba: nenalezena záložka '{produkt_lookup}'\n"
                            continue

                        # Načteme příslušnou záložku
                        df = pd.read_excel(cenik_path, sheet_name=sheet_match, index_col=0)

                        # Vyčistíme sloupce (šířky)
                        sloupce_ciste = []
                        for col in df.columns:
                            try:
                                sloupce_ciste.append(int(float(col)))
                            except (ValueError, TypeError):
                                continue
                        sloupce = sorted(sloupce_ciste)

                        # Vyčistíme indexy (výšky/hloubky)
                        radky_ciste = []
                        for idx in df.index:
                            try:
                                radky_ciste.append(int(float(idx)))
                            except (ValueError, TypeError):
                                continue
                        radky = sorted(radky_ciste)

                        # 🔍 Debug výpis dostupných hodnot
                        debug_text += f"DEBUG - Všechny sloupce (šířky): {sloupce}\n"
                        debug_text += f"DEBUG - Všechny řádky (výšky/hloubky): {radky}\n"
                        debug_text += f"DEBUG - Požadovaná šířka: {sirka}, požadovaná výška/hloubka: {vyska_hloubka}\n"

                        # Najdeme nejbližší vyšší nebo největší dostupnou hodnotu
                        sirka_real = next((s for s in sloupce if s >= sirka), sloupce[-1])
                        vyska_real = next((v for v in radky if v >= vyska_hloubka), radky[-1])

                        debug_text += f"DEBUG - Vybraná šířka (nejbližší vyšší/největší): {sirka_real}\n"
                        debug_text += f"DEBUG - Vybraná výška/hloubka (nejbližší vyšší/největší): {vyska_real}\n"

                        try:
                            cena = df.loc[vyska_real, sirka_real]
                        except KeyError:
                            try:
                                cena = df.loc[str(vyska_real), str(sirka_real)]
                            except KeyError:
                                st.error(f"❌ Nenalezena cena pro {sirka_real} × {vyska_real}")
                                debug_text += f"❌ Chyba: nenalezena cena pro {sirka_real} × {vyska_real}\n"
                                continue

                        debug_text += f"✅ Nalezená cena: {cena}\n"

                        all_rows.append({
                            "POLOŽKA": produkt_lookup,
                            "ROZMĚR": f"{sirka} × {vyska_hloubka} mm",
                            "CENA bez DPH": round(cena)
                        })

                        # Montáže (jen pro pergoly)
                        if "zip" not in produkt_lookup and "screen" not in produkt_lookup:
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

                    result_text = "\n".join([f"{row['POLOŽKA']}: {row['ROZMĚR']} → {row['CENA bez DPH']} Kč"
                                             for row in all_rows])
                    debug_text += f"\n📤 **Výsledek aplikace:**\n{result_text}\n---\n"

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

# Debug panel dole (vodorovně, zvětšený na 35 % výšky)
st.markdown(
    f"<div style='position: fixed; bottom: 0; left: 0; right: 0; height: 35%; overflow-y: scroll; "
    f"background-color: #f0f0f0; font-size: 10px; padding: 5px;'>"
    f"<pre>{st.session_state.debug_history}</pre></div>",
    unsafe_allow_html=True
)
