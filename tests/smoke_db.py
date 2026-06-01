"""End-to-end smoke test for the DB persistence layer.

Run from project root:
    python tests/smoke_db.py    (Linux/Mac)
    python tests\smoke_db.py    (Windows)

Exercises the full pipeline:
    yfinance -> cache -> get_ohlcv -> SMACrossover -> run_backtest
        -> repository.save_result -> SQLite -> repository.get_run -> verify
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data import get_ohlcv  # noqa: E402
from core.engine import run_backtest  # noqa: E402
from core.strategies import get_strategy  # noqa: E402
from db import repository as repo  # noqa: E402
from db.session import get_session  # noqa: E402
from db.models import Strategy as StrategyModel  # noqa: E402
from sqlalchemy import select  # noqa: E402


def fmt_pct(x):
    return f"{x*100:+7.2f}%" if x is not None else "    n/a"


def main() -> None:
    print("=" * 72)
    print("Smoke test: DB persistence (step 5)")
    print("=" * 72)

    today = date.today()
    start = today - timedelta(days=2 * 365)
    print(f"\n[1] Load data + run backtest: RELIANCE  {start} -> {today}")
    df = get_ohlcv("RELIANCE", start.isoformat(), today.isoformat())
    SMA = get_strategy("sma_crossover")
    result = run_backtest(df, SMA(), symbol="RELIANCE")
    print(f"   trades: {len(result.trades)}   metrics: {len(result.summary_metrics) + len(result.extended_metrics)}")

    print("\n[2] Save to DB")
    run_id = repo.save_result(result)
    print(f"   run_id = {run_id}")

    print("\n[3] List recent runs")
    runs = repo.list_runs(limit=5)
    for r in runs:
        print(
            f"   #{r['id']:<3}  {r['strategy']:<15s}  {r['symbol']:<10s}  "
            f"return={fmt_pct(r['total_return'])}  sharpe={r['sharpe']:+.3f}  "
            f"trades={r['num_trades']}"
        )

    print(f"\n[4] Read back run #{run_id}")
    loaded = repo.get_run(run_id)
    assert loaded is not None, "get_run returned None"
    print(f"   strategy:           {loaded['strategy_name']} v{loaded['strategy_version']}")
    print(f"   symbol/exchange:    {loaded['symbol']}/{loaded['exchange']}")
    print(f"   date range:         {loaded['start_date']} -> {loaded['end_date']}")
    print(f"   params:             {loaded['params']}")
    print(f"   trades rows:        {len(loaded['trades'])}    (expected {len(result.trades)})")
    print(f"   equity rows:        {len(loaded['equity_curve'])}    (expected {len(result.equity_curve)})")
    print(f"   summary metrics:    {len(loaded['summary_metrics'])}")
    print(f"   extended metrics:   {len(loaded['extended_metrics'])}")

    print("\n[5] Integrity checks")
    assert len(loaded["trades"]) == len(result.trades), "trade count mismatch"
    assert len(loaded["equity_curve"]) == len(result.equity_curve), "equity row mismatch"
    assert set(loaded["extended_metrics"]) == set(result.extended_metrics), "metric keys mismatch"
    # spot check: first equity value should be initial capital
    first_equity = float(loaded["equity_curve"]["equity"].iloc[0])
    assert abs(first_equity - 100_000.0) < 1.0, f"first equity {first_equity} ≠ initial capital"
    print("   trade rows, equity rows, metric keys all match in-memory result.")
    print(f"   first equity row equals initial capital ({first_equity:,.2f}).")

    print("\n[6] Re-save (verify strategy is upserted, not duplicated)")
    run_id_2 = repo.save_result(result)
    assert run_id_2 != run_id, "second save should create a new run row"
    print(f"   second run_id = {run_id_2} (different from {run_id} ✓)")

    with get_session() as session:
        sma_count = session.execute(
            select(StrategyModel).where(StrategyModel.name == "sma_crossover")
        ).scalars().all()
    assert len(sma_count) == 1, f"expected 1 sma_crossover strategy row, got {len(sma_count)}"
    print(f"   strategies table has 1 sma_crossover row ✓")

    print("\n[7] Strategies in DB")
    for s in repo.list_registered_strategies():
        print(
            f"   #{s['id']}  {s['name']} v{s['version']}  "
            f"hash={s['code_hash_short']}...  defaults={s['default_params']}"
        )

    print("\n[8] Delete the second run (cascade should clean up trades / equity / metrics)")
    deleted = repo.delete_run(run_id_2)
    assert deleted, "delete_run returned False"
    print(f"   deleted run #{run_id_2}")
    after = repo.list_runs(limit=5)
    assert all(r["id"] != run_id_2 for r in after), "deleted run still appears in list"
    print(f"   list_runs no longer contains #{run_id_2} ✓")

    print("\nSmoke test passed.")


if __name__ == "__main__":
    main()
