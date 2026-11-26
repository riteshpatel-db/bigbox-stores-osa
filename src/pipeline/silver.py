"""Silver: typed, deduplicated and normalised; rows failing an expectation go to quarantine tables.

POS and online lines are materialized views, so dedup can keep the earliest-arriving copy of each
line_id (a re-send lands in a later file). Each defect a row can carry fails exactly one
expectation, so the event-log expectation counts reconcile one-to-one with the defect manifest.
"""

from pyspark import pipelines as dp
from pyspark.sql import Window
from pyspark.sql import functions as F

CATALOG = spark.conf.get("bigbox.catalog")  # noqa: F821  (spark is provided by the pipeline)
CUTOVER = spark.conf.get("bigbox.live_cutover_date")  # noqa: F821
BRONZE, SILVER = f"{CATALOG}.bronze", f"{CATALOG}.silver"
ROW_TRACKING = {"delta.enableRowTracking": "true"}


def bronze(entity: str):
    return spark.read.table(f"{BRONZE}.{entity}")  # noqa: F821


def latest_by(df, keys: list[str]):
    """Keep the most recently delivered version of each key (master data)."""
    w = Window.partitionBy(*keys).orderBy(
        F.col("_file_modified").desc(), F.col("_source_file").desc()
    )
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def expected_extract(ts: str):
    """When an on-time row arrives: the nightly batch (02:00 next day) before the near-real-time
    cut-over date, the end of the event's hour after it."""
    day = F.to_date(ts)
    nightly = F.to_timestamp(F.date_add(day, 1)) + F.expr("INTERVAL 2 HOURS")
    hourly = F.date_trunc("hour", F.col(ts)) + F.expr("INTERVAL 1 HOUR")
    return F.when(day < F.lit(CUTOVER).cast("date"), nightly).otherwise(hourly)


def rules_sql(rules: dict[str, str]) -> dict[str, str]:
    # a NULL predicate counts as a failure, consistently in silver and in quarantine
    return {name: f"coalesce(({cond}), false)" for name, cond in rules.items()}


def all_pass(rules: dict[str, str]):
    return F.expr(" AND ".join(rules.values()))


def failed_rules(rules: dict[str, str]):
    return F.array_compact(F.array(*[F.when(~F.expr(c), F.lit(n)) for n, c in rules.items()]))


# ---------- masters ----------
@dp.materialized_view(name=f"{SILVER}.stores", comment="Store master (latest delivery).")
def stores():
    return latest_by(bronze("stores"), ["store_id"]).drop("_rescued_data")


@dp.materialized_view(name=f"{SILVER}.products", comment="Product master (latest delivery).")
def products():
    return latest_by(bronze("products"), ["sku_id"]).drop("_rescued_data")


@dp.materialized_view(name=f"{SILVER}.assortment", comment="Store x SKU ranging (latest delivery).")
def assortment():
    return latest_by(bronze("assortment"), ["store_id", "sku_id"]).drop("_rescued_data")


MASK = f"MASK {CATALOG}.serving.mask_pii"  # UC SQL UDF, created by src/governance/01_*.sql


@dp.materialized_view(
    name=f"{SILVER}.buyers",
    comment="Loyalty and online accounts. Contains PII: names, email and phone are masked for "
    "everyone except principals with pii_cleartext in serving.region_access.",
    schema=f"""
        buyer_id STRING, first_name STRING {MASK}, last_name STRING {MASK},
        email STRING {MASK}, phone STRING {MASK},
        home_store_id STRING, loyalty_since DATE,
        _source_file STRING, _file_modified TIMESTAMP, _ingested_at TIMESTAMP
    """,
)
def buyers():
    return latest_by(bronze("buyers"), ["buyer_id"]).drop("_rescued_data")


@dp.materialized_view(
    name=f"{SILVER}.promotions", comment="Promotion calendar: SKU x region x dates."
)
def promotions():
    return latest_by(bronze("promotions"), ["promo_id", "sku_id", "region"]).drop("_rescued_data")


def known_keys(df, store_col: str):
    p = spark.read.table(f"{SILVER}.products").select(  # noqa: F821
        "sku_id", F.col("unit_price").alias("_list_price"), F.lit(True).alias("_sku_known")
    )
    s = spark.read.table(f"{SILVER}.stores").select(  # noqa: F821
        F.col("store_id").alias(store_col), F.lit(True).alias("_store_known")
    )
    return (
        df.join(p, "sku_id", "left")
        .join(s, store_col, "left")
        .fillna(False, subset=["_sku_known", "_store_known"])
    )


