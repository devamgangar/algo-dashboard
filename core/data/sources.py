"""Data source adapters.

Each public `fetch_*` function takes the same arguments and returns a
standardized OHLCV DataFrame:
  - DatetimeIndex named 'timestamp' (tz-naive, exchange-local time)
  - Columns: open, high, low, close, volume (lowercase, in that order)
  - OHLC adjusted for splits and dividends
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf


_YF_INTERVAL_MAP = {
    "1d":  "1d",
    "1h":  "1h",
    "30m": "30m",
    "15m": "15m",
    "5m":  "5m",
    "1m":  "1m",
}

_YF_EXCHANGE_SUFFIX = {
    "NSE": ".NS",
    "BSE": ".BO",
}


def _to_yfinance_symbol(symbol: str, exchange: str) -> str:
    suffix = _YF_EXCHANGE_SUFFIX.get(exchange.upper())
    if suffix is None:
        raise ValueError(
            f"Unsupported exchange for yfinance: {exchange!r}. "
            f"Supported: {list(_YF_EXCHANGE_SUFFIX)}"
        )
    return f"{symbol.upper()}{suffix}"


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Conform to our standard OHLCV schema and drop garbage rows."""
    df = df.rename(columns=str.lower)
    keep = ["open", "high", "low", "close", "volume"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise ValueError(f"Data source returned DataFrame missing columns: {missing}")
    df = df[keep].copy()

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "timestamp"

    return _clean_ohlcv(df)


def _clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows yfinance inserts on holidays/today-before-close.

    Filters two patterns:
      - NaN in any OHLC column (today's bar before market opens)
      - Zero volume + perfectly flat OHLC (carry-forward placeholder for holidays)
    """
    df = df.dropna(subset=["open", "high", "low", "close"])
    flat_ohlc = (
        (df["open"] == df["high"])
        & (df["high"] == df["low"])
        & (df["low"] == df["close"])
    )
    zero_vol = df["volume"] == 0
    df = df[~(flat_ohlc & zero_vol)]
    return df


def fetch_yfinance(
    symbol: str,
    exchange: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    interval: str,
) -> pd.DataFrame:
    """Fetch OHLCV from Yahoo Finance.

    Indian symbols are mapped to .NS (NSE) or .BO (BSE).
    Uses auto_adjust=True so OHLC values reflect split/dividend adjustments.
    """
    if interval not in _YF_INTERVAL_MAP:
        raise ValueError(
            f"Unsupported interval for yfinance: {interval!r}. "
            f"Supported: {list(_YF_INTERVAL_MAP)}"
        )

    yf_symbol = _to_yfinance_symbol(symbol, exchange)
    # yfinance treats `end` as exclusive for daily data — add a day so the
    # caller's requested end date is actually included.
    fetch_end = end + pd.Timedelta(days=1)

    ticker = yf.Ticker(yf_symbol)
    df = ticker.history(
        start=start.strftime("%Y-%m-%d"),
        end=fetch_end.strftime("%Y-%m-%d"),
        interval=_YF_INTERVAL_MAP[interval],
        auto_adjust=True,
        actions=False,
    )

    if df.empty:
        raise ValueError(
            f"yfinance returned no data for {yf_symbol} "
            f"between {start.date()} and {end.date()} ({interval})"
        )

    return _standardize(df)
