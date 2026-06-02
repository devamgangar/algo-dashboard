"""Parameter Sweep tab — run a grid of backtests and visualize results."""
from __future__ import annotations

import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.analytics.plots import metric_heatmap  # noqa: E402
from core.strategies import list_strategies  # noqa: E402
from core.ui import inject_base_style, page_header  # noqa: E402
from services.sweep_service import run_sweep_and_collect  # noqa: E402


st.set_page_config(page_title="Parameter Sweep", layout="wide")
st.session_state["__current_page"] = "sweep"
inject_base_style()
page_header(
    "Parameter Sweep",
    "Run a grid of parameter combinations and see which perform best. Heatmap when exactly 2 parameters are swept; ranked table otherwise.",
)


# ─── Strategy ────────────────────────────────────────────────────────────────
strategies = list_strategies()
if not strategies:
    st.error("No strategies registered.")
    st.stop()

strategy_lookup = {c.name: c for c in strategies}
strategy_name = st.selectbox(
    "Strategy",
    options=[c.name for c in strategies],
    format_func=lambda n: f"{strategy_lookup[n].display_name} (v{strategy_lookup[n].version})",
)
strategy_cls = strategy_lookup[strategy_name]
st.caption(strategy_cls.description or "")

# Only numeric params are sweepable (int or float, excluding bool).
numeric_params = {
    k: v for k, v in strategy_cls.default_params.items()
    if isinstance(v, (int, float)) and not isinstance(v, bool)
}
if not numeric_params:
    st.warning(f"{strategy_cls.display_name} has no numeric parameters to sweep.")
    st.stop()


# ─── Data + execution config ────────────────────────────────────────────────
col_data, col_exec = st.columns(2)

with col_data:
    st.subheader("Data")
    symbol = st.text_input("Symbol", value="RELIANCE", help="No .NS suffix; we add it.")
    exchange = st.selectbox("Exchange", options=["NSE", "BSE"], index=0)
    today = date.today()
    start_date = st.date_input("Start date", value=today - timedelta(days=2 * 365))
    end_date = st.date_input("End date", value=today)
    interval = st.selectbox("Interval", options=["1d", "1h", "30m", "15m", "5m"], index=0)

with col_exec:
    st.subheader("Execution config (same for all combos)")
    initial_capital = st.number_input(
        "Initial capital (₹)", value=100_000.0, step=10_000.0, min_value=1_000.0,
    )
    commission_bps = st.number_input("Commission (bps)", value=3.0, step=0.5, min_value=0.0)
    slippage_bps   = st.number_input("Slippage (bps)",   value=5.0, step=0.5, min_value=0.0)
    risk_free_rate_pct = st.number_input(
        "Risk-free rate (% per year)", value=6.5, step=0.25, min_value=0.0, max_value=20.0,
    )


# ─── Sweep ranges per parameter ─────────────────────────────────────────────
st.divider()
st.subheader("Sweep configuration")
st.caption("Toggle each parameter to sweep; unswept params stay at their default.")

param_grid: dict[str, list] = {}