def earliest_copy(df, key: str, cols: list[str]):
    """One row per key: the copy with the earliest extract_ts; _copies counts re-sends."""
    return (
        df.groupBy(key)
        .agg(F.count("*").alias("_copies"), F.min_by(F.struct(*cols), "extract_ts").alias("r"))
        .select(key, "_copies", "r.*")
    )


# ---------- POS lines ----------
POS_RULES = rules_sql(
    {
        "sku_id_not_null": "sku_id IS NOT NULL",
        "store_id_not_null": "store_id IS NOT NULL",
        "unit_price_not_null": "unit_price IS NOT NULL",
        "sku_in_products": "sku_id IS NULL OR _sku_known",
        "store_in_stores": "store_id IS NULL OR _store_known",
        "quantity_positive": "quantity > 0",
        "event_not_after_extract": "event_ts <= extract_ts",
    }
)
POS_COLS = [
    "order_id",
    "store_id",
    "sku_id",
    "event_ts",
    "quantity",
    "unit_price",
    "discount_amount",
    "buyer_id",
    "extract_ts",
    "_source_file",
]


@dp.temporary_view()
def pos_candidates():
    lines = known_keys(earliest_copy(bronze("pos_order_lines"), "line_id", POS_COLS), "store_id")
    cents = F.coalesce(F.col("unit_price") > 50 * F.col("_list_price"), F.lit(False))
    return (
        lines.withColumn("_price_from_cents", cents)
        .withColumn(
            "unit_price", F.when(cents, F.col("unit_price") / 100).otherwise(F.col("unit_price"))
        )
        .withColumn(
            "discount_amount",
            F.when(cents, F.col("discount_amount") / 100).otherwise(F.col("discount_amount")),
        )
        .withColumn("sale_date", F.to_date("event_ts"))
        .withColumn("is_late", F.col("extract_ts") > expected_extract("event_ts"))
        .drop("_list_price")
    )


@dp.materialized_view(
    name=f"{SILVER}.pos_order_lines",
    comment="In-store sale lines: one row per line_id (earliest delivery), prices normalised, "
    "late arrivals flagged. Rows failing an expectation are in quarantine_pos_order_lines.",
    table_properties=ROW_TRACKING,
)
@dp.expect_all_or_drop(POS_RULES)
def pos_order_lines():
    return spark.read.table("pos_candidates")  # noqa: F821


@dp.materialized_view(
    name=f"{SILVER}.quarantine_pos_order_lines",
    comment="POS lines that failed a silver expectation, with the failed rule names.",
)
def quarantine_pos_order_lines():
    return (
        spark.read.table("pos_candidates")  # noqa: F821
        .where(~all_pass(POS_RULES))
        .withColumn("_failed_rules", failed_rules(POS_RULES))
    )


# ---------- online lines ----------
ONLINE_RULES = rules_sql(
    {
        "order_id_not_null": "order_id IS NOT NULL",
        "sku_id_not_null": "sku_id IS NOT NULL",
        "store_id_not_null": "store_id IS NOT NULL",
        "sku_in_products": "sku_id IS NULL OR _sku_known",
        "store_in_stores": "store_id IS NULL OR _store_known",
        "requested_positive": "requested_qty > 0",
        "shipped_not_negative": "shipped_qty >= 0",
        "shipped_not_above_requested": "shipped_qty <= requested_qty",
        "order_not_after_extract": "order_ts <= extract_ts",
    }
)
ONLINE_COLS = [
    "order_id",
    "line_number",
    "buyer_id",
    "store_id",
    "sku_id",
    "order_ts",
    "requested_qty",
    "shipped_qty",
    "unit_price",
    "discount_amount",
    "delivery_fee",
    "fulfilment_method",
    "extract_ts",
    "_source_file",
]


@dp.temporary_view()
def online_candidates():
    raw = bronze("online_order_lines").withColumnRenamed("fulfilling_store_id", "store_id")
    if "fulfilment_method" not in raw.columns:  # appears in the extract from 2026-04-01
        raw = raw.withColumn("fulfilment_method", F.lit(None).cast("string"))
    lines = known_keys(earliest_copy(raw, "line_id", ONLINE_COLS), "store_id")
    return (
        lines.withColumn("order_date", F.to_date("order_ts"))
        .withColumn("is_late", F.col("extract_ts") > expected_extract("order_ts"))
        .drop("_list_price")
    )


@dp.materialized_view(
    name=f"{SILVER}.online_order_lines",
    comment="Online order lines (ship-from-store): requested vs shipped, one row per line_id. "
    "Rows failing an expectation are in quarantine_online_order_lines.",
    table_properties=ROW_TRACKING,
)
@dp.expect_all_or_drop(ONLINE_RULES)
def online_order_lines():
    return spark.read.table("online_candidates")  # noqa: F821


