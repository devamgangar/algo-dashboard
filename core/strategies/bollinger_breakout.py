"""Bollinger Band Breakout — buy when close breaks above upper band.

Long-only trend-following. Assumes price breaking above the upper Bollinger
band signals a new bullish leg; exits when price reverts below the middle SMA.
"""
from __future__ import annotations

import pandas as pd

from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy


@register_strategy
class BollingerBreakout(BaseStrategy):
    name = "bollinger_breakout"
    display_name = "Bollinger Breakout"
    version = "1.0.0"
    description = (
        "Enter long when close crosses above the upper Bollinger Band. "
        "Exit when close crosses back below the middle band (SMA). "
        "Long-only volatility-based trend-following."
    )
    default_params = {"period": 20, "num_std": 2.0}
    sizing = {"type": "percent", "value": 0.95}

    def generate_signals(
        self, ohlcv: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        period = int(self.params["period"])
        num_std = float(self.params["num_std"])

        if period < 2:
            raise ValueError("Bollinger period must be >= 2")
        if num_std <= 0:
            raise ValueError(f"num_std must be > 0 (got {num_std})")

        close = ohlcv["close"]
        middle = close.rolling(period, min_periods=period).mean()
        std = close.rolling(period, min_periods=period).std()
        upper = middle + num_std * std

        above_upper = (close > upper).astype(bool)
        above_upper_prev = above_upper.shift(1, fill_value=False)

        below_middle = (close < middle).astype(bool)
        below_middle_prev = below_middle.shift(1, fill_value=False)

        # Suppress signals during warmup — middle is NaN for first period-1 bars.
        valid_prev = middle.shift(1).notna()

        entries = (valid_prev & ~above_upper_prev & above_upper).astype(bool)
        exits = (valid_prev & ~below_middle_prev & below_middle).astype(bool)

        return entries, exits
