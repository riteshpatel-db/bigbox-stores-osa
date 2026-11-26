import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pytest

from bigbox_gen.drip import release
from bigbox_gen.run import generate


@pytest.fixture
def landing(tmp_path, tiny_cfg):
    generate(tiny_cfg, tmp_path, log=lambda s: None)
    return tmp_path


def _csv(root: Path, entity: str) -> pa.Table:
    files = sorted((root / entity).glob("*.csv.gz")) + sorted(
        (root / "_staging" / entity).glob("*.csv.gz")
    )
    opts = pacsv.ConvertOptions(
        strings_can_be_null=True,
        column_types={
            "store_id": pa.string(),
            "sku_id": pa.string(),
            "buyer_id": pa.string(),
            "unit_price": pa.float64(),
            "discount_amount": pa.float64(),
            "refund_amount": pa.float64(),
        },
    )
    return pa.concat_tables(pacsv.read_csv(f, convert_options=opts) for f in files)


def _jsonl(root: Path, entity: str) -> list[dict]:
    files = sorted((root / entity).glob("*.jsonl.gz")) + sorted(
        (root / "_staging" / entity).glob("*.jsonl.gz")
    )
    return [
        json.loads(line) for f in files for line in gzip.decompress(f.read_bytes()).splitlines()
    ]


def _defects(root: Path) -> dict[str, int]:
    d = json.loads((root / "_manifest/injected_defects.json").read_text())["defects"]
    return {k: v["count"] for k, v in d.items()}


def _normal_extract(ts: np.ndarray, history_end: dt.date) -> np.ndarray:
    """When a row arrives if on time: nightly batch for history, end of its hour for live."""
    day = ts.astype("datetime64[D]")
    nightly = day + np.timedelta64(1, "D") + np.timedelta64(2, "h")
    hourly = ts.astype("datetime64[h]") + np.timedelta64(1, "h")
    return np.where(day <= np.datetime64(history_end), nightly, hourly)


def test_same_seed_same_hashes(tiny_cfg):
    a = generate(tiny_cfg, None, log=lambda s: None).files
    b = generate(tiny_cfg, None, log=lambda s: None).files
    assert a == b
    c = generate({**tiny_cfg, "seed": tiny_cfg["seed"] + 1}, None, log=lambda s: None).files
    assert {k: v["sha256"] for k, v in a.items()} != {k: v["sha256"] for k, v in c.items()}


def test_written_files_match_manifest(landing):
    files = json.loads((landing / "_manifest/files.json").read_text())
    for rel, meta in files.items():
        assert hashlib.sha256((landing / rel).read_bytes()).hexdigest() == meta["sha256"], rel
    assert not list(landing.rglob("_*.tmp"))


def test_pos_defects_reconcile_with_manifest(landing, tiny_cfg):
    t = _csv(landing, "pos_order_lines")
    inj = _defects(landing)
    products = set(_csv(landing, "products")["sku_id"].to_pylist())
    sku, store = (
        t["sku_id"].to_numpy(zero_copy_only=False),
        t["store_id"].to_numpy(zero_copy_only=False),
    )
    qty = t["quantity"].to_numpy()
    ev = t["event_ts"].to_numpy().astype("datetime64[s]")
    ex = t["extract_ts"].to_numpy().astype("datetime64[s]")
    line = t["line_id"].to_numpy()

    assert pc.sum(pc.is_null(t["sku_id"])).as_py() == inj["pos_null_sku"]
    assert pc.sum(pc.is_null(t["store_id"])).as_py() == inj["pos_null_store"]
    assert pc.sum(pc.is_null(t["unit_price"])).as_py() == inj["pos_null_price"]
    orphan = np.array([s is not None and s not in products for s in sku])
    assert orphan.sum() == inj["pos_orphan_sku"]
    assert (store == tiny_cfg["defects"]["test_store_id"]).sum() == inj["pos_test_store"]
    assert (qty < 0).sum() == inj["pos_negative_qty"]
    assert (ev > ex).sum() == inj["pos_future_ts"]
    assert len(line) - len(np.unique(line)) == inj["pos_duplicate"]
    # late = first delivery of a line arrives after its normal batch
    first = {}
    for lid, x in zip(line, ex, strict=True):
        first[lid] = min(first.get(lid, x), x)
    first_ex = np.array([first[lid] for lid in line])
    normal = _normal_extract(ev, tiny_cfg["calendar"]["history_end"])
    is_first = np.array([x == first[lid] for lid, x in zip(line, ex, strict=True)])
    late = (first_ex > normal) & (ev <= ex) & is_first
    assert late.sum() == inj["pos_late"]
    cents = tiny_cfg["defects"]["cents_price"]
    price = t["unit_price"].to_numpy(zero_copy_only=False)
    in_win = (
        (store == cents["store_id"])
        & (ev.astype("datetime64[D]") >= np.datetime64(cents["start"]))
        & (ev.astype("datetime64[D]") <= np.datetime64(cents["end"]))
    )
    assert (in_win & (price >= 99)).sum() == inj["pos_cents_price"]


