"""Deterministic tools. All money maths in Decimal built from strings; outputs
are JSON-serializable (Decimals rendered as plain strings)."""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .access import AuthorizedCustomer

DATA_DIR = Path(__file__).parent / "data"
STABLECOINS = frozenset({"USDC", "USDT"})
MAX_SINGLE_NONSTABLE_PCT = Decimal("60")  # KB-001, medium risk profile
ANNUAL_FEE_RATE = Decimal("0.008")  # KB-002: 0.8% per year, billed quarterly
CENT = Decimal("0.01")
PCT = Decimal("0.0001")


class DataUnavailable(Exception):
    pass


class MissingPriceError(Exception):
    def __init__(self, assets: Iterable[str]) -> None:
        self.assets = sorted(assets)
        super().__init__("Missing price for: " + ", ".join(self.assets))


class Store:
    """Fixture-backed data source. Inject dicts in tests."""

    def __init__(self, portfolios: Optional[Dict[str, Any]] = None,
                 prices: Optional[Dict[str, Any]] = None) -> None:
        self._portfolios = portfolios
        self._prices = prices

    def _load(self, name: str) -> Dict[str, Any]:
        try:
            return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DataUnavailable("data source unavailable: " + name) from exc

    def portfolio(self, customer_id: str) -> Dict[str, Any]:
        data = self._portfolios if self._portfolios is not None else self._load("portfolios.json")
        if customer_id not in data:
            raise DataUnavailable("portfolio not found")
        return data[customer_id]

    def price_table(self) -> Dict[str, Any]:
        return self._prices if self._prices is not None else self._load("prices.json")


def _s(d: Decimal) -> str:
    return format(d, "f")


def _money(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def get_portfolio(store: Store, auth: AuthorizedCustomer) -> Dict[str, Any]:
    p = store.portfolio(auth.customer_id)
    return {
        "customerId": p["customerId"],
        "riskProfile": p["riskProfile"],
        "holdings": [
            {"asset": h["asset"], "quantity": str(h["quantity"]),
             "avgCostUsd": str(h["avgCostUsd"])} for h in p["holdings"]
        ],
        "lastUpdated": p["lastUpdated"],
    }


def get_prices(store: Store, assets: List[str]) -> Dict[str, Any]:
    t = store.price_table()
    table = t.get("prices", {})
    found = {a: str(table[a]) for a in assets if a in table and table[a] is not None}
    return {
        "prices": found,
        "missing": sorted(a for a in assets if a not in found),
        "priceTimestamp": t.get("priceTimestamp"),
        "source": t.get("source", "unknown"),
    }


def compute_valuation(portfolio: Dict[str, Any], priced: Dict[str, Any]) -> Dict[str, Any]:
    """Fails (MissingPriceError) rather than valuing a portfolio partially."""
    if priced["missing"]:
        raise MissingPriceError(priced["missing"])
    rows = []
    total = Decimal(0)
    for h in portfolio["holdings"]:
        qty, price = Decimal(h["quantity"]), Decimal(priced["prices"][h["asset"]])
        value = qty * price
        total += value
        rows.append((h, qty, price, value))
    positions = []
    for h, qty, price, value in rows:
        positions.append({
            "asset": h["asset"],
            "quantity": _s(qty),
            "priceUsd": _s(price),
            "valueUsd": _s(_money(value)),
            "exposurePct": _s((value / total * 100).quantize(PCT, rounding=ROUND_HALF_UP)),
            "costBasisUsd": _s(_money(qty * Decimal(h["avgCostUsd"]))),  # historical cost
            "isStablecoin": h["asset"] in STABLECOINS,
        })
    return {
        "customerId": portfolio["customerId"],
        "totalUsd": _s(_money(total)),
        "positions": positions,
        "holdingsAsOf": portfolio["lastUpdated"],
        "priceTimestamp": priced["priceTimestamp"],
        "priceSource": priced["source"],
    }


def exposure_check(valuation: Dict[str, Any]) -> Dict[str, Any]:
    """Largest single non-stablecoin asset vs the 60% policy limit."""
    risky = [p for p in valuation["positions"] if not p["isStablecoin"]]
    top = max(risky, key=lambda p: Decimal(p["exposurePct"]))
    return {
        "asset": top["asset"],
        "exposurePct": top["exposurePct"],
        "limitPct": _s(MAX_SINGLE_NONSTABLE_PCT),
        "breach": Decimal(top["exposurePct"]) > MAX_SINGLE_NONSTABLE_PCT,
    }


def quarterly_fee_estimate(valuation: Dict[str, Any]) -> Dict[str, Any]:
    total = Decimal(valuation["totalUsd"])
    fee = _money(total * ANNUAL_FEE_RATE / 4)
    return {
        "estimateUsd": _s(fee),
        "annualRate": _s(ANNUAL_FEE_RATE),
        "assumption": ("Estimate only: assumes the snapshot value stays constant and "
                       "fee = annual 0.8% / 4. The actual billing convention is "
                       "unspecified; this is not a guaranteed future bill."),
    }
