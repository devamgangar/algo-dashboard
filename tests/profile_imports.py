"""One-shot import profiler.

Run from project root:
    python tests/profile_imports.py    (Linux/Mac)
    python tests\profile_imports.py    (Windows)

Times each of our heavy imports individually so we know which one is the
cold-load bottleneck on the network share.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to sys.path so our own modules import cleanly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

t_total = time.perf_counter()
results: list[tuple[str, float]] = []


def _time(label: str, fn) -> None:
    t = time.perf_counter()
    fn()
    dt = time.perf_counter() - t
    results.append((label, dt))
    print(f"  {label:35s}  {dt:6.2f}s")


print("\nProfiling cold imports (each ran for the first time in this process):")
print("-" * 60)

_time("streamlit",            lambda: __import__("streamlit"))
_time("pandas",               lambda: __import__("pandas"))
_time("numpy",                lambda: __import__("numpy"))
_time("pyarrow",              lambda: __import__("pyarrow"))
_time("yfinance",             lambda: __import__("yfinance"))
_time("sqlalchemy",           lambda: __import__("sqlalchemy"))
_time("plotly.graph_objects", lambda: __import__("plotly.graph_objects"))
_time("vectorbt",             lambda: __import__("vectorbt"))

print("\nProfiling our own modules:")
print("-" * 60)
_time("core.data",         lambda: __import__("core.data"))
_time("core.strategies",   lambda: __import__("core.strategies"))
_time("core.engine",       lambda: __import__("core.engine"))
_time("core.analytics.plots",
                           lambda: __import__("core.analytics.plots", fromlist=["*"]))
_time("db.repository",     lambda: __import__("db.repository", fromlist=["*"]))
_time("services.backtest_service",
                           lambda: __import__("services.backtest_service", fromlist=["*"]))

print("-" * 60)
print(f"  {'TOTAL':35s}  {time.perf_counter() - t_total:6.2f}s")

# Sort and highlight worst offenders
results.sort(key=lambda x: -x[1])
print("\nTop 3 worst offenders:")
for name, dt in results[:3]:
    print(f"  {name}: {dt:.2f}s")
