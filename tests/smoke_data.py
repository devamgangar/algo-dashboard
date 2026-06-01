"""Smoke test for the data layer.

Run from project root:
    python tests/smoke_data.py    (Linux/Mac)
    python tests\smoke_data.py    (Windows)

Demonstrates three cache behaviors in sequence:
  [1] First fetch  → API call, cache created
  [2] Same request → cache hit, NO API call
  [3] Extended end → partial fetch of just the missing tail
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

# Allow running this script directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data import get_ohlcv  # noqa: E402

CACHE_FILE = (
    Path(__file__).resolve().parent.parent
    / "data" / "cache" / "NSE_RELIANCE_1d.parquet"
)


def main() -> None:
    today = date.today()
    end_past = today - timedelta(days=14)        # safely closed bars
    start = end_past - timedelta(days=365)

    print("=" * 64)
    print("Smoke test: data layer")
    print("=" * 64)

    print(f"\n[1] Initial fetch: {start} -> {end_past}   (expect API call)")
    df1 = get_ohlcv(symbol="RELIANCE", start=start.isoformat(), end=end_past.isoformat())
    print(f"  Shape:        {df1.shape}")
    print(f"  Columns:      {list(df1.columns)}")
    print(f"  Date range:   {df1.index.min().date()} -> {df1.index.max().date()}")
    print(f"  Cache file:   {CACHE_FILE.exists()}, {CACHE_FILE.stat().st_size:,} bytes")
    print(f"  Any NaN:      {bool(df1.isna().any().any())}")

    print(f"\n[2] Same request                            (expect CACHE HIT, no API call)")
    df2 = get_ohlcv(symbol="RELIANCE", start=start.isoformat(), end=end_past.isoformat())
    print(f"  Shape:        {df2.shape}")
    print(f"  Equal to [1]: {df1.equals(df2)}")

    print(f"\n[3] Extend end to today: {start} -> {today}   (expect PARTIAL fetch of tail only)")
    df3 = get_ohlcv(symbol="RELIANCE", start=start.isoformat(), end=today.isoformat())
    print(f"  Shape:        {df3.shape}")
    print(f"  Date range:   {df3.index.min().date()} -> {df3.index.max().date()}")
    print(f"  Any NaN:      {bool(df3.isna().any().any())}")

    print("\n[4] Sample rows from final dataset:")
    print(df3.head(3).to_string())
    print("    ...")
    print(df3.tail(3).to_string())

    print("\nSmoke test complete.")


if __name__ == "__main__":
    main()
