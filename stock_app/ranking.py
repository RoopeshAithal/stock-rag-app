import sqlite3
from pathlib import Path
import pandas as pd

CACHE_DB = Path("cache/stocks.db")


def top_gainers(n: int = 20) -> pd.DataFrame:
    if not CACHE_DB.exists():
        raise FileNotFoundError("Cache DB not found. Run cache rebuild first.")
    conn = sqlite3.connect(CACHE_DB)
    df = pd.read_sql_query(
        """
        SELECT ticker,
               AVG(ret_1d) AS avg_ret_1d
        FROM prices
        GROUP BY ticker
        ORDER BY avg_ret_1d DESC
        LIMIT ?
        """,
        conn,
        params=(n,),
    )
    conn.close()
    return df
