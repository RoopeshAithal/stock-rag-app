import typer
from rich import print
from rich.table import Table
from typing import List, Optional

from .data_sources import fetch_prices_yahoo
from .file_store import save_prices, save_sentiment
from .sentiment import compute_sentiment_for_ticker
from .rag_build import build_rag_docs_for_ticker
from .rag_store import RAGStore
from .db_cache import rebuild_cache
from .rag_predictor import RAGPredictor
from .ranking import top_gainers
from .universe import load_universe
from .daily_job import run_daily
from .prediction_store import predictions_dataframe

app = typer.Typer(help="Hybrid Stock-RAG App")


@app.command()
def update(tickers: List[str] = typer.Argument(...)):
    """Fetch prices and save CSVs."""
    for t in tickers:
        print(f"[bold cyan]Fetching prices for {t}[/bold cyan]")
        df = fetch_prices_yahoo(t)
        save_prices(t, df)
    print("[green]Done.[/green]")


@app.command()
def news(tickers: List[str] = typer.Argument(...)):
    """Compute sentiment and save JSON."""
    for t in tickers:
        print(f"[bold cyan]Computing sentiment for {t}[/bold cyan]")
        scores = compute_sentiment_for_ticker(t)
        save_sentiment(t, scores)
    print("[green]Done.[/green]")


@app.command("rag-build")
def rag_build_cmd(tickers: List[str] = typer.Argument(...)):
    """Build RAG docs, embeddings, and FAISS index."""
    for t in tickers:
        print(f"[bold cyan]Building RAG docs for {t}[/bold cyan]")
        build_rag_docs_for_ticker(t)

    print("[bold cyan]Building embeddings + FAISS index[/bold cyan]")
    store = RAGStore()
    store.build_from_docs()
    print("[green]Done.[/green]")


@app.command("cache")
def cache_cmd(tickers: List[str] = typer.Argument(...)):
    """Rebuild local SQLite cache from CSVs."""
    print("[bold cyan]Rebuilding cache[/bold cyan]")
    rebuild_cache(tickers)
    print("[green]Done.[/green]")


@app.command("rag-predict")
def rag_predict_cmd(
    ticker: str = typer.Argument(...),
    horizon: int = typer.Option(5, help="Horizon in days"),
):
    """RAG-based numeric prediction for a single ticker."""
    predictor = RAGPredictor()
    pred = predictor.predict(ticker, horizon=horizon)
    print(pred.to_dict())


@app.command("top")
def top_cmd(n: int = typer.Option(20, help="Number of tickers")):
    """Show top N tickers by avg 1D return (from cache)."""
    df = top_gainers(n)
    print(df)


@app.command("daily")
def daily_cmd(
    horizon: int = typer.Option(5, help="Prediction horizon in days"),
    days: int = typer.Option(365, help="History window in days"),
    tickers: Optional[List[str]] = typer.Option(
        None, help="Override universe; defaults to S&P 100"
    ),
    push: bool = typer.Option(
        True, "--push/--no-push", help="Commit + push data/ to origin at the end"
    ),
):
    """Run the full nightly pipeline: fetch → sentiment → RAG → predict → cache → push."""
    run_daily(tickers=tickers, horizon=horizon, days=days, push=push)


@app.command("universe")
def universe_cmd():
    """Print the active universe (S&P 100 unless overridden)."""
    tickers = load_universe()
    print(f"[bold]Universe size:[/bold] {len(tickers)}")
    print(", ".join(tickers))


@app.command("predictions")
def predictions_cmd(
    n: int = typer.Option(20, help="Number of top rows to show"),
    direction: Optional[str] = typer.Option(
        None, help="Filter by direction: up/down/neutral"
    ),
):
    """Show the latest pre-computed predictions, sorted by score."""
    df = predictions_dataframe()
    if df.empty:
        print("[yellow]No predictions yet. Run `daily` first.[/yellow]")
        return
    if direction:
        df = df[df["direction"] == direction]

    table = Table(title=f"Top {n} predictions")
    for col in ["ticker", "direction", "score", "expected_return", "confidence", "as_of"]:
        table.add_column(col)
    for _, row in df.head(n).iterrows():
        table.add_row(
            str(row["ticker"]),
            str(row["direction"]),
            f"{row['score']:+.3f}",
            f"{row['expected_return']:+.2%}",
            f"{row['confidence']:.2f}",
            str(row["as_of"]),
        )
    print(table)


if __name__ == "__main__":
    app()
