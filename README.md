# Hybrid Stock-RAG App

A local stock dashboard with a daily offline pipeline + Streamlit UI.
Public repo: <https://github.com/RoopeshAithal/stock-rag-app>

**Core idea**

- Git stores all durable data (CSV, JSON, TXT, NPY, FAISS index) under `data/`.
- SQLite (`cache/stocks.db`) is local-only and rebuilt anytime from those files.
- RAG uses file-based embeddings + FAISS.
- Predictions blend RAG (nearest historical regimes) + 20d momentum + sentiment into a numeric score with **1-day / weekly / monthly min-max forecasts**.

---

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │  Streamlit dashboard (app.py)                │
                        │  Tabs: Dashboard · Portfolio · Stock detail  │
                        │        · Run pipeline                        │
                        │  Reads ONLY pre-computed files — no ML or    │
                        │  network calls at request time.              │
                        └────────────────────┬────────────────────────┘
                                             │ reads
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │  data/   (durable, git-tracked)              │
                        │  ├── prices/<TICKER>.csv                     │
                        │  ├── sentiment/<TICKER>.json                 │
                        │  ├── rag_docs/<TICKER>/doc_NNNN.txt          │
                        │  ├── rag_meta/<TICKER>.json                  │
                        │  ├── embeddings/all_docs.npy                 │
                        │  ├── faiss/rag.index, docs_meta.json         │
                        │  └── predictions/<TICKER>.json               │
                        └────────────────────▲────────────────────────┘
                                             │ writes
                                             │
   ┌─────────────────────────────────────────┴──────────────────────────────────────┐
   │   Daily pipeline (stock_app/daily_job.py · 6 stages, resilient per-ticker)     │
   │                                                                                 │
   │   1) fetch_prices_yahoo  ─────────────►  data/prices/<TICKER>.csv               │
   │   2) compute_sentiment   ─────────────►  data/sentiment/<TICKER>.json           │
   │   3) build_rag_docs      ─────────────►  data/rag_docs/ + data/rag_meta/        │
   │      RAGStore.build_from_docs ────────►  data/embeddings/ + data/faiss/         │
   │   4) RAGPredictor.predict ────────────►  data/predictions/<TICKER>.json         │
   │   5) rebuild_cache       ─────────────►  cache/stocks.db   (local-only)         │
   │   6) git commit + push   ─────────────►  GitHub  (origin)                       │
   └─────────────────────────────────────────────────────────────────────────────────┘
                                             ▲
                                             │ scheduled by
                                             │
                        ┌─────────────────────────────────────────────┐
                        │  Windows Task Scheduler                      │
                        │  Task name: StockRAG-Daily                   │
                        │  Trigger:   Mon-Fri at 18:30 local           │
                        │  Action:    scripts/run_daily.bat            │
                        └─────────────────────────────────────────────┘
