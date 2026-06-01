"""Tick all active forward runs once. Designed for scheduled execution.

Register with Windows Task Scheduler to run daily (e.g., 4 PM IST after
market close). Exits with status code 0 even if some runs errored — the
errors are logged to forward_runs.error_msg in the DB and surfaced in the
Forward Testing tab.

Run manually:
    python scripts/forward_tick.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.forward_service import tick_all_active  # noqa: E402


def main() -> int:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] forward_tick: starting")

    results = tick_all_active()
    if not results:
        print(f"[{ts}] forward_tick: no active forward runs")
        return 0

    n_updated = sum(1 for r in results if r.status == "updated")
    n_nochange = sum(1 for r in results if r.status == "no_new_bars")
    n_error = sum(1 for r in results if r.status == "error")
    n_skipped = sum(1 for r in results if r.status == "skipped")

    for r in results:
        line = (
            f"  run #{r.forward_run_id}: {r.status}"
            f"  bars={r.bars_processed}"
        )
        if r.last_processed_date:
            line += f"  last={r.last_processed_date}"
        if r.error_msg:
            line += f"  err={r.error_msg}"
        print(line)

    print(
        f"[{ts}] forward_tick: done  "
        f"updated={n_updated}  no_new_bars={n_nochange}  "
        f"error={n_error}  skipped={n_skipped}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
