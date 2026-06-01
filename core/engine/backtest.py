"""Backtest engine — wraps vectorbt and produces a standardized result object.

The engine is the only layer that knows about vectorbt. Strategies return plain
pandas boolean Series; the engine maps them onto `Portfolio.from_signals` along
with the sizing config the strategy declares.

Execution model:
  - Signals are computed at bar `t` close.
  - Orders are executed at bar `t+1` close (signals are shifted by 1 to avoid
    lookahead bias). This is a pessimistic but realistic model: "you saw the
    cross at end of day, you act tomorrow."
  - Whole-share quantities only (Indian equity reality).
  - Commission and slippage applied as bps of trade value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

# vectorbt is imported lazily inside run_backtest() — see comment there.
# `from __future__ import annotations` makes the vbt.Portfolio type hints in
# helper functions safe to keep without importing vbt at module load.

from core.strategies.base import BaseStrategy


_VBT_FREQ_MAP = {
    "1d":  "1D",
    "1h":  "1h",
    "30m": "30min",
    "15m": "15min",
    "5m":  "5min",
    "1m":  "1min",
}


@dataclass
class BacktestResult:
    """Self-contained result of a single backtest run.

    Shaped to match the DB schema (step 5). The persistence layer reads
    these fields and writes to backtest_runs / trades / equity_curve / run_metrics.
    """
    # Run identification
    symbol: str
    exchange: str
    start_date: date
    end_date: date
    interval: str
    data_source: str

    # Strategy reference
    strategy_name: str
    strategy_version: str
    strategy_params: dict

    # Execution config
    initial_capital: float
    commission_bps: float
    slippage_bps: float
    risk_free_rate: float
    sizing: dict

    # Results
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    summary_metrics: dict
    extended_metrics: dict = field(default_factory=dict)


def _vbt_sizing(sizing: dict) -> dict:
    """Map our sizing dict to vectorbt from_signals kwargs."""
    type_ = sizing.get("type")
    value = sizing.get("value")
    if type_ is None or value is None:
        raise ValueError(f"sizing must have 'type' and 'value' keys, got {sizing!r}")

    valid_types = {"percent", "amount", "value", "targetpercent"}
    if type_ not in valid_types:
        raise ValueError(
            f"Unsupported sizing type: {type_!r}. Supported: {sorted(valid_types)}"
        )
    return {"size": value, "size_type": type_}


def _build_trades(
    pf: vbt.Portfolio,
    ohlcv: pd.DataFrame,
    symbol: str,
    slippage_bps: float,
) -> pd.DataFrame:
    """Expand vectorbt round-trip trades into per-event rows (BUY then SELL).

    Sets `duration_days` on each SELL row (NULL on BUY).
    """
    trades_df = pf.trades.records_readable
    if trades_df.empty:
        return _empty_trades_df()

    rows = []
    slip_rate = slippage_bps / 10_000.0

    for _, t in trades_df.iterrows():
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
        has_exit = status == "closed" and pd.notna(t.get("Exit Timestamp"))
        if has_exit:
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

    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def _empty_trades_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "timestamp", "symbol", "side", "qty", "price", "trade_value",
        "commission", "slippage_cost", "pnl", "duration_days",
        "trade_type", "notes",
    ])


def _build_equity_curve(pf: vbt.Portfolio) -> pd.DataFrame:
    """Combine equity / cash / position / drawdown into one DataFrame."""
    equity = pf.value()
    cash = pf.cash()
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


_PERIODS_PER_YEAR = {
    "1d":  252,
    "1h":  252 * 6.25,  # ~6.25 hourly bars per trading day
    "30m": 252 * 12.5,
    "15m": 252 * 25,
    "5m":  252 * 75,
    "1m":  252 * 375,
}


def _compute_metrics(
    pf: vbt.Portfolio,
    ohlcv: pd.DataFrame,
    interval: str,
    risk_free_rate: float,
) -> tuple[dict, dict]:
    """Compute summary metrics (columns on backtest_runs) and extended (long-format)."""
    total_return = _safe_float(pf.total_return())
    num_trades = int(pf.trades.count())

    span_days = (ohlcv.index[-1] - ohlcv.index[0]).days
    years = span_days / 365.25 if span_days > 0 else 0.0
    cagr = ((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    # Convert annual RFR to per-period for vectorbt's sharpe/sortino.
    periods_per_year = _PERIODS_PER_YEAR.get(interval, 252)
    per_period_rfr = risk_free_rate / periods_per_year

    sharpe = _safe_float(pf.sharpe_ratio(risk_free=per_period_rfr))
    # Sortino's "minimum acceptable return" param is named `required_return`
    # in vectorbt, but conceptually it's the same as Sharpe's risk_free.
    sortino = _safe_float(pf.sortino_ratio(required_return=per_period_rfr))
    max_dd = _safe_float(pf.max_drawdown())
    win_rate = _safe_float(pf.trades.win_rate()) if num_trades > 0 else 0.0

    summary = {
        "total_return": total_return,
        "cagr":         cagr,
        "sharpe":       sharpe,
        "sortino":      sortino,
        "max_drawdown": max_dd,
        "win_rate":     win_rate,
        "num_trades":   num_trades,
    }

    # If the strategy never opened a position, Sharpe / Sortino / Win-rate
    # are mathematically undefined (division by zero std or zero trades).
    # Report as None rather than a misleading numerical value.
    if num_trades == 0:
        summary["sharpe"]   = None
        summary["sortino"]  = None
        summary["win_rate"] = None

    # Opportunity-cost-aware metrics.
    rfr_total_return = ((1 + risk_free_rate) ** years - 1.0) if years > 0 else 0.0
    excess_return_vs_rfr = total_return - rfr_total_return

    # In-market analytics.
    in_market_mask = (pf.value() - pf.cash()) > 0
    exposure_pct = _safe_float(in_market_mask.mean() * 100.0)
    in_market_bars = int(in_market_mask.sum())
    years_in_market = in_market_bars / periods_per_year if periods_per_year > 0 else 0.0
    return_per_year_in_market = (
        ((1 + total_return) ** (1 / years_in_market) - 1.0)
        if years_in_market > 0 else 0.0
    )

    extended = {
        "calmar_ratio":              _safe_float(pf.calmar_ratio()),
        "final_equity":              _safe_float(pf.value().iloc[-1]),
        "peak_equity":               _safe_float(pf.value().cummax().iloc[-1]),
        "exposure_pct":              exposure_pct,
        "trade_span_days":           float(span_days),
        "rfr_total_return":          rfr_total_return,
        "excess_return_vs_rfr":      excess_return_vs_rfr,
        "return_per_year_in_market": return_per_year_in_market,
    }

    # Trade duration metrics — only meaningful if at least one trade closed.
    trades_df = pf.trades.records_readable
    closed = trades_df[trades_df["Status"].astype(str).str.lower() == "closed"]
    if not closed.empty:
        durations = (
            pd.to_datetime(closed["Exit Timestamp"])
            - pd.to_datetime(closed["Entry Timestamp"])
        ).dt.days
        extended["avg_trade_duration_days"]    = float(durations.mean())
        extended["median_trade_duration_days"] = float(durations.median())
        extended["max_trade_duration_days"]    = float(durations.max())

    if num_trades > 0:
        try:
            extended["avg_winning_trade_pnl"] = _safe_float(pf.trades.winning.pnl.mean())
            extended["avg_losing_trade_pnl"]  = _safe_float(pf.trades.losing.pnl.mean())
        except Exception:
            pass

    return summary, extended


def _safe_float(value) -> float:
    """Coerce a possibly-NaN/inf vectorbt scalar to a plain float (NaN/inf → 0.0)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if np.isnan(f) or np.isinf(f):
        return 0.0
    return f


