-- Serving layer: one governed definition of every KPI (BUILD_PROMPT section 3).
-- Genie, the app and the deck read these metric views; the BI tools can read them too.
-- Needs the pipeline's silver and gold tables, so it is applied after the first pipeline update.

CREATE OR REPLACE VIEW ${catalog}.serving.sales_lines (
  channel COMMENT 'POS (in-store) or ONLINE (ship-from-store)',
  order_id COMMENT 'POS basket or online order id',
  line_id COMMENT 'Order line id (unique within a channel)',
  sale_date COMMENT 'Date of the sale; returns are attributed to this date',
  store_id COMMENT 'Selling (POS) or fulfilling (online) store',
  region COMMENT 'Store region; rows are filtered to the regions the current user may see',
  format COMMENT 'Store format: SUPERCENTER, STANDARD or COMPACT',
  sku_id COMMENT 'Product SKU',
  category COMMENT 'Product category',
  buyer_id COMMENT 'Loyalty / online account id (pseudonymous); NULL for anonymous POS baskets',
  units COMMENT 'Units sold (POS quantity or online shipped quantity)',
  gross_amount COMMENT 'units x unit_price, before discount',
  discount_amount COMMENT 'Promotion discount on the line',
  item_revenue COMMENT 'gross_amount - discount_amount',
  delivery_fee COMMENT 'Online delivery fee (on the first line of an order; 0 for POS)',
  units_returned COMMENT 'Units of this line returned later',
  refund_amount COMMENT 'Amount refunded for those returns'
)
COMMENT 'Sale lines from both channels with their later returns and the store region. Source of serving.sales_kpis. Region-filtered for the current user via serving.region_allowed.'
AS
WITH lines AS (
  SELECT 'POS' AS channel, order_id, line_id, sale_date, store_id, sku_id, buyer_id,
         quantity AS units, unit_price, discount_amount, 0.0 AS delivery_fee
  FROM ${catalog}.silver.pos_order_lines
  UNION ALL
  SELECT 'ONLINE', order_id, line_id, order_date, store_id, sku_id, buyer_id,
         shipped_qty, unit_price, discount_amount, delivery_fee
  FROM ${catalog}.silver.online_order_lines
),
rets AS (
  SELECT channel, original_line_id AS line_id, sum(quantity) AS units_returned,
         sum(refund_amount) AS refund_amount
  FROM ${catalog}.silver.returns
  GROUP BY channel, original_line_id
)
SELECT l.channel, l.order_id, l.line_id, l.sale_date, l.store_id, s.region, s.format, l.sku_id,
       p.category, l.buyer_id, l.units, l.units * l.unit_price AS gross_amount, l.discount_amount,
       l.units * l.unit_price - l.discount_amount AS item_revenue, l.delivery_fee,
       coalesce(r.units_returned, 0) AS units_returned, coalesce(r.refund_amount, 0) AS refund_amount
FROM lines l
JOIN ${catalog}.silver.stores s USING (store_id)
JOIN ${catalog}.silver.products p USING (sku_id)
LEFT JOIN rets r ON r.channel = l.channel AND r.line_id = l.line_id
WHERE ${catalog}.serving.region_allowed(s.region);

CREATE OR REPLACE VIEW ${catalog}.serving.sales_kpis
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: ${catalog}.serving.sales_lines
comment: >-
  Sales and returns KPIs for Bigbox Stores, both channels. One definition per KPI; ratios are
  re-aggregated correctly at any grain. Returns count against the original sale date.
  Rows are limited to the regions the current user may see.
dimensions:
  - name: sale_date
    expr: sale_date
    comment: Date of the sale
  - name: sale_week
    expr: DATE_TRUNC('WEEK', sale_date)
    comment: Week (Monday) of the sale
  - name: sale_month
    expr: DATE_TRUNC('MONTH', sale_date)
    comment: Month of the sale
  - name: channel
    expr: channel
    comment: POS or ONLINE
  - name: store_id
    expr: store_id
    comment: Store id
  - name: region
    expr: region
    comment: Store region (filtered to the regions the current user may see)
  - name: format
    expr: format
    comment: "Store format: SUPERCENTER, STANDARD or COMPACT"
  - name: category
    expr: category
    comment: Product category
  - name: sku_id
    expr: sku_id
    comment: Product SKU
