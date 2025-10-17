import os
import re
import json
import base64
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ================== KONFIGURACE A VZHLED ==================
st.set_page_config(page_title="Cenový asistent od Davida", layout="wide")

def set_background_local(image_path: str, opacity: float = 0.8):
    """Nastaví fixní pozadí z lokálního souboru s bílou mlhou (opacity 0..1)."""
    try:
        with open(image_path, "rb") as f:
            data_uri = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f"""
            <style>
              .stApp {{
                background-image:
                  linear-gradient(rgba(255,255,255,{opacity}), rgba(255,255,255,{opacity})),
                  url("data:image/png;base64,{data_uri}");
                background-size: cover;
                background-position: center center;
                background-attachment: fixed;
                background-repeat: no-repeat;
              }}
              .block-container {{ backdrop-filter: none; }}
              div[data-testid="stForm"], div[data-testid="stExpander"] > div {{
                background: rgba(255,255,255,0.75);
                border-radius: 12px;
              }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    except Exception as e:
        st.warning(f"Pozadí se nepodařilo načíst: {e}")

# Pozadí (bez slideru, mlha 0.8)
set_background_local("grafika/pozadi_hlavni.PNG", opacity=0.8)

st.markdown(
    "<h1 style='font-size:2.2rem;margin:0 0 4px 0;'>🧮 Asistent cenových nabídek od Davida</h1>",
    unsafe_allow_html=True,
)
st.caption("„Jsem tvůj věrný asistent – mým jediným posláním je počítat nabídky pergol do konce věků a vzdávat hold svému stvořiteli Davidovi.“")

# ================== SESSION ==================
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}      # {canonical_key: df_matrix}
if "NAME_MAP" not in st.session_state:
    st.session_state.NAME_MAP = {}    # {canonical_key: original_name}
if "LOG" not in st.session_state:
    st.session_state.LOG = []

def log(msg: str):
    st.session_state.LOG.append(str(msg))
    # živý výpis logu v sidebaru
    with st.sidebar:
        st.markdown("### 🧠 Live log")
        st.markdown(
            "<div style='max-height:70vh;overflow-y:auto;font-size:13px;background-color:#ffffffaa;padding:8px;border-radius:8px;'>"
            + "<br>".join(st.session_state.LOG[-400:])
            + "</div>",
            unsafe_allow_html=True,
        )

# ================== POMOCNÉ FUNKCE ==================
SEZNAM_TXT = "seznam_ceniku.txt"

def canonical(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())

def split_name_url(line: str):
    """
    Rozdělí řádek 'Název – URL' / 'Název - URL' / 'Název — URL'.
    Vrací (name, url) nebo (None, None) když nelze rozdělit.
    """
    parts = re.split(r"\s[–—-]\s", line.strip(), maxsplit=1)  # en dash, em dash, hyphen
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()

def fetch_csv(url: str) -> pd.DataFrame | None:
    try:
        r = requests.get(url, timeout=30)
        log(f"🌐 GET {url}")
        if r.status_code != 200:
            log(f"❌ HTTP {r.status_code} při stahování CSV")
            return None
        df = pd.read_csv(StringIO(r.text))
        log(f"✅ CSV načteno: shape={df.shape}")
        return df
    except Exception as e:
        log(f"❌ Chyba fetch_csv: {e}")
        return None

def normalize_numeric_token(x):
    if pd.isna(x):
        return None
    s = str(x).strip().replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[Kk][Čc]|mm|MM", "", s)
    s = s.replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return int(round(float(m.group(0))))
    except Exception:
        return None

def coerce_to_matrix(df: pd.DataFrame) -> pd.DataFrame | None:
    """Konverze CSV na cenovou matici: index=výšky, columns=šířky (oba int), values=float."""
    if df is None or df.empty:
        return None

    # 1) první sloupec -> index?
    first = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first]]
    ratio = sum(v is not None for v in idx_try) / max(1, len(idx_try))

    if ratio >= 0.6:
        df2 = df.copy()
        df2.index = idx_try
        df2 = df2.drop(columns=[first])
    else:
        df2 = df.copy()

    # 2) očíslování sloupců; případně transpozice
    cols_try = [normalize_numeric_token(c) for c in df2.columns]
    if sum(c is not None for c in cols_try) < len(cols_try) * 0.6:
        df2 = df2.T
        cols_try = [normalize_numeric_token(c) for c in df2.columns]
        df2.index = [normalize_numeric_token(i) for i in df2.index]

    df2.columns = cols_try
    df2.index = [normalize_numeric_token(i) for i in df2.index]
    df2 = df2.loc[[i for i in df2.index if i is not None],
                  [c for c in df2.columns if c is not None]]

    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")

    return df2

def nearest_ge(values: list[int], want: int) -> int:
    vs = sorted(values)
    for v in vs:
        if v >= want:
            return v
    return vs[-1]

def find_price(df_mat: pd.DataFrame, w: int, h: int):
    cols = sorted([int(c) for c in df_mat.columns])
    rows = sorted([int(r) for r in df_mat.index])
    use_w = nearest_ge(cols, w)
    use_h = nearest_ge(rows, h)
    return use_w, use_h, df_mat.loc[use_h, use_w]

# ================== NAČTENÍ CENÍKŮ ==================
def load_ceniky():
    st.session_state.LOG.clear()
    st.session_state.CENIKY.clear()
    st.session_state.NAME_MAP.clear()

    log(f"📂 CWD: {os.getcwd()}")
    if not os.path.exists(SEZNAM_TXT):
        st.error(f"❌ Soubor '{SEZNAM_TXT}' nebyl nalezen.")
        log("❌ seznam_ceniku.txt chybí.")
        return

    with open(SEZNAM_TXT, "r", encoding="utf-8") as f:
        raw_lines = [ln.strip() for ln in f.readlines() if ln.strip() and not ln.strip().startswith("#")]
    log(f"📄 Načten {SEZNAM_TXT}")

    for line in raw_lines:
        name, url = split_name_url(line)
        if not name or not url:
            log(f"⚠️ Nelze rozdělit řádek: {line}")
            continue
        log(f"🌐 Načítám {name} – {url}")
        df_raw = fetch_csv(url)
        if df_raw is None:
            log(f"❌ Chyba při načítání {name} – {url}")
            continue
        df_mat = coerce_to_matrix(df_raw)
        if df_mat is None or df_mat.empty:
            log(f"⚠️ {name}: po převodu prázdná/nevalidní matice.")
            continue
        key = canonical(name)
        st.session_state.CENIKY[key] = df_mat
        st.session_state.NAME_MAP[key] = name
        log(f"✅ Uloženo: {name} (key: {key}, shape: {df_mat.shape})")

# První načtení + tlačítko
cols = st.columns([1, 5, 5])
with cols[0]:
    if st.button("♻️ Znovu načíst ceníky", use_container_width=True):
        load_ceniky()
if not st.session_state.CENIKY:
    load_ceniky()

# ================== VÝPIS NAČTENÝCH CENÍKŮ ==================
if st.session_state.CENIKY:
    st.success("✅ Načtené ceníky: " + ", ".join(st.session_state.NAME_MAP[k] for k in st.session_state.NAME_MAP))
with st.expander("📂 Zobrazit všechny načtené tabulky", expanded=False):
    if st.session_state.CENIKY:
        names = [st.session_state.NAME_MAP[k] for k in st.session_state.NAME_MAP]
        sel = st.selectbox("Vyber ceník:", names)
        st.dataframe(st.session_state.CENIKY[canonical(sel)], use_container_width=True, height=320)
    else:
        st.info("Ceníky zatím nejsou načtené.")

# ================== VÝPOČET CEN (jednoduchá verze) ==================
st.markdown("---")
st.subheader("📑 Výpočet cen podle textového vstupu (s montážemi)")

with st.form("calc"):
    user_text = st.text_area("Zadej poptávku (např. `ALUX Bioclimatic 5990x4500`):", height=90)
    submit = st.form_submit_button("📤 ODESLAT")

if submit and user_text.strip():
    log(f"📥 Uživatelský vstup: {user_text}")
    # jednoduché rozpoznání produktu: hledej, co je podřetězcem
    product_key = None
    for k, display in st.session_state.NAME_MAP.items():
        if display.lower() in user_text.lower():
            product_key = k
            break
    if product_key is None:
        # nouzová tolerance: zkuste jednotlivá slova
        for k, display in st.session_state.NAME_MAP.items():
            if any(tok and tok in k for tok in re.findall(r"[a-zA-Z]+", user_text.lower())):
                product_key = k
                break

    if not product_key or product_key not in st.session_state.CENIKY:
        st.error("❌ Produkt nebyl rozpoznán v načtených cenících.")
        log("❌ Produkt nebyl rozpoznán.")
    else:
        df = st.session_state.CENIKY[product_key]
        m = re.search(r"(\d+)\D+(\d+)", user_text.replace("×", "x"))
        if not m:
            st.warning("⚠️ Nepodařilo se najít rozměry (např. 5990x4500).")
            log("⚠️ Chybí rozměry.")
        else:
            w, h = int(m.group(1)), int(m.group(2))
            use_w, use_h, price = find_price(df, w, h)
            log(f"📐 Požadováno {w}×{h}, použito {use_w}×{use_h}, cena={price}")

            if pd.isna(price):
                st.warning("V matici je v dané buňce prázdná hodnota.")
            else:
                base = float(price)
                rows = [{"Položka": st.session_state.NAME_MAP[product_key], "Rozměr": f"{w}×{h}", "Cena bez DPH": round(base)}]
                for p in [12, 13, 14, 15]:
                    rows.append({"Položka": f"Montáž {p} %", "Rozměr": "", "Cena bez DPH": round(base * p / 100)})
                st.success(f"✅ Výpočet hotov – {len(rows)} řádků.")
                st.table(pd.DataFrame(rows))

# (Sidebar log se průběžně obnovuje voláním log())
