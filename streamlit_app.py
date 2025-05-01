import streamlit as st
import pandas as pd
import numpy as np
import openai
import os

# Nastavení OpenAI klienta
client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Nadpis aplikace
st.title("Asistent cenových nabídek od Davida")

# Vstupní pole
user_input = st.text_area("Zadejte popis produktu, rozměry a místo dodání:")

if st.button("Spočítat cenu"):
    if not user_input.strip():
        st.warning("Prosím, zadejte vstupní text.")
    else:
        with st.spinner("Analyzuji vstup přes ChatGPT..."):
            try:
                # Dotaz na GPT-4-turbo pro rozpoznání parametrů
                response = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": "Extrahuj z textu přesný název produktu, šířku (v mm), hloubku/výšku (v mm) a cílové místo dodání. Vrať pouze v čistém JSON formátu: {'produkt': ..., 'šířka': ..., 'hloubka_výška': ..., 'misto': ...}."},
                        {"role": "user", "content": user_input}
                    ],
                    max_tokens=300
                )
                gpt_output = response.choices[0].message.content
                st.write("✅ Výstup z GPT:")
                st.code(gpt_output)

                import json
                params = json.loads(gpt_output)
                produkt = params['produkt']
                sirka = int(params['šířka'])
                vyska_hloubka = int(params['hloubka_výška'])
                misto = params['misto']

                # Načtení ceníku
                ceník_path = "./data/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
                df = pd.read_excel(ceník_path, sheet_name=produkt, index_col=0)

                # Najít nejbližší rozměry (bez interpolace pro screeny)
                if "Screen" in produkt:
                    sirky = [int(c) for c in df.columns]
                    vysky = [int(r) for r in df.index]
                    nejblizsi_sirka = min([s for s in sirky if s >= sirka], default=max(sirky))
                    nejblizsi_vyska = min([v for v in vysky if v >= vyska_hloubka], default=max(vysky))
                    cena = df.loc[nejblizsi_vyska, str(nejblizsi_sirka)]
                else:
                    # Lineární interpolace
                    df_interp = df.apply(pd.to_numeric, errors='coerce').interpolate(method='linear', axis=0).interpolate(method='linear', axis=1)
                    if sirka in df.columns and vyska_hloubka in df.index:
                        cena = df.loc[vyska_hloubka, str(sirka)]
                    else:
                        cena = df_interp.loc[vyska_hloubka, str(sirka)]

                # Výpočet dopravy
                st.write("✅ Výpočet dopravy:")
                vzdalenost_km = 100  # PŘÍKLAD! Nahraď skutečnou vzdáleností Blučina–misto
                doprava = vzdalenost_km * 2 * 15

                # Výpočet montáže (pouze pro pergoly)
                montaze = {}
                if "Screen" not in produkt:
                    montaze = {
                        "Montáž 12%": round(cena * 0.12),
                        "Montáž 13%": round(cena * 0.13),
                        "Montáž 14%": round(cena * 0.14),
                        "Montáž 15%": round(cena * 0.15)
                    }

                # Výstupní tabulka
                st.write("✅ **Výsledná tabulka**")
                tabulka = [
                    {"POLOŽKA": produkt, "ROZMĚR": f"{sirka} × {vyska_hloubka} mm", "CENA bez DPH": round(cena)},
                    {"POLOŽKA": "Doprava", "ROZMĚR": f"{vzdalenost_km} km", "CENA bez DPH": round(doprava)}
                ]

                for montaz_label, montaz_cena in montaze.items():
                    tabulka.append({"POLOŽKA": montaz_label, "ROZMĚR": "", "CENA bez DPH": montaz_cena})

                st.table(tabulka)

            except Exception as e:
                st.error(f"⚠ Chyba: {e}")
