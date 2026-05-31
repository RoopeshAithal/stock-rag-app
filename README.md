# Hybrid Stock-RAG App

A local stock dashboard with a daily offline pipeline + Streamlit UI.

**Core idea**

- Git stores all durable data (CSV, JSON, TXT, NPY, FAISS index) under `data/`.
- SQLite (`cache/stocks.db`) is local-only and rebuilt anytime from those files.
- RAG uses file-based embeddings + FAISS.
- Predictions blend RAG (nearest historical regimes) + 20d momentum + sentiment into a numeric score.

## Layout

```
stock_rag_app/
  app.py                  # Streamlit UI (Dashboard / Portfolio / Detail / Run)
  stock_app/              # Python package
    cli.py                # typer CLI: update, news, rag-build, cache,
                          #            rag-predict, top, daily, universe, predictions
    data_sources.py       # yfinance fetch
    file_store.py         # all disk I/O
    sentiment.py          # placeholder news + TextBlob polarity
    rag_build.py          # sliding-window regime docs + forward-return metadata
    rag_store.py          # MiniLM embeddings + FAISS index + (ticker, doc_id) map
    rag_predictor.py      # numeric Prediction(score, direction, confidence, ...)
    prediction_store.py   # save/load per-ticker prediction JSON
    portfolio.py          # named portfolios in data/portfolios.json
    db_cache.py           # rebuild local SQLite from CSVs
    ranking.py            # top-gainers from cache
    universe.py           # S&P 100 default universe
    daily_job.py          # nightly orchestrator (fetch → ... → predict)
  scripts/
    run_daily.bat         # what Task Scheduler runs
    register_task.ps1     # registers/updates the Windows scheduled task
  data/                   # generated, Git-tracked
    prices/*.csv
    sentiment/*.json
    rag_docs/<TICKER>/*.txt
    rag_meta/<TICKER>.json
    embeddings/all_docs.npy
    faiss/rag.index, docs_meta.json
    predictions/*.json
    portfolios.json
    universe.txt          # OPTIONAL — override the default S&P 100 list
  cache/                  # generated, local-only (gitignore-friendly)
    stocks.db
  logs/                   # daily job logs
```

## Install

```powershell
pip install -r requirements.txt
```

## Quickstart

```powershell
# One-shot: pull, embed, predict for the whole S&P 100 universe.
python -m stock_app.cli daily

# Inspect the active universe (S&P 100 unless data/universe.txt overrides).
python -m stock_app.cli universe

# Show the top predictions from data/predictions/*.json
python -m stock_app.cli predictions --n 20 --direction up

# Streamlit dashboard
streamlit run app.py
```

### Single-ticker commands (still available)

```powershell
python -m stock_app.cli update AAPL MSFT
python -m stock_app.cli news AAPL MSFT
python -m stock_app.cli rag-build AAPL MSFT
python -m stock_app.cli cache AAPL MSFT
python -m stock_app.cli rag-predict AAPL --horizon 5
python -m stock_app.cli top --n 20
```

## Schedule the daily job (Windows Task Scheduler)

```powershell
# From the project root, in an *elevated or normal* PowerShell:
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1

# Custom time:
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1 -At "21:00"

# Manage the task:
Get-ScheduledTask -TaskName 'StockRAG-Daily'
Start-ScheduledTask -TaskName 'StockRAG-Daily'    # trigger immediately
Unregister-ScheduledTask -TaskName 'StockRAG-Daily' -Confirm:$false
```

The task runs `scripts\run_daily.bat`, which calls `python -m stock_app.cli daily`. Logs land in `logs/daily_YYYYMMDD.log`.

## Streamlit UI

```powershell
streamlit run app.py
```

Tabs:

- **Dashboard** — filter the latest predictions by direction / min-confidence.
- **Portfolio** — create named portfolios, add/remove holdings, see value and value-weighted score.
- **Stock detail** — price chart + the latest prediction breakdown + sentiment items.
- **Run pipeline** — kick off the daily job from the UI; tail recent logs.

The UI **only reads** pre-computed files — it never runs the slow embedding/prediction step on a page load. Refresh artifacts via the daily job (scheduled or button).

## Prediction signal

For each ticker, `RAGPredictor.predict()` returns a `Prediction(score, direction, confidence, ...)`:

```
score      = 0.5 * rag_signal + 0.3 * momentum + 0.2 * sentiment
direction  = up  if score > +0.15
             down if score < -0.15
             neutral otherwise
```

- **rag_signal** — embed the last 20-day regime, FAISS-retrieve the 10 nearest historical regimes (across all tickers in the universe), look up each one's stored forward N-day return in `data/rag_meta/<TICKER>.json`, average them, squash through `tanh`.
- **momentum** — 20-day return, squashed through `tanh`.
- **sentiment** — average TextBlob polarity from `data/sentiment/<TICKER>.json`. *Note:* `sentiment.dummy_news_fetch` is a placeholder — wire in a real news source to make this useful.
- **confidence** — `n_neighbors_used/k * exp(-std(forward_returns) * 20)`. High when many neighbors agreed on a forward return.

## Customizing the universe

Drop a `data/universe.txt` file with one ticker per line. Comments (`#`) and blanks are ignored. `load_universe()` will prefer it over the built-in S&P 100 list.

## Publishing daily results to GitHub

The `daily` command pushes a fresh snapshot of `data/` to your remote at the end of every run:

```powershell
python -m stock_app.cli daily            # default: also commits + pushes
python -m stock_app.cli daily --no-push   # local-only refresh
```

Stage 6 (`commit + push data/ artifacts`) is a no-op if:
- there is no `origin` remote configured, OR
- nothing changed in `data/` since the last commit.

What gets pushed:
- `data/prices/*.csv`, `data/sentiment/*.json`
- `data/rag_docs/<TICKER>/*.txt`, `data/rag_meta/<TICKER>.json`
- `data/embeddings/all_docs.npy`, `data/faiss/rag.index`, `data/faiss/docs_meta.json`
- `data/predictions/*.json`

What stays local (via `.gitignore`):
- `cache/stocks.db` (rebuildable from CSVs)
- `logs/`, `__pycache__/`, `.venv/`
- `data/portfolios.json` (your personal holdings)
- `data/universe.txt` (your local universe override)

## Deploying the dashboard

The Streamlit app only reads pre-computed files in `data/predictions/`, so the deployed app has zero ML/yfinance work to do at runtime — fast cold-start, free-tier friendly.

Because this repo is **private**, free Streamlit Community Cloud won't deploy it. Options:

| Option | Cost | Notes |
|---|---|---|
| **Run locally** | free | `streamlit run app.py` — what you're already doing. |
| **Streamlit Cloud (paid)** | $$ | Supports private repos. Connect to GitHub, auto-redeploy on every push from the daily job. |
| **Render / Railway / Fly.io** | free tier | Connect the private repo, run `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`. Add a `Procfile` if needed. |
| **Make the repo public** | free | `gh repo edit RoopeshAithal/stock-rag-app --visibility public` → then Streamlit Community Cloud will deploy it. Anything in `data/` becomes public — fine since it's just market data and forecasts. |

### Minimum config for Streamlit Cloud (when ready)

1. **App entry point**: `app.py`
2. **Python version**: 3.12 (matches local)
3. **Requirements file**: `requirements.txt`
4. **Secrets**: none required — no API keys used.

Streamlit Cloud watches the default branch; every successful `daily` job push triggers a redeploy within ~1 minute.