measures:
  - name: units_sold
    expr: SUM(units)
    comment: Units sold in store plus units shipped online
  - name: item_revenue
    expr: SUM(item_revenue)
    comment: Sum of quantity x unit_price - discount_amount
  - name: total_revenue
    expr: SUM(item_revenue) + SUM(delivery_fee)
    comment: item_revenue plus online delivery fees
  - name: total_orders
    expr: COUNT(DISTINCT concat(channel, ':', order_id))
    comment: Distinct POS baskets and online orders
  - name: avg_order_value
    expr: (SUM(item_revenue) + SUM(delivery_fee)) / COUNT(DISTINCT concat(channel, ':', order_id))
    comment: total_revenue / total_orders
  - name: avg_discount
    expr: SUM(discount_amount) / SUM(gross_amount)
    comment: Revenue-weighted discount rate
  - name: unique_buyers
    expr: COUNT(DISTINCT buyer_id)
    comment: Distinct identified buyers (anonymous POS baskets excluded)
  - name: items_returned
    expr: SUM(units_returned)
    comment: Units returned, attributed to the original sale date
  - name: item_return_rate
    expr: SUM(units_returned) / SUM(units)
    comment: items_returned / units_sold
  - name: returned_orders
    expr: COUNT(DISTINCT CASE WHEN units_returned > 0 THEN concat(channel, ':', order_id) END)
    comment: Distinct orders with at least one returned line
  - name: return_rate
    expr: >-
      COUNT(DISTINCT CASE WHEN units_returned > 0 THEN concat(channel, ':', order_id) END)
      / COUNT(DISTINCT concat(channel, ':', order_id))
    comment: returned_orders / total_orders
  - name: refund_amount
    expr: SUM(refund_amount)
    comment: Amount refunded for returned units
$$;

CREATE OR REPLACE VIEW ${catalog}.serving.availability_kpis
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: ${catalog}.gold.store_sku_daily
comment: >-
  Availability and inventory KPIs per ranged store x SKU x day, from hourly on-hand snapshots.
  gold.store_sku_daily carries the region row filter, so every measure is limited to the regions
  the current user may see. Lost sales and forecast WAPE come from the joined gold.forecast.
joins:
  - name: fc
    source: ${catalog}.gold.forecast
    using:
      - store_id
      - sku_id
      - date
dimensions:
  - name: date
    expr: date
    comment: Trading day
  - name: week
    expr: DATE_TRUNC('WEEK', date)
    comment: Week (Monday)
  - name: month
    expr: DATE_TRUNC('MONTH', date)
    comment: Month of the trading day
  - name: store_id
    expr: store_id
    comment: Store id
  - name: region
    expr: region
    comment: Store region (filtered to the regions the current user may see)
  - name: format
    expr: format
    comment: "Store format: SUPERCENTER, STANDARD or COMPACT"
  - name: category
    expr: category
    comment: Product category
  - name: sku_id
    expr: sku_id
    comment: Product SKU
  - name: perishable
    expr: perishable
    comment: Product has a shelf life
  - name: on_promo
    expr: on_promo
    comment: A promotion discount was in force that day
measures:
  - name: ranged_sku_days
    expr: COUNT(1)
    comment: Ranged store x SKU x days in scope
  - name: in_stock_pct
    expr: SUM(IF(in_stock_at_close, 1, 0)) / COUNT(1)
    comment: Ranged store-SKU-days with closing on hand > 0 / ranged store-SKU-days
  - name: on_shelf_availability
    expr: SUM(trading_hours - stockout_hours) / SUM(trading_hours)
    comment: Ranged store-SKU trading hours with on hand > 0 / ranged store-SKU trading hours
  - name: stockout_hours
    expr: SUM(stockout_hours)
    comment: Store-SKU trading hours that ended with zero on hand
  - name: online_fill_rate
    expr: SUM(units_shipped_online) / SUM(units_requested_online)
    comment: Units shipped / units requested on online orders
  - name: shrink_pct
    expr: >-
      SUM(CASE WHEN perishable THEN expired_units + damaged_units END)
      / SUM(CASE WHEN perishable THEN received_units END)
    comment: Perishables, units written off (expired + damaged) / units received
  - name: units_sold
    expr: SUM(units_sold)
    comment: Units sold in store plus shipped online
  - name: days_of_supply
    expr: SUM(closing_on_hand) / SUM(units_sold)
    comment: Average closing on hand / average daily units sold over the selected days
  - name: inventory_turns
    expr: 365 * SUM(units_sold * unit_cost) / SUM(closing_on_hand * unit_cost)
    comment: Annualised cost of goods sold / average inventory at cost
  - name: lost_sales_units
    expr: SUM(fc.lost_sales_units)
    comment: Forecast demand in trading hours that ended with zero on hand (hour-of-day profile)
  - name: lost_sales
    expr: SUM(fc.lost_sales)
    comment: lost_sales_units x list unit_price
  - name: forecast_wape
    expr: SUM(ABS(fc.uncensored_actual - fc.forecast_units)) / SUM(fc.uncensored_actual)
    comment: Sum of absolute error / sum of actual, on complete store-SKU-days that never stocked out
$$;
