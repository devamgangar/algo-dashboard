"""Forward Testing tab — start, monitor, and tick paper-trading runs."""
from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.analytics.benchmark import attach_benchmark  # noqa: E402
from core.analytics.plots import drawdown_chart, equity_curve_chart  # noqa: E402
from core.strategies import list_strategies  # noqa: E402
from core.ui import (  # noqa: E402
    inject_base_style,
    page_header,
    render_benchmark_panel,
    select_strategy_or_preset,
)
from db import repository as repo  # noqa: E402
from services.forward_service import (  # noqa: E402
    start_forward_run,
    stop_forward_run,
    tick_all_active,
    tick_forward_run,
)


st.set_page_config(page_title="Forward Testing", layout="wide")
st.session_state["__current_page"] = "forward_testing"
inject_base_style()
page_header(
    "Forward Testing",
    "Paper-trade strategies against unfolding daily data. Each forward run is a virtual portfolio that ticks once per day using yfinance closes.",
)


# ─── Strategy + config (start new run) ──────────────────────────────────────
with st.expander("Start a new forward run", expanded=False):
    strategies = list_strategies()
    presets = repo.list_presets()

    s_col_1, s_col_2 = st.columns(2)
    with s_col_1:
        strategy_cls, initial_params, source_label = select_strategy_or_preset(
            strategies, presets, key="fwd_strategy_select",
        )
        strategy_name = strategy_cls.name
    with s_col_2:
        st.caption(f"{source_label}. {strategy_cls.description or ''}")

    d_col, c_col = st.columns(2)
    with d_col:
        st.subheader("Data")
        symbol = st.text_input("Symbol", value="RELIANCE", key="fwd_symbol")
        exchange = st.selectbox("Exchange", options=["NSE", "BSE"], index=0, key="fwd_exchange")
        start_date = st.date_input(
            "Track from", value=date.today(), key="fwd_start_date",
            help="The forward equity curve starts at initial capital on this date.",
        )
        interval = st.selectbox("Interval", options=["1d"], index=0, key="fwd_interval",
                                help="Only daily is supported for forward testing in this version.")
    with c_col:
        st.subheader("Execution")
        initial_capital = st.number_input(
            "Initial capital (₹)", value=100_000.0, step=10_000.0, min_value=1_000.0,
            key="fwd_capital",
        )
        commission_bps = st.number_input("Commission (bps)", value=3.0, step=0.5, min_value=0.0, key="fwd_comm")
        slippage_bps   = st.number_input("Slippage (bps)",   value=5.0, step=0.5, min_value=0.0, key="fwd_slip")
        risk_free_rate_pct = st.number_input(
            "Risk-free rate (% per year)", value=6.5, step=0.25, key="fwd_rfr",
        )

    st.markdown("**Strategy parameters** (pre-filled from selection; locked once the forward run is created)")
    p_cols = st.columns(max(1, len(strategy_cls.default_params)))
    fwd_params: dict = {}
    for i, (pkey, pdefault) in enumerate(strategy_cls.default_params.items()):
        starting = initial_params.get(pkey, pdefault)
        with p_cols[i % len(p_cols)]:
            if isinstance(pdefault, bool):
                fwd_params[pkey] = st.checkbox(pkey, value=bool(starting), key=f"fwd_p_{pkey}")
            elif isinstance(pdefault, int):
                fwd_params[pkey] = int(st.number_input(pkey, value=int(starting), step=1, key=f"fwd_p_{pkey}"))
            elif isinstance(pdefault, float):
                fwd_params[pkey] = float(st.number_input(pkey, value=float(starting), step=0.1, key=f"fwd_p_{pkey}"))
            else:
                fwd_params[pkey] = st.text_input(pkey, value=str(starting), key=f"fwd_p_{pkey}")

    if st.button("Start Forward Run", type="primary", key="fwd_start"):
        try:
            with st.spinner("Creating forward run and running initial tick..."):
                run_id, tick = start_forward_run(
                    strategy_name=strategy_name,
                    symbol=symbol.strip().upper(),
                    exchange=exchange,
                    interval=interval,
                    params=fwd_params,
                    initial_capital=float(initial_capital),
                    commission_bps=float(commission_bps),
                    slippage_bps=float(slippage_bps),
                    risk_free_rate=float(risk_free_rate_pct) / 100.0,
                    start_date=start_date,
                )
            if tick.status == "updated":
                st.success(f"Started forward run #{run_id}. {tick.bars_processed} bars processed.")
            else:
                st.warning(f"Started forward run #{run_id}, but initial tick: {tick.status} ({tick.error_msg or 'no detail'}).")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to start: {exc}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc())


