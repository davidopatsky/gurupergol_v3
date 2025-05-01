import openai
import streamlit as st

client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("Test spojení s ChatGPT API")

if st.button("Otestovat spojení"):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Řekni Ahoj"}],
            max_tokens=5
        )
        reply = response.choices[0].message.content
        st.success(f"Odpověď z API: {reply}")
    except Exception as e:
        st.error(f"Chyba při volání API: {e}")
