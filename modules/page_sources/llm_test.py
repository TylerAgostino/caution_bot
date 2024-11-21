from modules.llm import generate_caution_reason
import streamlit as st

def ui():
    st.header("Random Caution Bot")
    st.write("This bot generates random caution reasons for simulated racing events.")
    st.write("Click the button below to generate a random caution reason.")

    if st.button("Generate Random Caution Reason"):
        caution_reason = generate_caution_reason()
        st.write(f"**Caution Reason:** {caution_reason}")

    if st.button("Generate Random Black Flag Reason"):
        black_flag_reason = generate_black_flag_reason()
        st.write(f"**Black Flag Reason:** {black_flag_reason}")

llm_test = st.Page(ui, title='LLM Testing', url_path='llm_test')