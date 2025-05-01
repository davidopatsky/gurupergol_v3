import streamlit as st
import pandas as pd
import numpy as np

# === CONFIGURATION ===
EXCEL_FILE = "ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"
# Pokud budete načítat z GitHubu, použijte:
# EXCEL_FILE = "https://raw.githubusercontent.com/vas-ucet/repo/main/ALUX_pricelist_CZK_2025 simplified chatgpt v7.xlsx"

# === FUNCTIONS ===

@st.cache_data
def load_all_sheets(file_path):
    return pd.read_excel(file_path, sheet_name=None, header=0, index_col=0)

def find_nearest_bigger(arr, value):
    arr_sorted = sorted([x for x in arr if not np.isnan(x)])
    for v in arr_sorted:
        if v >= value:
            return v
    return max(arr_sorted)

def interpolate_value(df, width, height):
    widths = df.columns.astype(float)
    heights = df.index.astype(float)

    x1 = max([w for w in widths if w <= width], default=min(widths))
    x2 = min([w for w in widths if w >= width], default=max(widths))
    y1 = max([h for h in heights if h <= height], default=min(heights))
    y2 = min([h for h in heights if h >= height], default=max(heights))

    q11 = df.at[y1, x1]
    q12 = df.at[y2, x1]
    q21 = df.at[y1, x2]
    q22 = df.at[y2, x2]

    if x1 == x2 and y1 == y2:
        return q11
    elif x1 == x2:
        return q11 + (q12 - q11) * (height - y1) / (y2 - y1)
    elif y1 == y2:
        return q11 + (q21 - q11) * (width - x1) / (x2 - x1)
    else:
        return (q11 * (x2 - width) * (y2 - height) +
                q21 * (width - x1) * (y2 - height) +
                q12 * (x2 - width) * (height - y1) +
                q22 * (width - x1) * (height - y1)) / ((x2 - x1) * (y2 - y1))

# === STREAMLIT UI ===

st.title("ALUX Kalkulačka (Excel ceník)")

# Load Excel sheets
sheets = load_all_sheets(EXCEL_FILE)
products = list(sheets.keys())

product = st.selectbox("Vyberte produkt", products)
width = st.number_input("Zadejte šířku (mm)", min_value=1000, max_value=10000, step=100)
height = st.number_input("Zadejte výšku/hloubku (mm)", min_value=1000, max_value=5000, step=100)
location = st.text_input("Místo dodání")

if st.button("Spočítat"):
    df = sheets[product].dropna(how='all', axis=0).dropna(how='all', axis=1)
    df.columns = df.columns.astype(float)
    df.index = df.index.astype(float)

    if "screen" in product.lower():
        used_width = find_nearest_bigger(df.columns, width)
        used_height = find_nearest_bigger(df.index, 2500)  # fixní výška pro screeny
        base_price = df.at[used_height, used_width]
        st.write(f"Screen použitá šířka: {used_width}, výška: {used_height}")
    else:
        base_price = interpolate_value(df, width, height)

    transport_cost = 2 * 50 * 15  # placeholder, můžete napojit na API Google Maps
    montage_rates = [12, 13, 14, 15]
    montage_prices = [round(base_price * rate / 100) for rate in montage_rates]

    result_data = {
        "POLOŽKA": [product, "Doprava"] + [f"Montáž {rate}%" for rate in montage_rates],
        "ROZMĚR": [f"{width} × {height} mm", location] + ["-"] * len(montage_rates),
        "CENA bez DPH": [round(base_price), transport_cost] + montage_prices
    }

    result_df = pd.DataFrame(result_data)
    st.subheader("Výsledek kalkulace")
    st.table(result_df)
