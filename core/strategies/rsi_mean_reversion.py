"""RSI Mean Reversion — buy oversold, exit on overbought.

Long-only mean-reversion. Assumes extreme RSI readings will revert toward 50.
Uses Wilder's smoothing (EMA with alpha=1/period), the standard formulation.
"""
from __future__ import annotations

import pandas as pd

from core.strategies.base import BaseStrategy
from core.strategies.registry import register_strategy


@register_strategy
class RSIMeanReversion(BaseStrategy):
    name = "rsi_mean_reversion"
    display_name = "RSI Mean Reversion"
    version = "1.0.0"
    description = (
        "Enter long when RSI crosses below the oversold threshold (default 30). "
        "Exit when RSI crosses above the overbought threshold (default 70). "
        "Long-only mean-reversion using Wilder-smoothed RSI."
    )
    default_params = {"period": 14, "oversold": 30, "overbought": 70}
    sizing = {"type": "percent", "value": 0.95}

    def generate_signals(
        self, ohlcv: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        period = int(self.params["period"])
        oversold = float(self.params["oversold"])
        overbought = float(self.params["overbought"])

        if period < 2:
            raise ValueError("RSI period must be >= 2")
        if not (0.0 < oversold < overbought < 100.0):
            raise ValueError(
                f"thresholds must satisfy 0 < oversold ({oversold}) "
                f"< overbought ({overbought}) < 100"
            )

        close = ohlcv["close"]
        delta = close.diff()
        gains = delta.clip(lower=0.0)
        losses = -delta.clip(upper=0.0)

        # Wilder smoothing (EMA with alpha = 1/period). This is the canonical
        # RSI; using a simple rolling mean gives slightly different values.
        avg_gain = gains.ewm(alpha=1.0 / period, adjust=False).mean()
        avg_loss = losses.ewm(alpha=1.0 / period, adjust=False).mean()

        # Avoid division-by-zero when there were no losses in the window.
        rs = avg_gain / avg_loss.replace(0.0, pd.NA)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        below = (rsi < oversold).fillna(False).astype(bool)
        below_prev = below.shift(1, fill_value=False)

        above = (rsi > overbought).fillna(False).astype(bool)
        above_prev = above.shift(1, fill_value=False)

        # Suppress signals until RSI has had at least `period` bars to stabilize.
        warmup_done = pd.Series(False, index=close.index)
        warmup_done.iloc[period:] = True

        entries = (warmup_done & ~below_prev & below).astype(bool)
        exits = (warmup_done & ~above_prev & above).astype(bool)

        return entries, exits
