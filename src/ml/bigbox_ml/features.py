"""Demand-model features (Spark) and the multi-day horizon frame (pandas).

Row (store_id, sku_id, date = d) of ml.store_sku_features holds what the business knows at the
start of day d: sales and stockouts up to the end of d - 1 from gold.store_sku_daily, plus the plan
for day d (promotion, price, day of week). Training (point-in-time lookup on `date`), batch scoring,
the backtest and the serving endpoint all use these columns, so there is one definition.

A forecast for a later day d + k reuses the row of day d and replaces only the planned columns
(CALENDAR): the history columns stay as known at the start of day d.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

KEYS = ["store_id", "sku_id", "date"]
CATEGORICAL = ["category", "format"]
CALENDAR = ["dow", "promo_discount", "effective_price"]
NUMERIC = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "mean_7",
    "mean_28",
    "std_28",
    "dow_mean_4w",
    "instock_rate_28",
    "stockout_share_7",
    "stockout_share_28",
    "censored_prev_day",
    "online_share_28",
    "category_trend",
    "dow",
    "promo_discount",
    "effective_price",
    "unit_price",
    "perishable",
    "shelf_life_days",
    "lead_time_days",
    "case_pack",
]
FEATURES = NUMERIC + CATEGORICAL

DOCS = {
    "store_id": "Store id (primary key)",
    "sku_id": "Product SKU (primary key)",
    "date": "Day the row forecasts (timeseries key); history columns end the day before",
    "region": "Store region (not a model feature; kept for filtering)",
    "lag_1": "Units sold (in store + shipped online) on d-1",
    "lag_7": "Units sold on d-7",
    "lag_14": "Units sold on d-14",
    "lag_28": "Units sold on d-28",
    "mean_7": "Mean daily units sold over d-7 .. d-1",
    "mean_28": "Mean daily units sold over d-28 .. d-1 (the incumbent forecast)",
    "std_28": "Standard deviation of daily units sold over d-28 .. d-1",
    "dow_mean_4w": "Mean units sold on the same weekday over the last 4 weeks",
    "instock_rate_28": "Units sold per fully in-stock day, d-28 .. d-1 (corrects for censoring)",
    "stockout_share_7": "Share of trading hours ending with zero on hand, d-7 .. d-1",
    "stockout_share_28": "Share of trading hours ending with zero on hand, d-28 .. d-1",
    "censored_prev_day": "1 if d-1 had at least one stocked-out trading hour (sales below demand)",
    "online_share_28": "Online requested units / all demanded units over d-28 .. d-1 (channel mix)",
    "category_trend": "Region x category units, 7-day mean / 28-day mean (seasonality)",
    "dow": "Day of week of d, 0 = Monday",
    "promo_discount": "Planned promotion discount on d (0 if none)",
    "effective_price": "unit_price x (1 - promo_discount) on d",
    "unit_price": "List price",
    "perishable": "1 for products with a shelf life",
    "shelf_life_days": "Shelf life in days (0 for non-perishables)",
    "lead_time_days": "Supplier lead time in days",
    "case_pack": "Units per case",
    "category": "Product category",
    "format": "Store format",
}

EPOCH = "2000-01-03"  # a Monday, so (date - EPOCH) % 7 is the weekday with 0 = Monday
LOOKBACK_DAYS = 28


def build(daily, products, start: str | None = None):
    """Feature rows from gold.store_sku_daily (+ silver.products); dates >= start if given."""
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    if start is not None:
        daily = daily.where(F.col("date") >= F.date_sub(F.lit(start), LOOKBACK_DAYS + 1))
    d = daily.select(
        "store_id",
        "sku_id",
        "date",
        "region",
        "format",
        "category",
        F.datediff("date", F.lit(EPOCH)).alias("t"),
        F.col("units_sold").cast("double").alias("u"),
        F.col("stockout_hours").cast("double").alias("so"),
        F.col("trading_hours").cast("double").alias("th"),
        F.col("units_sold_instore").cast("double").alias("u_store"),
        F.col("units_requested_online").cast("double").alias("u_online"),
        F.col("promo_discount").cast("double").alias("promo_discount"),
        F.col("unit_price").cast("double").alias("unit_price"),
    ).withColumn("in_stock", 1 - F.col("so") / F.col("th"))

    w = Window.partitionBy("store_id", "sku_id").orderBy("t")
    div = (
        F.try_divide
    )  # NULL instead of an error when a window has no stock or no sales (ANSI mode)

    def back(col, first, last=1, fn=F.sum):
        return fn(col).over(w.rangeBetween(-first, -last))

    lags = {k: back("u", k, k) for k in (1, 7, 14, 21, 28)}
    same_dow = [lags[k] for k in (7, 14, 21, 28)]
    feats = d.select(
        "store_id",
        "sku_id",
        "date",
        "t",
        "region",
        "format",
        "category",
        "promo_discount",
        "unit_price",
        *[lags[k].alias(f"lag_{k}") for k in (1, 7, 14, 28)],
        back("u", 7, fn=F.avg).alias("mean_7"),
        back("u", 28, fn=F.avg).alias("mean_28"),
        back("u", 28, fn=F.stddev_samp).alias("std_28"),
        div(
            sum(F.coalesce(c, F.lit(0.0)) for c in same_dow),
            sum(c.isNotNull().cast("double") for c in same_dow),
        ).alias("dow_mean_4w"),
        div(back("u", 28), back("in_stock", 28)).alias("instock_rate_28"),
        div(back("so", 7), back("th", 7)).alias("stockout_share_7"),
        div(back("so", 28), back("th", 28)).alias("stockout_share_28"),
        (back("so", 1, 1) > 0).cast("double").alias("censored_prev_day"),
        div(back("u_online", 28), back("u_store", 28) + back("u_online", 28)).alias(
            "online_share_28"
        ),
    )

    wc = Window.partitionBy("region", "category").orderBy("t")
    trend = (
        d.groupBy("region", "category", "t")
        .agg(F.sum("u").alias("cu"))
        .select(
            "region",
            "category",
            "t",
            div(
                F.avg("cu").over(wc.rangeBetween(-7, -1)),
                F.avg("cu").over(wc.rangeBetween(-28, -1)),
            ).alias("category_trend"),
        )
    )
    prod = products.select(
        "sku_id",
        F.col("perishable").cast("double").alias("perishable"),
        F.coalesce("shelf_life_days", F.lit(0)).cast("double").alias("shelf_life_days"),
        F.col("lead_time_days").cast("double").alias("lead_time_days"),
        F.col("case_pack").cast("double").alias("case_pack"),
    )
    out = (
        feats.join(trend, ["region", "category", "t"], "left")
        .join(prod, "sku_id")
        .withColumn("dow", (F.col("t") % 7).cast("double"))
        .withColumn("effective_price", F.col("unit_price") * (1 - F.col("promo_discount")))
    )
    if start is not None:
        out = out.where(F.col("date") >= F.lit(start).cast("date"))
    return out.select(*KEYS, "region", *[F.col(c).cast("double") for c in NUMERIC], *CATEGORICAL)


def planned_promotions(promotions, stores, start: str, end: str):
    """(store_id, sku_id, date, promo_discount) for planned promotions between start and end."""
    from pyspark.sql import functions as F

    return (
        promotions.where((F.col("end_date") >= F.lit(start)) & (F.col("start_date") <= F.lit(end)))
        .withColumn("date", F.explode(F.sequence("start_date", "end_date")))
        .where(F.col("date").between(F.lit(start), F.lit(end)))
        .join(stores.select("store_id", "region"), "region")
        .groupBy("store_id", "sku_id", "date")
        .agg(F.max(F.col("discount_pct") / 100).cast("double").alias("promo_discount"))
    )


def horizon_frame(origin: pd.DataFrame, promos: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Repeat each origin row for `horizon` consecutive days with that day's planned columns.

    origin: KEYS + FEATURES, one row per store x SKU, `date` = the first day to forecast.
    promos: (store_id, sku_id, date, promo_discount) covering those days; missing = no promotion.
    Returns the same columns plus `step` (0 = the origin day), in origin order then step order.
    """
    n = len(origin)
    step = np.tile(np.arange(horizon), n)
    out = origin.loc[origin.index.repeat(horizon)].reset_index(drop=True)
    out["step"] = step
    out["date"] = pd.to_datetime(out["date"]) + pd.to_timedelta(step, unit="D")
    out["dow"] = (out["dow"] + step) % 7
    p = promos.assign(date=pd.to_datetime(promos["date"])).rename(
        columns={"promo_discount": "_planned"}
    )
    out = out.merge(p, on=KEYS, how="left", validate="many_to_one")
    out["promo_discount"] = out.pop("_planned").fillna(0.0).astype(float)
    out["effective_price"] = out["unit_price"] * (1 - out["promo_discount"])
    out["date"] = out["date"].dt.date
    return out
