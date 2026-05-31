"""Streamlit dashboard for the Hybrid Stock-RAG App.

Reads only pre-computed artifacts under data/ — never runs the slow
embedding/prediction pipeline on a page load. Use the "Run pipeline" tab
(or the scheduled Windows task) to refresh the artifacts.
"""
from __future__ import annotations
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from stock_app import portfolio as portfolio_mod
from stock_app.file_store import load_prices, load_sentiment, BASE
from stock_app.prediction_store import (
    load_prediction,
    predictions_dataframe,
)
from stock_app.universe import load_universe


st.set_page_config(
    page_title="Hybrid Stock-RAG",
    page_icon="",
    layout="wide",
)


# ----------------- shared cached loaders -----------------

@st.cache_data(ttl=60)
def cached_predictions() -> pd.DataFrame:
    return predictions_dataframe()


@st.cache_data(ttl=60)
def cached_prices(ticker: str) -> pd.DataFrame | None:
    try:
        return load_prices(ticker)
    except FileNotFoundError:
        return None


def _latest_close(ticker: str) -> float | None:
    df = cached_prices(ticker)
    if df is None or df.empty:
        return None
    return float(df["close"].iloc[-1])


def _format_pct(x):
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.2%}"


# ----------------- header -----------------

st.title("Hybrid Stock-RAG")
preds_df = cached_predictions()
n_preds = len(preds_df)
last_gen = preds_df["generated_at"].max() if n_preds else "—"
universe = load_universe()

c1, c2, c3 = st.columns(3)
c1.metric("Universe", f"{len(universe)} tickers")
c2.metric("Predictions ready", f"{n_preds}")
c3.metric("Last refresh", str(last_gen)[:19] if last_gen != "—" else "—")
if n_preds == 0:
    st.warning(
        "No predictions found in `data/predictions/`. Run the pipeline "
        "(see the *Run pipeline* tab) or wait for the scheduled job."
    )

tab_dash, tab_portfolio, tab_detail, tab_run = st.tabs(
    ["Dashboard", "Portfolio", "Stock detail", "Run pipeline"]
)


# ----------------- TAB: Dashboard -----------------

