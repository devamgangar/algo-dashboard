"""Results tab — browse past backtest runs, view details, compare multiple."""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core.analytics.metrics import metrics_to_table  # noqa: E402
from core.analytics.plots import (  # noqa: E402
    drawdown_chart,
    equity_curve_chart,
    equity_curves_comparison_chart,
    price_with_signals_chart,
)
from core.data import get_ohlcv  # noqa: E402
from db import repository as repo  # noqa: E402

st.set_page_config(page_title="Results", layout="wide")
st.session_state["__current_page"] = "results"
st.title("Results")
st.caption("Browse past backtest runs. Filter, then select rows for detail or comparison.")


# ─── Load runs ──────────────────────────────────────────────────────────────
all_runs = repo.list_runs(limit=200)
if not all_runs:
    st.info("No backtest runs yet. Run one on the Backtest tab to see it here.")
    st.stop()


# ─── Filter bar (defaults empty — user opts in) ─────────────────────────────
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
    available_symbols = sorted({r["symbol"] for r in all_runs})
    selected_symbols = st.multiselect(
        "Symbol",
        options=available_symbols,
        default=[],
        placeholder="Pick one or more symbols",
    )

with fc3:
    show_limit = st.number_input(
        "Show last N", value=50, min_value=1, max_value=200, step=10,
    )


# Both filters empty → don't list anything yet. User must opt-in.
if not selected_strategies and not selected_symbols:
    st.info(
        f"**{len(all_runs)}** total runs available. "
        "Pick at least one strategy or symbol above to view results."
    )
    st.stop()

# Apply filters: empty multiselect means "no constraint" on that dimension.
filtered = [
    r for r in all_runs
    if (not selected_strategies or r["strategy"] in selected_strategies)
    and (not selected_symbols or r["symbol"] in selected_symbols)
][:int(show_limit)]

if not filtered:
    st.warning("No runs match the current filters.")
    st.stop()


# ─── Aggregate summary across the filtered set ──────────────────────────────
def _fmt_pct(x):
    return f"{x*100:+.2f}%" if x is not None else "—"


def _fmt_num(x):
    return f"{x:+.3f}" if x is not None else "—"


def _render_filter_summary(runs: list[dict]) -> None:
    returns = [r["total_return"] for r in runs if r["total_return"] is not None]
    sharpes = [r["sharpe"]       for r in runs if r["sharpe"]       is not None]
    profitable = sum(1 for v in returns if v > 0)
    n_strats = len({r["strategy"] for r in runs})
    n_syms   = len({r["symbol"]   for r in runs})

    st.subheader("Aggregate across filtered runs")
    st.caption(f"{len(runs)} runs across {n_strats} strategies and {n_syms} symbols.")

    m = st.columns(5)
    m[0].metric("Avg return",     _fmt_pct(mean(returns))   if returns else "—")
    m[1].metric("Median return",  _fmt_pct(median(returns)) if returns else "—")
    m[2].metric(
        "Profitable",
        f"{profitable}/{len(returns)}  ({profitable/len(returns)*100:.0f}%)"
        if returns else "—",
    )
    m[3].metric(
        "Best",
        _fmt_pct(max(returns)) if returns else "—",
        help=f"Run #{max(runs, key=lambda r: r['total_return'] or -1e9)['id']}",
    )
    m[4].metric(
        "Worst",
        _fmt_pct(min(returns)) if returns else "—",
        help=f"Run #{min(runs, key=lambda r: r['total_return'] or 1e9)['id']}",
    )

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
        "ID":       r["id"],
        "Strategy": r["strategy"],
        "Symbol":   r["symbol"],
        "Range":    f"{r['start_date']} → {r['end_date']}",
        "Return":   _fmt_pct(r["total_return"]),
        "CAGR":     _fmt_pct(r["cagr"]),
        "Sharpe":   _fmt_num(r["sharpe"]),
        "Max DD":   _fmt_pct(r["max_drawdown"]),
        "Trades":   r["num_trades"] if r["num_trades"] is not None else "—",
        "Started":  str(r["started_at"])[:19],
    })

event = st.dataframe(
    pd.DataFrame(display_rows),
    width="stretch",
    hide_index=True,
    selection_mode="multi-row",
    on_select="rerun",
    key="runs_table",
)

selected_indices = event.selection.rows if event.selection else []
selected_run_ids = [filtered[i]["id"] for i in selected_indices]


# ─── Conditional render: nothing / detail / comparison ──────────────────────