def run_backtest(
    ohlcv: pd.DataFrame,
    strategy: BaseStrategy,
    symbol: str,
    exchange: str = "NSE",
    interval: str = "1d",
    data_source: str = "yfinance",
    initial_capital: float = 100_000.0,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
    risk_free_rate: float = 0.065,
) -> BacktestResult:
    """Run a single-symbol backtest of `strategy` on `ohlcv` and return results.

    Strategy signals are shifted by 1 bar to avoid lookahead bias — orders fill
    at the close of the bar AFTER the signal. Whole shares only.

    `risk_free_rate` is annual (e.g. 0.065 for 6.5%). Used in Sharpe/Sortino
    and to compute excess return over the risk-free baseline. Default reflects
    Indian liquid-fund yields as of early 2026.
    """
    if interval not in _VBT_FREQ_MAP:
        raise ValueError(
            f"Unsupported interval for engine: {interval!r}. "
            f"Supported: {list(_VBT_FREQ_MAP)}"
        )
    if ohlcv.empty:
        raise ValueError("ohlcv is empty")

    # Lazy import: vectorbt drags in numba/llvmlite (~200MB, ~1s cold load).
    # Keep it out of the module-level import chain so pages that never run a
    # backtest (Strategies, Results, Forward Testing) don't pay this cost.
    import vectorbt as vbt

    entries, exits = strategy.generate_signals(ohlcv)
    # Shift by 1: signal at bar t → order fills at bar t+1
    entries = entries.shift(1, fill_value=False).astype(bool)
    exits = exits.shift(1, fill_value=False).astype(bool)

    sizing_kwargs = _vbt_sizing(strategy.sizing)

    pf = vbt.Portfolio.from_signals(
        close=ohlcv["close"],
        entries=entries,
        exits=exits,
        init_cash=initial_capital,
        fees=commission_bps / 10_000.0,
        slippage=slippage_bps / 10_000.0,
        size_granularity=1,
        freq=_VBT_FREQ_MAP[interval],
        **sizing_kwargs,
    )

    trades = _build_trades(pf, ohlcv, symbol, slippage_bps)
    equity_curve = _build_equity_curve(pf)
    summary, extended = _compute_metrics(pf, ohlcv, interval, risk_free_rate)

    return BacktestResult(
        symbol=symbol,
        exchange=exchange,
        start_date=ohlcv.index[0].date(),
        end_date=ohlcv.index[-1].date(),
        interval=interval,
        data_source=data_source,
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        strategy_params=dict(strategy.params),
        initial_capital=float(initial_capital),
        commission_bps=float(commission_bps),
        slippage_bps=float(slippage_bps),
        risk_free_rate=float(risk_free_rate),
        sizing=dict(strategy.sizing),
        trades=trades,
        equity_curve=equity_curve,
        summary_metrics=summary,
        extended_metrics=extended,
    )