with tab_dash:
    st.subheader("Latest predictions")
    if preds_df.empty:
        st.info("Nothing to show yet.")
    else:
        col_a, col_b, col_c = st.columns([2, 2, 2])
        direction_filter = col_a.multiselect(
            "Direction",
            options=["up", "neutral", "down"],
            default=["up", "neutral", "down"],
        )
        min_conf = col_b.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)
        max_rows = col_c.slider("Show top N", 5, 100, 25, 5)

        view = preds_df[
            preds_df["direction"].isin(direction_filter)
            & (preds_df["confidence"] >= min_conf)
        ].head(max_rows)

        display_cols = [
            "ticker", "direction", "score", "confidence", "last_close",
            "1d_ret",
            "weekly_min", "weekly_ret", "weekly_max",
            "monthly_min", "monthly_ret", "monthly_max",
            "as_of",
        ]
        display_cols = [c for c in display_cols if c in view.columns]
        st.dataframe(
            view[display_cols].style.format(
                {
                    "score": "{:+.3f}",
                    "confidence": "{:.2f}",
                    "last_close": "${:,.2f}",
                    "1d_ret": "{:+.2%}",
                    "weekly_min": "{:+.2%}",
                    "weekly_ret": "{:+.2%}",
                    "weekly_max": "{:+.2%}",
                    "monthly_min": "{:+.2%}",
                    "monthly_ret": "{:+.2%}",
                    "monthly_max": "{:+.2%}",
                },
                na_rep="—",
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Columns: 1d = next-day expected return · weekly/monthly = expected "
            "min/return/max over the next 5 / 20 trading days, averaged from "
            "RAG-retrieved nearest historical regimes."
        )


# ----------------- TAB: Portfolio -----------------

with tab_portfolio:
    st.subheader("Portfolios")

    portfolios = portfolio_mod.list_portfolios()
    col_sel, col_new, col_del = st.columns([3, 2, 1])
    selected = col_sel.selectbox("Portfolio", portfolios)
    new_name = col_new.text_input("Create new", placeholder="e.g. growth")
    if col_new.button("Create"):
        if new_name.strip():
            portfolio_mod.create_portfolio(new_name.strip())
            st.rerun()
    if col_del.button("Clear / delete", type="secondary"):
        portfolio_mod.delete_portfolio(selected)
        st.rerun()

    holdings = portfolio_mod.get_portfolio(selected)

    st.markdown("**Add or update holding**")
    add_col1, add_col2, add_col3 = st.columns([3, 2, 1])
    new_ticker = add_col1.selectbox(
        "Ticker", universe, key=f"add_ticker_{selected}"
    )
    new_qty = add_col2.number_input(
        "Quantity", min_value=0.0, value=0.0, step=1.0, key=f"add_qty_{selected}"
    )
    if add_col3.button("Save", key=f"add_btn_{selected}"):
        portfolio_mod.set_holding(new_ticker, new_qty, name=selected)
        st.rerun()

    if not holdings:
        st.info(f"Portfolio **{selected}** is empty. Add a holding above.")
    else:
        rows = []
        total_value = 0.0
        weighted_score = 0.0
        weight_total = 0.0
        for ticker, qty in holdings.items():
            close = _latest_close(ticker)
            value = (close or 0.0) * qty
            total_value += value
            pred = load_prediction(ticker) or {}
            score = pred.get("score")
            if close is not None and score is not None:
                weighted_score += score * value
                weight_total += value
            rows.append(
                {
                    "ticker": ticker,
                    "qty": qty,
                    "last_close": close,
                    "value": value,
                    "direction": pred.get("direction", "—"),
                    "score": score,
                    "expected_return": pred.get("expected_return"),
                    "confidence": pred.get("confidence"),
                }
            )
        port_df = pd.DataFrame(rows).sort_values("value", ascending=False)

        m1, m2, m3 = st.columns(3)
        m1.metric("Holdings", len(port_df))
        m2.metric("Total value", f"${total_value:,.2f}")
        avg = (weighted_score / weight_total) if weight_total > 0 else 0.0
        m3.metric("Value-weighted score", f"{avg:+.3f}")

        st.dataframe(
            port_df.style.format(
                {
                    "qty": "{:.4g}",
                    "last_close": "${:,.2f}",
                    "value": "${:,.2f}",
                    "score": "{:+.3f}",
                    "expected_return": "{:+.2%}",
                    "confidence": "{:.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("**Remove a holding**")
        rm_col1, rm_col2 = st.columns([3, 1])
        rm_ticker = rm_col1.selectbox(
            "Ticker to remove",
            list(holdings.keys()),
            key=f"rm_ticker_{selected}",
        )
        if rm_col2.button("Remove", key=f"rm_btn_{selected}"):
            portfolio_mod.remove_holding(rm_ticker, name=selected)
            st.rerun()


# ----------------- TAB: Stock detail -----------------

with tab_detail:
    st.subheader("Single-stock view")
    ticker = st.selectbox("Ticker", universe, key="detail_ticker")
    df = cached_prices(ticker)

    if df is None or df.empty:
        st.warning(
            f"No price data for {ticker} yet. Run the pipeline to fetch it."
        )
    else:
        pred = load_prediction(ticker)

        col_l, col_r = st.columns([2, 1])
        with col_l:
            st.line_chart(df.set_index("date")["close"], height=320)

        with col_r:
            if pred:
                st.markdown(f"### {pred['direction'].upper()}")
                st.metric("Score", f"{pred['score']:+.3f}")
                st.metric("Confidence", f"{pred['confidence']:.2f}")
                st.caption(f"As of {pred.get('as_of', '')}  •  last_close ${pred.get('last_close', 0):,.2f}")
                with st.expander("Components"):
                    st.json(pred.get("components", {}))
                    st.caption(f"Neighbors used: {pred.get('n_neighbors')}")
            else:
                st.info("No prediction yet for this ticker.")

        if pred:
            st.markdown("#### Forecast by horizon")
            forecasts = pred.get("forecasts", {}) or {}
            last_close = float(pred.get("last_close", 0) or 0)
            cols = st.columns(len(forecasts) or 1)
            for col, (label, f) in zip(cols, forecasts.items()):
                exp_ret = f.get("expected_return", 0.0)
                exp_min = f.get("expected_min", 0.0)
                exp_max = f.get("expected_max", 0.0)
                h_days = f.get("horizon_days")
                with col:
                    st.markdown(f"**{label}**  ·  {h_days}d  ·  n={f.get('n_neighbors', 0)}")
                    st.metric(
                        "Expected return",
                        _format_pct(exp_ret),
                        delta=f"{exp_min:+.2%} … {exp_max:+.2%}",
                        delta_color="off",
                    )
                    if last_close > 0:
                        st.caption(
                            f"Price band: "
                            f"${last_close * (1 + exp_min):,.2f}  …  "
                            f"${last_close * (1 + exp_max):,.2f}  "
                            f"(target ${last_close * (1 + exp_ret):,.2f})"
                        )

        with st.expander("Sentiment items"):
            sent = load_sentiment(ticker)
            if sent:
                st.write(
                    f"avg_polarity: **{sent.get('avg_polarity', 0):+.3f}**"
                )
                st.dataframe(
                    pd.DataFrame(sent.get("items", [])),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No sentiment file for this ticker.")


# ----------------- TAB: Run pipeline -----------------

with tab_run:
    st.subheader("Run the daily pipeline now")
    st.caption(
        "Runs `python -m stock_app.cli daily` as a background process. "
        "Logs are written to the `logs/` folder."
    )

    col_h, col_d = st.columns(2)
    horizon = col_h.number_input("Horizon (days)", min_value=1, max_value=60, value=5)
    days = col_d.number_input("History window (days)", min_value=60, max_value=2000, value=365)

    if st.button("Start pipeline", type="primary"):
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"streamlit_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        cmd = [
            sys.executable,
            "-m",
            "stock_app.cli",
            "daily",
            "--horizon",
            str(int(horizon)),
            "--days",
            str(int(days)),
        ]
        # Detach so the Streamlit page returns immediately.
        with open(log_path, "w", encoding="utf-8") as logf:
            subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
        st.success(
            f"Pipeline started. Tail the log: `{log_path}`. "
            "Refresh the page (R) once it finishes to see new predictions."
        )

    # Show recent log files.
    log_dir = Path("logs")
    if log_dir.exists():
        logs = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
        if logs:
            st.markdown("**Recent logs**")
            for p in logs:
                size_kb = p.stat().st_size / 1024
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                with st.expander(f"{p.name}  ·  {size_kb:.1f} KB  ·  {mtime}"):
                    try:
                        tail = "\n".join(
                            p.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
                        )
                        st.code(tail or "(empty)")
                    except OSError as e:
                        st.error(str(e))
