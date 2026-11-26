"""Run-cost model: arithmetic by hand and the assumptions file."""

import cost_model
from cost_model import UnitCosts


def test_assumptions_load_as_numbers():
    a = cost_model.load()
    for k, v in a.items():
        assert isinstance(v, bool if k.startswith("scale_") else (int, float)), k


def test_monthly_cost_by_hand():
    a = {
        "days_per_month": 30,
        "refresh_runs_per_day": 96,
        "training_runs_per_month": 4,
        "endpoint_hours_per_day": 12,
        "warehouse_hours_per_day": 10,
        "app_hours_per_day": 24,
        "scale_data_costs_with_revenue": True,
    }
    u = UnitCosts(1.0, 10.0, 2.0, 3.0, 0.5, 4.0)
    m = cost_model.monthly_cost(u, a, revenue_scale=2.0)
    assert m["refresh"] == 1.0 * 96 * 30 * 2
    assert m["training"] == 10.0 * 4 * 2
    assert m["endpoint"] == 2.0 * 12 * 30  # not scaled with revenue
    assert m["warehouse"] == 3.0 * 10 * 30
    assert m["app"] == 0.5 * 24 * 30
    assert m["lakebase"] == 4.0 * 30
    assert m["total"] == sum(v for k, v in m.items() if k != "total")
    unscaled = cost_model.monthly_cost(u, {**a, "scale_data_costs_with_revenue": False}, 2.0)
    assert unscaled["refresh"] == m["refresh"] / 2


def test_roi():
    r = cost_model.roi(annual_value=1200.0, monthly_total=10.0)
    assert r["annual_cost"] == 120.0 and r["net"] == 1080.0 and r["value_per_dollar"] == 10.0
