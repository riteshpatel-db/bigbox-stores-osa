"""bigbox_refresh task `write_back`: copy new planner decisions from Lakebase into Delta.

Reads Postgres app.reorder_decisions through its Unity Catalog registration (catalog
bigbox_ops_pg) and MERGEs decision ids not yet in gold.reorder_decisions (insert-only: a decision
is never updated). The region comes from silver.stores so the Delta table can carry the region row
filter. Idempotent: a re-run with no new decisions inserts 0 rows.
"""

import argparse
import json

from pyspark.sql import SparkSession


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--pg-catalog", default="bigbox_ops_pg")
    args = ap.parse_args()
    spark = SparkSession.builder.getOrCreate()
    c, pg = args.catalog, args.pg_catalog
    m = spark.sql(f"""
        MERGE INTO {c}.gold.reorder_decisions AS t
        USING (
          SELECT CAST(d.decision_id AS STRING) AS decision_id, d.store_id, d.sku_id, s.region,
                 d.rec_as_of_ts, d.recommended_qty, d.final_qty, d.action, d.reason,
                 d.decided_by, d.decided_at
          FROM {pg}.app.reorder_decisions d
          LEFT JOIN {c}.silver.stores s ON s.store_id = d.store_id
        ) AS s
        ON t.decision_id = s.decision_id
        WHEN NOT MATCHED THEN INSERT (
          decision_id, store_id, sku_id, region, rec_as_of_ts, recommended_qty, final_qty, action,
          reason, decided_by, decided_at, written_back_at
        ) VALUES (
          s.decision_id, s.store_id, s.sku_id, s.region, s.rec_as_of_ts, s.recommended_qty,
          s.final_qty, s.action, s.reason, s.decided_by, s.decided_at, current_timestamp()
        )
    """).first()
    counts = spark.sql(f"""
        SELECT (SELECT count(*) FROM {pg}.app.reorder_decisions) AS postgres_rows,
               (SELECT count(*) FROM {c}.gold.reorder_decisions) AS delta_rows
    """).first()
    print(
        json.dumps(
            {
                "inserted": int(m["num_inserted_rows"]),
                "postgres_rows": counts["postgres_rows"],
                "delta_rows": counts["delta_rows"],
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    code = main()
    if code:  # serverless treats any SystemExit, even exit(0), as a task failure
        raise SystemExit(code)
