"""MACD Crossover — buy when MACD line crosses above signal line.

Long-only momentum strategy. MACD line is the difference between fast and
slow exponential moving averages; signal line is an EMA of the MACD line.
"""
from __future__ import annotations

import pandas as pd

from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy


@register_strategy
class MACDCrossover(BaseStrategy):
    name = "macd_crossover"
    display_name = "MACD Crossover"
    version = "1.0.0"
    description = (
        "MACD line = EMA(fast) − EMA(slow). Enter long when the MACD line crosses "
        "above the signal line (EMA of MACD). Exit on the reverse cross. "
        "Long-only momentum strategy."
    )
    default_params = {"fast": 12, "slow": 26, "signal": 9}
    sizing = {"type": "percent", "value": 0.95}

    def generate_signals(
        self, ohlcv: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        fast = int(self.params["fast"])
        slow = int(self.params["slow"])
        signal = int(self.params["signal"])

        if fast <= 0 or slow <= 0 or signal <= 0:
            raise ValueError("All EMA spans must be positive")
        if fast >= slow:
            raise ValueError(f"fast ({fast}) must be < slow ({slow})")

        close = ohlcv["close"]
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()

        above = (macd_line > signal_line).astype(bool)
        above_prev = above.shift(1, fill_value=False)

        # EMAs return values from bar 0 (initialized to the first close), so
        # there's no NaN to mask on. Instead use positional warmup: ignore
        # signals until both EMAs and the signal EMA have had time to stabilize.
        warmup_done = pd.Series(False, index=close.index)
        warmup_done.iloc[slow + signal:] = True

        entries = (warmup_done & ~above_prev & above).astype(bool)
        exits = (warmup_done & above_prev & ~above).astype(bool)

        return entries, exits
