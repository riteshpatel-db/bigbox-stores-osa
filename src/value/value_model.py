"""Scale the backtest deltas to an annual dollar value for a ~$1B retailer.

Inputs are measured: per-policy totals over the holdout from ml.backtest_daily, and the modelled
assortment's annual revenue from gold.store_sku_daily. Everything else is a named assumption in
assumptions.yaml. The value has three parts, each "incumbent minus new" (positive = better):

- gross margin on sales no longer lost to stockouts (lost units x (list price - unit cost));
- waste avoided (expired + damaged units at cost);
- carrying cost on the change in average inventory at cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ASSUMPTIONS = Path(__file__).resolve().parent / "assumptions.yaml"


@dataclass(frozen=True)
class PolicyTotals:
    """Sums over the holdout for one policy (columns of ml.backtest_daily)."""

    days: int
    lost_sales: float
    lost_margin: float
    waste_cost: float
    closing_cost: float  # sum over days of closing inventory at cost


def load(path: Path | str = DEFAULT_ASSUMPTIONS) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def annual_value(
    base: PolicyTotals,
    new: PolicyTotals,
    modelled_annual_revenue: float,
    a: dict,
    realisation: float | None = None,
    company_revenue: float | None = None,
) -> dict[str, float]:
    """Annual value in $ at company scale, by component, plus the scale factors used."""
    if base.days != new.days:
        raise ValueError("both policies must cover the same days")
    realisation = a["realisation"] if realisation is None else realisation
    company_revenue = (
        a["company_annual_revenue_usd"] if company_revenue is None else company_revenue
    )
    per_year = a["annualise_from_days"] / base.days
    scale = company_revenue / modelled_annual_revenue
    margin = (base.lost_margin - new.lost_margin) * per_year
    waste = (base.waste_cost - new.waste_cost) * per_year
    carrying = (
        (base.closing_cost - new.closing_cost) / base.days * a["inventory_carrying_cost_rate"]
    )
    k = scale * realisation
    return {
        "lost_sales_recovered": (base.lost_sales - new.lost_sales) * per_year * k,
        "margin_recovered": margin * k,
        "waste_avoided": waste * k,
        "carrying_cost_avoided": carrying * k,
        "total": (margin + waste + carrying) * k,
        "scale_to_company": scale,
        "realisation": realisation,
        "annualise": per_year,
    }


def sensitivity(
    base: PolicyTotals, new: PolicyTotals, modelled_annual_revenue: float, a: dict
) -> list[dict[str, float]]:
    """Total annual value over the grid of realisation x company revenue."""
    s = a["sensitivity"]
    return [
        {
            "company_annual_revenue_usd": rev,
            "realisation": r,
            "total": annual_value(base, new, modelled_annual_revenue, a, r, rev)["total"],
        }
        for rev in s["company_annual_revenue_usd"]
        for r in s["realisation"]
    ]
