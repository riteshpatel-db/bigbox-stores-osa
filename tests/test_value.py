import pytest

import value_model
from value_model import PolicyTotals, annual_value, sensitivity


def test_assumptions_load_and_name_every_input():
    a = value_model.load()
    for key in ("company_annual_revenue_usd", "realisation", "inventory_carrying_cost_rate"):
        assert key in a
    assert a["realisation"] in a["sensitivity"]["realisation"]
    # YAML 1.1 reads "1.0e9" as a string; every assumption must load as a number
    numbers = [v for k, v in a.items() if k != "sensitivity"]
    numbers += [x for grid in a["sensitivity"].values() for x in grid]
    assert all(isinstance(x, int | float) for x in numbers)


def test_annual_value_by_hand():
    a = {
        "company_annual_revenue_usd": 1000.0,
        "realisation": 0.5,
        "inventory_carrying_cost_rate": 0.2,
        "annualise_from_days": 365,
        "sensitivity": {"realisation": [0.5, 1.0], "company_annual_revenue_usd": [1000.0]},
    }
    base = PolicyTotals(days=73, lost_sales=50, lost_margin=20, waste_cost=10, closing_cost=730)
    new = PolicyTotals(days=73, lost_sales=30, lost_margin=12, waste_cost=6, closing_cost=365)
    v = annual_value(base, new, modelled_annual_revenue=250.0, a=a)
    # x5 to a year, x4 to company scale, x0.5 realisation = x10 on the 73-day deltas
    assert v["margin_recovered"] == pytest.approx(80)
    assert v["waste_avoided"] == pytest.approx(40)
    # average inventory falls by 365 / 73 = 5 at cost; 20 % a year; x4 x0.5
    assert v["carrying_cost_avoided"] == pytest.approx(2)
    assert v["total"] == pytest.approx(122)
    assert v["lost_sales_recovered"] == pytest.approx(200)
    grid = sensitivity(base, new, 250.0, a)
    assert [g["total"] for g in grid] == pytest.approx([122, 244])


def test_policies_must_cover_the_same_days():
    a = value_model.load()
    with pytest.raises(ValueError):
        annual_value(PolicyTotals(56, 0, 0, 0, 0), PolicyTotals(55, 0, 0, 0, 0), 1.0, a)
