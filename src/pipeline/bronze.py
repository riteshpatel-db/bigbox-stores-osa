"""Bronze: one Auto Loader streaming table per landing folder, kept as delivered.

Only the gzipped extracts in landing/<entity>/ are read. The _staging/ (live batches not yet
released), _manifest/ and _ground_truth/ folders are never part of a bronze source.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

CATALOG = spark.conf.get("bigbox.catalog")  # noqa: F821  (spark is provided by the pipeline)
LANDING = spark.conf.get("bigbox.landing")  # noqa: F821

# entity: (format, schema hints). Columns without a hint stay STRING, as delivered.
SOURCES = {
    "stores": ("csv", "sales_area_sqft BIGINT"),
    "products": (
        "csv",
        "perishable BOOLEAN, shelf_life_days INT, unit_cost DOUBLE, unit_price DOUBLE, "
        "case_pack INT, lead_time_days INT, launch_date DATE",
    ),
    "assortment": ("csv", "ranged BOOLEAN, effective_from DATE"),
    "buyers": ("csv", "loyalty_since DATE"),
    "promotions": ("csv", "start_date DATE, end_date DATE, discount_pct INT"),
    "pos_order_lines": (
        "csv",
        "line_id BIGINT, event_ts TIMESTAMP, quantity BIGINT, unit_price DOUBLE, "
        "discount_amount DOUBLE, extract_ts TIMESTAMP",
    ),
    "online_order_lines": (
        "json",
        "line_id BIGINT, line_number INT, order_ts TIMESTAMP, requested_qty BIGINT, "
        "shipped_qty BIGINT, unit_price DOUBLE, discount_amount DOUBLE, delivery_fee DOUBLE, "
        "extract_ts TIMESTAMP",
    ),
    "inventory_snapshots": ("csv", "snapshot_ts TIMESTAMP, on_hand BIGINT"),
    "replenishment_orders": (
        "csv",
        "po_line_id BIGINT, order_ts TIMESTAMP, ordered_qty BIGINT, due_date DATE",
    ),
    "replenishment_receipts": (
        "csv",
        "receipt_id BIGINT, po_line_id BIGINT, received_ts TIMESTAMP, received_qty BIGINT",
    ),
    "write_offs": ("csv", "writeoff_date DATE, quantity BIGINT"),
    "returns": (
        "csv",
        "return_id BIGINT, original_line_id BIGINT, return_ts TIMESTAMP, quantity BIGINT, "
        "refund_amount DOUBLE",
    ),
}


def bronze_table(entity: str, fmt: str, hints: str) -> None:
    ext = "jsonl" if fmt == "json" else "csv"

    @dp.table(
        name=f"{CATALOG}.bronze.{entity}",
        comment=f"Raw {entity} extracts as delivered, ingested incrementally by Auto Loader.",
        table_properties={"delta.enableRowTracking": "true"},
    )
    def _bronze():
        reader = (
            spark.readStream.format("cloudFiles")  # noqa: F821
            .option("cloudFiles.format", fmt)
            .option("cloudFiles.inferColumnTypes", "false")
            .option("cloudFiles.schemaHints", hints)
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .option("pathGlobFilter", f"*.{ext}.gz")
            .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
        )
        if fmt == "csv":
            reader = reader.option("header", "true")
        return (
            reader.load(f"{LANDING}/{entity}/")
            .withColumn("_source_file", F.col("_metadata.file_path"))
            .withColumn("_file_modified", F.col("_metadata.file_modification_time"))
            .withColumn("_ingested_at", F.current_timestamp())
        )


for _entity, (_fmt, _hints) in SOURCES.items():
    bronze_table(_entity, _fmt, _hints)
