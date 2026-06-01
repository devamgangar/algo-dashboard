"""Algo Trading Dashboard - main entry point."""
import streamlit as st

st.set_page_config(
    page_title="Algo Dashboard",
    layout="wide",
)
st.session_state["__current_page"] = "home"

st.title("Algo Trading Dashboard")
st.markdown(
    "Backtest and forward-test trading strategies on Indian equities."
)

st.markdown("---")

st.subheader("Navigation")
st.markdown(
    """
- **Strategies** — Browse registered strategies
- **Backtest** — Run a backtest on historical data
- **Results** — View past backtest runs and compare performance
- **Sweep** — Run a grid of parameter combinations and visualize the best performers
- **Forward Testing** — Paper-trade strategies against live daily data
"""
)