for pname, default in numeric_params.items():
    is_int = isinstance(default, int)
    with st.container():
        cols = st.columns([1, 1, 1, 1, 1])
        cols[0].markdown(f"**{pname}** _(default: {default})_")
        enable = cols[1].checkbox("sweep", value=False, key=f"sw_{pname}")
        if enable:
            if is_int:
                lo = int(cols[2].number_input(
                    f"min {pname}", value=max(2, default // 2), step=1, key=f"lo_{pname}",
                ))
                hi = int(cols[3].number_input(
                    f"max {pname}", value=default * 2, step=1, key=f"hi_{pname}",
                ))
                step = int(cols[4].number_input(
                    f"step {pname}", value=max(1, (hi - lo) // 5 or 1),
                    min_value=1, step=1, key=f"st_{pname}",
                ))
                if hi < lo:
                    hi = lo
                values = list(range(lo, hi + 1, step))
            else:
                lo = float(cols[2].number_input(
                    f"min {pname}", value=float(default) * 0.5, step=0.1, key=f"lo_{pname}",
                ))
                hi = float(cols[3].number_input(
                    f"max {pname}", value=float(default) * 2.0, step=0.1, key=f"hi_{pname}",
                ))
                step = float(cols[4].number_input(
                    f"step {pname}", value=0.5, step=0.1, min_value=0.01, key=f"st_{pname}",
                ))
                if hi < lo:
                    hi = lo
                values = []
                v = lo
                while v <= hi + 1e-9:
                    values.append(round(v, 6))
                    v += step
            param_grid[pname] = values if values else [default]
        else:
            param_grid[pname] = [default]


# ─── Combo count + metric selector ──────────────────────────────────────────
total_combos = 1
for vals in param_grid.values():
    total_combos *= len(vals)

swept_params = [k for k, vs in param_grid.items() if len(vs) > 1]
swept_dim_count = len(swept_params)

st.info(
    f"**{total_combos}** combinations will run "
    f"({swept_dim_count} parameter{'' if swept_dim_count == 1 else 's'} swept). "
    f"Estimated time: ~{max(1, total_combos // 20)}s."
)
if total_combos > 500:
    st.warning("Large sweep (>500 combos). Expect this to take a while.")

metric_options = {
    "sharpe":       "Sharpe (higher is better)",
    "total_return": "Total return (higher is better)",
    "cagr":         "CAGR (higher is better)",
    "sortino":      "Sortino (higher is better)",
    "max_drawdown": "Max drawdown (less-negative is better)",
    "win_rate":     "Win rate (higher is better)",
}
selected_metric = st.selectbox(
    "Metric to visualize",
    options=list(metric_options.keys()),
    format_func=lambda k: metric_options[k],
)


# ─── Run ────────────────────────────────────────────────────────────────────
run_clicked = st.button("Run Sweep", type="primary", width="stretch")

if run_clicked:
    if start_date >= end_date:
        st.error("End date must be after start date.")
        st.stop()
    if swept_dim_count == 0:
        st.error("Enable at least one parameter to sweep (toggle the 'sweep' checkbox).")
        st.stop()

    progress = st.progress(0.0, text="Starting sweep…")

    def _update_progress(current: int, total: int) -> None:
        progress.progress(current / total, text=f"Running backtest {current}/{total}…")

    try:
        sweep = run_sweep_and_collect(
            strategy_name=strategy_name,
            symbol=symbol.strip().upper(),
            start_date=start_date,
            end_date=end_date,
            param_grid=param_grid,
            interval=interval,
            exchange=exchange,
            initial_capital=float(initial_capital),
            commission_bps=float(commission_bps),
            slippage_bps=float(slippage_bps),
            risk_free_rate=float(risk_free_rate_pct) / 100.0,
            progress_callback=_update_progress,
        )
        progress.empty()
        st.session_state["last_sweep"] = sweep
        st.session_state["last_sweep_metric"] = selected_metric
    except Exception as exc:
        progress.empty()
        st.error(f"Sweep failed: {exc}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())


# ─── Results ────────────────────────────────────────────────────────────────
if "last_sweep" in st.session_state:
    sr = st.session_state["last_sweep"]
    metric_for_view = st.session_state.get("last_sweep_metric", "sharpe")
    combos = sr.combos
    swept = [k for k, vs in sr.param_grid.items() if len(vs) > 1]

    n_valid = int(combos[metric_for_view].notna().sum()) if metric_for_view in combos else 0
    n_total = len(combos)
    n_errors = int(combos["error"].notna().sum())

    st.divider()
    st.subheader(f"Sweep results: {sr.strategy_name} on {sr.symbol}")
    st.caption(
        f"{n_valid}/{n_total} combos completed successfully"
        + (f" ({n_errors} errors)" if n_errors else "")
        + f". Visualizing **{metric_options.get(metric_for_view, metric_for_view)}**."
    )

    # Fraction metrics need ×100 to display as percentages (the engine returns
    # them as raw fractions, same as on the Backtest tab).
    _FRACTION_METRICS = {"total_return", "cagr", "max_drawdown", "win_rate"}
    _RATIO_METRICS    = {"sharpe", "sortino"}

    def _scale_for_display(df: pd.DataFrame) -> pd.DataFrame:
        """Convert fraction metric columns to percentages for display."""
        out = df.copy()
        for c in _FRACTION_METRICS:
            if c in out.columns:
                out[c] = out[c] * 100.0
        return out

    def _column_config(df: pd.DataFrame) -> dict:
        """Streamlit column_config for nicer formatting (after _scale_for_display)."""
        cfg: dict = {}
        for c in df.columns:
            if c in _FRACTION_METRICS:
                cfg[c] = st.column_config.NumberColumn(c, format="%+.2f%%")
            elif c in _RATIO_METRICS:
                cfg[c] = st.column_config.NumberColumn(c, format="%+.3f")
            elif c == "num_trades":
                cfg[c] = st.column_config.NumberColumn(c, format="%d")
        return cfg

    if len(swept) == 2:
        x_p, y_p = swept[0], swept[1]
        heatmap_data = combos.dropna(subset=[metric_for_view]).copy()
        # Scale the heatmap value column to percent if it's a fraction metric.
        if metric_for_view in _FRACTION_METRICS:
            heatmap_data[metric_for_view] = heatmap_data[metric_for_view] * 100.0
        st.plotly_chart(
            metric_heatmap(heatmap_data, x_param=x_p, y_param=y_p, metric=metric_for_view),
            width="stretch",
        )
    elif len(swept) == 1:
        only = swept[0]
        line_df = combos.dropna(subset=[metric_for_view]).set_index(only)[[metric_for_view]]
        if metric_for_view in _FRACTION_METRICS:
            line_df = line_df * 100.0
        st.line_chart(line_df)
    else:
        st.info("Heatmap requires exactly 2 swept parameters; full table is shown below.")

    # Top-N table
    st.subheader(f"Top 10 combos by {metric_for_view}")
    if combos[metric_for_view].notna().any():
        top_n = combos.dropna(subset=[metric_for_view]).nlargest(10, metric_for_view)
        param_cols = list(sr.param_grid.keys())
        metric_cols = [c for c in top_n.columns if c not in param_cols and c != "error"]
        scaled = _scale_for_display(top_n[param_cols + metric_cols])
        st.dataframe(scaled, width="stretch", hide_index=True,
                     column_config=_column_config(scaled))
    else:
        st.warning("No successful combos for this metric.")

    with st.expander("All combinations (raw)"):
        scaled_all = _scale_for_display(combos)
        st.dataframe(scaled_all, width="stretch", hide_index=True,
                     column_config=_column_config(scaled_all))

    # CSV export — raw fractions, not display-scaled (for downstream analysis)
    st.divider()
    fname = f"sweep_{sr.strategy_name}_{sr.symbol}.csv"
    st.download_button(
        label=f"Download all combos as CSV ({len(combos)} rows)",
        data=combos.to_csv(index=False).encode("utf-8"),
        file_name=fname,
        mime="text/csv",
        help="Raw fraction values (×100 to get percentages). Includes the 'error' column.",
    )
