"""Pre-defined symbol universes for portfolio backtests.

Currently only NIFTY 50. The list is hardcoded — it shifts ~quarterly when
NSE rebalances; update manually as needed. Stocks that fail to fetch (e.g.,
recently delisted) are silently skipped in the portfolio engine.
"""
from __future__ import annotations

NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BHARTIARTL", "BPCL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "LTIM", "M&M", "MARUTI", "NESTLEIND", "NTPC",
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "ULTRACEMCO", "UPL", "WIPRO",
]


UNIVERSES: dict[str, list[str]] = {
    "NIFTY 50": NIFTY_50,
}


def get_universe(name: str) -> list[str]:
    """Return the symbol list for a named universe."""
    if name not in UNIVERSES:
        raise ValueError(
            f"Unknown universe {name!r}. Available: {list(UNIVERSES)}"
        )
    return list(UNIVERSES[name])
