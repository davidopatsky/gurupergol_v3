import os
import json
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ===============================
# ZÁKLAD
# ===============================
st.set_page_config(page_title="Cenový asistent", layout="wide")
st.title("🧠 Cenový asistent – čistý start")

# Session
if "LOG" not in st.session_state:
    st.session_state.LOG = []
if "CENIKY" not in st.session_state:
    st.session_state.CENIKY = {}   # dict[str(lower) -> DataFrame]
if "PRODUKTY" not in st.session_state:
    st.session_state.PRODUKTY = [] # hezké názvy pro prompt

def log(msg: str):
    st.session_state.LOG.append(str(msg))

def show_log():
    st.text_area("🪵 Live log", value="\n".join(st.session_state.LOG), height=320)

# ===============================
# POMOCNÉ FUNKCE
# ===============================
SEZNAM_PATH = "seznam_ceniku.txt"

def cwd_and_existence_probe():
    log(f"📂 CWD: {os.getcwd()}")
    log(f"🔎 exists('{SEZNAM_PATH}')? {os.path.exists(SEZNAM_PATH)}")

def read_seznam_ceniku():
    """
    Vrátí list (name, url) z `seznam_ceniku.txt`.
    Formát řádků: 'Název - URL' nebo 'Název – URL'
    Ignoruje prázdné řádky a řádky začínající #.
    """
    pairs = []
    try:
        with open(SEZNAM_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        log(f"📄 Načten {SEZNAM_PATH} ({len(lines)} řádků)")
        for i, line in enumerate(lines, start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            # povolíme oba oddělovače: " - " i " – "
            if " - " in raw:
                name, url = raw.split(" - ", 1)
            elif " – " in raw:
                name, url = raw.split(" – ", 1)
            else:
                log(f"⚠️ Řádek {i} přeskočen (chybí oddělovač ' - ' nebo ' – '): {raw}")
                continue
            name = name.strip()
            url = url.strip()
            if not name or not url:
                log(f"⚠️ Řádek {i} má prázdný název nebo URL: {raw}")
                continue
            pairs.append((name, url))
        log(f"✅ Zparsováno {len(pairs)} položek ze seznamu")
    except Exception as e:
        log(f"❌ Chyba při čtení '{SEZNAM_PATH}': {e}")
        st.error(f"Soubor '{SEZNAM_PATH}' chybí nebo nejde číst.")
    return pairs

def fetch_csv(url: str) -> pd.DataFrame | None:
    try:
        log(f"🌐 GET {url}")
        r = requests.get(url, timeout=30)
        log(f"🔁 HTTP {r.status_code}, {len(r.text)} znaků")
        if r.status_code != 200:
            return None
        df = pd.read_csv(StringIO(r.text))
        log(f"✅ CSV načteno: shape={df.shape}")
        # ukázka prvních 3 řádků (bez zahlcení)
        log("👀 Náhled CSV (3 řádky):\n" + df.head(3).to_string(index=False))
        return df
    except Exception as e:
        log(f"❌ Chyba při stahování CSV: {e}")
        return None

def normalize_numeric_token(x) -> int | None:
    """
    Vezme token (hlavičku nebo index), vyrobí z něj int:
    - odstraní NBSP, mezery, tečky, tisícové oddělovače, jednotky, měnu
    - nahradí čárku tečkou
    - převede přes float -> int
    Pokud to nejde, vrátí None.
    """
    if pd.isna(x):
        return None
    s = str(x).strip()
    # pryč měny, mm, texty v závorkách apod.
    s = s.replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[Kk][Čc]|\s*mm|\s*MM", "", s)
    s = s.replace(".", "")  # tečky jako tisícové odděl.
    s = s.replace(",", ".") # česká čárka -> tečka
    # vyber jen čísla a případně tečku/znamenko
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        val = float(m.group(0))
        return int(round(val))
    except Exception:
        return None

def coerce_matrix(df: pd.DataFrame) -> pd.DataFrame | None:
    """
    Očekává matici: první sloupec = index (výšky), hlavičky sloupců = šířky.
    Vrátí DF s indexy a sloupci jako int (rozměry). Na těle ponechá float.
    """
    if df is None or df.empty:
        log("⚠️ Prázdný DF, nelze převést na matici.")
        return None

    # Pokud první sloupec není rozměr, pokusíme se poznat, jestli je.
    # Heuristika: když první sloupec vypadá numericky u většiny řádků, použij ho jako index.
    first_col = df.columns[0]
    idx_try = [normalize_numeric_token(v) for v in df[first_col]]
    numerics_ratio = sum(v is not None for v in idx_try) / max(1, len(idx_try))

    if numerics_ratio > 0.6:
        # použij první sloupec jako index
        df2 = df.copy()
        df2.index = idx_try
        df2 = df2.drop(columns=[first_col])
    else:
        # už pravděpodobně index má (nebo máme první řádek jako hlavičku) – zkus přímo
        df2 = df.copy()

    # normalizuj sloupce
    new_cols = [normalize_numeric_token(c) for c in df2.columns]
    # pokud to selže (moc None), zkus transponovat (někdy Sheets vyexportuje otočené)
    if sum(c is not None for c in new_cols) < len(new_cols) * 0.6:
        log("↔️ Sloupce nevypadají numericky, zkouším transponovat…")
        df2 = df2.T
        new_cols = [normalize_numeric_token(c) for c in df2.columns]
        # a indexy znovu
        df2.index = [normalize_numeric_token(i) for i in df2.index]

    df2.columns = new_cols
    df2.index = [normalize_numeric_token(i) for i in df2.index]

    # zahodit sloupce/indexy, které nejdou převést
    df2 = df2.loc[ [i for i in df2.index if i is not None],
                   [c for c in df2.columns if c is not None] ]

    # tělo na float (kde to jde)
    for c in df2.columns:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")

    log(f"🧩 Matice připravena: shape={df2.shape} (indexy a sloupce jsou int)")
    return df2

def nearest_ge(values: list[int], want: int) -> int:
    """Nejbližší hodnota >= want (jinak vezmi max)."""
    vals = sorted(values)
    for v in vals:
        if v >= want:
            return v
    return vals[-1]

def find_price(df_mat: pd.DataFrame, width: int, height: int):
    """Najde cenu v matici podle nejbližších rozměrů (šířka = columns, výška = index)."""
    if df_mat is None or df_mat.empty:
        return None, None, None
    cols = sorted([int(c) for c in df_mat.columns])
    rows = sorted([int(r) for r in df_mat.index])
    use_w = nearest_ge(cols, width)
    use_h = nearest_ge(rows, height)
    price = df_mat.loc[use_h, use_w]
    return use_w, use_h, price

# ===============================
# NAČTENÍ CENÍKŮ
# ===============================
def load_all_ceniky():
    st.session_state.LOG.clear()
    cwd_and_existence_probe()
    pairs = read_seznam_ceniku()
    st.session_state.CENIKY.clear()
    st.session_state.PRODUKTY.clear()

    for name, url in pairs:
        raw = fetch_csv(url)
        if raw is None:
            log(f"❌ {name}: CSV nedostupné.")
            continue
        mat = coerce_matrix(raw)
        if mat is None or mat.empty:
            log(f"⚠️ {name}: po převodu na matici je DF prázdný.")
            continue
        st.session_state.CENIKY[name.lower()] = mat
        st.session_state.PRODUKTY.append(name)
        # zobrazení rozpětí rozměrů
        try:
            cols = sorted([int(c) for c in mat.columns])
            rows = sorted([int(r) for r in mat.index])
            log(f"📏 {name}: šířky {cols[0]}–{cols[-1]} | výšky {rows[0]}–{rows[-1]} (kroků: {len(cols)}×{len(rows)})")
        except Exception:
            pass

# UI: reload ceníků
colA, colB = st.columns([1,1])
with colA:
    if st.button("♻️ Znovu načíst ceníky"):
        load_all_ceniky()
with colB:
    st.write("")  # placeholder

# Auto-load při prvním spuštění (pokud nic není)
if not st.session_state.CENIKY:
    load_all_ceniky()

# ===============================
# NÁHLED VŠECH TABULEK
# ===============================
with st.expander("📂 Zobrazit všechny načtené tabulky"):
    if not st.session_state.CENIKY:
        st.info("Zatím nic nenalezeno – zkontroluj 'seznam_ceniku.txt' a klikni na 'Znovu načíst ceníky'.")
    else:
        for name in st.session_state.PRODUKTY:
            df = st.session_state.CENIKY.get(name.lower())
            st.markdown(f"#### {name}")
            if df is not None:
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Ceník není načten.")

# ===============================
# VÝPOČET CEN – TEXTOVÝ VSTUP (přes GPT)
# ===============================
st.markdown("---")
st.subheader("📝 Výpočet cen podle textového vstupu")

with st.form("calc_form"):
    user_text = st.text_area("Zadej poptávku (např. `ALUX Bioclimatic 5990x4500`):", height=100)
    submitted = st.form_submit_button("📤 ODESLAT")

if submitted and user_text.strip():
    log("\n---")
    log(f"📥 Uživatelský vstup:\n{user_text}")

    # připrav seznam produktů pro GPT
    product_list = ", ".join(st.session_state.PRODUKTY) if st.session_state.PRODUKTY else "screen"
    system_prompt = (
        "Tvůj úkol: z následujícího textu vytáhni VŠECHNY položky s názvem produktu, šířkou (mm) a výškou (mm). "
        f"Název produktu vybírej co nejpřesněji z tohoto seznamu: {product_list}. "
        "Fráze jako 'screen', 'screenová roleta' vždy přiřaď k produktu 'screen'. "
        "Rozměry jako 3500-250 nejprve spočítej a výstup dej jako čistá čísla v mm. "
        "Vrať POUZE validní JSON list, např. "
        "[{\"produkt\":\"ALUX Bioclimatic\",\"šířka\":5990,\"hloubka_výška\":4500}]"
    )
    try:
        import openai
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role":"system","content": system_prompt},
                {"role":"user","content": user_text}
            ],
            max_tokens=600
        )
        raw = resp.choices[0].message.content.strip()
        log("📨 GPT odpověď (RAW):\n" + raw)
        try:
            items = json.loads(raw)
        except Exception as e:
            log(f"❌ JSON decode chyba: {e}")
            items = []
    except Exception as e:
        log(f"❌ GPT chyba: {e}")
        items = []

    # zpracování položek
    results = []
    for it in items:
        try:
            produkt = str(it["produkt"]).strip()
            w = int(float(it["šířka"]))
            h = int(float(it["hloubka_výška"]))
        except Exception as e:
            log(f"❌ Položka má špatný formát: {it} ({e})")
            continue

        df_mat = st.session_state.CENIKY.get(produkt.lower())
        if df_mat is None:
            log(f"❌ Ceník nenalezen: {produkt}")
            continue

        # najdi nejbližší rozměry a cenu
        use_w, use_h, price = find_price(df_mat, w, h)
        log(f"📐 Požadováno {w}×{h}, použito {use_w}×{use_h}")
        log(f"📤 df.loc[{use_h}, {use_w}] = {price}")
        if pd.isna(price):
            st.warning(f"{produkt}: {w}×{h} → {use_w}×{use_h}: buňka je prázdná (NaN).")
            continue

        results.append({
            "Produkt": produkt,
            "Rozměr (požadovaný)": f"{w}×{h}",
            "Rozměr (použitý)": f"{use_w}×{use_h}",
            "Cena bez DPH": float(price) if not pd.isna(price) else None
        })

    if results:
        st.success(f"Hotovo – nalezeno {len(results)} položek.")
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.info("Nebyla nalezena žádná ocenitelná položka (zkontroluj vstup nebo ceník).")

# ===============================
# DEBUG PANEL
# ===============================
st.markdown("---")
st.subheader("🛠️ Debug panel")
show_log()
