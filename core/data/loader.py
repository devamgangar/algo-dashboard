"""Public data loading API with parquet caching.

Caller-facing entry point is `get_ohlcv()`. Internally:
  1. Look up a cache file at data/cache/<EXCHANGE>_<SYMBOL>_<INTERVAL>.parquet
  2. Decide what (if anything) is missing vs the requested range
  3. Fetch the missing portion from the chosen source
  4. Merge, dedupe, persist, return the requested slice
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.data.sources import fetch_yfinance

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"

_SOURCES = {
    "yfinance": fetch_yfinance,
}


def _cache_path(symbol: str, exchange: str, interval: str) -> Path:
    fname = f"{exchange.upper()}_{symbol.upper()}_{interval}.parquet"
    return CACHE_DIR / fname


def _load_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.index.name = "timestamp"
    return df


def _save_cache(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _to_naive_timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value).normalize()
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    return ts


def _determine_fetch_range(
    cached: pd.DataFrame,
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Pick what to fetch given current cache state.

    Strategy (deliberately simple for v1):
      - empty cache              → fetch full requested range
      - request extends past end → fetch (cache_end+1, requested_end)
      - request starts before cache start → fetch full requested range
      - cache's last bar is today → refetch today (it may still be updating)
      - otherwise                → no fetch
    """
    if cached.empty:
        return requested_start, requested_end

    cache_start = pd.Timestamp(cached.index.min()).normalize()
    cache_end = pd.Timestamp(cached.index.max()).normalize()
    today = pd.Timestamp.today().normalize()

    if requested_start < cache_start:
        return requested_start, requested_end

    if requested_end > cache_end:
        return cache_end + pd.Timedelta(days=1), requested_end

    if cache_end >= today and requested_end >= today:
        return today, today

    return None, None


def get_ohlcv(
    symbol: str,
    start,
    end,
    interval: str = "1d",
    exchange: str = "NSE",
    source: str = "yfinance",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return OHLCV for a symbol, hitting the on-disk parquet cache first.

    Args:
        symbol: e.g. "RELIANCE" (no .NS suffix — the source adapter adds it).
        start: ISO date string or pd.Timestamp (inclusive).
        end: ISO date string or pd.Timestamp (inclusive).
        interval: "1d", "1h", "30m", "15m", "5m", "1m".
        exchange: "NSE" or "BSE".
        source: "yfinance" (Groww coming later).
        force_refresh: bypass cache, re-fetch everything.

    Returns:
        DataFrame indexed by tz-naive 'timestamp', columns
        [open, high, low, close, volume]. OHLC adjusted for corp actions.
    """
    if source not in _SOURCES:
        raise ValueError(
            f"Unknown source: {source!r}. Options: {list(_SOURCES)}"
        )

    requested_start = _to_naive_timestamp(start)
    requested_end = _to_naive_timestamp(end)
    if requested_end < requested_start:
        raise ValueError(f"end {end!r} is before start {start!r}")

    path = _cache_path(symbol, exchange, interval)
    cached = pd.DataFrame() if force_refresh else _load_cache(path)

    fetch_start, fetch_end = _determine_fetch_range(
        cached, requested_start, requested_end
    )

    if fetch_start is not None:
        print(
            f"[data] Fetching {symbol} ({exchange}) "
            f"{fetch_start.date()} -> {fetch_end.date()} from {source}"
        )
        new_data = _SOURCES[source](
            symbol, exchange, fetch_start, fetch_end, interval
        )
        if new_data.empty:
            print("[data] No new bars in fetched range (weekend/holiday/today-before-close).")
        else:
            merged = pd.concat([cached, new_data]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
            _save_cache(path, merged)
            cached = merged
    else:
        print(
            f"[data] Cache hit: {symbol} ({exchange}) "
            f"{requested_start.date()} -> {requested_end.date()}"
        )

    return cached.loc[requested_start:requested_end].copy()
