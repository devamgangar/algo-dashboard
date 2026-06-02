"""Portfolio tab — run one strategy across a basket of symbols with shared cash."""
from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.analytics.benchmark import attach_benchmark  # noqa: E402
from core.analytics.metrics import metrics_to_table  # noqa: E402
from core.analytics.plots import drawdown_chart, equity_curve_chart  # noqa: E402
from core.strategies import list_strategies  # noqa: E402
from core.ui import (  # noqa: E402
    inject_base_style,
    page_header,
    render_benchmark_panel,
    select_strategy_or_preset,
)
from core.universe import UNIVERSES, get_universe  # noqa: E402
from db import repository as repo  # noqa: E402
from services.portfolio_service import run_portfolio_and_save  # noqa: E402


st.set_page_config(page_title="Portfolio", layout="wide")
st.session_state["__current_page"] = "portfolio"
inject_base_style()
page_header(
    "Portfolio",
    "Deploy one strategy across a basket of stocks with shared cash. "
    "Each entry signal opens a new position sized as a % of current portfolio equity.",
)


# ─── Strategy / Preset selection ─────────────────────────────────────────────
strategies = list_strategies()
if not strategies:
    st.error("No strategies registered.")
    st.stop()

presets = repo.list_presets()
strategy_cls, initial_params, source_label = select_strategy_or_preset(
    strategies, presets, key="pf_strategy_select",
)
strategy_name = strategy_cls.name
st.caption(f"{source_label}. {strategy_cls.description or ''}")


# ─── Universe + execution config ─────────────────────────────────────────────
col_uni, col_exec = st.columns(2)

with col_uni:
    st.subheader("Universe")
    universe_label = st.selectbox(
        "Symbol universe",
        options=list(UNIVERSES.keys()),
        index=0,
        help="Pick the base universe; you can deselect specific symbols below.",
    )
    universe_symbols = get_universe(universe_label)

    # Pre-initialize the symbol selection so the bulk-action buttons can mutate
    # session_state BEFORE the multiselect widget claims the key. (Streamlit
    # disallows setting `st.session_state[key]` after a widget with that key
    # has been instantiated in the current script run.)
    if "pf_symbols" not in st.session_state:
        st.session_state["pf_symbols"] = list(universe_symbols)

    # Bulk-action buttons render FIRST so their handlers can update state
    # before the multiselect reads it.
    bcol1, bcol2, _bcap_slot = st.columns([1, 1, 3])
    with bcol1:
        if st.button("Select all", key="pf_sym_all"):
            st.session_state["pf_symbols"] = list(universe_symbols)
            st.rerun()
    with bcol2:
        if st.button("Clear all", key="pf_sym_clr"):
            st.session_state["pf_symbols"] = []
            st.rerun()

    # Multiselect — reads from session_state via key (no `default` because
    # state is pre-initialized above; passing both would conflict).
    selected_symbols = st.multiselect(
        f"Symbols to include ({len(universe_symbols)} available)",
        options=universe_symbols,
        key="pf_symbols",
        help="Click the × on any symbol to exclude it. Use the buttons above for bulk select/clear.",
    )
    st.caption(f"**{len(selected_symbols)} of {len(universe_symbols)} selected**")

    exchange = st.selectbox("Exchange", options=["NSE", "BSE"], index=0, key="pf_exchange")
    today = date.today()
    start_date = st.date_input("Start date", value=today - timedelta(days=2 * 365), key="pf_start")
    end_date = st.date_input("End date", value=today, key="pf_end")
    interval = st.selectbox(
        "Interval", options=["1d"], index=0, key="pf_interval",
        help="Daily only for v1. Intraday portfolio across 50 symbols requires more data infrastructure.",
    )

