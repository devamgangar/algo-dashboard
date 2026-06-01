"""SMA Crossover — go long when fast SMA crosses above slow SMA, exit on the reverse.

Long-only. Position sizing handled at the engine level (95% of cash by default).
"""
from __future__ import annotations

import pandas as pd

from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy


@register_strategy
class SMACrossover(BaseStrategy):
    name = "sma_crossover"
    display_name = "SMA Crossover"
    version = "1.0.0"
    description = (
        "Long when the fast simple moving average crosses above the slow SMA. "
        "Exit when it crosses back below. Long-only, no shorts, no stop loss."
    )
    default_params = {"fast": 20, "slow": 50}
    sizing = {"type": "percent", "value": 0.95}

    def generate_signals(
        self, ohlcv: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        fast_window = int(self.params["fast"])
        slow_window = int(self.params["slow"])

        if fast_window <= 0 or slow_window <= 0:
            raise ValueError("SMA windows must be positive")
        if fast_window >= slow_window:
            raise ValueError(
                f"fast ({fast_window}) must be < slow ({slow_window})"
            )

        close = ohlcv["close"]
        fast = close.rolling(window=fast_window, min_periods=fast_window).mean()
        slow = close.rolling(window=slow_window, min_periods=slow_window).mean()

        # `fast > slow` returns False where either is NaN (numpy semantics).
        above = (fast > slow).astype(bool)
        above_prev = above.shift(1, fill_value=False)

        # Suppress signals during the warmup window: only fire if the slow MA
        # had a real value on the prior bar (so a "cross" is meaningful, not
        # just an artifact of the NaN → number transition).
        slow_prev_valid = slow.shift(1).notna()

        entries = (slow_prev_valid & (~above_prev) & above).astype(bool)
        exits = (slow_prev_valid & above_prev & (~above)).astype(bool)

        return entries, exits
