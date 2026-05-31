"""Tiny multi-portfolio store: list of named portfolios in a single JSON.

Layout in data/portfolios.json:
    {"portfolios": {"default": {"AAPL": 10, "MSFT": 5}, "growth": {...}}}

Quantity = number of shares (float for fractional).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict

from .file_store import BASE

PORTFOLIO_PATH = BASE / "portfolios.json"


def _load_all() -> Dict[str, Dict[str, float]]:
    if not PORTFOLIO_PATH.exists():
        return {"default": {}}
    data = json.loads(PORTFOLIO_PATH.read_text())
    return data.get("portfolios", {"default": {}})


def _save_all(portfolios: Dict[str, Dict[str, float]]):
    PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_PATH.write_text(json.dumps({"portfolios": portfolios}, indent=2))


def list_portfolios() -> list[str]:
    return sorted(_load_all().keys())


def get_portfolio(name: str = "default") -> Dict[str, float]:
    return _load_all().get(name, {})


def create_portfolio(name: str):
    portfolios = _load_all()
    portfolios.setdefault(name, {})
    _save_all(portfolios)


def delete_portfolio(name: str):
    if name == "default":
        # Don't allow deleting default — just clear it.
        portfolios = _load_all()
        portfolios["default"] = {}
        _save_all(portfolios)
        return
    portfolios = _load_all()
    portfolios.pop(name, None)
    _save_all(portfolios)


def set_holding(ticker: str, qty: float, name: str = "default"):
    portfolios = _load_all()
    portfolio = portfolios.setdefault(name, {})
    if qty <= 0:
        portfolio.pop(ticker.upper(), None)
    else:
        portfolio[ticker.upper()] = float(qty)
    _save_all(portfolios)


def remove_holding(ticker: str, name: str = "default"):
    set_holding(ticker, 0, name)
