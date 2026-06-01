"""Backtest engine: vectorbt-based wrapper that produces standardized BacktestResult."""
from core.engine.backtest import BacktestResult, run_backtest

__all__ = ["BacktestResult", "run_backtest"]
