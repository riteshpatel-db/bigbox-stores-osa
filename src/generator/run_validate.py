"""Job entry point: re-read the generated files with Spark and print the stage-0 evidence tables.

Spark row counts are compared with the generator's own manifest, so the evidence does not rely on
the generator reporting on itself.
"""

import argparse
import json
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ENTITIES = {  # entity: (format, timestamp/date column)
    "stores": ("csv", None),
    "products": ("csv", None),
    "assortment": ("csv", None),
    "buyers": ("csv", None),
    "promotions": ("csv", "start_date"),
    "pos_order_lines": ("csv", "event_ts"),
    "online_order_lines": ("json", "order_ts"),
    "inventory_snapshots": ("csv", "snapshot_ts"),
    "replenishment_orders": ("csv", "order_ts"),
    "replenishment_receipts": ("csv", "received_ts"),
    "write_offs": ("csv", "writeoff_date"),
    "returns": ("csv", "return_ts"),
}


def read(spark, fmt: str, path: str):
    if fmt == "json":
        return spark.read.json(path)
    return spark.read.option("header", True).csv(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", required=True)
    args = ap.parse_args()
    root = Path(args.landing)
    spark = SparkSession.builder.getOrCreate()
    run = json.loads((root / "_manifest/generator_run.json").read_text())
    files = json.loads((root / "_manifest/files.json").read_text())
    defects = json.loads((root / "_manifest/injected_defects.json").read_text())
    hist_end = run["calendar"]["history_end"]
    hours = run["calendar"]["close_hour"] - run["calendar"]["open_hour"]

    print("## Files, bytes and rows per entity\n")
    print("| entity | files | MB | rows (manifest) | rows (Spark) | match | min ts | max ts |")
    print("|---|---|---|---|---|---|---|---|")
    total_rows = 0
    for entity, (fmt, col) in ENTITIES.items():
        metas = [
            m
            for p, m in files.items()
            if p.split("/")[0] == entity
            or (p.startswith("_staging/") and p.split("/")[1] == entity)
        ]
        manifest_rows = sum(m["rows"] or 0 for m in metas)
        paths = [str(root / entity)]
        if (root / "_staging" / entity).exists():
            paths.append(str(root / "_staging" / entity))
        df = read(spark, fmt, paths)
        n = df.count()
        total_rows += n
        lo = hi = "-"
        if col:
            r = df.agg(F.min(col).alias("lo"), F.max(col).alias("hi")).first()
            lo, hi = r["lo"], r["hi"]
        mb = sum(m["bytes"] for m in metas) / 1e6
        ok = "yes" if n == manifest_rows else "NO"
        print(
            f"| {entity} | {len(metas)} | {mb:,.1f} | {manifest_rows:,} | {n:,} | {ok} "
            f"| {lo} | {hi} |"
        )
    print(f"\nTotal rows read by Spark: {total_rows:,}")

    print("\n## Injected defects (generator manifest)\n")
    print("| defect | entity | injected | must be caught by |")
    print("|---|---|---|---|")
    for name, d in defects["defects"].items():
        print(f"| {name} | {d['entity']} | {d['count']:,} | {d['caught_by']} |")

    print(f"\n## Censored demand vs ground truth (history, through {hist_end})\n")
    gt = read(spark, "csv", str(root / "_ground_truth")).where(F.col("date") <= hist_end)
    num = [c for c in gt.columns if c not in ("date", "store_id", "sku_id")]
    gt = gt.select("date", "store_id", "sku_id", *[F.col(c).cast("double").alias(c) for c in num])
    prices = read(spark, "csv", str(root / "products")).select(
        "sku_id", F.col("unit_price").cast("double").alias("price"), "perishable"
    )
    g = gt.join(prices, "sku_id").withColumn(
        "demand", F.col("demand_instore") + F.col("demand_online")
    )
    s = g.agg(
        F.count("*").alias("cell_days"),
        F.avg((F.col("stockout_hours") > 0).cast("int")).alias("days_with_stockout"),
        F.avg((F.col("closing_on_hand") == 0).cast("int")).alias("days_closing_oos"),
        F.avg(F.col("stockout_hours") / hours).alias("oos_hour_share"),
        F.sum("demand").alias("demand"),
        F.sum(F.col("sold_instore") + F.col("shipped_online")).alias("served"),
        F.sum("demand_online").alias("online_req"),
        F.sum("shipped_online").alias("online_ship"),
        F.sum(
            (F.col("demand") - F.col("sold_instore") - F.col("shipped_online")) * F.col("price")
        ).alias("lost_dollars"),
        F.sum((F.col("sold_instore") + F.col("shipped_online")) * F.col("price")).alias(
            "sales_dollars"
        ),
        F.sum(F.when(F.col("perishable") == "true", F.col("expired_units"))).alias("expired"),
        F.sum(F.when(F.col("perishable") == "true", F.col("received_units"))).alias(
            "perish_received"
        ),
    ).first()
    rows = [
        ("store-SKU-days (history)", f"{s['cell_days']:,}"),
        ("days with >=1 stocked-out trading hour", f"{s['days_with_stockout']:.2%}"),
        ("days closing with zero on hand", f"{s['days_closing_oos']:.2%}"),
        ("stocked-out share of trading hours (1 - OSA)", f"{s['oos_hour_share']:.2%}"),
        ("true demand units", f"{s['demand']:,.0f}"),
        ("units served (sold + shipped)", f"{s['served']:,.0f}"),
        ("demand lost to stockouts (units)", f"{1 - s['served'] / s['demand']:.2%}"),
        ("lost sales at list price ($, ground truth)", f"{s['lost_dollars']:,.0f}"),
        ("sales at list price ($)", f"{s['sales_dollars']:,.0f}"),
        ("online fill rate (shipped / requested)", f"{s['online_ship'] / s['online_req']:.2%}"),
        ("perishable shrink (expired / received)", f"{s['expired'] / s['perish_received']:.2%}"),
    ]
    print("| measure | value |")
    print("|---|---|")
    for k, v in rows:
        print(f"| {k} | {v} |")
    return 0


if __name__ == "__main__":
    code = main()
    if code:  # serverless treats any SystemExit, even exit(0), as a task failure
        raise SystemExit(code)