# ─── Tick controls ──────────────────────────────────────────────────────────
tick_col_l, tick_col_r = st.columns([3, 1])
with tick_col_r:
    if st.button("Tick all active runs", help="Run a tick on every active forward run now."):
        with st.spinner("Ticking all active runs..."):
            results = tick_all_active()
        if not results:
            st.info("No active forward runs to tick.")
        else:
            for r in results:
                if r.status == "updated":
                    st.success(f"#{r.forward_run_id}: updated ({r.bars_processed} bars)")
                elif r.status == "no_new_bars":
                    st.info(f"#{r.forward_run_id}: no new bars")
                else:
                    st.warning(f"#{r.forward_run_id}: {r.status} — {r.error_msg or 'no detail'}")


# ─── Active + stopped forward runs ──────────────────────────────────────────
all_runs = repo.list_forward_runs()
if not all_runs:
    st.info("No forward runs yet. Start one above.")
    st.stop()

st.divider()
st.subheader("Forward runs")

rows = []
for r in all_runs:
    days_running = (
        (r["last_processed_date"] - r["start_date"]).days
        if r["last_processed_date"] is not None else 0
    )
    rows.append({
        "ID":            r["id"],
        "Strategy":      r["strategy"],
        "Symbol":        r["symbol"],
        "Status":        r["status"],
        "Start date":    str(r["start_date"]),
        "Last processed": str(r["last_processed_date"]) if r["last_processed_date"] else "—",
        "Days running":  days_running,
        "Started at":    str(r["started_at"])[:19],
    })

event = st.dataframe(
    pd.DataFrame(rows),
    width="stretch",
    hide_index=True,
    selection_mode="single-row",
    on_select="rerun",
    key="fwd_runs_table",
)

selected_indices = event.selection.rows if event.selection else []

if not selected_indices:
    st.info("Select a row above to see details, tick, or stop the run.")
    st.stop()


# ─── Detail view ────────────────────────────────────────────────────────────
selected_run_id = all_runs[selected_indices[0]]["id"]
detail = repo.get_forward_run_detail(selected_run_id)
if detail is None:
    st.error(f"Forward run #{selected_run_id} not found.")
    st.stop()

st.divider()
st.subheader(f"Forward run #{selected_run_id}: {detail['strategy_name']} on {detail['symbol']}")

# Status + current position summary
eq = detail["equity_curve"]
trades = detail["trades"]

if eq.empty:
    st.info("No equity data yet — initial tick may not have processed any bars (start_date is today, no closed bar available).")
    cur_equity = detail["initial_capital"]
    cur_cash = detail["initial_capital"]
    cur_pos_value = 0.0
    pnl_pct = 0.0
else:
    cur_equity = float(eq["equity"].iloc[-1])
    cur_cash = float(eq["cash"].iloc[-1])
    cur_pos_value = float(eq["position_value"].iloc[-1])
    pnl_pct = (cur_equity / detail["initial_capital"] - 1.0) * 100.0

