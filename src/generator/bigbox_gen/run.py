"""Generate the full dataset (or only its file hashes) and write the manifests."""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import __version__
from .config import Calendar, config_sha256
from .extracts import Extracts
from .masters import build_masters
from .simulate import simulate
from .sink import Sink

# The pipeline rule that must catch each injected defect (stage-A evidence reconciles to it).
DEFECT_RULES = {
    "pos_duplicate": ("pos_order_lines", "silver dedup on line_id (extra copies removed)"),
    "pos_null_sku": ("pos_order_lines", "expectation sku_id IS NOT NULL -> quarantine"),
    "pos_null_store": ("pos_order_lines", "expectation store_id IS NOT NULL -> quarantine"),
    "pos_null_price": ("pos_order_lines", "expectation unit_price IS NOT NULL -> quarantine"),
    "pos_late": ("pos_order_lines", "extract_ts - event_ts > 24 h: flagged late, gold recomputed"),
    "pos_orphan_sku": ("pos_order_lines", "FK expectation sku_id in products -> quarantine"),
    "pos_test_store": (
        "pos_order_lines",
        "FK expectation store_id in stores (test store) -> quarantine",
    ),
    "pos_negative_qty": ("pos_order_lines", "expectation quantity > 0 on sale lines -> drop"),
    "pos_future_ts": ("pos_order_lines", "expectation event_ts <= extract_ts -> drop"),
    "pos_cents_price": (
        "pos_order_lines",
        "price-range check: unit_price > 50 x list price -> /100",
    ),
    "receipts_uom_cases": ("replenishment_receipts", "UoM normalisation: CS x case_pack -> EA"),
    "online_overship": ("online_order_lines", "expectation shipped_qty <= requested_qty -> drop"),
    "online_late": (
        "online_order_lines",
        "extract_ts - order_ts beyond the batch window: flagged late",
    ),
    "online_schema_drift_rows": (
        "online_order_lines",
        "Auto Loader schema evolution / _rescued_data",
    ),
}


def generate(cfg: dict, root: Path | str | None, log=print) -> Sink:
    """Run the seeded simulation end to end. root=None hashes the output without writing it."""
    t0 = time.time()
    seeds = np.random.SeedSequence(cfg["seed"]).spawn(3)
    rng_masters, rng_sim, rng_extract = (np.random.default_rng(s) for s in seeds)
    cal = Calendar.from_config(cfg)
    masters = build_masters(cfg, cal, rng_masters)
    sink = Sink(root)
    ex = Extracts(cfg, cal, masters, sink, rng_extract)
    ex.write_masters()
    log(
        f"masters: {len(masters.store_id)} stores, {len(masters.sku_id)} SKUs, "
        f"{masters.n_cells} ranged store-SKU cells, {len(masters.buyer_id)} buyers"
    )
    for res in simulate(cfg, cal, masters, rng_sim):
        ex.add_day(res)
        if res.day % 30 == 0:
            log(f"  simulated {cal.date(res.day)}  ({time.time() - t0:.0f} s)")
    ex.finish()

    rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {"history": 0, "staged_live": 0, "files": 0}
    )
    for path, meta in sink.files.items():
        parts = path.split("/")
        entity, where = (
            (parts[1], "staged_live") if parts[0] == "_staging" else (parts[0], "history")
        )
        rows[entity][where] += meta["rows"] or 0
        rows[entity]["files"] += 1
    defects = {
        name: {
            "entity": DEFECT_RULES[name][0],
            "count": ex.defects.get(name, 0),
            "caught_by": DEFECT_RULES[name][1],
        }
        for name in DEFECT_RULES
    }
    sink.json(
        "_manifest/injected_defects.json",
        {
            "rates": cfg["defects"],
            "defects": defects,
        },
    )
    sink.json(
        "_manifest/generator_run.json",
        {
            "generator_version": __version__,
            "seed": cfg["seed"],
            "config_sha256": config_sha256(cfg),
            "calendar": cfg["calendar"],
            "rows": dict(sorted(rows.items())),
        },
    )
    sink.json("_manifest/injected_defects_by_file.json", ex.defects_by_file())
    files = {k: v for k, v in sorted(sink.files.items())}
    sink.json("_manifest/files.json", files)
    sink.close()
    log(
        f"done: {len(files)} files, {sum(f['bytes'] for f in files.values()) / 1e9:.2f} GB "
        f"in {time.time() - t0:.0f} s"
    )
    return sink
