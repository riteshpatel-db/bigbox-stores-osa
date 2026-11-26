"""Gold: business tables for the reorder decision, the KPIs, Genie and the app.

Every measure is stored as additive components (sums and counts) next to its ratio, so the stage-B
metric views can re-aggregate them correctly at any grain.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

CATALOG = spark.conf.get("bigbox.catalog")  # noqa: F821  (spark is provided by the pipeline)
SILVER, GOLD = f"{CATALOG}.silver", f"{CATALOG}.gold"
# Region row filter (UC SQL UDF over serving.region_access, created by src/governance/01_*.sql)
REGION_FILTER = f"ROW FILTER {CATALOG}.serving.region_allowed ON (region)"
KEYS = ["store_id", "sku_id", "date"]


def silver(name: str):
    return spark.read.table(f"{SILVER}.{name}")  # noqa: F821


def ratio(num, den):
    return F.when(den > 0, num / den)


@dp.materialized_view(
    name=f"{GOLD}.store_sku_daily",
    row_filter=REGION_FILTER,
    comment="One row per ranged store x SKU x day: sales by channel, availability from the hourly "
    "snapshots, receipts, write-offs, returns and promo discount. Training grain for the demand "
    "model.",
    cluster_by=["date", "store_id"],
)
def store_sku_daily():
    snaps = (
        silver("inventory_snapshots")
        .groupBy("store_id", "sku_id", F.col("snapshot_date").alias("date"))
        .agg(
            F.count("*").alias("trading_hours"),
            F.sum((F.col("on_hand") == 0).cast("int")).alias("stockout_hours"),
            F.max_by("on_hand", "snapshot_ts").alias("closing_on_hand"),
            F.min("on_hand").alias("min_on_hand"),
        )
    )
    pos = (
        silver("pos_order_lines")
        .groupBy("store_id", "sku_id", F.col("sale_date").alias("date"))
        .agg(
            F.sum("quantity").alias("units_sold_instore"),
            F.sum(F.col("quantity") * F.col("unit_price") - F.col("discount_amount")).alias(
                "revenue_instore"
            ),
            F.sum("discount_amount").alias("discount_instore"),
            F.count("*").alias("pos_lines"),
        )
    )
    online = (
        silver("online_order_lines")
        .groupBy("store_id", "sku_id", F.col("order_date").alias("date"))
        .agg(
            F.sum("requested_qty").alias("units_requested_online"),
            F.sum("shipped_qty").alias("units_shipped_online"),
            F.sum(F.col("shipped_qty") * F.col("unit_price") - F.col("discount_amount")).alias(
                "revenue_online"
            ),
        )
    )
    received = (
        silver("replenishment_receipts")
        .groupBy("store_id", "sku_id", F.to_date("received_ts").alias("date"))
        .agg(F.sum("received_qty_ea").alias("received_units"))
    )
    written_off = (
        silver("write_offs")
        .groupBy("store_id", "sku_id", F.col("writeoff_date").alias("date"))
        .agg(
            F.sum(F.when(F.col("reason") == "EXPIRED", F.col("quantity"))).alias("expired_units"),
            F.sum(F.when(F.col("reason") == "DAMAGED", F.col("quantity"))).alias("damaged_units"),
        )
    )
    returned = (
        silver("returns")
        .groupBy("store_id", "sku_id", F.to_date("return_ts").alias("date"))
        .agg(
            F.sum("quantity").alias("units_returned"), F.sum("refund_amount").alias("refund_amount")
        )
    )
    stores = silver("stores").select("store_id", "region", "format")
    promo = (
        silver("promotions")
        .withColumn("date", F.explode(F.sequence("start_date", "end_date")))
        .join(stores, "region")
        .groupBy("store_id", "sku_id", "date")
        .agg(F.max(F.col("discount_pct") / 100).alias("promo_discount"))
    )
    products = silver("products").select(
        "sku_id", "category", "perishable", "unit_price", "unit_cost"
    )
    zero = [
        "units_sold_instore",
        "revenue_instore",
        "discount_instore",
        "pos_lines",
        "units_requested_online",
        "units_shipped_online",
        "revenue_online",
        "received_units",
        "expired_units",
        "damaged_units",
        "units_returned",
        "refund_amount",
        "promo_discount",
    ]
    out = snaps
    for part in (pos, online, received, written_off, returned, promo):
        out = out.join(part, KEYS, "left")
    return (
        out.fillna(0, subset=zero)
        .join(stores, "store_id")
        .join(products, "sku_id")
        .withColumn("units_sold", F.col("units_sold_instore") + F.col("units_shipped_online"))
        .withColumn("revenue", F.col("revenue_instore") + F.col("revenue_online"))
        .withColumn("in_stock_at_close", F.col("closing_on_hand") > 0)
        .withColumn("on_promo", F.col("promo_discount") > 0)
    )


@dp.materialized_view(
    name=f"{GOLD}.replenishment_fill",
    comment="One row per purchase-order line: ordered vs received (eaches), timeliness and status.",
)
def replenishment_fill():
    rcv = (
        silver("replenishment_receipts")
        .groupBy("po_line_id")
        .agg(
            F.sum("received_qty_ea").alias("received_qty_ea"),
            F.min("received_ts").alias("first_received_ts"),
        )
    )
    return (
        silver("replenishment_orders")
        .select(
            "po_id",
            "po_line_id",
            "store_id",
            "sku_id",
            "supplier_id",
            "order_ts",
            "ordered_qty",
            "due_date",
        )
        .join(rcv, "po_line_id", "left")
        .withColumn("received_qty_ea", F.coalesce("received_qty_ea", F.lit(0)))
        .withColumn("fill_rate", ratio(F.col("received_qty_ea"), F.col("ordered_qty")))
        .withColumn("days_late", F.datediff(F.to_date("first_received_ts"), F.col("due_date")))
        .withColumn(
            "status",
            F.when(F.col("first_received_ts").isNull(), "OPEN")
            .when(F.col("received_qty_ea") >= F.col("ordered_qty"), "RECEIVED_FULL")
            .otherwise("RECEIVED_SHORT"),
        )
    )


@dp.materialized_view(
    name=f"{GOLD}.online_fill",
    comment="Online fill per store x day: units requested vs shipped (ship-from-store).",
)
def online_fill():
    return (
        silver("online_order_lines")
        .groupBy("store_id", F.col("order_date").alias("date"))
        .agg(
            F.count("*").alias("lines"),
            F.sum("requested_qty").alias("units_requested"),
            F.sum("shipped_qty").alias("units_shipped"),
            F.sum((F.col("shipped_qty") < F.col("requested_qty")).cast("int")).alias("short_lines"),
            F.sum((F.col("shipped_qty") == 0).cast("int")).alias("unfilled_lines"),
        )
        .withColumn("fill_rate", ratio(F.col("units_shipped"), F.col("units_requested")))
    )


@dp.materialized_view(
    name=f"{GOLD}.inventory_position",
    row_filter=REGION_FILTER,
    comment="Latest on-hand per store x SKU, open purchase orders and days of supply "
    "(on hand / mean daily units sold over the trailing 28 days).",
)
def inventory_position():
    snaps = silver("inventory_snapshots")
    last_day = snaps.agg(F.max("snapshot_date").alias("d"))
    latest = (
        snaps.join(last_day, F.col("snapshot_date") >= F.date_sub(F.col("d"), 1))
        .groupBy("store_id", "sku_id")
        .agg(
            F.max_by("on_hand", "snapshot_ts").alias("on_hand"),
            F.max("snapshot_ts").alias("as_of_ts"),
        )
    )
    on_order = (
        spark.read.table(f"{GOLD}.replenishment_fill")  # noqa: F821
        .where("status = 'OPEN'")
        .groupBy("store_id", "sku_id")
        .agg(F.sum("ordered_qty").alias("on_order_units"), F.min("due_date").alias("next_due_date"))
    )
    daily = spark.read.table(f"{GOLD}.store_sku_daily")  # noqa: F821
    window_end = daily.agg(F.max("date").alias("e"))
    velocity = (
        daily.join(window_end, F.col("date") > F.date_sub(F.col("e"), 28))
        .groupBy("store_id", "sku_id")
        .agg((F.sum("units_sold") / 28).alias("avg_daily_units_28d"))
    )
    products = silver("products").select(
        "sku_id", "category", "case_pack", "lead_time_days", "perishable"
    )
    stores = silver("stores").select("store_id", "region")
    return (
        latest.join(stores, "store_id")
        .join(on_order, ["store_id", "sku_id"], "left")
        .join(velocity, ["store_id", "sku_id"], "left")
        .join(products, "sku_id")
        .fillna(0, subset=["on_order_units", "avg_daily_units_28d"])
        .withColumn("days_of_supply", ratio(F.col("on_hand"), F.col("avg_daily_units_28d")))
    )


@dp.materialized_view(
    name=f"{GOLD}.kpi_store_daily",
    row_filter=REGION_FILTER,
    comment="KPI components per store x day across both channels. Returns are attributed to the "
    "original sale date. Ratios are provided for convenience; re-aggregate from the components.",
    cluster_by=["date", "store_id"],
)
def kpi_store_daily():
    pos = silver("pos_order_lines").select(
        "store_id",
        F.col("sale_date").alias("date"),
        "order_id",
        "buyer_id",
        "line_id",
        F.col("quantity").alias("units"),
        F.col("unit_price"),
        "discount_amount",
        F.lit(0.0).alias("delivery_fee"),
        F.lit("POS").alias("channel"),
    )
    online = silver("online_order_lines").select(
        "store_id",
        F.col("order_date").alias("date"),
        "order_id",
        "buyer_id",
        "line_id",
        F.col("shipped_qty").alias("units"),
        F.col("unit_price"),
        "discount_amount",
        "delivery_fee",
        F.lit("ONLINE").alias("channel"),
    )
    lines = pos.unionByName(online)
    sales = lines.groupBy("store_id", "date").agg(
        F.sum("units").alias("units_sold"),
        F.sum(F.col("units") * F.col("unit_price")).alias("gross_amount"),
        F.sum("discount_amount").alias("discount_amount"),
        F.sum("delivery_fee").alias("delivery_fees"),
        F.countDistinct("channel", "order_id").alias("total_orders"),
        F.countDistinct("buyer_id").alias("unique_buyers"),
    )
    rets = (
        silver("returns")
        .join(
            lines.select(
                "channel",
                F.col("line_id").alias("original_line_id"),
                F.col("date").alias("sale_date"),
                F.col("store_id").alias("sale_store_id"),
            ),
            ["channel", "original_line_id"],
        )
        .groupBy(F.col("sale_store_id").alias("store_id"), F.col("sale_date").alias("date"))
        .agg(
            F.sum("quantity").alias("items_returned"),
            F.countDistinct("channel", "original_order_id").alias("returned_orders"),
        )
    )
    daily = spark.read.table(f"{GOLD}.store_sku_daily")  # noqa: F821
    avail = daily.groupBy("store_id", "date").agg(
        F.count("*").alias("ranged_sku_days"),
        F.sum(F.col("in_stock_at_close").cast("int")).alias("in_stock_sku_days"),
        F.sum("trading_hours").alias("sku_trading_hours"),
        F.sum(F.col("trading_hours") - F.col("stockout_hours")).alias("sku_hours_on_shelf"),
        F.sum("units_requested_online").alias("online_units_requested"),
        F.sum("units_shipped_online").alias("online_units_shipped"),
        F.sum(F.when(F.col("perishable"), F.col("received_units"))).alias(
            "perishable_units_received"
        ),
        F.sum(F.when(F.col("perishable"), F.col("expired_units"))).alias(
            "perishable_units_expired"
        ),
    )
    stores = silver("stores").select("store_id", "region", "format")
    return (
        avail.join(sales, ["store_id", "date"], "left")
        .join(rets, ["store_id", "date"], "left")
        .join(stores, "store_id")
        .fillna(0)
        .withColumn("item_revenue", F.col("gross_amount") - F.col("discount_amount"))
        .withColumn("total_revenue", F.col("item_revenue") + F.col("delivery_fees"))
        .withColumn("avg_order_value", ratio(F.col("total_revenue"), F.col("total_orders")))
        .withColumn("avg_discount", ratio(F.col("discount_amount"), F.col("gross_amount")))
        .withColumn("item_return_rate", ratio(F.col("items_returned"), F.col("units_sold")))
        .withColumn("return_rate", ratio(F.col("returned_orders"), F.col("total_orders")))
        .withColumn("in_stock_pct", ratio(F.col("in_stock_sku_days"), F.col("ranged_sku_days")))
        .withColumn(
            "on_shelf_availability", ratio(F.col("sku_hours_on_shelf"), F.col("sku_trading_hours"))
        )
        .withColumn(
            "online_fill_rate",
            ratio(F.col("online_units_shipped"), F.col("online_units_requested")),
        )
    )