with col_exec:
    st.subheader("Execution config")
    initial_capital = st.number_input(
        "Initial capital (₹)",
        value=1_000_000.0, step=100_000.0, min_value=10_000.0,
        help="Recommended ≥ ₹10L since we may hold multiple positions simultaneously.",
        key="pf_capital",
    )
    position_size_pct_input = st.number_input(
        "Position size (% of initial capital per trade)",
        value=10.0, step=1.0, min_value=1.0, max_value=50.0,
        help=(
            "Each new BUY allocates this % of the ORIGINAL capital. "
            "Fixed rupee amount per trade (doesn't compound within a backtest). "
            "Max simultaneous positions ≈ 100 / this value (10% → ~10 slots)."
        ),
        key="pf_size_pct",
    )
    commission_bps = st.number_input("Commission (bps)", value=3.0, step=0.5, min_value=0.0, key="pf_comm")
    slippage_bps   = st.number_input("Slippage (bps)",   value=5.0, step=0.5, min_value=0.0, key="pf_slip")
    risk_free_rate_pct = st.number_input(
        "Risk-free rate (% per year)", value=6.5, step=0.25, key="pf_rfr",
    )


# ─── Strategy parameters ─────────────────────────────────────────────────────
st.divider()
st.subheader("Strategy parameters")
st.caption("Pre-filled from the selected strategy/preset. Same params apply to all symbols in the universe.")
p_cols = st.columns(max(1, len(strategy_cls.default_params)))
pf_params: dict = {}
for i, (pkey, pdefault) in enumerate(strategy_cls.default_params.items()):
    starting = initial_params.get(pkey, pdefault)
    with p_cols[i % len(p_cols)]:
        if isinstance(pdefault, bool):
            pf_params[pkey] = st.checkbox(pkey, value=bool(starting), key=f"pf_p_{pkey}")
        elif isinstance(pdefault, int):
            pf_params[pkey] = int(st.number_input(pkey, value=int(starting), step=1, key=f"pf_p_{pkey}"))
        elif isinstance(pdefault, float):
            pf_params[pkey] = float(st.number_input(pkey, value=float(starting), step=0.1, key=f"pf_p_{pkey}"))
        else:
            pf_params[pkey] = st.text_input(pkey, value=str(starting), key=f"pf_p_{pkey}")


# ─── Run button ──────────────────────────────────────────────────────────────
st.divider()
run_clicked = st.button("Run Portfolio Backtest", type="primary", width="stretch")


