"""End-to-end offline pipeline: fetch → sentiment → RAG build → predict → cache.

Run nightly from Windows Task Scheduler. Designed to be resilient: a failure on
one ticker logs and continues; subsequent stages skip tickers without prices.
"""
from __future__ import annotations
import logging
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .data_sources import fetch_prices_yahoo
from .file_store import save_prices, save_sentiment, prices_exist, BASE
from .sentiment import compute_sentiment_for_ticker
from .rag_build import build_rag_docs_for_ticker
from .rag_store import RAGStore
from .rag_predictor import RAGPredictor
from .prediction_store import save_prediction
from .db_cache import rebuild_cache
from .universe import load_universe


def _setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"daily_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("daily_job")


def stage_fetch_prices(tickers: List[str], days: int, log):
    log.info("STAGE 1/6: fetch prices (%d tickers)", len(tickers))
    ok = []
    for t in tickers:
        try:
            df = fetch_prices_yahoo(t, days=days)
            save_prices(t, df)
            ok.append(t)
        except Exception as e:
            log.warning("  fetch failed for %s: %s", t, e)
    log.info("  fetched: %d/%d", len(ok), len(tickers))
    return ok


def stage_sentiment(tickers: List[str], log):
    log.info("STAGE 2/6: sentiment (%d tickers)", len(tickers))
    for t in tickers:
        try:
            scores = compute_sentiment_for_ticker(t)
            save_sentiment(t, scores)
        except Exception as e:
            log.warning("  sentiment failed for %s: %s", t, e)


def stage_rag_build(tickers: List[str], log):
    log.info("STAGE 3/6: build RAG docs (%d tickers)", len(tickers))
    for t in tickers:
        if not prices_exist(t):
            continue
        try:
            build_rag_docs_for_ticker(t)
        except Exception as e:
            log.warning("  RAG docs failed for %s: %s", t, e)

    log.info("  building embeddings + FAISS index...")
    store = RAGStore()
    store.build_from_docs()
    return store


def stage_predict(tickers: List[str], store: RAGStore, horizon: int, log):
    log.info("STAGE 4/6: predict (%d tickers, horizon=%d)", len(tickers), horizon)
    predictor = RAGPredictor(store=store)
    n_saved = 0
    for t in tickers:
        if not prices_exist(t):
            continue
        try:
            pred = predictor.predict(t, horizon=horizon)
            save_prediction(pred.to_dict())
            n_saved += 1
        except Exception as e:
            log.warning("  predict failed for %s: %s", t, e)
            log.debug(traceback.format_exc())
    log.info("  saved predictions: %d", n_saved)


def stage_cache(tickers: List[str], log):
    log.info("STAGE 5/6: rebuild SQLite cache")
    present = [t for t in tickers if prices_exist(t)]
    if present:
        rebuild_cache(present)
        log.info("  cached %d tickers into %s", len(present), BASE.parent / "cache" / "stocks.db")


def _git(args, log, capture=True):
    """Run a git command; return (returncode, stdout, stderr). Never raises."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=capture,
            text=True,
            check=False,
        )
        return result.returncode, (result.stdout or ""), (result.stderr or "")
    except FileNotFoundError:
        log.warning("  git not found on PATH; skipping push")
        return 127, "", "git not found"


def stage_git_push(n_predictions: int, log):
    """Commit fresh data/ artifacts and push to origin, if a remote is configured."""
    log.info("STAGE 6/6: commit + push data/ artifacts")

    # Bail if we're not inside a git repo.
    rc, _, _ = _git(["rev-parse", "--is-inside-work-tree"], log)
    if rc != 0:
        log.info("  not a git repo; skipping push")
        return

    # Bail if no 'origin' remote.
    rc, remotes, _ = _git(["remote"], log)
    if "origin" not in remotes.split():
        log.info("  no 'origin' remote configured; skipping push")
        return

    # Stage data/ only.
    _git(["add", "data/"], log)

    # Anything to commit?
    rc, _, _ = _git(["diff", "--cached", "--quiet"], log)
    if rc == 0:
        log.info("  no changes in data/ to commit")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"data refresh {stamp} ({n_predictions} predictions)"
    rc, _, err = _git(["commit", "-m", msg], log)
    if rc != 0:
        log.warning("  commit failed: %s", err.strip())
        return

    rc, _, err = _git(["push"], log)
    if rc != 0:
        log.warning("  push failed: %s", err.strip())
        return
    log.info("  pushed: %s", msg)


def _count_predictions() -> int:
    pred_dir = BASE / "predictions"
    if not pred_dir.exists():
        return 0
    return len(list(pred_dir.glob("*.json")))


def run_daily(
    tickers: List[str] | None = None,
    horizon: int = 5,
    days: int = 365,
    push: bool = True,
):
    log = _setup_logging()
    tickers = tickers or load_universe()
    log.info("=" * 60)
    log.info("Daily job starting (%d tickers, horizon=%dd, push=%s)", len(tickers), horizon, push)
    started = datetime.now()

    fetched = stage_fetch_prices(tickers, days=days, log=log)
    stage_sentiment(fetched, log=log)
    store = stage_rag_build(fetched, log=log)
    stage_predict(fetched, store=store, horizon=horizon, log=log)
    stage_cache(tickers, log=log)
    if push:
        stage_git_push(_count_predictions(), log=log)

    elapsed = (datetime.now() - started).total_seconds()
    log.info("Daily job complete in %.1fs", elapsed)


if __name__ == "__main__":
    run_daily()
