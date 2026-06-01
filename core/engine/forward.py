"""Forward testing engine.

A forward run is "a backtest with a moving end date." Each tick re-runs the
backtest from the run's start_date to today, and replaces the stored trades +
equity_curve. This makes the state atomic and free of drift bugs — there's no
'state to update'; only state to recompute and replace.

The tradeoff: O(days) work per tick. For daily forward tests on a few years
of accumulated history, that's still <1s per run. If a run accumulates 10+
years of daily history, we'd want incremental ticking — defer that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class TickResult:
    """Outcome of ticking a single forward run."""
    forward_run_id: int
    status: str           # "updated", "no_new_bars", "error", "skipped"
    bars_processed: int
    last_processed_date: Optional[date]
    error_msg: Optional[str] = None
