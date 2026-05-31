import sqlite3
import pandas as pd
from pathlib import Path
from .file_store import BASE

CACHE_DB = Path("cache/stocks.db")


def rebuild_cache(tickers):
    CACHE_DB.parent.mkdir(exist_ok=True)
    if CACHE_DB.exists():
        CACHE_DB.unlink()

    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE prices (
            ticker TEXT,
            date TEXT,
            close REAL,
            ret_1d REAL
        )
        """
    )

    for t in tickers:
        path = BASE / "prices" / f"{t}.csv"
        df = pd.read_csv(path)
        df["ticker"] = t
        df.to_sql("prices", conn, if_exists="append", index=False)

    conn.commit()
    conn.close()
