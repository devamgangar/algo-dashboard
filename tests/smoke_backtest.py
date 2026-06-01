"""End-to-end smoke test for the backtest engine.

Run from project root:
    python tests/smoke_backtest.py    (Linux/Mac)
    python tests\smoke_backtest.py    (Windows)

Pipeline exercised:
    yfinance → cache → get_ohlcv → SMACrossover → run_backtest → BacktestResult
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data import get_ohlcv  # noqa: E402
from core.engine import run_backtest  # noqa: E402
from core.strategies import get_strategy  # noqa: E402


def fmt_pct(x: float) -> str:
    return f"{x*100:+7.2f}%"


def main() -> None:
    print("=" * 72)
    print("Smoke test: backtest engine")
    print("=" * 72)

    today = date.today()
    start = today - timedelta(days=3 * 365)
    print(f"\n[1] Load OHLCV: RELIANCE.NS  {start} -> {today}")
    df = get_ohlcv("RELIANCE", start.isoformat(), today.isoformat())
    print(f"   bars: {len(df)}    range: {df.index.min().date()} -> {df.index.max().date()}")

    print("\n[2] Instantiate SMA Crossover with defaults (fast=20, slow=50)")
    SMACrossover = get_strategy("sma_crossover")
    strategy = SMACrossover()

    print("\n[3] Run backtest  (RFR = 6.5% per annum)")
    result = run_backtest(
        ohlcv=df,
        strategy=strategy,
        symbol="RELIANCE",
        exchange="NSE",
        interval="1d",
        data_source="yfinance",
        initial_capital=100_000.0,
        commission_bps=3.0,
        slippage_bps=5.0,
        risk_free_rate=0.065,
    )

    print("\n[4] Summary metrics")
    s = result.summary_metrics
    print(f"   Total return:  {fmt_pct(s['total_return'])}")
    print(f"   CAGR:          {fmt_pct(s['cagr'])}")
    print(f"   Sharpe:        {s['sharpe']:+7.3f}")
    print(f"   Sortino:       {s['sortino']:+7.3f}")
    print(f"   Max drawdown:  {fmt_pct(s['max_drawdown'])}")
    print(f"   Win rate:      {fmt_pct(s['win_rate'])}")
    print(f"   Num trades:    {s['num_trades']}")

    print("\n[5] Extended metrics")
    for k, v in result.extended_metrics.items():
        print(f"   {k:25s}  {v:.4f}")

    print(f"\n[6] Trades  ({len(result.trades)} rows)")
    if not result.trades.empty:
        print(result.trades.head(8).to_string())
        if len(result.trades) > 8:
            print("   ...")
            print(result.trades.tail(2).to_string())

    print(f"\n[7] Equity curve  ({len(result.equity_curve)} rows)")
    eq = result.equity_curve
    print(f"   First bar: equity = {eq['equity'].iloc[0]:,.2f}  cash = {eq['cash'].iloc[0]:,.2f}")
    print(f"   Last bar:  equity = {eq['equity'].iloc[-1]:,.2f}  cash = {eq['cash'].iloc[-1]:,.2f}")
    print(f"   Peak equity:  {eq['equity'].max():,.2f}")
    print(f"   Min equity:   {eq['equity'].min():,.2f}")
    print(f"   Max drawdown: {eq['drawdown_pct'].min():+.2f}%")

    print("\n[8] Sanity checks")
    assert len(eq) == len(df), (
        f"equity curve length {len(eq)} != ohlcv length {len(df)}"
    )
    assert abs(eq['equity'].iloc[0] - 100_000.0) < 1.0, (
        f"first equity {eq['equity'].iloc[0]} should be initial capital"
    )
    # BUY count must equal SELL count + 0 or 1 (1 if a position is still open at end)
    n_buy = int((result.trades['side'] == 'BUY').sum())
    n_sell = int((result.trades['side'] == 'SELL').sum())
    assert 0 <= n_buy - n_sell <= 1, (
        f"trade side imbalance: {n_buy} BUYs vs {n_sell} SELLs"
    )
    print(f"   trades: {n_buy} BUYs, {n_sell} SELLs (open positions: {n_buy - n_sell})")
    print("   All checks passed.")

    print("\nSmoke test passed.")


if __name__ == "__main__":
    main()
