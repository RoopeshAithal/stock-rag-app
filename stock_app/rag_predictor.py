"""Numeric prediction blending RAG, momentum, and sentiment.

For each ticker we produce a multi-horizon forecast:
  - "1d"      (daily,   1 trading day)
  - "weekly"  (5 trading days)
  - "monthly" (20 trading days)

Each forecast contains expected_return (endpoint), expected_min, expected_max
returns — derived from averaging the corresponding fields across the k nearest
historical regimes retrieved by FAISS.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Tuple
import numpy as np

from .rag_store import RAGStore
from .rag_build import describe_recent_regime
from .file_store import load_prices, load_rag_meta, load_sentiment


# Horizon label → days. The primary horizon (used for the blended score) is "weekly".
HORIZONS: List[Tuple[str, int]] = [("1d", 1), ("weekly", 5), ("monthly", 20)]
PRIMARY_LABEL = "weekly"

# Score weights.
W_RAG = 0.5
W_MOMENTUM = 0.3
W_SENTIMENT = 0.2


@dataclass
class Prediction:
    ticker: str
    score: float
    direction: str
    confidence: float
    primary_horizon: int
    expected_return: float                     # primary-horizon endpoint return
    forecasts: Dict[str, Dict[str, float]]     # label -> {expected_return, expected_min, expected_max, horizon_days, n_neighbors}
    components: Dict[str, float]
    n_neighbors: int                           # primary horizon
    as_of: str
    last_close: float
    horizon: int = field(default=5)            # back-compat alias for primary_horizon

    def to_dict(self):
        return asdict(self)


def _tanh_clip(x: float, scale: float = 1.0) -> float:
    return float(np.tanh(x * scale))


class RAGPredictor:
    def __init__(self, store: RAGStore | None = None):
        self.store = store or RAGStore()
        if self.store.index is None:
            self.store.load_from_files()
        self._meta_cache: Dict[str, List[dict]] = {}

    def _meta_lookup(self, ticker: str, doc_id: int) -> dict | None:
        if ticker not in self._meta_cache:
            self._meta_cache[ticker] = load_rag_meta(ticker)
        for m in self._meta_cache[ticker]:
            if m["doc_id"] == doc_id:
                return m
        return None

    def predict(self, ticker: str, horizon: int = 5, k: int = 10) -> Prediction:
        """`horizon` controls the primary horizon used for the blended score.
        All horizons in HORIZONS are computed and returned in `forecasts`.
        """
        # --- prices / momentum ---
        df = load_prices(ticker).sort_values("date").reset_index(drop=True)
        as_of = str(df["date"].iloc[-1].date()) if len(df) else ""
        last_close = float(df["close"].iloc[-1]) if len(df) else 0.0
        closes = df["close"].values

        if len(closes) < 21:
            momentum = 0.0
        else:
            momentum_raw = float(closes[-1] / closes[-21] - 1.0)
            momentum = _tanh_clip(momentum_raw, scale=5.0)

        # --- RAG retrieval (once, reused across horizons) ---
        query = describe_recent_regime(ticker)
        hits = self.store.retrieve(query, k=k) if query else []
        neighbor_metas = []
        for hit_ticker, doc_id, _text, _dist in hits:
            meta = self._meta_lookup(hit_ticker, doc_id)
            if meta is not None:
                neighbor_metas.append(meta)

        # --- aggregate per horizon ---
        forecasts: Dict[str, Dict[str, float]] = {}
        primary_returns: List[float] = []
        for label, h in HORIZONS:
            rets, mins, maxs = [], [], []
            for m in neighbor_metas:
                if f"fwd_{h}d" in m:
                    rets.append(float(m[f"fwd_{h}d"]))
                if f"fwd_{h}d_min" in m:
                    mins.append(float(m[f"fwd_{h}d_min"]))
                if f"fwd_{h}d_max" in m:
                    maxs.append(float(m[f"fwd_{h}d_max"]))
            forecasts[label] = {
                "horizon_days": h,
                "expected_return": float(np.mean(rets)) if rets else 0.0,
                "expected_min": float(np.mean(mins)) if mins else 0.0,
                "expected_max": float(np.mean(maxs)) if maxs else 0.0,
                "n_neighbors": len(rets),
            }
            if h == horizon:
                primary_returns = rets

        primary_label = next((lbl for lbl, h in HORIZONS if h == horizon), PRIMARY_LABEL)
        if primary_label not in forecasts:
            primary_label = PRIMARY_LABEL
        primary = forecasts[primary_label]
        expected_return = primary["expected_return"]

        rag_signal = _tanh_clip(expected_return, scale=10.0) if primary_returns else 0.0

        # --- sentiment ---
        sent = load_sentiment(ticker)
        polarity = float(sent.get("avg_polarity", 0.0)) if sent else 0.0

        # --- blend ---
        score = W_RAG * rag_signal + W_MOMENTUM * momentum + W_SENTIMENT * polarity
        if score > 0.15:
            direction = "up"
        elif score < -0.15:
            direction = "down"
        else:
            direction = "neutral"

        # --- confidence (primary horizon agreement) ---
        if primary_returns:
            n_factor = min(1.0, len(primary_returns) / k)
            agreement = float(np.exp(-float(np.std(primary_returns)) * 20.0))
            confidence = n_factor * agreement
        else:
            confidence = 0.0

        return Prediction(
            ticker=ticker,
            score=float(score),
            direction=direction,
            confidence=float(confidence),
            primary_horizon=horizon,
            expected_return=float(expected_return),
            forecasts=forecasts,
            components={
                "rag_signal": float(rag_signal),
                "momentum": float(momentum),
                "sentiment": float(polarity),
            },
            n_neighbors=len(primary_returns),
            as_of=as_of,
            last_close=last_close,
            horizon=horizon,
        )

    def predict_direction(self, ticker: str, horizon: int = 5) -> str:
        p = self.predict(ticker, horizon=horizon)
        lines = [
            f"{p.ticker}  direction={p.direction}  score={p.score:+.3f}  confidence={p.confidence:.2f}",
            f"  last_close=${p.last_close:.2f}  as_of={p.as_of}",
        ]
        for label, _h in HORIZONS:
            f = p.forecasts.get(label, {})
            lines.append(
                f"  {label:>7s}: ret={f.get('expected_return', 0):+.2%}  "
                f"min={f.get('expected_min', 0):+.2%}  max={f.get('expected_max', 0):+.2%}  "
                f"(n={f.get('n_neighbors', 0)})"
            )
        return "\n".join(lines)
