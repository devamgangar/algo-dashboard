"""Abstract base class for all backtesting strategies.

A strategy declares its identity (name, version, defaults, sizing) as class
attributes, and implements one method — `generate_signals` — that takes an
OHLCV DataFrame and returns two boolean Series: entries and exits.

Strategies do NOT know about the backtesting engine, the cache, or the DB.
They only know prices in, signals out. This keeps them portable and testable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    # Class-level metadata. Subclasses MUST override `name`, `display_name`,
    # `default_params`, and `description`.
    name: str = ""
    display_name: str = ""
    version: str = "1.0.0"
    description: str = ""
    default_params: dict = {}
    sizing: dict = {"type": "percent", "value": 0.95}

    def __init__(self, **params) -> None:
        if not self.name:
            raise ValueError(
                f"{type(self).__name__} must define a class-level `name`"
            )

        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(
                f"Unknown params for {self.name}: {sorted(unknown)}. "
                f"Valid: {sorted(self.default_params)}"
            )

        self.params = {**self.default_params, **params}

    @abstractmethod
    def generate_signals(
        self, ohlcv: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """Return (entries, exits) — boolean Series indexed like ohlcv.

        entries[t] == True  → strategy says "open a long position at bar t"
        exits[t]   == True  → strategy says "close any open position at bar t"

        Both Series MUST have the same index as ohlcv. Entry and exit on the
        same bar is treated as a no-op by the engine.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__} params={self.params}>"