def test_pos_units_equal_ground_truth(landing, tiny_cfg):
    t = _csv(landing, "pos_order_lines")
    gt = _csv(landing, "_ground_truth")
    store = t["store_id"].to_numpy(zero_copy_only=False)
    line = t["line_id"].to_numpy()
    _, first = np.unique(line, return_index=True)
    keep = np.zeros(len(line), dtype=bool)
    keep[first] = True
    keep &= store != tiny_cfg["defects"]["test_store_id"]
    units = np.abs(t["quantity"].to_numpy())[keep].sum()
    assert units == pc.sum(gt["sold_instore"]).as_py()


def test_online_defects_and_units(landing, tiny_cfg):
    rows = _jsonl(landing, "online_order_lines")
    inj = _defects(landing)
    gt = _csv(landing, "_ground_truth")
    drift = tiny_cfg["defects"]["schema_drift"]["column"]
    over = [r for r in rows if r["shipped_qty"] > r["requested_qty"]]
    assert len(over) == inj["online_overship"]
    assert sum(drift in r for r in rows) == inj["online_schema_drift_rows"]
    ts = np.array([r["order_ts"] for r in rows], dtype="datetime64[s]")
    ex = np.array([r["extract_ts"] for r in rows], dtype="datetime64[s]")
    assert (ex > _normal_extract(ts, tiny_cfg["calendar"]["history_end"])).sum() == inj[
        "online_late"
    ]
    assert sum(r["requested_qty"] for r in rows) == pc.sum(gt["demand_online"]).as_py()
    # overshipped rows were fully shipped lines, so their true shipped quantity = requested
    shipped = sum(min(r["shipped_qty"], r["requested_qty"]) for r in rows)
    assert shipped == pc.sum(gt["shipped_online"]).as_py()


def test_receipts_in_cases(landing, tiny_cfg):
    t = _csv(landing, "replenishment_receipts")
    assert pc.sum(pc.equal(t["uom"], "CS")).as_py() == _defects(landing)["receipts_uom_cases"]


def test_ground_truth_is_censored_not_corrupt(landing):
    gt = _csv(landing, "_ground_truth")
    col = {c: gt[c].to_numpy() for c in gt.column_names if c not in ("date", "store_id", "sku_id")}
    assert (col["sold_instore"] <= col["demand_instore"]).all()
    assert (col["shipped_online"] <= col["demand_online"]).all()
    assert (col["closing_on_hand"] >= 0).all()
    stocked_out = col["stockout_hours"] > 0
    assert stocked_out.any()
    lost = (col["demand_instore"] + col["demand_online"]) - (
        col["sold_instore"] + col["shipped_online"]
    )
    assert (lost[stocked_out] > 0).any() and (lost[~stocked_out] == 0).all()


def test_drip_releases_everything_in_order(landing):
    staged = sorted(p.name for p in (landing / "_staging").rglob("*") if p.is_file())
    assert staged
    released, cursors = 0, []
    for _ in range(200):
        out = release(landing, hours=4)
        released += out["released"]
        cursors.append(out["released_before"])
        if out["remaining"] == 0:
            break
    assert released == len(staged)
    assert cursors == sorted(cursors)
    assert not [p for p in (landing / "_staging").rglob("*") if p.is_file()]
    assert release(landing, hours=4)["released"] == 0
    assert not list(landing.rglob("_*.tmp"))


def test_defects_by_file_match_each_file(landing):
    by_file = json.loads((landing / "_manifest/injected_defects_by_file.json").read_text())
    pos_files = sorted(landing.glob("pos_order_lines/*.csv.gz")) + sorted(
        landing.glob("_staging/pos_order_lines/*.csv.gz")
    )
    opts = pacsv.ConvertOptions(strings_can_be_null=True, column_types={"sku_id": pa.string()})
    for f in pos_files:
        rel = str(f.relative_to(landing))
        nulls = pc.sum(pc.is_null(pacsv.read_csv(f, convert_options=opts)["sku_id"])).as_py()
        assert nulls == by_file.get(rel, {}).get("pos_null_sku", 0), rel
    for f in sorted(landing.rglob("online_order_lines/*.jsonl.gz")):
        rows = [json.loads(x) for x in gzip.decompress(f.read_bytes()).splitlines()]
        over = sum(r["shipped_qty"] > r["requested_qty"] for r in rows)
        rel = str(f.relative_to(landing))
        assert over == by_file.get(rel, {}).get("online_overship", 0), rel
