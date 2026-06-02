"""Portfolio Results tab — browse past portfolio backtests, view detail, compare.

Mirrors the single-symbol Results tab but reads from portfolio_runs /
portfolio_trades / portfolio_equity_curve.
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.analytics.benchmark import attach_benchmark  # noqa: E402
from core.analytics.metrics import metrics_to_table  # noqa: E402
from core.analytics.plots import (  # noqa: E402
    drawdown_chart,
    equity_curve_chart,
    equity_curves_comparison_chart,
)
from core.ui import (  # noqa: E402
    inject_base_style,
    page_header,
    render_benchmark_panel,
)
from db import repository as repo  # noqa: E402

st.set_page_config(page_title="Portfolio Results", layout="wide")
st.session_state["__current_page"] = "portfolio_results"
inject_base_style()
page_header(
    "Portfolio Results",
    "Browse past portfolio backtests. Select one row for details, two or more for comparison.",
)


# ─── Load runs ──────────────────────────────────────────────────────────────
all_runs = repo.list_portfolio_runs(limit=200)
if not all_runs:
    st.info(
        "No portfolio runs yet. Run one on the **Portfolio** tab to see it here."
    )
    st.stop()


# ─── Filter bar ─────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([2, 2, 1])

with fc1:
    available_strategies = sorted({r["strategy"] for r in all_runs})
    selected_strategies = st.multiselect(
        "Strategy",
        options=available_strategies,
        default=[],
        placeholder="Pick one or more strategies",
    )

with fc2:
    available_universes = sorted({r["universe_label"] for r in all_runs})
    selected_universes = st.multiselect(
        "Universe",
        options=available_universes,
        default=[],
        placeholder="Pick one or more universes",
    )

with fc3:
    show_limit = st.number_input(
        "Show last N", value=50, min_value=1, max_value=200, step=10,
    )

if not selected_strategies and not selected_universes:
    st.info(
        f"**{len(all_runs)}** total portfolio runs available. "
        "Pick at least one strategy or universe above to view results."
    )
    st.stop()

filtered = [
    r for r in all_runs
    if (not selected_strategies or r["strategy"] in selected_strategies)
    and (not selected_universes or r["universe_label"] in selected_universes)
][:int(show_limit)]

if not filtered:
    st.warning("No runs match the current filters.")
    st.stop()


# ─── Formatters ─────────────────────────────────────────────────────────────
def _fmt_pct(x):
    return f"{x*100:+.2f}%" if x is not None else "—"


def _fmt_num(x):
    return f"{x:+.3f}" if x is not None else "—"


# ─── Aggregate summary ──────────────────────────────────────────────────────
def _render_filter_summary(runs: list[dict]) -> None:
    returns = [r["total_return"] for r in runs if r["total_return"] is not None]
    sharpes = [r["sharpe"]       for r in runs if r["sharpe"]       is not None]
    profitable = sum(1 for v in returns if v > 0)
    n_strats = len({r["strategy"] for r in runs})
    n_unis = len({r["universe_label"] for r in runs})

    st.subheader("Aggregate across filtered runs")
    st.caption(f"{len(runs)} portfolio runs across {n_strats} strategies and {n_unis} universes.")

    m = st.columns(5)
    m[0].metric("Avg return",     _fmt_pct(mean(returns))   if returns else "—")
    m[1].metric("Median return",  _fmt_pct(median(returns)) if returns else "—")
    m[2].metric(
        "Profitable",
        f"{profitable}/{len(returns)}  ({profitable/len(returns)*100:.0f}%)"
        if returns else "—",
    )
    m[3].metric("Best",  _fmt_pct(max(returns)) if returns else "—")
    m[4].metric("Worst", _fmt_pct(min(returns)) if returns else "—")

    if sharpes:
        st.caption(
            f"Sharpe — avg {_fmt_num(mean(sharpes))}, median {_fmt_num(median(sharpes))}"
        )


_render_filter_summary(filtered)


# ─── Runs table ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("Runs")
st.caption("Select one row for details, two or more for side-by-side comparison.")

display_rows = []
for r in filtered:
    display_rows.append({
        "ID":         r["id"],
        "Strategy":   r["strategy"],
        "Universe":   r["universe_label"],
        "Range":      f"{r['start_date']} → {r['end_date']}",
        "Return":     _fmt_pct(r["total_return"]),
        "CAGR":       _fmt_pct(r["cagr"]),
        "Sharpe":     _fmt_num(r["sharpe"]),
        "Max DD":     _fmt_pct(r["max_drawdown"]),
        "Trades":     r["num_trades"] if r["num_trades"] is not None else "—",
        "Symbols":    f"{r['num_symbols_traded']}/{len(r['symbols'])}",
        "Started":    str(r["started_at"])[:19],
    })

event = st.dataframe(
    pd.DataFrame(display_rows),
    width="stretch",
    hide_index=True,
    selection_mode="multi-row",
    on_select="rerun",
    key="portfolio_runs_table",
)

selected_indices = event.selection.rows if event.selection else []
selected_run_ids = [filtered[i]["id"] for i in selected_indices]


# ─── Detail view ────────────────────────────────────────────────────────────
def _show_portfolio_detail(run_id: int) -> None:
    full = repo.get_portfolio_run(run_id)
    if full is None:
        st.error(f"Portfolio run #{run_id} not found.")
        return

    st.divider()
    st.subheader(
        f"Portfolio run #{run_id}: {full['strategy_name']} on {full['universe_label']}"
    )

    s = full["summary_metrics"]

    m = st.columns(4)
    m[0].metric("Total return", _fmt_pct(s.get("total_return")))
    m[1].metric("CAGR",          _fmt_pct(s.get("cagr")))
    m[2].metric("Sharpe",        _fmt_num(s.get("sharpe")))
    m[3].metric("Max drawdown",  _fmt_pct(s.get("max_drawdown")))

    m2 = st.columns(4)
    m2[0].metric("Trades",       f"{s.get('num_trades', 0)}")
    m2[1].metric("Win rate",     _fmt_pct(s.get("win_rate")))
    m2[2].metric(
        "Symbols traded",
        f"{full['num_symbols_traded']} / {len(full['symbols'])}",
    )
    m2[3].metric("Position size", f"{full['position_size_pct']*100:.0f}%")

    # Benchmark overlay
    bench_series, bench_metrics, bench_error = None, None, None
    try:
        bench_series, bench_metrics = attach_benchmark(
            equity_df=full["equity_curve"],
            initial_capital=full["initial_capital"],
            start_date=full["start_date"],
            end_date=full["end_date"],
            risk_free_rate=full["risk_free_rate"],
            interval=full["interval"],
        )
        if bench_series is None:
            bench_error = "Benchmark data unavailable for this period."
    except Exception as exc:
        bench_error = f"Benchmark fetch failed: {exc}"

    st.plotly_chart(
        equity_curve_chart(
            full["equity_curve"],
            initial_capital=full["initial_capital"],
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
    st.plotly_chart(drawdown_chart(full["equity_curve"]), width="stretch")

    # Per-symbol contribution
    trades = full["trades"]
    if not trades.empty:
        with st.expander("Per-symbol contribution", expanded=False):
            sells = trades[trades["side"] == "SELL"]
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
        if trades.empty:
            st.info("No trades.")
        else:
            tdf = trades.copy()
            tdf["timestamp"] = pd.to_datetime(tdf["timestamp"]).dt.date
            st.dataframe(tdf, width="stretch", hide_index=True)

    with st.expander("Run config", expanded=False):
        st.json({
            "strategy":          full["strategy_name"],
            "strategy_version":  full["strategy_version"],
            "params":            full["params"],
            "universe":          full["universe_label"],
            "symbols":           full["symbols"],
            "exchange":          full["exchange"],
            "interval":          full["interval"],
            "data_source":       full["data_source"],
            "initial_capital":   full["initial_capital"],
            "position_size_pct": full["position_size_pct"],
            "commission_bps":    full["commission_bps"],
            "slippage_bps":      full["slippage_bps"],
            "risk_free_rate":    full["risk_free_rate"],
        })

    # Delete (gated checkbox)
    st.divider()
    confirm_key = f"confirm_pf_delete_{run_id}"
    confirm = st.checkbox(
        f"Confirm I want to delete portfolio run #{run_id}",
        key=confirm_key,
    )
    if st.button("Delete this portfolio run", type="secondary", disabled=not confirm):
        if repo.delete_portfolio_run(run_id):
            st.success(f"Deleted portfolio run #{run_id}.")
            if "portfolio_runs_table" in st.session_state:
                del st.session_state["portfolio_runs_table"]
            st.rerun()
        else:
            st.error(f"Failed to delete portfolio run #{run_id}.")


def _show_portfolio_comparison(run_ids: list[int]) -> None:
    full_runs = []
    for rid in run_ids:
        f = repo.get_portfolio_run(rid)
        if f is not None:
            f["_label"] = f"#{rid} {f['strategy_name']} on {f['universe_label']}"
            full_runs.append(f)

    if not full_runs:
        st.warning("Could not load any of the selected portfolio runs.")
        return

    st.divider()
    st.subheader(f"Comparing {len(full_runs)} portfolio runs")

    # Per-run metrics table
    comp_rows = []
    for f in full_runs:
        s = f["summary_metrics"]
        comp_rows.append({
            "Run":              f["_label"],
            "Return":           _fmt_pct(s.get("total_return")),
            "CAGR":             _fmt_pct(s.get("cagr")),
            "Sharpe":           _fmt_num(s.get("sharpe")),
            "Sortino":          _fmt_num(s.get("sortino")),
            "Max DD":           _fmt_pct(s.get("max_drawdown")),
            "Trades":           s.get("num_trades"),
            "Win rate":         _fmt_pct(s.get("win_rate")),
            "Symbols traded":   f"{f['num_symbols_traded']}/{len(f['symbols'])}",
            "Position size":    f"{f['position_size_pct']*100:.0f}%",
        })

    # Aggregate (mean across the selection)
    rets   = [f["summary_metrics"].get("total_return") for f in full_runs if f["summary_metrics"].get("total_return") is not None]
    cagrs  = [f["summary_metrics"].get("cagr")         for f in full_runs if f["summary_metrics"].get("cagr")         is not None]
    sharps = [f["summary_metrics"].get("sharpe")       for f in full_runs if f["summary_metrics"].get("sharpe")       is not None]
    if rets:
        comp_rows.append({
            "Run":              f"— MEAN of {len(full_runs)} —",
            "Return":           _fmt_pct(mean(rets)),
            "CAGR":             _fmt_pct(mean(cagrs)) if cagrs else "—",
            "Sharpe":           _fmt_num(mean(sharps)) if sharps else "—",
            "Sortino":          "—",
            "Max DD":           "—",
            "Trades":           "—",
            "Win rate":         "—",
            "Symbols traded":   "—",
            "Position size":    "—",
        })

    st.dataframe(pd.DataFrame(comp_rows), width="stretch", hide_index=True)

    normalize = st.toggle(
        "Normalize equity to 100 (compare percent returns)",
        value=False,
        help="Useful when runs have different initial capital or date ranges.",
    )
    curves = [
        {"label": f["_label"], "equity_curve": f["equity_curve"]}
        for f in full_runs
    ]
    st.plotly_chart(
        equity_curves_comparison_chart(curves, normalize=normalize,
                                       title="Portfolio equity curves"),
        width="stretch",
    )


# ─── Route ──────────────────────────────────────────────────────────────────
if not selected_run_ids:
    st.info("Select one or more rows above to view details or compare.")
elif len(selected_run_ids) == 1:
    _show_portfolio_detail(selected_run_ids[0])
else:
    _show_portfolio_comparison(selected_run_ids)
