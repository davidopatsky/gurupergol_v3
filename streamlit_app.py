# ==========================================
# 📂 NÁHLED NAČTENÝCH CENÍKŮ
# ==========================================
st.markdown("---")
with st.expander("📂 Zobrazit všechny načtené ceníky", expanded=False):
    if not st.session_state.CENIKY:
        st.warning("⚠️ Zatím nejsou načtené žádné ceníky. Klikni na tlačítko ♻️ Znovu načíst.")
    else:
        st.success(f"✅ Načteno {len(st.session_state.CENIKY)} ceníků:")
        for name in st.session_state.PRODUKTY:
            df = st.session_state.CENIKY.get(name.lower())
            if df is None or df.empty:
                st.error(f"❌ {name}: prázdný nebo vadný ceník.")
                continue
            st.markdown(f"### {name}")
            st.dataframe(df.head(5), use_container_width=True)
