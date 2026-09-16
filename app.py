import streamlit as st

from src.pipeline import run_ingestion_pipeline


st.set_page_config(
    page_title="Miau",
    layout="wide"
)


st.title("Miau")

st.write(
    "Motor de análisis automatizado de campañas."
)