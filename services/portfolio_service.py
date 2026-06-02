"""Portfolio backtest orchestration.

Fetches OHLCV for every symbol in the universe, runs the multi-symbol engine,
saves the result. Symbols that fail to fetch (e.g., delisted) are silently
skipped — the skip list is included in the result so the UI can surface it.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from core.data import get_ohlcv
from core.engine.portfolio import PortfolioResult, run_portfolio_backtest
from core.strategies import get_strategy
from core.universe import get_universe
from db import repository as repo


def run_portfolio_and_save(
    *,
    strategy_name: str,
    universe_label: str,
    symbols: Optional[list[str]] = None,
    exchange: str = "NSE",
    interval: str = "1d",
    data_source: str = "yfinance",
    params: Optional[dict] = None,
    initial_capital: float = 1_000_000.0,
    position_size_pct: float = 0.10,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
    risk_free_rate: float = 0.065,
    start_date,
    end_date,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[int, PortfolioResult]:
    """Run a portfolio backtest end-to-end and persist it.

    Returns (run_id, PortfolioResult).

    `symbols` overrides the universe lookup when provided (use case: subsetting).
    `progress_callback(current, total, label)` is called once per symbol fetched.
    """
    if symbols is None:
        symbols = get_universe(universe_label)
    if not symbols:
        raise ValueError("No symbols to backtest")

    start_iso = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
    end_iso = end_date.isoformat() if isinstance(end_date, date) else str(end_date)

    # Fetch OHLCV per symbol. Skip + collect any that fail.
    ohlcv_by_symbol: dict = {}
    skipped: list[str] = []
    for i, sym in enumerate(symbols):
        if progress_callback is not None:
            progress_callback(i + 1, len(symbols), sym)
        try:
            df = get_ohlcv(
                symbol=sym,
                start=start_iso,
                end=end_iso,
                interval=interval,
                exchange=exchange,
                source=data_source,
            )
            if df.empty:
                skipped.append(sym)
                continue
            ohlcv_by_symbol[sym] = df
        except Exception:
            skipped.append(sym)

    if not ohlcv_by_symbol:
        raise RuntimeError(
            f"All {len(symbols)} symbols failed to fetch. Check connectivity / tickers."
        )

    # Instantiate strategy
    strategy_cls = get_strategy(strategy_name)
    strategy = strategy_cls(**(params or {}))

    # Run the engine
    result = run_portfolio_backtest(
        ohlcv_by_symbol=ohlcv_by_symbol,
        strategy=strategy,
        universe_label=universe_label,
        initial_capital=initial_capital,
        position_size_pct=position_size_pct,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
        interval=interval,
        data_source=data_source,
        skipped_symbols=skipped,
    )

    # Persist
    run_id = repo.save_portfolio_result(
        strategy_name=strategy_name,
        universe_label=universe_label,
        symbols=result.symbols,
        exchange=exchange,
        interval=interval,
        data_source=data_source,
        params=result.strategy_params,
        initial_capital=initial_capital,
        position_size_pct=position_size_pct,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
        start_date=result.start_date,
        end_date=result.end_date,
        summary_metrics=result.summary_metrics,
        num_symbols_traded=result.num_symbols_traded,
        trades=result.trades,
        equity_curve=result.equity_curve,
    )

    return run_id, result
