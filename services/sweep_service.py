"""Orchestration for parameter sweeps — fetches data once, then sweeps."""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from core.data import get_ohlcv
from core.engine.sweep import SweepResult, run_sweep


def run_sweep_and_collect(
    *,
    strategy_name: str,
    symbol: str,
    start_date,
    end_date,
    param_grid: dict[str, list],
    interval: str = "1d",
    exchange: str = "NSE",
    data_source: str = "yfinance",
    initial_capital: float = 100_000.0,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
    risk_free_rate: float = 0.065,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> SweepResult:
    """Fetch OHLCV once, then run a sweep over `param_grid`.

    All non-swept config (capital, costs, etc.) stays constant across combos.
    Sweep results are NOT persisted to the DB — they're exploratory by nature.
    Once you've found a promising combo, re-run it via the Backtest tab to save.
    """
    start_iso = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
    end_iso = end_date.isoformat() if isinstance(end_date, date) else str(end_date)

    ohlcv = get_ohlcv(
        symbol=symbol,
        start=start_iso,
        end=end_iso,
        interval=interval,
        exchange=exchange,
        source=data_source,
    )

    return run_sweep(
        ohlcv=ohlcv,
        strategy_name=strategy_name,
        param_grid=param_grid,
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        data_source=data_source,
        initial_capital=initial_capital,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
        progress_callback=progress_callback,
    )
