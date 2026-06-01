"""Backtest tab — configure, run, and save a single-symbol backtest.

Pipeline (all in the service layer):
    UI inputs -> services.run_and_save -> data + engine + DB save -> result
"""
from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.analytics.metrics import metrics_to_table  # noqa: E402
from core.analytics.plots import drawdown_chart, equity_curve_chart  # noqa: E402
from core.strategies import list_strategies  # noqa: E402
from services.backtest_service import run_and_save  # noqa: E402


st.set_page_config(page_title="Backtest", layout="wide")

# Clear stale results if the user just landed here from a different page.
# (Within-page interactions like expanders / dropdowns leave last_run alone,
# so the result panel stays visible until the user navigates away or re-runs.)
_prev_page = st.session_state.get("__current_page")
st.session_state["__current_page"] = "backtest"
if _prev_page != "backtest":
    st.session_state.pop("last_run", None)

st.title("Backtest")
st.caption("Configure a backtest, run it, and save the results.")


# ─── Strategy selection (OUTSIDE the form so changing it re-renders params) ──
strategies = list_strategies()
if not strategies:
    st.error("No strategies registered. Add one under core/strategies/ and update __init__.py.")
    st.stop()

strategy_name_to_display = {c.name: f"{c.display_name} (v{c.version})" for c in strategies}
strategy_lookup = {c.name: c for c in strategies}

strategy_name = st.selectbox(
    "Strategy",
    options=list(strategy_name_to_display.keys()),
    format_func=lambda n: strategy_name_to_display[n],
    key="strategy_select",
)
strategy_cls = strategy_lookup[strategy_name]
st.caption(strategy_cls.description or "")


# ─── The rest of the inputs ──────────────────────────────────────────────────
col_data, col_exec = st.columns(2)

with col_data:
    st.subheader("Data")
    symbol = st.text_input("Symbol", value="RELIANCE", help="No .NS suffix; we add it.")
    exchange = st.selectbox("Exchange", options=["NSE", "BSE"], index=0)
    today = date.today()
    start_date = st.date_input("Start date", value=today - timedelta(days=2 * 365))
    end_date = st.date_input("End date", value=today)
    interval = st.selectbox(
        "Interval", options=["1d", "1h", "30m", "15m", "5m"], index=0,
        help="yfinance limits: 1m only last 7 days, 5m/15m/30m last 60 days.",
    )

with col_exec:
    st.subheader("Execution config")
    initial_capital = st.number_input(
        "Initial capital (₹)", value=100_000.0, step=10_000.0, min_value=1_000.0,
    )
    commission_bps = st.number_input(
        "Commission (bps)", value=3.0, step=0.5, min_value=0.0,
        help="3 bps = 0.03% per trade. Typical Indian discount broker.",
    )
    slippage_bps = st.number_input(
        "Slippage (bps)", value=5.0, step=0.5, min_value=0.0,
        help="Adverse price movement on fill. 5 bps is a reasonable default.",
    )
    risk_free_rate_pct = st.number_input(
        "Risk-free rate (% per year)", value=6.5, step=0.25, min_value=0.0, max_value=20.0,
        help="Indian liquid-fund yield default. Used in Sharpe/Sortino and excess-return metrics.",
    )

st.divider()
st.subheader("Strategy parameters")
param_cols = st.columns(max(1, len(strategy_cls.default_params)))
params: dict = {}
for i, (key, default) in enumerate(strategy_cls.default_params.items()):
    with param_cols[i % len(param_cols)]:
        if isinstance(default, bool):
            params[key] = st.checkbox(key, value=default)
        elif isinstance(default, int):
            params[key] = int(st.number_input(key, value=default, step=1))
        elif isinstance(default, float):
            params[key] = float(st.number_input(key, value=default, step=0.1))
        else:
            params[key] = st.text_input(key, value=str(default))

st.divider()


# ─── Run button ──────────────────────────────────────────────────────────────
force_rerun = st.checkbox(
    "Force re-run (ignore cached result)",
    value=False,
    help=(
        "By default, if you've already run this exact backtest (same symbol, "
        "dates, params, costs, RFR), we reuse the saved result. Tick to "
        "recompute — useful after yfinance updates the data."
    ),
)
run_clicked = st.button("Run Backtest", type="primary", width="stretch")


def _show_results(run_id: int, result, from_cache: bool) -> None:
    s = result.summary_metrics
    e = result.extended_metrics

    if from_cache:
        st.info(
            f"Reused cached run #{run_id} — identical inputs already executed. "
            "Tick 'Force re-run' above and click again to recompute."
        )
    else:
        st.success(f"Saved as run #{run_id}.")

    m = st.columns(4)
    m[0].metric("Total return", f"{s['total_return']*100:+.2f}%")
    m[1].metric("CAGR",          f"{s['cagr']*100:+.2f}%")
    m[2].metric("Sharpe",        f"{s['sharpe']:+.3f}")
    m[3].metric("Max drawdown",  f"{s['max_drawdown']*100:.2f}%")

    m2 = st.columns(4)
    m2[0].metric("# Trades",          f"{s['num_trades']}")
    m2[1].metric("Win rate",          f"{s['win_rate']*100:.1f}%")
    m2[2].metric("Exposure",          f"{e.get('exposure_pct', 0):.1f}%")
    m2[3].metric("Excess vs RFR",     f"{e.get('excess_return_vs_rfr', 0)*100:+.2f}%")

    st.plotly_chart(
        equity_curve_chart(result.equity_curve, initial_capital=result.initial_capital),
        width="stretch",
    )
    st.plotly_chart(drawdown_chart(result.equity_curve), width="stretch")

    with st.expander("Trade log", expanded=False):
        if result.trades.empty:
            st.info("Strategy generated no trades in this period.")
        else:
            df = result.trades.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
            st.dataframe(df, width="stretch", hide_index=True)

    with st.expander("Extended metrics", expanded=False):
        if not result.extended_metrics:
            st.info("No extended metrics for this run.")
        else:
            st.dataframe(
                metrics_to_table(result.extended_metrics),
                width="stretch",
                hide_index=True,
            )
            if st.checkbox("Show raw JSON", value=False, key="extended_metrics_raw"):
                st.json(result.extended_metrics)


if run_clicked:
    if start_date >= end_date:
        st.error("End date must be after start date.")
        st.stop()

    try:
        with st.spinner(f"Running {strategy_cls.display_name} on {symbol}..."):
            run_id, result, from_cache = run_and_save(
                symbol=symbol.strip().upper(),
                strategy_name=strategy_name,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                exchange=exchange,
                data_source="yfinance",
                params=params,
                initial_capital=float(initial_capital),
                commission_bps=float(commission_bps),
                slippage_bps=float(slippage_bps),
                risk_free_rate=float(risk_free_rate_pct) / 100.0,
                force_rerun=force_rerun,
            )
        st.session_state["last_run"] = (run_id, result, from_cache)
    except Exception as exc:
        st.error(f"Backtest failed: {exc}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())

if "last_run" in st.session_state:
    st.divider()
    st.subheader("Results")
    last_run_id, last_result, last_from_cache = st.session_state["last_run"]
    _show_results(last_run_id, last_result, last_from_cache)
