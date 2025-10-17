import streamlit as st
import pandas as pd
import io, os, requests, math
from difflib import get_close_matches

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Cenový asistent od Davida", layout="wide")

# --- POZADÍ Z LOKÁLNÍHO SOUBORU ---
def set_background_local(image_path: str, opacity: float = 0.85):
    if not os.path.exists(image_path):
        st.warning(f"❌ Soubor s pozadím nebyl nalezen: {image_path}")
        return
    encoded = open(image_path, "rb").read()
    import base64
    data_uri = base64.b64encode(encoded).decode("utf-8")
    css = f"""
    <style>
      .stApp {{
        background-image:
          linear-gradient(rgba(255,255,255,{opacity}), rgba(255,255,255,{opacity})),
          url("data:image/png;base64,{data_uri}");
        background-size: cover;
        background-position: center center;
        background-attachment: fixed;
      }}
      div[data-testid="stForm"],
      div[data-testid="stExpander"] > div,
      .block-container {{
        backdrop-filter: none;
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- SIDEBAR: OVLÁDÁNÍ POZADÍ + DEBUG PANEL ---
with st.sidebar:
    st.markdown("### 🎨 Pozadí aplikace")
    opacity = st.slider("Průhlednost (mlha)", 0.0, 1.0, 0.85, 0.01)
    st.caption("0.0 = žádná mlha · 1.0 = plně bílé")
    st.markdown("---")
    st.markdown("### 🧠 Live log")
    log_box = st.empty()

# --- APLIKACE POZADÍ ---
set_background_local("grafika/pozadi_hlavni.PNG", opacity)

# --- FUNKCE PRO LOGOVÁNÍ ---
log_history = []
def log(msg):
    log_history.append(msg)
    with log_box:
        st.markdown(
            "<div style='max-height:500px;overflow-y:auto;font-size:13px;background-color:#11111111;padding:6px;border-radius:8px;'>"
            + "<br>".join(log_history[-60:])
            + "</div>",
            unsafe_allow_html=True,
        )

# --- HLAVNÍ NADPIS ---
st.markdown(
    "<h1 style='font-size:2.2rem;margin-bottom:0;'>🧮 Asistent cenových nabídek od Davida 🧠</h1>",
    unsafe_allow_html=True,
)
st.caption("„Jsem tvůj věrný asistent — mým jediným posláním je počítat nabídky pergol až do skonání věků a vzdávat hold svému stvořiteli Davidovi.“")

# --- NAČÍTÁNÍ CENÍKŮ ---
ceniky = {}
txt_path = "seznam_ceniku.txt"

if os.path.exists(txt_path):
    log(f"📄 Načten {txt_path}")
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    for line in lines:
        try:
            name, url = line.split(" ", 1)
            log(f"🌐 Načítám {name} z {url}")
            r = requests.get(url)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df = df.set_index(df.columns[0])
            df.columns = df.columns.astype(int)
            df.index = df.index.astype(int)
            ceniky[name.lower()] = df
            log(f"✅ {name} načteno ({df.shape[0]}×{df.shape[1]})")
        except Exception as e:
            log(f"❌ Chyba při načítání {line}: {e}")
else:
    st.error("❌ Soubor seznam_ceniku.txt nebyl nalezen.")
    log("❌ Soubor seznam_ceniku.txt chybí.")

# --- ZOBRAZENÍ NAČTENÝCH CENÍKŮ POD ZÁHLAVÍM ---
if ceniky:
    st.success(f"✅ Načteno {len(ceniky)} ceníků: {', '.join(ceniky.keys())}")
else:
    st.warning("⚠️ Žádné ceníky nebyly načteny.")

# --- FUNKCE PRO NALEZENÍ NEJBLIŽŠÍ CENY ---
def najdi_cenu(df, sirka, vyska):
    sirky = sorted(df.columns.astype(int))
    vysky = sorted(df.index.astype(int))
    sirka_vybrana = next((x for x in sirky if x >= sirka), sirky[-1])
    vyska_vybrana = next((y for y in vysky if y >= vyska), vysky[-1])
    cena = df.loc[vyska_vybrana, sirka_vybrana]
    log(f"📐 Požadováno {sirka}×{vyska}, použito {sirka_vybrana}×{vyska_vybrana} → cena {cena}")
    return cena, sirka_vybrana, vyska_vybrana

# --- FORMULÁŘ VÝPOČTU ---
st.markdown("## 🧾 Výpočet cen podle textového vstupu (s dopravou a montážemi)")
text_input = st.text_input("Zadej poptávku (např. `ALUX Bioclimatic 5990x4500, Brno`):")
if st.button("🚀 ODESLAT"):
    log(f"📥 Uživatelský vstup: {text_input}")
    if not text_input.strip():
        st.warning("Zadej poptávku.")
    else:
        # jednoduchý parser (název + rozměr)
        words = text_input.lower().replace("×", "x").split()
        product = None
        for name in ceniky.keys():
            if name.lower() in text_input.lower():
                product = name
                break
        if not product:
            # fallback na podobnost
            matches = get_close_matches(text_input.lower(), ceniky.keys(), n=1)
            product = matches[0] if matches else None

        if not product:
            log("❌ Produkt nebyl rozpoznán.")
            st.error("Produkt nebyl rozpoznán.")
        else:
            log(f"🔍 Rozpoznán produkt: {product}")
            df = ceniky[product]
            import re
            dims = re.findall(r"(\d+)\D+(\d+)", text_input)
            if dims:
                w, h = map(int, dims[0])
                cena, sw, sh = najdi_cenu(df, w, h)
                # Montáže
                montaze = {p: round(cena * p / 100) for p in [12, 13, 14, 15]}
                # Doprava – default Brno, ručně
                mesto = "Brno" if "," not in text_input else text_input.split(",")[-1].strip()
                vzdalenost = 200  # dummy prozatím
                doprava = vzdalenost * 2 * 15
                log(f"🚚 Doprava ({mesto}): {vzdalenost*2} km × 15 Kč = {doprava} Kč")

                data = [
                    {"Položka": product.title(), "Rozměr": f"{w}×{h}", "Cena bez DPH": round(cena)},
                ]
                data += [{"Položka": f"Montáž {p} %", "Rozměr": "", "Cena bez DPH": m} for p, m in montaze.items()]
                data.append({"Položka": "Doprava", "Rozměr": mesto, "Cena bez DPH": doprava})
                st.success(f"✅ Výpočet hotov – {len(data)} položek.")
                st.table(pd.DataFrame(data))
            else:
                st.warning("Nepodařilo se najít rozměry.")