@dp.materialized_view(
    name=f"{SILVER}.quarantine_online_order_lines",
    comment="Online lines that failed a silver expectation, with the failed rule names.",
)
def quarantine_online_order_lines():
    return (
        spark.read.table("online_candidates")  # noqa: F821
        .where(~all_pass(ONLINE_RULES))
        .withColumn("_failed_rules", failed_rules(ONLINE_RULES))
    )


# ---------- operational feeds (append-only streams) ----------
@dp.table(
    name=f"{SILVER}.inventory_snapshots",
    comment="Hourly on-hand per store x SKU during trading hours.",
    table_properties=ROW_TRACKING,
    cluster_by=["snapshot_date", "store_id"],
)
@dp.expect_all_or_drop(
    rules_sql(
        {
            "keys_not_null": "store_id IS NOT NULL AND sku_id IS NOT NULL"
            " AND snapshot_ts IS NOT NULL",
            "on_hand_not_negative": "on_hand >= 0",
        }
    )
)
def inventory_snapshots():
    return (
        spark.readStream.table(f"{BRONZE}.inventory_snapshots")  # noqa: F821
        .select("store_id", "sku_id", "snapshot_ts", "on_hand", "_source_file")
        .withColumn("snapshot_date", F.to_date("snapshot_ts"))
    )


@dp.table(
    name=f"{SILVER}.replenishment_orders",
    comment="Purchase-order lines raised by the incumbent nightly replenishment policy.",
    table_properties=ROW_TRACKING,
)
@dp.expect_all_or_drop(
    rules_sql(
        {
            "keys_not_null": "po_line_id IS NOT NULL AND store_id IS NOT NULL"
            " AND sku_id IS NOT NULL",
            "ordered_positive": "ordered_qty > 0",
        }
    )
)
def replenishment_orders():
    return spark.readStream.table(f"{BRONZE}.replenishment_orders").drop(  # noqa: F821
        "_rescued_data", "_file_modified", "_ingested_at"
    )


@dp.table(
    name=f"{SILVER}.replenishment_receipts",
    comment="Goods received per PO line, normalised to eaches (cases x case_pack).",
    table_properties=ROW_TRACKING,
)
@dp.expect_all_or_drop(
    rules_sql(
        {
            "keys_not_null": "po_line_id IS NOT NULL AND store_id IS NOT NULL"
            " AND sku_id IS NOT NULL",
            "known_uom": "uom IN ('EA', 'CS')",
            "case_pack_known": "uom = 'EA' OR case_pack IS NOT NULL",
            "received_not_negative": "received_qty >= 0",
        }
    )
)
def replenishment_receipts():
    packs = spark.read.table(f"{SILVER}.products").select("sku_id", "case_pack")  # noqa: F821
    return (
        spark.readStream.table(f"{BRONZE}.replenishment_receipts")  # noqa: F821
        .drop("_rescued_data", "_file_modified", "_ingested_at")
        .join(packs, "sku_id", "left")
        .withColumn("_uom_converted", F.col("uom") == "CS")
        .withColumn(
            "received_qty_ea",
            F.when(F.col("uom") == "CS", F.col("received_qty") * F.col("case_pack")).otherwise(
                F.col("received_qty")
            ),
        )
    )


@dp.table(
    name=f"{SILVER}.write_offs",
    comment="Units written off per store x SKU x day: EXPIRED (perishables) or DAMAGED.",
    table_properties=ROW_TRACKING,
)
@dp.expect_all_or_drop(
    rules_sql(
        {
            "keys_not_null": "store_id IS NOT NULL AND sku_id IS NOT NULL"
            " AND writeoff_date IS NOT NULL",
            "known_reason": "reason IN ('EXPIRED', 'DAMAGED')",
            "quantity_positive": "quantity > 0",
        }
    )
)
def write_offs():
    return spark.readStream.table(f"{BRONZE}.write_offs").drop(  # noqa: F821
        "_rescued_data", "_file_modified", "_ingested_at"
    )


@dp.table(
    name=f"{SILVER}.returns",
    comment="Return lines referencing the original order line (POS or ONLINE).",
    table_properties=ROW_TRACKING,
)
@dp.expect_all_or_drop(
    rules_sql(
        {
            "keys_not_null": "return_id IS NOT NULL AND original_line_id IS NOT NULL",
            "known_channel": "channel IN ('POS', 'ONLINE')",
            "quantity_positive": "quantity > 0",
        }
    )
)
def returns():
    return spark.readStream.table(f"{BRONZE}.returns").drop(  # noqa: F821
        "_rescued_data", "_file_modified", "_ingested_at"
    )