def _show_portfolio_results(run_id: int, result) -> None:
    s = result.summary_metrics
    e = result.extended_metrics

    st.success(f"Saved as portfolio run #{run_id}.")
    if result.skipped_symbols:
        st.warning(
            f"{len(result.skipped_symbols)} symbol(s) skipped (data fetch failed): "
            f"{', '.join(result.skipped_symbols[:8])}"
            + ("..." if len(result.skipped_symbols) > 8 else "")
        )

    m = st.columns(4)
    m[0].metric("Total return", f"{(s['total_return'] or 0)*100:+.2f}%")
    m[1].metric("CAGR",          f"{(s['cagr'] or 0)*100:+.2f}%")
    m[2].metric(
        "Sharpe",
        f"{s['sharpe']:+.3f}" if s['sharpe'] is not None else "—",
    )
    m[3].metric("Max drawdown",  f"{(s['max_drawdown'] or 0)*100:.2f}%")

    m2 = st.columns(4)
    m2[0].metric("Total trades", f"{s['num_trades']}")
    m2[1].metric(
        "Win rate",
        f"{s['win_rate']*100:.1f}%" if s['win_rate'] is not None else "—",
    )
    m2[2].metric("Symbols traded", f"{result.num_symbols_traded} / {len(result.symbols)}")
    m2[3].metric("Position size", f"{result.position_size_pct*100:.0f}%")

    # Benchmark overlay (NIFTY 50)
    bench_series, bench_metrics, bench_error = None, None, None
    try:
        bench_series, bench_metrics = attach_benchmark(
            equity_df=result.equity_curve,
            initial_capital=result.initial_capital,
            start_date=result.start_date,
            end_date=result.end_date,
            risk_free_rate=result.risk_free_rate,
            interval=result.interval,
        )
        if bench_series is None:
            bench_error = "Benchmark data unavailable for this period."
    except Exception as exc:
        bench_error = f"Benchmark fetch failed: {exc}"

    st.plotly_chart(
        equity_curve_chart(
            result.equity_curve, initial_capital=result.initial_capital,
            title="Portfolio equity curve",
            benchmark_series=bench_series,
        ),
        width="stretch",
    )
    if bench_metrics is not None:
        with st.container(border=True):
            render_benchmark_panel(bench_metrics)
    elif bench_error is not None:
        st.info(bench_error)
    st.plotly_chart(drawdown_chart(result.equity_curve), width="stretch")

    # Per-symbol contribution
    if not result.trades.empty:
        with st.expander("Per-symbol contribution", expanded=False):
            sells = result.trades[result.trades["side"] == "SELL"]
            if sells.empty:
                st.info("No closed trades yet to attribute PnL by symbol.")
            else:
                by_sym = sells.groupby("symbol").agg(
                    trades=("pnl", "count"),
                    total_pnl=("pnl", "sum"),
                    avg_pnl=("pnl", "mean"),
                    win_rate=("pnl", lambda x: (x > 0).mean() * 100),
                ).sort_values("total_pnl", ascending=False).reset_index()
                by_sym["total_pnl"] = by_sym["total_pnl"].round(2)
                by_sym["avg_pnl"] = by_sym["avg_pnl"].round(2)
                by_sym["win_rate"] = by_sym["win_rate"].round(1).astype(str) + "%"
                st.dataframe(by_sym, width="stretch", hide_index=True)

    with st.expander("Trade log", expanded=False):
        if result.trades.empty:
            st.info("No trades.")
        else:
            tdf = result.trades.copy()
            tdf["timestamp"] = pd.to_datetime(tdf["timestamp"]).dt.date
            st.dataframe(tdf, width="stretch", hide_index=True)

    with st.expander("Extended metrics", expanded=False):
        if not e:
            st.info("No extended metrics.")
        else:
            st.dataframe(metrics_to_table(e), width="stretch", hide_index=True)


if run_clicked:
    if start_date >= end_date:
        st.error("End date must be after start date.")
        st.stop()
    if not selected_symbols:
        st.error("Select at least one symbol to include.")
        st.stop()

    # Build a descriptive universe label that reflects subsetting
    universe_label_for_run = (
        universe_label
        if len(selected_symbols) == len(universe_symbols)
        else f"{universe_label} ({len(selected_symbols)} of {len(universe_symbols)})"
    )

    progress = st.progress(0.0, text="Starting portfolio backtest...")

    def _update(current: int, total: int, symbol: str) -> None:
        progress.progress(current / total, text=f"Fetching {current}/{total}: {symbol}")

    try:
        with st.spinner(f"Running {strategy_cls.display_name} on {len(selected_symbols)} symbols..."):
            run_id, result = run_portfolio_and_save(
                strategy_name=strategy_name,
                universe_label=universe_label_for_run,
                symbols=selected_symbols,
                exchange=exchange,
                interval=interval,
                data_source="yfinance",
                params=pf_params,
                initial_capital=float(initial_capital),
                position_size_pct=float(position_size_pct_input) / 100.0,
                commission_bps=float(commission_bps),
                slippage_bps=float(slippage_bps),
                risk_free_rate=float(risk_free_rate_pct) / 100.0,
                start_date=start_date,
                end_date=end_date,
                progress_callback=_update,
            )
        progress.empty()
        st.session_state["last_portfolio_run"] = (run_id, result)
    except Exception as exc:
        progress.empty()
        st.error(f"Portfolio backtest failed: {exc}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())


# ─── Past portfolio runs ─────────────────────────────────────────────────────
if "last_portfolio_run" in st.session_state:
    st.divider()
    st.subheader("Results")
    last_id, last_result = st.session_state["last_portfolio_run"]
    _show_portfolio_results(last_id, last_result)


st.divider()
st.caption(
    "Past portfolio runs live in the **Portfolio Results** tab — filter, drill in, "
    "and compare multiple runs side-by-side there."
)
