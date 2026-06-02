"""Benchmark comparison — typically vs NIFTY 50 buy-and-hold.

Fetches the benchmark index price series, computes "what if we'd put
initial capital into the index instead," and produces relative-performance
metrics (alpha, beta, information ratio, tracking error).

Designed to be called at render time, NOT inside the engine — keeps the
engine pure and lets us add benchmark overlays to historical runs that
weren't computed against a benchmark originally.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from core.data import get_ohlcv


# NIFTYBEES is the largest NIFTY 50 ETF (NSE-listed, treated as a regular
# stock by yfinance — much more reliable than `^NSEI`, which yfinance handles
# inconsistently across versions). Tracking error vs the index is tiny
# (<0.5% annual), and what we care about is RELATIVE performance vs benchmark,
# so the ETF proxy is appropriate. ^NSEI is the formal fallback.
DEFAULT_BENCHMARK_SYMBOL = "NIFTYBEES"
DEFAULT_BENCHMARK_LABEL = "NIFTY 50 (via NIFTYBEES ETF)"
_BENCHMARK_FALLBACKS = ["^NSEI"]

_PERIODS_PER_YEAR = {
    "1d":  252,
    "1h":  252 * 6.25,
    "30m": 252 * 12.5,
    "15m": 252 * 25,
    "5m":  252 * 75,
    "1m":  252 * 375,
}


def fetch_benchmark(
    start, end,
    interval: str = "1d",
    symbol: str = DEFAULT_BENCHMARK_SYMBOL,
) -> Optional[pd.DataFrame]:
    """Fetch benchmark OHLCV. Returns None if all symbols fail.

    Tries the requested symbol first, then falls back to alternatives
    (NIFTYBEES ETF). Uses the same parquet cache as regular symbols.
    """
    candidates = [symbol] + [s for s in _BENCHMARK_FALLBACKS if s != symbol]
    for sym in candidates:
        try:
            df = get_ohlcv(
                symbol=sym,
                start=start,
                end=end,
                interval=interval,
                exchange="NSE",   # ignored for ^ symbols
            )
            if df is not None and not df.empty:
                return df
        except Exception:
            continue
    return None


def compute_benchmark_equity(
    benchmark_close: pd.Series,
    initial_capital: float,
) -> pd.Series:
    """Equity curve if `initial_capital` had been invested in the benchmark on day 1."""
    if benchmark_close.empty or benchmark_close.iloc[0] == 0:
        return pd.Series([], dtype=float)
    units = initial_capital / benchmark_close.iloc[0]
    return (units * benchmark_close).rename("benchmark_equity")


def compute_benchmark_metrics(
    strategy_equity: pd.Series,
    benchmark_equity: pd.Series,
    risk_free_rate: float,
    interval: str = "1d",
) -> dict:
    """Alpha, Beta, Information Ratio, Tracking Error vs benchmark.

    All metrics annualized using the bar frequency. Strategy and benchmark
    are aligned on their common timestamps before computation.
    """
    df = pd.DataFrame({
        "strategy":  strategy_equity,
        "benchmark": benchmark_equity,
    }).dropna()

    if len(df) < 5:
        return {
            "beta":                       None,
            "alpha_annualized":           None,
            "tracking_error_annualized":  None,
            "information_ratio":          None,
            "benchmark_total_return":     None,
            "benchmark_cagr":             None,
            "strategy_minus_benchmark":   None,
        }

    strat_rets = df["strategy"].pct_change().dropna()
    bench_rets = df["benchmark"].pct_change().dropna()

    aligned = pd.DataFrame({"s": strat_rets, "b": bench_rets}).dropna()
    if len(aligned) < 5:
        return {k: None for k in [
            "beta", "alpha_annualized", "tracking_error_annualized",
            "information_ratio", "benchmark_total_return",
            "benchmark_cagr", "strategy_minus_benchmark",
        ]}

    periods = _PERIODS_PER_YEAR.get(interval, 252)

    bench_var = aligned["b"].var()
    beta = float(aligned["s"].cov(aligned["b"]) / bench_var) if bench_var > 0 else 0.0

    # CAPM-style alpha, annualized
    mean_s_annual = float(aligned["s"].mean() * periods)
    mean_b_annual = float(aligned["b"].mean() * periods)
    alpha_annual = mean_s_annual - risk_free_rate - beta * (mean_b_annual - risk_free_rate)

    # Information ratio + tracking error (vs benchmark, not RFR)
    excess = aligned["s"] - aligned["b"]
    te_annual = float(excess.std() * np.sqrt(periods))
    ir = float((excess.mean() * periods) / te_annual) if te_annual > 0 else 0.0

    # Benchmark total return & CAGR over the visible window
    bench_total_return = float(df["benchmark"].iloc[-1] / df["benchmark"].iloc[0] - 1.0)
    span_years = (df.index[-1] - df.index[0]).days / 365.25 if len(df) >= 2 else 0
    bench_cagr = float((1 + bench_total_return) ** (1 / span_years) - 1) if span_years > 0 else 0.0

    strat_total_return = float(df["strategy"].iloc[-1] / df["strategy"].iloc[0] - 1.0)

    return {
        "beta":                       beta,
        "alpha_annualized":           alpha_annual,
        "tracking_error_annualized":  te_annual,
        "information_ratio":          ir,
        "benchmark_total_return":     bench_total_return,
        "benchmark_cagr":             bench_cagr,
        "strategy_minus_benchmark":   strat_total_return - bench_total_return,
    }


def attach_benchmark(
    equity_df: pd.DataFrame,
    initial_capital: float,
    start_date,
    end_date,
    risk_free_rate: float,
    interval: str = "1d",
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
) -> tuple[Optional[pd.Series], Optional[dict]]:
    """Convenience: fetch benchmark + compute its equity series + metrics.

    Returns (benchmark_equity_series, benchmark_metrics_dict). Both are None
    if fetch fails. Designed to be called inside a try/except by the UI;
    failures shouldn't break the page.

    `equity_df` is the run's equity_curve DataFrame (timestamp, equity, ...).
    """
    bench_df = fetch_benchmark(start_date, end_date, interval=interval, symbol=benchmark_symbol)
    if bench_df is None or bench_df.empty:
        return None, None

    # Build strategy equity Series indexed by timestamp
    eq = equity_df.copy()
    eq["timestamp"] = pd.to_datetime(eq["timestamp"])
    strat_series = eq.set_index("timestamp")["equity"]

    # Align benchmark to strategy's timestamps where possible
    bench_close = bench_df["close"]
    bench_equity = compute_benchmark_equity(bench_close, initial_capital)
    if bench_equity.empty:
        return None, None

    metrics = compute_benchmark_metrics(
        strategy_equity=strat_series,
        benchmark_equity=bench_equity,
        risk_free_rate=risk_free_rate,
        interval=interval,
    )
    return bench_equity, metrics
