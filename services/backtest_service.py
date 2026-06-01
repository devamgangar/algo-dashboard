"""Orchestration layer: ties data layer → strategy → engine → DB persistence.

This is the single entry point the Streamlit UI calls. Keeps the UI ignorant
of pandas, vectorbt, and SQLAlchemy — pages only know about service functions
and primitive Python types.

Deduplication: each run is identified by a SHA-256 `fingerprint` over all its
inputs. By default `run_and_save` looks up the fingerprint first and reuses
an existing row if found. Pass `force_rerun=True` to bypass the cache (e.g.,
after yfinance updates the underlying data).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from core.data import get_ohlcv
from core.engine import BacktestResult, run_backtest
from core.strategies import get_strategy
from db import repository as repo


def _compute_fingerprint(
    *,
    symbol: str,
    exchange: str,
    interval: str,
    start_date,
    end_date,
    strategy_name: str,
    strategy_version: str,
    params: dict,
    initial_capital: float,
    commission_bps: float,
    slippage_bps: float,
    risk_free_rate: float,
    data_source: str,
) -> str:
    """SHA-256 over a canonical JSON of all inputs that affect the result."""
    canonical = {
        "symbol":           symbol.upper(),
        "exchange":         exchange.upper(),
        "interval":         interval,
        "start_date":       str(start_date),
        "end_date":         str(end_date),
        "strategy_name":    strategy_name,
        "strategy_version": strategy_version,
        "params":           {k: params[k] for k in sorted(params)},
        "initial_capital":  float(initial_capital),
        "commission_bps":   float(commission_bps),
        "slippage_bps":     float(slippage_bps),
        "risk_free_rate":   float(risk_free_rate),
        "data_source":      data_source,
    }
    payload = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reconstruct_result(cached: dict) -> BacktestResult:
    """Convert a repo.get_run() dict back to a BacktestResult."""
    strategy_cls = get_strategy(cached["strategy_name"])
    return BacktestResult(
        symbol=cached["symbol"],
        exchange=cached["exchange"],
        start_date=cached["start_date"],
        end_date=cached["end_date"],
        interval=cached["interval"],
        data_source=cached["data_source"],
        strategy_name=cached["strategy_name"],
        strategy_version=cached["strategy_version"],
        strategy_params=cached["params"],
        initial_capital=cached["initial_capital"],
        commission_bps=cached["commission_bps"],
        slippage_bps=cached["slippage_bps"],
        risk_free_rate=cached.get("risk_free_rate", 0.0),
        sizing=dict(strategy_cls.sizing),
        trades=cached["trades"],
        equity_curve=cached["equity_curve"],
        summary_metrics=cached["summary_metrics"],
        extended_metrics=cached["extended_metrics"],
    )


def run_and_save(
    *,
    symbol: str,
    strategy_name: str,
    start_date,
    end_date,
    interval: str = "1d",
    exchange: str = "NSE",
    data_source: str = "yfinance",
    params: dict | None = None,
    initial_capital: float = 100_000.0,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
    risk_free_rate: float = 0.065,
    force_rerun: bool = False,
) -> tuple[int, BacktestResult, bool]:
    """Run a backtest end-to-end and persist it.

    Returns:
        (run_id, BacktestResult, from_cache).
        `from_cache` is True if we returned an existing matching run without
        re-running the backtest.

    Pass `force_rerun=True` to recompute even if a matching fingerprint exists
    (e.g., to pick up new bars from yfinance).
    """
    start_iso = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
    end_iso = end_date.isoformat() if isinstance(end_date, date) else str(end_date)

    strategy_cls = get_strategy(strategy_name)
    effective_params = {**strategy_cls.default_params, **(params or {})}

    fingerprint = _compute_fingerprint(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        start_date=start_iso,
        end_date=end_iso,
        strategy_name=strategy_name,
        strategy_version=strategy_cls.version,
        params=effective_params,
        initial_capital=initial_capital,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
        data_source=data_source,
    )

    if not force_rerun:
        existing_id = repo.find_run_by_fingerprint(fingerprint)
        if existing_id is not None:
            cached = repo.get_run(existing_id)
            if cached is not None:
                return existing_id, _reconstruct_result(cached), True

    # Fresh run
    ohlcv = get_ohlcv(
        symbol=symbol,
        start=start_iso,
        end=end_iso,
        interval=interval,
        exchange=exchange,
        source=data_source,
    )

    strategy = strategy_cls(**(params or {}))

    result = run_backtest(
        ohlcv=ohlcv,
        strategy=strategy,
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        data_source=data_source,
        initial_capital=initial_capital,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
    )

    run_id = repo.save_result(result, fingerprint=fingerprint)
    return run_id, result, False
