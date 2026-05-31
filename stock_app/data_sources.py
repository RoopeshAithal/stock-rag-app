import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


def fetch_prices_yahoo(ticker: str, days: int = 365) -> pd.DataFrame:
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    df = yf.download(
        ticker,
        start=start,
        end=end,
        progress=False,
        auto_adjust=True,
        group_by="column",
    )
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    # Recent yfinance versions return a MultiIndex like (field, ticker).
    # Flatten by taking the first level (field name) so "Close" stays "Close".
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index().rename(columns={"Date": "date", "Close": "close"})
    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    df["ret_1d"] = df["close"].pct_change()
    return df
