"""Display metadata and formatting helpers for extended metrics.

Used by the Backtest and Results tabs to render the long-format
`extended_metrics` dict as a human-readable table.
"""
from __future__ import annotations

import pandas as pd

# (display_name, format_type, description)
#   format types: "rupees", "fraction", "percent", "days", "ratio", "raw"
EXTENDED_METRIC_META: dict[str, tuple[str, str, str]] = {
    "calmar_ratio":               ("Calmar ratio",               "ratio",    "CAGR ÷ |Max drawdown|. Higher = better risk-adjusted growth."),
    "final_equity":               ("Final equity",               "rupees",   "Portfolio value at end of backtest."),
    "peak_equity":                ("Peak equity",                "rupees",   "Highest portfolio value reached."),
    "exposure_pct":               ("Exposure",                   "percent",  "% of bars where a position was held."),
    "trade_span_days":            ("Trade span",                 "days",     "Calendar days from first to last bar."),
    "rfr_total_return":           ("RFR baseline return",        "fraction", "What the risk-free rate alone would have returned over the same period."),
    "excess_return_vs_rfr":       ("Excess return vs RFR",       "fraction", "Strategy total return minus RFR total return."),
    "return_per_year_in_market":  ("Return/yr while in market",  "fraction", "Annualized return counting only bars when invested."),
    "avg_trade_duration_days":    ("Avg trade duration",         "days",     "Mean days held per closed trade."),
    "median_trade_duration_days": ("Median trade duration",      "days",     "Median days held per closed trade."),
    "max_trade_duration_days":    ("Max trade duration",         "days",     "Longest closed trade."),
    "avg_winning_trade_pnl":      ("Avg winning trade",          "rupees",   "Mean P&L of profitable trades."),
    "avg_losing_trade_pnl":       ("Avg losing trade",           "rupees",   "Mean P&L of losing trades."),
}


def format_metric(value, fmt: str) -> str:
    """Format a scalar according to its declared metric type."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)

    if fmt == "percent":
        return f"{v:.2f}%"
    if fmt == "fraction":
        return f"{v * 100:+.2f}%"
    if fmt == "rupees":
        return f"₹{v:,.2f}"
    if fmt == "days":
        return f"{int(round(v)):,} days"
    if fmt == "ratio":
        return f"{v:.3f}"
    return f"{v}"


def metrics_to_table(metrics: dict) -> pd.DataFrame:
    """Build a 3-column display DataFrame from an extended_metrics dict.

    Unknown keys (no metadata entry) fall through with the raw key as the
    display name and no formatting / description.
    """
    rows = []
    for key, value in metrics.items():
        display_name, fmt, description = EXTENDED_METRIC_META.get(
            key, (key, "raw", "")
        )
        rows.append({
            "Metric":      display_name,
            "Value":       format_metric(value, fmt),
            "Description": description,
        })
    return pd.DataFrame(rows)
