from .file_store import save_rag_doc, save_rag_meta, load_prices
import numpy as np

WINDOW = 20
# Horizons in trading days: 1d = daily, 5d = weekly, 20d = monthly.
FORWARD_HORIZONS = (1, 5, 20)


def build_rag_docs_for_ticker(ticker: str, window: int = WINDOW):
    """Build sliding-window regime docs + per-horizon forward-range metadata.

    For each window of length `window` ending at index i-1, we record:
      - the regime description (text — used for retrieval)
      - for each horizon h in FORWARD_HORIZONS:
          fwd_{h}d      = (close[i+h-1] / close[i-1]) - 1   (endpoint return)
          fwd_{h}d_min  = (min(close[i:i+h]) / close[i-1]) - 1   (lowest reached)
          fwd_{h}d_max  = (max(close[i:i+h]) / close[i-1]) - 1   (highest reached)
    """
    df = load_prices(ticker)
    df = df.sort_values("date").reset_index(drop=True)
    max_h = max(FORWARD_HORIZONS)
    if len(df) < window + max_h:
        return

    closes = df["close"].values
    dates = df["date"].dt.date.astype(str).values

    meta = []
    for i in range(window, len(df) - max_h):
        w_close = closes[i - window : i]
        start_price = float(w_close[0])
        end_price = float(w_close[-1])
        window_return = end_price / start_price - 1.0
        daily_rets = np.diff(w_close) / w_close[:-1]
        vol = float(np.std(daily_rets)) if len(daily_rets) > 0 else 0.0

        fwd = {}
        for h in FORWARD_HORIZONS:
            fwd_slice = closes[i : i + h]  # h days AFTER the window ends
            fwd[f"fwd_{h}d"] = float(fwd_slice[-1] / end_price - 1.0)
            fwd[f"fwd_{h}d_min"] = float(fwd_slice.min() / end_price - 1.0)
            fwd[f"fwd_{h}d_max"] = float(fwd_slice.max() / end_price - 1.0)

        text = (
            f"{ticker} regime from {dates[i - window]} to {dates[i - 1]}.\n"
            f"Start price: {start_price:.2f}, End price: {end_price:.2f}.\n"
            f"Window return: {window_return:.2%}, Volatility: {vol:.2%}.\n"
        )
        save_rag_doc(ticker, i, text)
        meta.append(
            {
                "doc_id": i,
                "start": dates[i - window],
                "end": dates[i - 1],
                "window_return": window_return,
                "vol": vol,
                **fwd,
            }
        )

    save_rag_meta(ticker, meta)


def describe_recent_regime(ticker: str, window: int = WINDOW) -> str:
    """Build a regime description for the LAST `window` days — used as the query."""
    df = load_prices(ticker)
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < window:
        return ""
    w = df.iloc[-window:]
    closes = w["close"].values
    daily_rets = np.diff(closes) / closes[:-1]
    vol = float(np.std(daily_rets)) if len(daily_rets) > 0 else 0.0
    window_return = float(closes[-1] / closes[0] - 1.0)
    return (
        f"{ticker} regime from {w['date'].iloc[0].date()} to {w['date'].iloc[-1].date()}.\n"
        f"Start price: {closes[0]:.2f}, End price: {closes[-1]:.2f}.\n"
        f"Window return: {window_return:.2%}, Volatility: {vol:.2%}.\n"
    )
