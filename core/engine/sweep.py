"""Parameter sweep — run a grid of backtests over parameter combinations.

For each combo in the cartesian product of the param grid, runs an isolated
backtest and collects its summary metrics into a single DataFrame.

Combos that violate strategy constraints (e.g. SMA's `fast < slow` check)
are caught — the row still appears in the result with NaN metrics and an
`error` column populated.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Optional

import pandas as pd

from core.engine.backtest import run_backtest
from core.strategies import get_strategy


@dataclass
class SweepResult:
    """Aggregated results from a parameter sweep."""
    strategy_name: str
    symbol: str
    param_grid: dict[str, list]
    combos: pd.DataFrame  # one row per combo; columns = params + summary metrics + 'error'


# Summary-metric keys the engine produces — used to fill NaN rows on error.
_METRIC_KEYS = [
    "total_return", "cagr", "sharpe", "sortino",
    "max_drawdown", "win_rate", "num_trades",
]


def run_sweep(
    *,
    ohlcv: pd.DataFrame,
    strategy_name: str,
    param_grid: dict[str, list],
    symbol: str,
    exchange: str = "NSE",
    interval: str = "1d",
    data_source: str = "yfinance",
    initial_capital: float = 100_000.0,
    commission_bps: float = 3.0,
    slippage_bps: float = 5.0,
    risk_free_rate: float = 0.065,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> SweepResult:
    """Run a backtest for each combination in `param_grid`.

    `param_grid` maps param_name → list of values to try. Cartesian product
    expansion. e.g. {"fast": [10, 20], "slow": [50, 100]} → 4 combos.

    `progress_callback(current, total)` is called after each combo for UI updates.
    """
    strategy_cls = get_strategy(strategy_name)

    param_names = list(param_grid.keys())
    value_lists = [param_grid[k] for k in param_names]
    combos = list(product(*value_lists))
    total = len(combos)

    rows: list[dict] = []
    for i, combo in enumerate(combos):
        params = dict(zip(param_names, combo))
        row: dict = dict(params)

        try:
            strategy = strategy_cls(**params)
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
            row.update(result.summary_metrics)
            row["error"] = None
        except Exception as exc:
            row.update({k: None for k in _METRIC_KEYS})
            row["error"] = str(exc)

        rows.append(row)

        if progress_callback is not None:
            progress_callback(i + 1, total)

    df = pd.DataFrame(rows)
    return SweepResult(
        strategy_name=strategy_name,
        symbol=symbol,
        param_grid=param_grid,
        combos=df,
    )
