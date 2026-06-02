"""Portfolio backtest engine — one strategy applied across N symbols.

Wraps vectorbt's multi-asset `Portfolio.from_signals` with `cash_sharing=True`
so all symbols draw from a single cash pool. Each entry signal opens a new
position sized as `position_size_pct` of current portfolio equity (compounding).

The strategy runs independently on each symbol's price history — there's no
cross-symbol signal coordination. Cash constraints decide which simultaneous
signals get filled when multiple fire on the same bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from core.strategies.base import BaseStrategy


_VBT_FREQ_MAP = {
    "1d":  "1D",
    "1h":  "1h",
    "30m": "30min",
    "15m": "15min",
    "5m":  "5min",
    "1m":  "1min",
}

_PERIODS_PER_YEAR = {
    "1d":  252,
    "1h":  252 * 6.25,
    "30m": 252 * 12.5,
    "15m": 252 * 25,
    "5m":  252 * 75,
    "1m":  252 * 375,
}


@dataclass
class PortfolioResult:
    """Result of a multi-symbol portfolio backtest."""
    universe_label: str
    symbols: list[str]
    skipped_symbols: list[str]            # failed data fetch / no signals
    start_date: date
    end_date: date
    interval: str
    data_source: str
    strategy_name: str
    strategy_version: str
    strategy_params: dict
    initial_capital: float
    position_size_pct: float
    commission_bps: float
    slippage_bps: float
    risk_free_rate: float
    trades: pd.DataFrame                   # per-event log (incl. symbol col)
    equity_curve: pd.DataFrame             # portfolio-level
    summary_metrics: dict
    num_symbols_traded: int                # distinct symbols that had trades
    extended_metrics: dict = field(default_factory=dict)


def _safe_float(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if np.isnan(f) or np.isinf(f):
        return 0.0
    return f


def _build_portfolio_trades(
    pf, slippage_bps: float,
) -> tuple[pd.DataFrame, int]:
    """Expand multi-symbol vectorbt trades into per-event rows.

    Returns (trades_df, num_symbols_traded).
    """
    trades_df = pf.trades.records_readable
    if trades_df.empty:
        return _empty_trades_df(), 0

    rows = []
    slip_rate = slippage_bps / 10_000.0

    # vectorbt's `records_readable` for multi-asset includes 'Column' (the symbol).
    col_name = "Column" if "Column" in trades_df.columns else trades_df.columns[1]

    for _, t in trades_df.iterrows():
        symbol = str(t[col_name])
        qty = int(t["Size"])
        entry_ts = pd.Timestamp(t["Entry Timestamp"])
        entry_price = float(t["Avg Entry Price"])
        entry_value = qty * entry_price
        rows.append({
            "timestamp":     entry_ts,
            "symbol":        symbol,
            "side":          "BUY",
            "qty":           qty,
            "price":         entry_price,
            "trade_value":   entry_value,
            "commission":    float(t["Entry Fees"]),
            "slippage_cost": entry_value * slip_rate,
            "pnl":           None,
            "duration_days": None,
            "trade_type":    "entry",
            "notes":         None,
        })

        status = str(t.get("Status", "")).lower()
        if status == "closed" and pd.notna(t.get("Exit Timestamp")):
            exit_ts = pd.Timestamp(t["Exit Timestamp"])
            exit_price = float(t["Avg Exit Price"])
            exit_value = qty * exit_price
            duration = int((exit_ts - entry_ts).days)
            rows.append({
                "timestamp":     exit_ts,
                "symbol":        symbol,
                "side":          "SELL",
                "qty":           qty,
                "price":         exit_price,
                "trade_value":   exit_value,
                "commission":    float(t["Exit Fees"]),
                "slippage_cost": exit_value * slip_rate,
                "pnl":           float(t["PnL"]),
                "duration_days": duration,
                "trade_type":    "exit",
                "notes":         None,
            })

    out = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    distinct_symbols = int(out["symbol"].nunique()) if not out.empty else 0
    return out, distinct_symbols


def _empty_trades_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "timestamp", "symbol", "side", "qty", "price", "trade_value",
        "commission", "slippage_cost", "pnl", "duration_days",
        "trade_type", "notes",
    ])


def _build_portfolio_equity_curve(pf) -> pd.DataFrame:
    """Aggregate portfolio-level equity / cash / position value over time.

    With `cash_sharing=True`, `pf.value()` is already the sum across symbols.
    """
    equity = pf.value()
    cash = pf.cash()
    # When cash_sharing is True, cash is a single Series. value() is too.
    if hasattr(equity, "to_frame") and isinstance(equity, pd.DataFrame):
        # Defensive: collapse if it came back as 2D
        equity = equity.sum(axis=1)
    if hasattr(cash, "to_frame") and isinstance(cash, pd.DataFrame):
        cash = cash.iloc[:, 0]  # shared cash — same across columns

    position_value = equity - cash
    peak = equity.cummax()
    drawdown_pct = ((equity - peak) / peak * 100.0).fillna(0.0)

    return pd.DataFrame({
        "timestamp":      equity.index,
        "equity":         equity.values.astype(float),
        "cash":           cash.values.astype(float),
        "position_value": position_value.values.astype(float),
        "drawdown_pct":   drawdown_pct.values.astype(float),
    })


def _compute_portfolio_metrics(
    pf, interval: str, risk_free_rate: float,
) -> tuple[dict, dict]:
    """Portfolio-level summary + extended metrics."""
    total_return = _safe_float(pf.total_return())
    num_trades = int(pf.trades.count())

    eq = pf.value()
    span_days = (eq.index[-1] - eq.index[0]).days if len(eq) >= 2 else 0
    years = span_days / 365.25 if span_days > 0 else 0.0
    cagr = ((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    periods_per_year = _PERIODS_PER_YEAR.get(interval, 252)
    per_period_rfr = risk_free_rate / periods_per_year

    sharpe = _safe_float(pf.sharpe_ratio(risk_free=per_period_rfr))
    sortino = _safe_float(pf.sortino_ratio(required_return=per_period_rfr))
    max_dd = _safe_float(pf.max_drawdown())
    win_rate = _safe_float(pf.trades.win_rate()) if num_trades > 0 else None

    summary = {
        "total_return": total_return,
        "cagr":         cagr,
        "sharpe":       sharpe if num_trades > 0 else None,
        "sortino":      sortino if num_trades > 0 else None,
        "max_drawdown": max_dd,
        "win_rate":     win_rate,
        "num_trades":   num_trades,
    }

    rfr_total = ((1 + risk_free_rate) ** years - 1.0) if years > 0 else 0.0
    extended = {
        "calmar_ratio":           _safe_float(pf.calmar_ratio()),
        "final_equity":           _safe_float(eq.iloc[-1]),
        "peak_equity":            _safe_float(eq.cummax().iloc[-1]),
        "trade_span_days":        float(span_days),
        "rfr_total_return":       rfr_total,
        "excess_return_vs_rfr":   total_return - rfr_total,
    }
    return summary, extended


def run_portfolio_backtest(
    *,
    ohlcv_by_symbol: dict[str, pd.DataFrame],
    strategy: BaseStrategy,
    universe_label: str,
    initial_capital: float,
    position_size_pct: float,
    commission_bps: float,
    slippage_bps: float,
    risk_free_rate: float,
    interval: str,
    data_source: str,
    skipped_symbols: Optional[list[str]] = None,
) -> PortfolioResult:
    """Run one strategy across the basket of symbols and return aggregated results.

    `ohlcv_by_symbol` must contain DataFrames with a `close` column,
    indexed by timestamp. The function aligns indices, builds 2D signal
    arrays, and calls vectorbt with `cash_sharing=True`.
    """
    import vectorbt as vbt

    if interval not in _VBT_FREQ_MAP:
        raise ValueError(f"Unsupported interval: {interval!r}")
    if not ohlcv_by_symbol:
        raise ValueError("ohlcv_by_symbol is empty")
    if not (0 < position_size_pct <= 1):
        raise ValueError(
            f"position_size_pct must be in (0, 1], got {position_size_pct}"
        )

    symbols = sorted(ohlcv_by_symbol.keys())

    # Build aligned 2D close DataFrame (rows = timestamp, cols = symbols)
    close_2d = pd.DataFrame({
        s: ohlcv_by_symbol[s]["close"] for s in symbols
    }).sort_index()
    # Use forward-fill for any per-symbol missing days, then drop fully-empty rows
    close_2d = close_2d.dropna(how="all")

    # Generate per-symbol signals and stack into 2D
    entries_2d = pd.DataFrame(False, index=close_2d.index, columns=symbols)
    exits_2d = pd.DataFrame(False, index=close_2d.index, columns=symbols)
    for s in symbols:
        sym_ohlcv = ohlcv_by_symbol[s].reindex(close_2d.index)
        # Skip symbols where strategy fails (e.g., not enough bars for warmup)
        try:
            e, x = strategy.generate_signals(sym_ohlcv)
        except Exception:
            continue
        entries_2d[s] = e.reindex(close_2d.index).fillna(False).astype(bool)
        exits_2d[s] = x.reindex(close_2d.index).fillna(False).astype(bool)

    # Shift by 1: signal at bar t fills at bar t+1 (lookahead safety)
    entries_2d = entries_2d.shift(1, fill_value=False).astype(bool)
    exits_2d = exits_2d.shift(1, fill_value=False).astype(bool)

    pf = vbt.Portfolio.from_signals(
        close=close_2d,
        entries=entries_2d,
        exits=exits_2d,
        init_cash=initial_capital,
        fees=commission_bps / 10_000.0,
        slippage=slippage_bps / 10_000.0,
        size_granularity=1,
        freq=_VBT_FREQ_MAP[interval],
        # Fixed-value sizing: each entry uses (initial_capital * pct) rupees.
        # vectorbt's from_signals supports only Amount / Value / Percent — not
        # targetpercent. Using Value gives a clean "10% of initial capital per
        # trade" semantic, which also matches the original spec.
        # Max simultaneous positions ≈ 1 / position_size_pct (10% → ~10 slots).
        size=initial_capital * position_size_pct,
        size_type="value",
        # Single shared cash pool across all symbols.
        cash_sharing=True,
        # Long-only — same guard as single-symbol engine.
        direction="longonly",
        # Default call_seq processes sells before buys per bar; ties broken
        # alphabetically by column. Deterministic, mildly biased.
        call_seq="auto",
    )

    trades, num_symbols_traded = _build_portfolio_trades(pf, slippage_bps)
    equity_curve = _build_portfolio_equity_curve(pf)
    summary, extended = _compute_portfolio_metrics(pf, interval, risk_free_rate)

    return PortfolioResult(
        universe_label=universe_label,
        symbols=symbols,
        skipped_symbols=list(skipped_symbols or []),
        start_date=close_2d.index[0].date(),
        end_date=close_2d.index[-1].date(),
        interval=interval,
        data_source=data_source,
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        strategy_params=dict(strategy.params),
        initial_capital=float(initial_capital),
        position_size_pct=float(position_size_pct),
        commission_bps=float(commission_bps),
        slippage_bps=float(slippage_bps),
        risk_free_rate=float(risk_free_rate),
        trades=trades,
        equity_curve=equity_curve,
        summary_metrics=summary,
        num_symbols_traded=num_symbols_traded,
        extended_metrics=extended,
    )
