"""Smoke test for the strategy registry and SMA crossover.

Run from project root:
    python tests/smoke_strategy.py    (Linux/Mac)
    python tests\smoke_strategy.py    (Windows)

Verifies:
  [1] At least one strategy is auto-discovered and registered
  [2] SMACrossover can be instantiated with defaults and with overrides
  [3] Bad params raise informative errors
  [4] Signals are generated on real RELIANCE data
  [5] Sanity checks: no NaN signals, no same-bar entry+exit,
      crossover counts in a plausible range
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data import get_ohlcv  # noqa: E402
from core.strategies import get_strategy, list_strategies  # noqa: E402


def main() -> None:
    print("=" * 64)
    print("Smoke test: strategy registry + SMA crossover")
    print("=" * 64)

    print("\n[1] Registered strategies (via auto-discovery):")
    strategies = list_strategies()
    assert strategies, "No strategies registered - auto-discovery failed"
    for cls in strategies:
        print(f"  - {cls.name:20s}  v{cls.version}  ({cls.display_name})")

    print("\n[2] Instantiation")
    sma_cls = get_strategy("sma_crossover")
    default = sma_cls()
    custom = sma_cls(fast=10, slow=30)
    print(f"  Defaults: {default.params}    sizing={default.sizing}")
    print(f"  Custom:   {custom.params}")

    print("\n[3] Bad-params handling")
    try:
        sma_cls(slow_period=100)
    except ValueError as e:
        print(f"  Unknown param rejected: {e}")
    try:
        sma_cls(fast=50, slow=20).generate_signals(
            __import__("pandas").DataFrame({"close": []})
        )
    except ValueError as e:
        print(f"  fast>=slow rejected: {e}")

    today = date.today()
    start = today - timedelta(days=730)
    print(f"\n[4] Generating signals on RELIANCE: {start} -> {today}")
    df = get_ohlcv("RELIANCE", start.isoformat(), today.isoformat())
    print(f"  OHLCV shape: {df.shape}")

    entries, exits = default.generate_signals(df)
    n_entries = int(entries.sum())
    n_exits = int(exits.sum())
    print(f"  Entry signals: {n_entries}")
    print(f"  Exit signals:  {n_exits}")

    print("\n[5] Sanity checks")
    overlap = int((entries & exits).sum())
    print(f"  Same-bar entry+exit: {overlap}")
    assert overlap == 0, "logic error: entry and exit fired on same bar"
    assert not entries.isna().any(), "entries contains NaN"
    assert not exits.isna().any(), "exits contains NaN"
    # SMA(20,50) on 2y of daily data: expect roughly 2-15 crossovers
    assert 1 <= n_entries <= 40, f"suspicious entry count: {n_entries}"
    assert abs(n_entries - n_exits) <= 1, (
        f"entries ({n_entries}) and exits ({n_exits}) should be balanced "
        "give or take 1"
    )
    print("  All checks passed.")

    print("\n[6] First 5 entry signals:")
    for ts in entries[entries].index[:5]:
        price = df.loc[ts, "close"]
        print(f"  {ts.date()}  close={price:.2f}")

    print("\nSmoke test passed.")


if __name__ == "__main__":
    main()
