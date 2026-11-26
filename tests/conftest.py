import datetime as dt

import pytest

from bigbox_gen.config import load_config

D = dt.date


@pytest.fixture
def tiny_cfg():
    """A few stores and SKUs over ~7 weeks, with defect rates raised so every defect occurs."""
    return load_config(
        overrides={
            "calendar": {
                "history_start": D(2025, 10, 1),
                "history_end": D(2025, 11, 15),
                "live_end": D(2025, 11, 18),
                "burn_in_days": 14,
            },
            "stores": {"count": 6},
            "products": {"count": 40, "new_launches": {"count": 2, "launch_date": D(2025, 10, 20)}},
            "buyers": {"count": 600},
            "promotions": {"events": 3},
            "defects": {
                "pos_duplicate_rate": 0.02,
                "pos_null_sku_rate": 0.01,
                "pos_null_store_rate": 0.01,
                "pos_null_price_rate": 0.01,
                "pos_late_rate": 0.03,
                "pos_orphan_sku_rate": 0.01,
                "pos_test_store_rate": 0.01,
                "pos_negative_qty_rate": 0.01,
                "pos_future_ts_rate": 0.01,
                "online_late_rate": 0.05,
                "online_overship_rate": 0.02,
                "cents_price": {
                    "store_id": "S002",
                    "start": D(2025, 10, 10),
                    "end": D(2025, 10, 12),
                },
                "uom_cases": {
                    "supplier_id": "SUP03",
                    "start": D(2025, 10, 1),
                    "end": D(2025, 11, 30),
                },
                "schema_drift": {
                    "entity": "online_order_lines",
                    "column": "fulfilment_method",
                    "start": D(2025, 11, 1),
                },
            },
        }
    )
