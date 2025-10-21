import streamlit as st
def load_custom_css(file_path: str = "styles/style.css"):
    with open(file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)