items = json.loads(gpt_output_clean)
log("📦 Parsováno: " + json.dumps(items, ensure_ascii=False))

available_display_names = [st.session_state.NAME_MAP[k] for k in st.session_state.NAME_MAP]
available_canon = { # map pro robustní porovnání case/mezery, ale stále omezené na seznam
    re.sub(r"\s+", "", name.strip().lower()): name for name in available_display_names
}

results = []

for it in items:
    if it.get("nenalezeno"):
        msg = it.get("zprava", "Produkt nebyl rozpoznán, upřesněte název.")
        st.warning(f"⚠️ {msg}")
        log(f"⚠️ GPT vrátil nenalezeno: {msg}")
        continue

    produkt_display = str(it.get("produkt", "")).strip()
    canon = re.sub(r"\s+", "", produkt_display.lower())

    if canon not in available_canon:
        # Striktně odmítnout a vypsat, co máme k dispozici
        st.error(
            "❌ Produkt nebyl rozpoznán přesně v nabídce ceníků. "
            "Upřesněte, prosím, název.\n\n"
            "Dostupné produkty:\n- " + "\n- ".join(available_display_names)
        )
        log(f"❌ GPT produkt mimo seznam: '{produkt_display}'")
        continue

    # Máme přesnou shodu s jedním z ceníků
    picked_display = available_canon[canon]
    key = canonical(picked_display)
    df_mat = st.session_state.CENIKY.get(key)

    if df_mat is None or df_mat.empty:
        st.error(f"❌ Ceník '{picked_display}' není načten.")
        log(f"❌ Ceník není načten (key={key})")
        continue

    try:
        w = int(float(it["šířka"]))
        h = int(float(it["hloubka_výška"]))
    except Exception as e:
        st.error("❌ Šířka/výška nejsou správná čísla. Upravte prosím zadání.")
        log(f"❌ Chybná čísla rozměrů v položce: {it} ({e})")
        continue

    # … zde pokračuj tvým stávajícím výpočtem:
    use_w, use_h, price = find_price(df_mat, w, h)
    log(f"📐 Požadováno {w}×{h}, použito {use_w}×{use_h} v '{picked_display}'")
    log(f"📤 Hodnota df[{use_h}][{use_w}] = {price}")

    if pd.isna(price):
        st.warning(f"{picked_display}: buňka {use_w}×{use_h} je prázdná.")
        continue

    base_price = float(price)
    rowz = [{"Položka": picked_display, "Rozměr": f"{w}×{h}", "Cena bez DPH": round(base_price)}]

    # Montáže 12–15 %
    for p in [12, 13, 14, 15]:
        rowz.append({"Položka": f"Montáž {p} %", "Rozměr": "", "Cena bez DPH": round(base_price * p / 100)})

    # Doprava (pokud máš aktivní Google API klíč + místo)
    place = (it.get("misto") or "").strip()
    if place and place.lower() not in ["neuvedeno", "nedodano", "nedodáno"] and st.secrets.get("GOOGLE_API_KEY"):
        km = get_distance_km("Blučina, Czechia", place, st.secrets["GOOGLE_API_KEY"])
        if km is not None:
            travel_cost = round(km * 2 * 15)
            rowz.append({"Položka": "Doprava", "Rozměr": f"{km:.1f} km (tam+zpět)", "Cena bez DPH": travel_cost})
            log(f"🚚 Doprava {km:.1f} km = {travel_cost} Kč")

    results.extend(rowz)

if results:
    st.success(f"✅ Výpočet hotov – {len(results)} řádků.")
    st.dataframe(pd.DataFrame(results), use_container_width=True)
