import copy
import datetime as dt

import numpy as np
import pandas as pd
import pyarrow.csv as pacsv
import pytest

from bigbox_gen.config import Calendar
from bigbox_gen.run import generate
from bigbox_ml.backtest import METRICS, Cells, Incumbent, capture, replay, world
from bigbox_ml.features import FEATURES, KEYS, horizon_frame
from bigbox_ml.policy import (
    Policy,
    days_of_supply,
    expected_shortfall,
    levels,
    order_quantity,
    overstock,
    stockout_risk,
)

POLICY = Policy(
    review_days=1,
    service_level=0.95,
    service_level_sensitivity=(0.95,),
    min_presentation_cases=1,
    horizon_days=4,
    at_risk_threshold=0.5,
    overstock_days_nonperishable=21,
    slow_mover_units_per_day=1.0,
)


def _cells(cfg):
    _, m, _ = world(cfg)
    return m, Cells.of(cfg, m, np.zeros(m.n_cells, dtype=np.int64), 1)


def test_policy_file_loads():
    p = Policy.load()
    assert p.horizon_days >= 13  # the longest lead time (12 days) + the nightly review
    assert p.service_level in p.service_level_sensitivity


def test_levels_and_order_quantity_by_hand():
    f = np.array([[2.0, 3.0, 4.0, 5.0]] * 2)
    lead, case = np.array([2, 2]), np.array([6, 6])
    shelf, perish = np.array([0, 2]), np.array([False, True])
    sigma = np.zeros(2)
    rop, out = levels(f, lead, shelf, perish, sigma, case, POLICY)
    # non-perishable: lead 2 days = 2+3, lead + review = 2+3+4; the perishable is capped at
    # lead + shelf - 1 = 3 days = 9; both are then floored at one case
    np.testing.assert_allclose(rop, [6, 6])
    np.testing.assert_allclose(out, [9, 9])
    np.testing.assert_array_equal(order_quantity(np.array([5, 6]), rop, out, case), [6, 0])
    rop2, out2 = levels(f, lead, shelf, perish, np.ones(2), case, POLICY)
    z = POLICY.z
    assert out2[0] == pytest.approx(9 + z * np.sqrt(3))
    assert out2[1] == pytest.approx(9)  # the shelf-life cap binds before the safety stock


def test_levels_reject_short_horizon():
    with pytest.raises(ValueError):
        levels(
            np.ones((1, 3)),
            np.array([3]),
            np.array([0]),
            np.array([False]),
            np.ones(1),
            np.array([1]),
            POLICY,
        )


def test_risk_shortfall_and_days_of_supply():
    mu, s = np.array([10.0, 10.0, 10.0]), np.array([2.0, 2.0, 0.0])
    risk = stockout_risk(np.array([10.0, 30.0, 9.0]), mu, s)
    np.testing.assert_allclose(risk, [0.5, 0.0, 1.0], atol=1e-9)
    loss = expected_shortfall(np.array([10.0, 30.0, 9.0]), mu, s)
    np.testing.assert_allclose(loss, [2.0 / np.sqrt(2 * np.pi), 0.0, 1.0], atol=1e-6)
    dos = days_of_supply(np.array([10.0, 5.0]), np.array([2.0, 0.0]))
    assert dos[0] == 5.0 and np.isnan(dos[1])
    flags = overstock(
        np.array([50.0, 5.0, 5.0]),
        np.array([25.0, 4.0, np.nan]),
        np.array([False, True, False]),
        np.array([0, 3, 0]),
        POLICY,
    )
    np.testing.assert_array_equal(flags, [True, True, True])


def test_horizon_frame_moves_only_the_plan():
    origin = pd.DataFrame(
        {
            "store_id": ["S001", "S002"],
            "sku_id": ["P1", "P1"],
            "date": [dt.date(2026, 8, 9)] * 2,  # a Sunday
            **{c: [1.0, 2.0] for c in FEATURES if c not in ("category", "format")},
            "category": ["Dairy", "Dairy"],
            "format": ["STANDARD", "COMPACT"],
        }
    )
    origin["dow"] = 6.0
    origin["unit_price"] = 4.0
    promos = pd.DataFrame(
        {
            "store_id": ["S001"],
            "sku_id": ["P1"],
            "date": [dt.date(2026, 8, 10)],
            "promo_discount": [0.25],
        }
    )
    h = horizon_frame(origin, promos, 3)
    assert list(h["step"]) == [0, 1, 2, 0, 1, 2]
    assert list(h["dow"]) == [6, 0, 1, 6, 0, 1]
    assert h["date"].iloc[1] == dt.date(2026, 8, 10)
    assert list(h["promo_discount"]) == [0, 0.25, 0, 0, 0, 0]
    assert h["effective_price"].iloc[1] == pytest.approx(3.0)
    assert (h["lag_1"].iloc[:3] == 1.0).all() and (h["lag_1"].iloc[3:] == 2.0).all()
    assert set(KEYS) <= set(h.columns)


def test_capture_matches_the_published_ground_truth(tiny_cfg, tmp_path):
    generate(tiny_cfg, tmp_path, log=lambda s: None)
    truth = pacsv.read_csv(tmp_path / "_ground_truth" / "truth_202511.csv.gz").to_pandas()
    cal = Calendar.from_config(tiny_cfg)
    m, c = _cells(tiny_cfg)
    first, last = cal.index(dt.date(2025, 11, 1)), cal.index(dt.date(2025, 11, 15))
    cap = capture(tiny_cfg, c, first, last, log=lambda s: None)
    want = truth.groupby("date")[["demand_instore", "demand_online"]].sum().sum(axis=1).to_numpy()
    got = np.array([h[0, METRICS.index("demand_units")] for h in cap.history])
    np.testing.assert_array_equal(got, want[: len(got)])


def test_replay_of_the_incumbent_reproduces_history(tiny_cfg):
    """With deterministic supply and no damage, the replay must re-trade history exactly."""
    cfg = copy.deepcopy(tiny_cfg)
    for cat in cfg["products"]["categories"]:
        cat["damage_rate"] = 0.0
    cfg["supply"].update(full_fill_prob=1.0, late_prob=0.0)
    cal = Calendar.from_config(cfg)
    m, c = _cells(cfg)
    first, last = cal.index(dt.date(2025, 10, 25)), cal.index(dt.date(2025, 11, 15))
    cap = capture(cfg, c, first, last, log=lambda s: None)
    assert cap.start.inv[c.perishable].sum() > 0 and cap.start.on_order.sum() > 0
    got = replay(cfg, c, cap, Incumbent(cfg, c, cap.start.sales_ring), seed=1)
    np.testing.assert_array_equal(np.stack(got), np.stack(cap.history))