# Reconstruct current position from trades
buys = trades[trades["side"] == "BUY"] if not trades.empty else trades
sells = trades[trades["side"] == "SELL"] if not trades.empty else trades
net_qty = (int(buys["qty"].sum()) if not buys.empty else 0) - (int(sells["qty"].sum()) if not sells.empty else 0)
position_status = "LONG" if net_qty > 0 else "FLAT"

# Row 1 — current financial state
m = st.columns(4)
m[0].metric("Position",            position_status)
m[1].metric("Shares held",         f"{net_qty}")
m[2].metric("Cash (₹)",            f"₹{cur_cash:,.2f}")
m[3].metric(
    "Portfolio value (₹)",
    f"₹{cur_equity:,.2f}",
    delta=f"{pnl_pct:+.2f}%",
    help="Cash + current value of held shares. Delta is return vs initial capital.",
)

# Row 2 — run lifecycle / activity
m2 = st.columns(4)
m2[0].metric("Run status",      detail["status"])
m2[1].metric("Tracked since",   str(detail["start_date"]))
m2[2].metric("Last processed",  str(detail["last_processed_date"]) if detail["last_processed_date"] else "—")
m2[3].metric("Trades to date",  int(len(trades)))

# Action buttons
act_col_l, act_col_r, _ = st.columns([1, 1, 4])
with act_col_l:
    if st.button("Refresh Now", key="fwd_refresh", help="Tick this run immediately"):
        with st.spinner("Ticking..."):
            tick = tick_forward_run(selected_run_id)
        if tick.status == "updated":
            st.success(f"Updated. {tick.bars_processed} bars processed (latest: {tick.last_processed_date}).")
        elif tick.status == "no_new_bars":
            st.info("No new bars since last tick.")
        else:
            st.warning(f"{tick.status}: {tick.error_msg or 'no detail'}")
        st.rerun()
with act_col_r:
    if detail["status"] == "active":
        if st.button("Stop Run", key="fwd_stop", type="secondary"):
            stop_forward_run(selected_run_id)
            st.success(f"Stopped run #{selected_run_id}.")
            st.rerun()
    else:
        st.caption(f"Run is {detail['status']}.")

# Charts
if not eq.empty:
    # Benchmark overlay — fetched from the start_date of the forward run
    bench_series, bench_metrics = None, None
    try:
        eq_end_ts = pd.to_datetime(eq["timestamp"].iloc[-1]).date()
        bench_series, bench_metrics = attach_benchmark(
            equity_df=eq,
            initial_capital=detail["initial_capital"],
            start_date=detail["start_date"],
            end_date=eq_end_ts,
            risk_free_rate=detail["risk_free_rate"],
            interval=detail["interval"],
        )
    except Exception:
        pass

    st.plotly_chart(
        equity_curve_chart(
            eq, initial_capital=detail["initial_capital"],
            title=f"Forward equity since {detail['start_date']}",
            benchmark_series=bench_series,
        ),
        width="stretch",
    )
    if bench_metrics is not None:
        with st.container(border=True):
            render_benchmark_panel(bench_metrics)
    st.plotly_chart(drawdown_chart(eq), width="stretch")

# Trade log
with st.expander("Trade log", expanded=False):
    if trades.empty:
        st.info("No trades yet.")
    else:
        tdf = trades.copy()
        tdf["timestamp"] = pd.to_datetime(tdf["timestamp"]).dt.date
        st.dataframe(tdf, width="stretch", hide_index=True)

with st.expander("Run config"):
    st.json({
        "strategy":         detail["strategy_name"],
        "version":          detail["strategy_version"],
        "params":           detail["params"],
        "symbol":           detail["symbol"],
        "exchange":         detail["exchange"],
        "interval":         detail["interval"],
        "data_source":      detail["data_source"],
        "initial_capital":  detail["initial_capital"],
        "commission_bps":   detail["commission_bps"],
        "slippage_bps":     detail["slippage_bps"],
        "risk_free_rate":   detail["risk_free_rate"],
    })
