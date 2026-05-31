"""Read/write per-ticker prediction JSON, and aggregate them into a table."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List
import pandas as pd

from .file_store import BASE


def _pred_dir() -> Path:
    return BASE / "predictions"


def save_prediction(pred_dict: dict):
    out_dir = _pred_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(pred_dict)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = out_dir / f"{pred_dict['ticker']}.json"
    path.write_text(json.dumps(payload, indent=2))


def load_prediction(ticker: str) -> dict | None:
    path = _pred_dir() / f"{ticker}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_all_predictions() -> List[dict]:
    out_dir = _pred_dir()
    if not out_dir.exists():
        return []
    preds = []
    for path in sorted(out_dir.glob("*.json")):
        try:
            preds.append(json.loads(path.read_text()))
        except json.JSONDecodeError:
            continue
    return preds


HORIZON_LABELS = ("1d", "weekly", "monthly")


def predictions_dataframe() -> pd.DataFrame:
    preds = load_all_predictions()
    if not preds:
        return pd.DataFrame()
    rows = []
    for p in preds:
        row = {
            "ticker": p.get("ticker"),
            "direction": p.get("direction"),
            "score": p.get("score"),
            "confidence": p.get("confidence"),
            "last_close": p.get("last_close"),
            "expected_return": p.get("expected_return"),
            "as_of": p.get("as_of"),
        }
        forecasts = p.get("forecasts", {}) or {}
        for label in HORIZON_LABELS:
            f = forecasts.get(label, {}) or {}
            row[f"{label}_ret"] = f.get("expected_return")
            row[f"{label}_min"] = f.get("expected_min")
            row[f"{label}_max"] = f.get("expected_max")
        comps = p.get("components", {}) or {}
        row["rag"] = comps.get("rag_signal")
        row["momentum"] = comps.get("momentum")
        row["sentiment"] = comps.get("sentiment")
        row["n_neighbors"] = p.get("n_neighbors")
        row["generated_at"] = p.get("generated_at")
        rows.append(row)
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
