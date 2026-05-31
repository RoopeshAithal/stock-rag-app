"""S&P 100 (OEX) ticker universe.

Snapshot of constituents. The list changes slowly (a few times per year), so
this is a static fallback. Override by writing a custom list to
`data/universe.txt` (one ticker per line) — `load_universe()` will prefer it.
"""
from pathlib import Path
from typing import List

SP100 = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK-B", "C",
    "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS",
    "CVX", "DE", "DHR", "DIS", "DUK", "EMR", "F", "FDX", "GD", "GE",
    "GILD", "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU",
    "ISRG", "JNJ", "JPM", "KHC", "KO", "LIN", "LLY", "LMT", "LOW", "MA",
    "MCD", "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT",
    "NEE", "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM", "PYPL",
    "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO", "TMUS",
    "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT",
]


def load_universe() -> List[str]:
    """Return user override at data/universe.txt if present, else S&P 100."""
    override = Path("data") / "universe.txt"
    if override.exists():
        tickers = [
            line.strip().upper()
            for line in override.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if tickers:
            return tickers
    return list(SP100)
