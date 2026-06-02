"""Algo Trading Dashboard - main entry point + landing page."""
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Algo Dashboard",
    layout="wide",
)
st.session_state["__current_page"] = "home"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.ui import NAVY, inject_base_style, page_header  # noqa: E402
inject_base_style()

# ─── Hero ────────────────────────────────────────────────────────────────────
page_header(
    "Algo Trading Dashboard",
    "Backtest, sweep, and forward-test trading strategies on Indian equities.",
)

st.divider()


# ─── Feature list ────────────────────────────────────────────────────────────
def _feature(title: str, description: str) -> str:
    return f"""
    <div style="padding: 1rem 0; border-bottom: 1px solid #e2e8f0;">
        <div style="font-weight: 600; color: {NAVY}; font-size: 1.2rem;
                    margin-bottom: 0.3rem;">
            {title}
        </div>
        <div style="color: #475569; font-size: 1.05rem; line-height: 1.55;">
            {description}
        </div>
    </div>
    """


st.markdown(
    "<h3 style='color: #0f172a; font-weight: 600; margin-bottom: 0.5rem;'>"
    "What's here</h3>",
    unsafe_allow_html=True,
)

st.markdown(_feature(
    "Strategies",
    "Four built-in strategies — SMA Crossover (trend), RSI Mean Reversion "
    "(counter-trend), Bollinger Breakout (volatility), MACD Crossover (momentum). "
    "Adding a new one is a single file."
), unsafe_allow_html=True)

st.markdown(_feature(
    "Backtest + Results",
    "Single-symbol backtests with realistic costs (commission, slippage, risk-free rate). "
    "RFR-aware Sharpe / Sortino. Trade log, equity curve, drawdown, and "
    "price-with-signals overlay on the Results tab."
), unsafe_allow_html=True)

st.markdown(_feature(
    "Sweep",
    "Parameter sweeps rendered as a heatmap; top-N ranking; CSV export."
), unsafe_allow_html=True)

st.markdown(_feature(
    "Portfolio + Portfolio Results",
    "Deploy one strategy across a basket (NIFTY 50). Shared cash pool; each entry "
    "sized as a fixed % of initial capital; cash-constrained allocation. "
    "Past portfolio runs browse / detail / comparison on a dedicated tab."
), unsafe_allow_html=True)

st.markdown(_feature(
    "Forward Testing",
    "Paper-trade strategies against unfolding daily yfinance data. Virtual portfolio "
    "with equity curve, refreshable manually or via scheduled daily ticks."
), unsafe_allow_html=True)


# ─── Quick start ─────────────────────────────────────────────────────────────
st.write("")
st.markdown(
    "<h3 style='color: #0f172a; font-weight: 600; margin-top: 1.5rem;'>"
    "Quick start</h3>",
    unsafe_allow_html=True,
)

st.markdown(
    """
1. Click **Backtest** in the sidebar.
2. Defaults are loaded — SMA Crossover on RELIANCE, last 2 years, ₹1,00,000 capital.
3. Hit **Run Backtest**. The run saves automatically.
4. Open **Results** to see it, drill in, and compare with future runs.
5. **Sweep** explores parameter ranges. **Forward Testing** tracks strategies on live data.
"""
)


# ─── Footer ──────────────────────────────────────────────────────────────────
st.divider()
fcol1, fcol2 = st.columns([3, 2])
with fcol1:
    st.caption(
        "Python · Streamlit · vectorbt · SQLite · Plotly · yfinance · Parquet. "
        "Single-user, file-based, no external services."
    )
with fcol2:
    st.caption(
        "Source: [github.com/devamgangar/algo-dashboard]"
        "(https://github.com/devamgangar/algo-dashboard)  ·  "
        "[Setup guide](https://github.com/devamgangar/algo-dashboard/blob/main/docs/setup.md)"
    )
