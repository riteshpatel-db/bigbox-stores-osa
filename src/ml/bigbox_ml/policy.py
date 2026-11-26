"""Reorder policy from daily demand forecasts (numpy, vectorised over store x SKU cells).

The same functions produce gold.recommendations and drive policy (b) in the backtest, so the
replayed decisions are the ones the app shows. The structure mirrors the incumbent: order when the
position (on hand + on order) falls below a reorder point, up to an order-up-to level, in whole
cases, never below one presentation case. Two things change:

- demand: a day-by-day forecast of uncensored demand (day of week, promotions, trend) instead of a
  28-day average of censored sales;
- safety stock: sized from demand variability for a target service level instead of a fixed
  3 days, and capped for perishables at what sells before the newest delivery expires.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import NormalDist

import numpy as np
import yaml

DEFAULT_POLICY = Path(__file__).resolve().parent.parent / "policy.yaml"


@dataclass(frozen=True)
class Policy:
    review_days: int
    service_level: float
    service_level_sensitivity: tuple[float, ...]
    min_presentation_cases: int
    horizon_days: int
    at_risk_threshold: float
    overstock_days_nonperishable: float
    slow_mover_units_per_day: float

    @classmethod
    def load(cls, path: Path | str = DEFAULT_POLICY) -> Policy:
        with open(path) as f:
            raw = yaml.safe_load(f)
        raw["service_level_sensitivity"] = tuple(raw["service_level_sensitivity"])
        return cls(**raw)

    def with_service_level(self, level: float) -> Policy:
        return replace(self, service_level=level)

    @property
    def z(self) -> float:
        return NormalDist().inv_cdf(self.service_level)


def daily_sigma(forecast_mean: np.ndarray, std_recent: np.ndarray) -> np.ndarray:
    """Daily demand standard deviation: the recent sales spread, floored at the Poisson spread."""
    var = np.where(np.isnan(std_recent), 0.0, std_recent) ** 2
    return np.sqrt(np.maximum(var, np.maximum(forecast_mean, 0.0)))


def _through(cum: np.ndarray, days: np.ndarray) -> np.ndarray:
    """Cumulative forecast over the first `days` days (days >= 1) for every row."""
    idx = np.clip(days, 1, cum.shape[1]) - 1
    return cum[np.arange(cum.shape[0]), idx]


def levels(
    forecast: np.ndarray,
    lead: np.ndarray,
    shelf_life: np.ndarray,
    perishable: np.ndarray,
    sigma: np.ndarray,
    case: np.ndarray,
    p: Policy,
) -> tuple[np.ndarray, np.ndarray]:
    """Reorder point and order-up-to level per row.

    The order is placed at the end of day 0; forecast[:, k] is the demand forecast for day k + 1.
    As in the incumbent rule, the reorder point covers the lead time and the order-up-to level
    covers the lead time plus the review period.
    """
    if forecast.ndim != 2:
        raise ValueError("forecast must be (rows, horizon_days)")
    cover = lead + p.review_days
    if (cover > forecast.shape[1]).any():
        raise ValueError("horizon_days must cover lead time + review period")
    cum = np.cumsum(forecast, axis=1)
    rop = _through(cum, lead) + p.z * sigma * np.sqrt(lead)
    out = _through(cum, cover) + p.z * sigma * np.sqrt(cover)
    cap = _through(cum, lead + np.maximum(shelf_life, 1) - 1)
    out = np.where(perishable, np.minimum(out, cap), out)
    rop = np.minimum(rop, out)
    min_stock = case * p.min_presentation_cases
    return np.maximum(rop, min_stock), np.maximum(out, min_stock)


def order_quantity(
    position: np.ndarray, rop: np.ndarray, out: np.ndarray, case: np.ndarray
) -> np.ndarray:
    """Whole cases up to the order-up-to level, when the position is below the reorder point."""
    need = position < rop
    qty = np.ceil(np.maximum(out - position, 0) / case) * case
    return np.where(need, qty, 0).astype(np.int64)


_erf = np.vectorize(math.erf, otypes=[float])


def _phi(z: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _cdf(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1 + _erf(z / math.sqrt(2)))


def stockout_risk(available: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """P(demand over the window > available), with demand ~ Normal(mu, sigma)."""
    safe = np.where(sigma > 0, sigma, 1.0)
    risk = 1 - _cdf((available - mu) / safe)
    return np.where(sigma > 0, risk, (mu > available).astype(float))


def expected_shortfall(available: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """E[max(demand - available, 0)] for demand ~ Normal(mu, sigma) (the normal loss function)."""
    safe = np.where(sigma > 0, sigma, 1.0)
    z = (available - mu) / safe
    loss = safe * (_phi(z) - z * (1 - _cdf(z)))
    return np.where(sigma > 0, loss, np.maximum(mu - available, 0.0))


def days_of_supply(on_hand: np.ndarray, daily_rate: np.ndarray) -> np.ndarray:
    """On hand / forecast daily demand; NaN when nothing is expected to sell."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(daily_rate > 0, on_hand / np.where(daily_rate > 0, daily_rate, 1), np.nan)


def overstock(
    on_hand: np.ndarray, dos: np.ndarray, perishable: np.ndarray, shelf_life: np.ndarray, p: Policy
) -> np.ndarray:
    """Days of supply above the threshold (perishables: shelf life), or stock that won't sell."""
    threshold = np.where(perishable, shelf_life, p.overstock_days_nonperishable)
    return np.where(np.isnan(dos), on_hand > 0, dos > threshold)
