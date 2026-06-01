"""Strategy framework: base class, registry, and explicit strategy imports.

To register a new strategy:
  1. Create core/strategies/your_strategy.py with @register_strategy
  2. Add `from core.strategies import your_strategy` below

We use explicit imports rather than auto-discovery so the list of active
strategies is auditable from one place and there are no dynamic imports.
"""
from __future__ import annotations

from core.strategies.base import BaseStrategy
from core.strategies.registry import (
    get_strategy,
    list_strategies,
    register_strategy,
)

# --- Strategy modules. Importing each one triggers its @register_strategy. ---
from core.strategies import sma_crossover         # noqa: F401
from core.strategies import rsi_mean_reversion    # noqa: F401
from core.strategies import bollinger_breakout    # noqa: F401
from core.strategies import macd_crossover        # noqa: F401

__all__ = [
    "BaseStrategy",
    "register_strategy",
    "get_strategy",
    "list_strategies",
]