def _show_detail(run_id: int) -> None:
    full = repo.get_run(run_id)
    if full is None:
        st.error(f"Run #{run_id} not found.")
        return

    st.divider()
    st.subheader(f"Run #{run_id}: {full['strategy_name']} on {full['symbol']}")

    s = full["summary_metrics"]
    e = full["extended_metrics"]

    m = st.columns(4)
    m[0].metric("Total return", f"{s['total_return']*100:+.2f}%")
    m[1].metric("CAGR",          f"{s['cagr']*100:+.2f}%")
    m[2].metric("Sharpe",        f"{s['sharpe']:+.3f}")
    m[3].metric("Max drawdown",  f"{s['max_drawdown']*100:.2f}%")

    m2 = st.columns(4)
    m2[0].metric("# Trades",      f"{s['num_trades']}")
    m2[1].metric("Win rate",      f"{s['win_rate']*100:.1f}%")
    m2[2].metric("Exposure",      f"{e.get('exposure_pct', 0):.1f}%")
    m2[3].metric("Excess vs RFR", f"{e.get('excess_return_vs_rfr', 0)*100:+.2f}%")

    st.plotly_chart(
        equity_curve_chart(full["equity_curve"], initial_capital=full["initial_capital"]),
        width="stretch",
    )
    st.plotly_chart(drawdown_chart(full["equity_curve"]), width="stretch")

    # Price + signal overlay — re-fetch OHLCV from cache (typically <50ms hit).
    try:
        ohlcv = get_ohlcv(
            symbol=full["symbol"],
            start=full["start_date"],
            end=full["end_date"],
            interval=full["interval"],
            exchange=full["exchange"],
            source=full["data_source"],
        )
        st.plotly_chart(
            price_with_signals_chart(
                ohlcv, full["trades"],
                title=f"{full['symbol']} price with trade signals",
            ),
            width="stretch",
        )
    except Exception as exc:
        st.info(f"Price overlay unavailable: {exc}")

    with st.expander("Trade log", expanded=False):
        if full["trades"].empty:
            st.info("No trades.")
        else:
            tdf = full["trades"].copy()
            tdf["timestamp"] = pd.to_datetime(tdf["timestamp"]).dt.date
            st.dataframe(tdf, width="stretch", hide_index=True)

    with st.expander("Extended metrics", expanded=False):
        if not e:
            st.info("No extended metrics.")
        else:
            st.dataframe(metrics_to_table(e), width="stretch", hide_index=True)

    with st.expander("Run config", expanded=False):
        st.json({
            "params":          full["params"],
            "initial_capital": full["initial_capital"],
            "commission_bps":  full["commission_bps"],
            "slippage_bps":    full["slippage_bps"],
            "risk_free_rate":  full["risk_free_rate"],
            "data_source":     full["data_source"],
            "interval":        full["interval"],
            "fingerprint":     full["fingerprint"][:16] + "...",
        })

    st.divider()
    confirm_key = f"confirm_delete_{run_id}"
    confirm = st.checkbox(f"Confirm I want to delete run #{run_id}", key=confirm_key)
    if st.button("Delete this run", type="secondary", disabled=not confirm):
        if repo.delete_run(run_id):
            st.success(f"Deleted run #{run_id}.")
            if "runs_table" in st.session_state:
                del st.session_state["runs_table"]
            st.rerun()
        else:
            st.error(f"Failed to delete run #{run_id}.")


def _show_comparison(run_ids: list[int]) -> None:
    full_runs = []
    for rid in run_ids:
        f = repo.get_run(rid)
        if f is not None:
            f["_label"] = f"#{rid} {f['strategy_name']} {f['symbol']}"
            full_runs.append(f)

    if not full_runs:
        st.warning("Could not load any of the selected runs.")
        return

    st.divider()
    st.subheader(f"Comparing {len(full_runs)} runs")

    # Per-run rows
    comp_rows = []
    for f in full_runs:
        s = f["summary_metrics"]
        e = f["extended_metrics"]
        comp_rows.append({
            "Run":         f["_label"],
            "Return":      _fmt_pct(s["total_return"]),
            "CAGR":        _fmt_pct(s["cagr"]),
            "Sharpe":      _fmt_num(s["sharpe"]),
            "Sortino":     _fmt_num(s["sortino"]),
            "Max DD":      _fmt_pct(s["max_drawdown"]),
            "Trades":      s["num_trades"],
            "Win rate":    _fmt_pct(s["win_rate"]),
            "Exposure":    f"{e.get('exposure_pct', 0):.1f}%",
            "Excess RFR":  _fmt_pct(e.get("excess_return_vs_rfr", 0)),
        })

    # Aggregate row (mean across selection)
    rets   = [f["summary_metrics"]["total_return"] for f in full_runs if f["summary_metrics"]["total_return"] is not None]
    cagrs  = [f["summary_metrics"]["cagr"]         for f in full_runs if f["summary_metrics"]["cagr"]         is not None]
    sharp  = [f["summary_metrics"]["sharpe"]       for f in full_runs if f["summary_metrics"]["sharpe"]       is not None]
    if rets:
        comp_rows.append({
            "Run":         f"— MEAN of {len(full_runs)} —",
            "Return":      _fmt_pct(mean(rets)),
            "CAGR":        _fmt_pct(mean(cagrs)) if cagrs else "—",
            "Sharpe":      _fmt_num(mean(sharp)) if sharp else "—",
            "Sortino":     "—",
            "Max DD":      "—",
            "Trades":      "—",
            "Win rate":    "—",
            "Exposure":    "—",
            "Excess RFR":  "—",
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
        equity_curves_comparison_chart(curves, normalize=normalize),
        width="stretch",
    )


if not selected_run_ids:
    st.info("Select one or more rows above to view details or compare.")
elif len(selected_run_ids) == 1:
    _show_detail(selected_run_ids[0])
else:
    _show_comparison(selected_run_ids)
