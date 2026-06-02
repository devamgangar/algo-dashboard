"""Inspect the SQLite backtest database.

Run: python db/inspect.py
Shows: table list with row counts, recent backtest runs, registered strategies.
"""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "backtest.db"

# Hardcoded count queries (no dynamic table-name interpolation = no SQL injection risk).
# Add a new line here when you add a new table to schema.sql.
TABLE_COUNT_QUERIES = {
    "backtest_runs":         "SELECT COUNT(*) FROM backtest_runs",
    "equity_curve":          "SELECT COUNT(*) FROM equity_curve",
    "forward_runs":          "SELECT COUNT(*) FROM forward_runs",
    "forward_trades":        "SELECT COUNT(*) FROM forward_trades",
    "forward_equity_curve":  "SELECT COUNT(*) FROM forward_equity_curve",
    "run_metrics":           "SELECT COUNT(*) FROM run_metrics",
    "portfolio_runs":        "SELECT COUNT(*) FROM portfolio_runs",
    "portfolio_trades":      "SELECT COUNT(*) FROM portfolio_trades",
    "portfolio_equity_curve":"SELECT COUNT(*) FROM portfolio_equity_curve",
    "strategies":            "SELECT COUNT(*) FROM strategies",
    "strategy_presets":      "SELECT COUNT(*) FROM strategy_presets",
    "trades":                "SELECT COUNT(*) FROM trades",
    "universe":              "SELECT COUNT(*) FROM universe",
}


def inspect() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run: python db/init_db.py")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        actual_tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name != 'sqlite_sequence'"
            ).fetchall()
        }

        print(f"\nDatabase: {DB_PATH}")
        print(f"Tables ({len(actual_tables)}):")
        print("-" * 50)

        for name, query in TABLE_COUNT_QUERIES.items():
            if name not in actual_tables:
                print(f"  {name:25s}  MISSING")
                continue
            count = conn.execute(query).fetchone()[0]
            print(f"  {name:25s}  {count:>6} rows")

        unknown = actual_tables - set(TABLE_COUNT_QUERIES.keys())
        for name in sorted(unknown):
            print(f"  {name:25s}  (in DB but not tracked in inspect.py)")

        strategies = conn.execute(
            "SELECT id, name, version, created_at FROM strategies ORDER BY id"
        ).fetchall()
        if strategies:
            print("\nRegistered strategies:")
            print("-" * 50)
            for s in strategies:
                print(f"  #{s['id']}  {s['name']} v{s['version']}  (added {s['created_at']})")
        else:
            print("\nNo strategies registered yet.")

        runs = conn.execute(
            "SELECT id, symbol, status, total_return, sharpe, num_trades, "
            "started_at FROM backtest_runs ORDER BY started_at DESC LIMIT 5"
        ).fetchall()
        if runs:
            print("\nRecent backtest runs (last 5):")
            print("-" * 50)
            print(
                f"  {'ID':>4}  {'Symbol':10s}  {'Status':10s}  "
                f"{'Return':>8}  {'Sharpe':>7}  {'Trades':>6}  Started"
            )
            for r in runs:
                ret = f"{r['total_return']:.2%}" if r['total_return'] is not None else "-"
                shp = f"{r['sharpe']:.2f}" if r['sharpe'] is not None else "-"
                trd = r['num_trades'] if r['num_trades'] is not None else "-"
                print(
                    f"  {r['id']:>4}  {r['symbol']:10s}  {r['status']:10s}  "
                    f"{ret:>8}  {shp:>7}  {trd:>6}  {r['started_at']}"
                )
        else:
            print("\nNo backtest runs yet.")


if __name__ == "__main__":
    inspect()
