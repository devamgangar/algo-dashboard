"""Plotly chart helpers for the dashboard.

All functions take a DataFrame in the shape the engine produces and return
a `plotly.graph_objects.Figure` ready for `st.plotly_chart`.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def equity_curve_chart(
    equity_df: pd.DataFrame,
    initial_capital: float | None = None,
    title: str = "Equity Curve",
    height: int = 380,
) -> go.Figure:
    """Single-run equity over time. Optionally shows initial-capital baseline."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"],
        y=equity_df["equity"],
        name="Equity",
        line=dict(color="#1f77b4", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>₹%{y:,.0f}<extra></extra>",
    ))
    if initial_capital is not None:
        fig.add_hline(
            y=initial_capital,
            line=dict(color="gray", dash="dot", width=1),
            annotation_text=f"Initial: ₹{initial_capital:,.0f}",
            annotation_position="top left",
        )
    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title="Equity (₹)",
        hovermode="x unified",
        height=height,
        margin=dict(l=40, r=20, t=50, b=30),
    )
    return fig


def drawdown_chart(
    equity_df: pd.DataFrame,
    title: str = "Drawdown",
    height: int = 240,
) -> go.Figure:
    """Underwater curve — drawdown as a negative shaded area."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"],
        y=equity_df["drawdown_pct"],
        name="Drawdown %",
        fill="tozeroy",
        line=dict(color="#d62728", width=1),
        hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title="Drawdown (%)",
        hovermode="x unified",
        height=height,
        margin=dict(l=40, r=20, t=50, b=30),
    )
    return fig


def price_with_signals_chart(
    ohlcv: pd.DataFrame,
    trades: pd.DataFrame,
    title: str = "Price + Trade Signals",
    height: int = 420,
) -> go.Figure:
    """Close price as a line with BUY/SELL markers overlaid at execution prices.

    Hover on a BUY marker shows price + qty. Hover on a SELL marker also shows
    PnL and holding duration for that round-trip.

    Assumes `ohlcv` is indexed by timestamp and has a `close` column; `trades`
    has the standard run-result columns (timestamp, side, qty, price, pnl,
    duration_days).
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=ohlcv.index,
        y=ohlcv["close"],
        name="Close",
        line=dict(color="#1f77b4", width=1.5),
        hovertemplate="%{x|%Y-%m-%d}<br>₹%{y:,.2f}<extra></extra>",
    ))

    if not trades.empty:
        trades_ts = pd.to_datetime(trades["timestamp"])

        buys = trades[trades["side"] == "BUY"]
        if not buys.empty:
            fig.add_trace(go.Scatter(
                x=trades_ts[buys.index],
                y=buys["price"],
                name="BUY",
                mode="markers",
                marker=dict(
                    color="#2ca02c", size=12, symbol="triangle-up",
                    line=dict(color="white", width=1),
                ),
                customdata=buys[["qty"]].values,
                hovertemplate=(
                    "<b>BUY</b><br>%{x|%Y-%m-%d}<br>"
                    "₹%{y:,.2f}<br>qty=%{customdata[0]}<extra></extra>"
                ),
            ))

        sells = trades[trades["side"] == "SELL"]
        if not sells.empty:
            pnl_str = sells["pnl"].apply(
                lambda v: f"₹{v:+,.2f}" if pd.notna(v) else "—"
            )
            dur_str = sells["duration_days"].apply(
                lambda v: f"{int(v)}d" if pd.notna(v) else "—"
            )
            sell_custom = pd.DataFrame({
                "qty": sells["qty"].values,
                "pnl": pnl_str.values,
                "dur": dur_str.values,
            })
            fig.add_trace(go.Scatter(
                x=trades_ts[sells.index],
                y=sells["price"],
                name="SELL",
                mode="markers",
                marker=dict(
                    color="#d62728", size=12, symbol="triangle-down",
                    line=dict(color="white", width=1),
                ),
                customdata=sell_custom[["qty", "pnl", "dur"]].values,
                hovertemplate=(
                    "<b>SELL</b><br>%{x|%Y-%m-%d}<br>"
                    "₹%{y:,.2f}<br>qty=%{customdata[0]}<br>"
                    "pnl=%{customdata[1]}<br>held=%{customdata[2]}<extra></extra>"
                ),
            ))

    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title="Price (₹)",
        hovermode="closest",
        height=height,
        margin=dict(l=40, r=20, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def returns_bar_chart(
    labels: list[str],
    returns_pct: list[float],
    title: str = "Total return per run",
    height: int = 320,
) -> go.Figure:
    """Bar chart of per-run returns, green for positive, red for negative.

    `labels` and `returns_pct` must be the same length; values in `returns_pct`
    are already in percent units (e.g. 18.37 for +18.37%).
    """
    colors = ["#2ca02c" if v > 0 else "#d62728" for v in returns_pct]
    fig = go.Figure(go.Bar(
        x=labels,
        y=returns_pct,
        marker_color=colors,
        hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title="Return (%)",
        height=height,
        margin=dict(l=40, r=20, t=50, b=100),
        xaxis_tickangle=-45,
    )
    return fig


def metric_heatmap(
    combos: pd.DataFrame,
    x_param: str,
    y_param: str,
    metric: str,
    title: str | None = None,
    height: int = 480,
) -> go.Figure:
    """2D heatmap of a metric over two parameter axes.

    `combos` must have columns x_param, y_param, and metric.
    Uses RdYlGn diverging colorscale centered at 0 (good for returns / Sharpe).
    """
    grid = combos.pivot(index=y_param, columns=x_param, values=metric)

    fig = go.Figure(go.Heatmap(
        x=grid.columns.tolist(),
        y=grid.index.tolist(),
        z=grid.values,
        colorscale="RdYlGn",
        zmid=0,
        colorbar=dict(title=metric),
        hovertemplate=(
            f"{x_param}=%{{x}}<br>{y_param}=%{{y}}<br>"
            f"{metric}=%{{z:.4f}}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title=title or f"{metric} by ({x_param}, {y_param})",
        xaxis_title=x_param,
        yaxis_title=y_param,
        xaxis=dict(type="category"),
        yaxis=dict(type="category"),
        height=height,
        margin=dict(l=60, r=40, t=50, b=50),
    )
    return fig


def equity_curves_comparison_chart(
    runs: list[dict],
    title: str = "Equity Curve Comparison",
    height: int = 450,
    normalize: bool = False,
) -> go.Figure:
    """Overlay multiple runs' equity curves with named legends.

    Each entry in `runs` must have:
      - 'label':         display name for the legend (e.g. "#3 SMA RELIANCE")
      - 'equity_curve':  DataFrame with 'timestamp' and 'equity' columns

    If `normalize=True`, each curve is rescaled so its starting equity = 100,
    making strategies with different initial capital directly comparable.
    """
    fig = go.Figure()
    for r in runs:
        eq = r["equity_curve"]
        if eq.empty:
            continue
        y = eq["equity"].astype(float)
        if normalize and y.iloc[0] != 0:
            y = (y / y.iloc[0]) * 100.0
        fig.add_trace(go.Scatter(
            x=eq["timestamp"],
            y=y,
            name=r["label"],
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>",
        ))
    fig.update_layout(
        title=title,
        xaxis_title=None,
        yaxis_title=("Equity (normalized = 100)" if normalize else "Equity (₹)"),
        hovermode="x unified",
        height=height,
        margin=dict(l=40, r=20, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig
