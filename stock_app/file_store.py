import json
import pandas as pd
from pathlib import Path

BASE = Path("data")


def save_prices(ticker: str, df: pd.DataFrame):
    path = BASE / "prices" / f"{ticker}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_prices(ticker: str) -> pd.DataFrame:
    path = BASE / "prices" / f"{ticker}.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.sort_values("date")
    return df


def prices_exist(ticker: str) -> bool:
    return (BASE / "prices" / f"{ticker}.csv").exists()


def save_sentiment(ticker: str, scores: dict):
    path = BASE / "sentiment" / f"{ticker}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(scores, f, indent=2)


def load_sentiment(ticker: str) -> dict:
    path = BASE / "sentiment" / f"{ticker}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_rag_doc(ticker: str, doc_id: int, text: str):
    path = BASE / "rag_docs" / ticker / f"doc_{doc_id:04d}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def save_rag_meta(ticker: str, meta: list):
    path = BASE / "rag_meta" / f"{ticker}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, default=str))


def load_rag_meta(ticker: str) -> list:
    path = BASE / "rag_meta" / f"{ticker}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def iter_rag_docs():
    docs_dir = BASE / "rag_docs"
    if not docs_dir.exists():
        return
    for ticker_dir in sorted(docs_dir.iterdir()):
        if not ticker_dir.is_dir():
            continue
        for doc_file in sorted(ticker_dir.glob("*.txt")):
            yield ticker_dir.name, doc_file
