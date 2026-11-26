"""Monthly run cost and ROI from measured unit costs and named assumptions (cost_assumptions.yaml).

Pure arithmetic, no I/O beyond loading the YAML; scripts/evidence_cost.py measures the unit costs.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ASSUMPTIONS = Path(__file__).with_name("cost_assumptions.yaml")


@dataclass(frozen=True)
class UnitCosts:
    """Measured at list price, in $."""

    refresh_run: float
    training_run: float
    endpoint_hour: float
    warehouse_hour: float
    app_hour: float
    lakebase_day: float


def load(path: Path | str = DEFAULT_ASSUMPTIONS) -> dict:
    return yaml.safe_load(Path(path).read_text())


def monthly_cost(u: UnitCosts, a: dict, revenue_scale: float = 1.0) -> dict[str, float]:
    """$ per month by component; `revenue_scale` multiplies the data-volume components."""
    days = a["days_per_month"]
    data_scale = revenue_scale if a["scale_data_costs_with_revenue"] else 1.0
    parts = {
        "refresh": u.refresh_run * a["refresh_runs_per_day"] * days * data_scale,
        "training": u.training_run * a["training_runs_per_month"] * data_scale,
        "endpoint": u.endpoint_hour * a["endpoint_hours_per_day"] * days,
        "warehouse": u.warehouse_hour * a["warehouse_hours_per_day"] * days,
        "app": u.app_hour * a["app_hours_per_day"] * days,
        "lakebase": u.lakebase_day * days,
    }
    parts["total"] = sum(parts.values())
    return parts


def roi(annual_value: float, monthly_total: float) -> dict[str, float]:
    annual_cost = 12 * monthly_total
    return {
        "annual_cost": annual_cost,
        "annual_value": annual_value,
        "net": annual_value - annual_cost,
        "value_per_dollar": annual_value / annual_cost if annual_cost else float("inf"),
    }
