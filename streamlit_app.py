import streamlit as st
import openai

# Načtení API klíče ze Streamlit Secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]

st.title("Test spojení s ChatGPT API")

if st.button("Otestovat spojení"):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # levnější testovací model
            messages=[{"role": "user", "content": "Řekni Ahoj"}],
            max_tokens=5  # omezíme na pár tokenů
        )
        reply = response['choices'][0]['message']['content']
        st.success(f"Odpověď z API: {reply}")
    except Exception as e:
        st.error(f"Chyba při volání API: {e}")
