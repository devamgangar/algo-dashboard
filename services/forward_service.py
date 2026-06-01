"""Orchestration for forward (paper-trading) runs.

Tick pattern: on each invocation, re-run the underlying backtest from the
run's start_date to today, then overwrite forward_trades + forward_equity_curve
in the DB. Idempotent. No drift across ticks.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.data import get_ohlcv
from core.engine import run_backtest
from core.engine.forward import TickResult
from core.strategies import get_strategy
from db import repository as repo


LOOKBACK_BUFFER_DAYS = 365  # extra calendar days of history beyond start_date
                            # to ensure strategy warmup is satisfied


def start_forward_run(
    *,
    strategy_name: str,
    symbol: str,
    exchange: str = "NSE",
    interval: str = "1d",
    data_source: str = "yfinance",
    params: Optional[dict] = None,
    initial_capital: float = 100_000.0,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
    risk_free_rate: float = 0.065,
    start_date: Optional[date] = None,
) -> tuple[int, TickResult]:
    """Create a forward run and immediately do its first tick.

    Returns (forward_run_id, first_tick_result).
    """
    if start_date is None:
        start_date = date.today()

    strategy_cls = get_strategy(strategy_name)
    effective_params = {**strategy_cls.default_params, **(params or {})}

    run_id = repo.create_forward_run(
        strategy_name=strategy_name,
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        data_source=data_source,
        params=effective_params,
        initial_capital=initial_capital,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        risk_free_rate=risk_free_rate,
        start_date=start_date,
    )

    tick = tick_forward_run(run_id)
    return run_id, tick


def tick_forward_run(forward_run_id: int) -> TickResult:
    """Re-run the underlying backtest from start_date to today, replace stored state.

    Safe to call repeatedly: each invocation overwrites trades + equity_curve
    with freshly-computed values.
    """
    run = repo.get_forward_run_detail(forward_run_id)
    if run is None:
        return TickResult(forward_run_id, "skipped", 0, None, "run not found")
    if run["status"] != "active":
        return TickResult(forward_run_id, "skipped", 0, run["last_processed_date"],
                          f"status={run['status']}")

    today = date.today()
    if today < run["start_date"]:
        return TickResult(forward_run_id, "skipped", 0, None,
                          "today is before start_date")

    # Fetch with a generous lookback so strategy warmup is satisfied even if
    # start_date was very recent (e.g., starting today with SMA(20,50) needs
    # ~50 bars BEFORE start_date for indicators to be stable).
    fetch_start = run["start_date"] - timedelta(days=LOOKBACK_BUFFER_DAYS)

    try:
        ohlcv = get_ohlcv(
            symbol=run["symbol"],
            start=fetch_start.isoformat(),
            end=today.isoformat(),
            interval=run["interval"],
            exchange=run["exchange"],
            source=run["data_source"],
        )
    except Exception as exc:
        msg = f"data fetch failed: {exc}"
        repo.replace_forward_run_data(
            forward_run_id=forward_run_id,
            trades=__import__("pandas").DataFrame(),
            equity_curve=__import__("pandas").DataFrame(),
            last_processed_date=run["last_processed_date"],
            error_msg=msg,
        )
        return TickResult(forward_run_id, "error", 0, run["last_processed_date"], msg)

    if ohlcv.empty:
        return TickResult(forward_run_id, "no_new_bars", 0, run["last_processed_date"])

    # Slice to start_date onward for the backtest portion (warmup bars stay
    # available to the strategy via its rolling computations, since we hand
    # the FULL ohlcv to the engine).
    try:
        strategy_cls = get_strategy(run["strategy_name"])
        strategy = strategy_cls(**run["params"])

        # The engine itself will use all bars in `ohlcv` to compute signals.
        # The equity curve will span the full range — but we only care about
        # what happened from start_date onward. Filter after.
        result = run_backtest(
            ohlcv=ohlcv,
            strategy=strategy,
            symbol=run["symbol"],
            exchange=run["exchange"],
            interval=run["interval"],
            data_source=run["data_source"],
            initial_capital=run["initial_capital"],
            commission_bps=run["commission_bps"],
            slippage_bps=run["slippage_bps"],
            risk_free_rate=run["risk_free_rate"],
        )

        # Filter trades + equity to start_date onward (the "forward window")
        import pandas as pd
        start_ts = pd.Timestamp(run["start_date"])
        eq_filtered = result.equity_curve[
            pd.to_datetime(result.equity_curve["timestamp"]) >= start_ts
        ].copy()

        # Renormalize the equity curve so it begins at initial_capital on the
        # first forward-window bar (rather than wherever the backtest left it).
        if not eq_filtered.empty:
            scale = run["initial_capital"] / eq_filtered["equity"].iloc[0]
            eq_filtered["equity"]         = eq_filtered["equity"] * scale
            eq_filtered["cash"]           = eq_filtered["cash"] * scale
            eq_filtered["position_value"] = eq_filtered["position_value"] * scale
            # Recompute drawdown for the filtered window
            peak = eq_filtered["equity"].cummax()
            eq_filtered["drawdown_pct"] = ((eq_filtered["equity"] - peak) / peak * 100.0).fillna(0.0)

        tr_filtered = result.trades[
            pd.to_datetime(result.trades["timestamp"]) >= start_ts
        ].copy() if not result.trades.empty else result.trades

        bars_processed = len(eq_filtered)

        repo.replace_forward_run_data(
            forward_run_id=forward_run_id,
            trades=tr_filtered,
            equity_curve=eq_filtered,
            last_processed_date=today,
            error_msg=None,
        )

        return TickResult(forward_run_id, "updated", bars_processed, today)

    except Exception as exc:
        msg = f"tick failed: {exc}"
        return TickResult(forward_run_id, "error", 0, run["last_processed_date"], msg)


def tick_all_active() -> list[TickResult]:
    """Tick every active forward run. Used by scheduled jobs."""
    runs = repo.list_forward_runs(status="active")
    return [tick_forward_run(r["id"]) for r in runs]


def stop_forward_run(forward_run_id: int) -> bool:
    return repo.stop_forward_run(forward_run_id)