```

### Module reference

| File | Role |
|---|---|
| [stock_app/data_sources.py](stock_app/data_sources.py) | yfinance fetch → DataFrame `[date, close, ret_1d]` |
| [stock_app/file_store.py](stock_app/file_store.py) | All disk I/O (prices, sentiment, RAG docs/meta) |
| [stock_app/sentiment.py](stock_app/sentiment.py) | Placeholder news source + TextBlob polarity |
| [stock_app/rag_build.py](stock_app/rag_build.py) | 20-day sliding-window regime docs + forward 1/5/20-day endpoint·min·max metadata |
| [stock_app/rag_store.py](stock_app/rag_store.py) | MiniLM embeddings, FAISS `IndexFlatL2`, `(ticker, doc_id)` map |
| [stock_app/rag_predictor.py](stock_app/rag_predictor.py) | Numeric `Prediction(score, direction, confidence, forecasts[1d, weekly, monthly])` blending RAG + momentum + sentiment |
| [stock_app/prediction_store.py](stock_app/prediction_store.py) | Save/load `data/predictions/*.json` + DataFrame view |
| [stock_app/portfolio.py](stock_app/portfolio.py) | Named portfolios in `data/portfolios.json` |
| [stock_app/universe.py](stock_app/universe.py) | S&P 100 default; `data/universe.txt` override |
| [stock_app/db_cache.py](stock_app/db_cache.py) | Rebuild local `cache/stocks.db` from CSVs |
| [stock_app/ranking.py](stock_app/ranking.py) | Top-gainers from the SQLite cache |
| [stock_app/daily_job.py](stock_app/daily_job.py) | 6-stage orchestrator (the only thing the scheduled task calls) |
| [stock_app/cli.py](stock_app/cli.py) | Typer CLI — see [CLI reference](#cli-reference) |
| [app.py](app.py) | Streamlit UI (read-only over `data/`) |
| [scripts/run_daily.bat](scripts/run_daily.bat) | Entry point invoked by Task Scheduler |
| [scripts/register_task.ps1](scripts/register_task.ps1) | One-shot registration / update of the scheduled task |

### Prediction signal

For each ticker, `RAGPredictor.predict()` produces a multi-horizon forecast:

```
score      = 0.5 * rag_signal + 0.3 * momentum + 0.2 * sentiment
direction  = "up"      if score > +0.15
             "down"    if score < -0.15
             "neutral" otherwise

forecasts  = {
    "1d":      {expected_return, expected_min, expected_max, n_neighbors}
    "weekly":  { ... over next 5 trading days ... }
    "monthly": { ... over next 20 trading days ... }
}
```

- **rag_signal** — embed the last 20-day regime, FAISS-retrieve the k=10 nearest historical regimes across the universe, look up each one's stored forward 1/5/20-day return in `data/rag_meta/<TICKER>.json`, average, squash through `tanh`.
- **momentum** — 20-day endpoint return, squashed through `tanh`.
- **sentiment** — average TextBlob polarity from `data/sentiment/<TICKER>.json`. The news source is a stub — see [sentiment.dummy_news_fetch](stock_app/sentiment.py#L14) to replace with a real API.
- **confidence** — `n_neighbors_used/k * exp(-std(forward_returns) * 20)`. High when many neighbors agreed.

### What gets pushed vs. what stays local

| Pushed to git | Stays local (`.gitignore`) |
|---|---|
| `data/prices/*.csv` | `cache/stocks.db` (rebuildable from CSVs) |
| `data/sentiment/*.json` | `logs/`, `__pycache__/`, `.venv/` |
| `data/rag_docs/<TICKER>/*.txt` | `data/portfolios.json` (your holdings) |
| `data/rag_meta/<TICKER>.json` | `data/universe.txt` (local override) |
| `data/embeddings/all_docs.npy` | |
| `data/faiss/rag.index`, `docs_meta.json` | |
| `data/predictions/<TICKER>.json` | |

---

## Install

```powershell
pip install -r requirements.txt
```

Python 3.12 is what the repo is developed on. Other 3.10+ versions should work.

---

## Common tasks (runbook)

Everything below is copy-pasteable PowerShell. No Claude required.

### 1. First-time setup, clean machine

```powershell
git clone https://github.com/RoopeshAithal/stock-rag-app.git
cd stock-rag-app
pip install -r requirements.txt

# Pulls the committed data/ snapshot; the UI works immediately:
streamlit run app.py
```

### 2. View current predictions without running anything

```powershell
python -m stock_app.cli predictions --n 25                # top 25 by score
python -m stock_app.cli predictions --n 25 --direction up # only "up" calls
python -m stock_app.cli universe                          # active universe
python -m stock_app.cli top --n 20                        # top by avg 1d return
```

### 3. Refresh predictions for everything (full pipeline)

```powershell
# Full S&P 100 run, then auto-commit + push the new data/ to GitHub.
python -m stock_app.cli daily

# Same, but skip the git push (local-only):
python -m stock_app.cli daily --no-push

# Different primary horizon for the blended score (default 5d):
python -m stock_app.cli daily --horizon 10
```

First run is slow (downloads the MiniLM model + embeds ~21k regime docs on CPU). Expect 10–30 min on a typical laptop, longer on slow disks. Subsequent runs reuse the cached model.

### 4. Add a new ticker

There are two scopes:

**Local-only (just for your machine):** edit `data/universe.txt` (one ticker per line) — this file is gitignored.

```powershell
"TSLA" | Add-Content -Path .\data\universe.txt
"NFLX" | Add-Content -Path .\data\universe.txt
python -m stock_app.cli daily   # recomputes everything for the new list
```

**Permanent (also visible in the deployed app's dropdowns):** edit the `SP100` list in [stock_app/universe.py](stock_app/universe.py), commit, push. The next `daily` run will pick them up.

> Heads-up: the dropdowns in **Stock detail** and **Portfolio** tabs read from `load_universe()`, which only sees `data/universe.txt` or the hard-coded `SP100`. Tickers that have a prediction but are not in either list **will appear on the Dashboard table** but **not in the dropdowns**.

### 5. Update / re-predict a single ticker

```powershell
python -m stock_app.cli update TSLA
python -m stock_app.cli news TSLA
python -m stock_app.cli rag-build TSLA      # this also re-embeds the full corpus
python -m stock_app.cli rag-predict TSLA --horizon 5
```

Or just lean on `daily` with a ticker override:

```powershell
python -m stock_app.cli daily --no-push --tickers TSLA --tickers NFLX
```

### 6. Remove a ticker

```powershell
# 1. Remove it from the universe (either edit universe.py or universe.txt).
# 2. Delete its artifacts:
$t = "TSLA"
Remove-Item -ErrorAction SilentlyContinue `
    .\data\prices\$t.csv, `
    .\data\sentiment\$t.json, `
    .\data\rag_meta\$t.json, `
    .\data\predictions\$t.json
Remove-Item -Recurse -ErrorAction SilentlyContinue .\data\rag_docs\$t
# 3. Rebuild the FAISS index so the removed ticker's regimes drop out:
python -c "from stock_app.rag_store import RAGStore; RAGStore().build_from_docs()"
```

### 7. Launch the dashboard

```powershell
streamlit run app.py
# Local URL:   http://localhost:8501
# Network URL: http://<your-LAN-ip>:8501
```

The **Run pipeline** tab inside the dashboard can start the daily job in the background — useful when you don't want to leave the browser.

### 8. Schedule the daily job (Windows Task Scheduler)

```powershell
# Register or update — defaults to weekdays at 18:30 local time:
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1

# Custom time:
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1 -At "21:00"

# Manage the task:
Get-ScheduledTask -TaskName 'StockRAG-Daily'
Start-ScheduledTask -TaskName 'StockRAG-Daily'    # run now
Unregister-ScheduledTask -TaskName 'StockRAG-Daily' -Confirm:$false
```

Logs land in `logs/daily_YYYYMMDD.log`.

### 9. Roll back a bad data push

```powershell
git log --oneline -5            # find the bad commit
git revert HEAD                 # creates a new commit reverting it
git push
```

### 10. Inspect a single prediction JSON

```powershell
Get-Content .\data\predictions\AAPL.json
```

The shape:

```jsonc
{
  "ticker": "AAPL",
  "score": 0.181,
  "direction": "up",
  "confidence": 0.56,
  "last_close": 312.06,
  "expected_return": -0.0064,           // primary horizon (weekly)
  "forecasts": {
    "1d":      { "expected_return": 0.0071, "expected_min":  0.0071, "expected_max":  0.0071, "horizon_days":  1, "n_neighbors": 10 },
    "weekly":  { "expected_return": -0.0064, "expected_min": -0.0118, "expected_max":  0.0182, "horizon_days":  5, "n_neighbors": 10 },
    "monthly": { "expected_return": -0.0182, "expected_min": -0.0520, "expected_max":  0.0350, "horizon_days": 20, "n_neighbors": 10 }
  },
  "components":    { "rag_signal": -0.064, "momentum": 0.638, "sentiment": 0.108 },
  "n_neighbors":   10,
  "as_of":         "2026-05-29",
  "generated_at":  "2026-05-31T18:49:36+00:00"
}
```

---

## CLI reference

```
python -m stock_app.cli --help

Commands:
  update         Fetch prices for given tickers and save CSVs.
  news           Compute (placeholder) sentiment for given tickers.
  rag-build      Build RAG docs + embeddings + FAISS index for given tickers.
  cache          Rebuild local SQLite cache from CSVs.
  rag-predict    Numeric prediction for a single ticker.
  top            Top N tickers by avg 1d return (from cache).
  daily          Full pipeline: fetch → sentiment → RAG → predict → cache → push.
                 Flags: --horizon N  --days N  --tickers TICKER ...  --no-push
  universe       Print the active universe.
  predictions    Print pre-computed predictions sorted by score.
                 Flags: --n N  --direction {up|down|neutral}
```

---

## Publishing daily results to GitHub

The `daily` command pushes a fresh snapshot of `data/` to your remote at the end of every run:

```powershell
python -m stock_app.cli daily            # default: also commits + pushes
python -m stock_app.cli daily --no-push  # local-only refresh
```

Stage 6 (`commit + push data/ artifacts`) is a no-op if:
- there is no `origin` remote configured, OR
- nothing changed in `data/` since the last commit.

---

## Deploying the dashboard

The Streamlit app only reads pre-computed files in `data/predictions/`, so the deployed app has zero ML / yfinance work to do at runtime — fast cold-start, free-tier friendly.

This repo is **public**, so Streamlit Community Cloud free tier will deploy it.

### Streamlit Community Cloud (recommended, free)

1. Go to <https://share.streamlit.io>.
2. Sign in with your GitHub account.
3. Click **New app**, pick `RoopeshAithal/stock-rag-app`, branch `main`, file `app.py`.
4. Click **Deploy** — no secrets needed.
5. Every push from the daily job auto-redeploys within ~1 minute.

### Self-host alternatives

| Platform | Command |
|---|---|
| Render / Railway | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
| Fly.io | same; add a `Dockerfile` if needed |
| Docker (local) | `docker run -p 8501:8501 -v ${PWD}:/app -w /app python:3.12 bash -c "pip install -r requirements.txt && streamlit run app.py --server.address 0.0.0.0"` |

### Minimum config for cloud deploys

1. **App entry point**: `app.py`
2. **Python version**: 3.12 (matches local)
3. **Requirements file**: `requirements.txt`
4. **Secrets**: none required — no API keys used.

---

## Known limitations

- **Sentiment is a stub.** [sentiment.dummy_news_fetch](stock_app/sentiment.py#L14) returns two hardcoded headlines per ticker. Wire in a real news API (NewsAPI, yfinance's `Ticker.news`, etc.) to make the sentiment component meaningful.
- **Re-embedding is O(corpus) every run.** Each `daily` pass re-embeds all ~21k regime docs from scratch. Incremental embedding (only re-encode new docs) would cut the long pole of the pipeline from ~hours to ~minutes — not yet implemented.
- **Min/max ranges are close-to-close.** We don't fetch intraday OHLC, so the 1d forecast collapses to a single point and weekly/monthly mins/maxes are over daily closes, not intraday extremes.
