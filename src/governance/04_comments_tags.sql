-- Comments on every gold column and governance tags (layer, domain, kpi, sensitivity, pii_type).
-- Gold tables are pipeline materialized views: table comments come from the pipeline code, column
-- comments are set here (ALTER MATERIALIZED VIEW) and survive pipeline refreshes.

-- ---------- tags ----------
-- The workspace's account enforces governed tag policies, so values come from those policies:
--   layer       bronze | silver | gold            (raw, ml and serving have no allowed value: untagged)
--   domain      sales | supply_chain | operations (subset used here)
--   sensitivity pii | internal | public            (table-level classification)
--   pii_type    name | email | phone               (column-level PII type)
-- kpi is not governed; 'true' marks objects that carry KPI measures.
ALTER SCHEMA ${catalog}.bronze SET TAGS ('layer' = 'bronze');
ALTER SCHEMA ${catalog}.silver SET TAGS ('layer' = 'silver');
ALTER SCHEMA ${catalog}.gold SET TAGS ('layer' = 'gold');

ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily SET TAGS ('layer' = 'gold', 'domain' = 'supply_chain', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily SET TAGS ('layer' = 'gold', 'domain' = 'sales', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position SET TAGS ('layer' = 'gold', 'domain' = 'supply_chain', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill SET TAGS ('layer' = 'gold', 'domain' = 'sales', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill SET TAGS ('layer' = 'gold', 'domain' = 'supply_chain', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER MATERIALIZED VIEW ${catalog}.silver.buyers SET TAGS ('layer' = 'silver', 'domain' = 'sales', 'sensitivity' = 'pii');
ALTER TABLE ${catalog}.serving.region_access SET TAGS ('domain' = 'operations', 'sensitivity' = 'internal');
ALTER VIEW ${catalog}.serving.sales_lines SET TAGS ('domain' = 'sales', 'sensitivity' = 'internal');
ALTER VIEW ${catalog}.serving.sales_kpis SET TAGS ('domain' = 'sales', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER VIEW ${catalog}.serving.availability_kpis SET TAGS ('domain' = 'supply_chain', 'kpi' = 'true', 'sensitivity' = 'internal');
-- stage-C tables (column comments are declared in 02_ml_tables.sql)
ALTER TABLE ${catalog}.gold.forecast SET TAGS ('layer' = 'gold', 'domain' = 'supply_chain', 'kpi' = 'true', 'sensitivity' = 'internal');
ALTER TABLE ${catalog}.gold.recommendations SET TAGS ('layer' = 'gold', 'domain' = 'supply_chain', 'sensitivity' = 'internal');
ALTER TABLE ${catalog}.ml.sweep_results SET TAGS ('domain' = 'supply_chain', 'sensitivity' = 'internal');
ALTER TABLE ${catalog}.ml.backtest_daily SET TAGS ('domain' = 'supply_chain', 'sensitivity' = 'internal');
-- stage-D table (column comments are declared in 02b_lakebase_tables.sql)
ALTER TABLE ${catalog}.gold.reorder_decisions SET TAGS ('layer' = 'gold', 'domain' = 'supply_chain', 'sensitivity' = 'internal');

-- ---------- PII column tags ----------
ALTER MATERIALIZED VIEW ${catalog}.silver.buyers ALTER COLUMN first_name SET TAGS ('pii_type' = 'name');
ALTER MATERIALIZED VIEW ${catalog}.silver.buyers ALTER COLUMN last_name SET TAGS ('pii_type' = 'name');
ALTER MATERIALIZED VIEW ${catalog}.silver.buyers ALTER COLUMN email SET TAGS ('pii_type' = 'email');
ALTER MATERIALIZED VIEW ${catalog}.silver.buyers ALTER COLUMN phone SET TAGS ('pii_type' = 'phone');
ALTER TABLE ${catalog}.serving.region_access ALTER COLUMN pii_cleartext COMMENT 'True only for principals allowed to see buyer PII (name, email, phone) in cleartext';

-- ---------- gold.store_sku_daily ----------
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN store_id COMMENT 'Store id (S001..S100)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN sku_id COMMENT 'Product SKU';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN date COMMENT 'Trading day';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN trading_hours COMMENT 'Hourly on-hand snapshots that day (trading hours with a snapshot)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN stockout_hours COMMENT 'Trading hours that ended with zero on hand';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN closing_on_hand COMMENT 'On hand at the last snapshot of the day (store close)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN min_on_hand COMMENT 'Lowest hourly on hand that day';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN units_sold_instore COMMENT 'Units sold at the POS (valid lines only)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN revenue_instore COMMENT 'POS quantity x unit_price - discount';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN discount_instore COMMENT 'POS promotion discount';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN pos_lines COMMENT 'Valid POS lines';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN units_requested_online COMMENT 'Online units requested (observed demand, even when not shipped)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN units_shipped_online COMMENT 'Online units shipped from this store';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN revenue_online COMMENT 'Online shipped quantity x unit_price - discount';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN received_units COMMENT 'Units received from suppliers, in eaches';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN expired_units COMMENT 'Units written off as expired (perishables)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN damaged_units COMMENT 'Units written off as damaged';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN units_returned COMMENT 'Units returned on this day (by return date)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN refund_amount COMMENT 'Refunds paid on this day';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN promo_discount COMMENT 'Promotion discount in force (0.10 = 10 %), 0 if none';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN region COMMENT 'Store region (row filter column)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN format COMMENT 'Store format';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN category COMMENT 'Product category';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN perishable COMMENT 'Product has a shelf life';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN unit_price COMMENT 'List price';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN unit_cost COMMENT 'Unit cost';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN units_sold COMMENT 'units_sold_instore + units_shipped_online (censored by stockouts)';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN revenue COMMENT 'revenue_instore + revenue_online';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN in_stock_at_close COMMENT 'closing_on_hand > 0';
ALTER MATERIALIZED VIEW ${catalog}.gold.store_sku_daily ALTER COLUMN on_promo COMMENT 'promo_discount > 0';

-- ---------- gold.kpi_store_daily ----------
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN store_id COMMENT 'Store id';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN date COMMENT 'Trading day (sale date for sales and returns)';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN region COMMENT 'Store region (row filter column)';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN format COMMENT 'Store format';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN ranged_sku_days COMMENT 'Component: ranged SKUs that day';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN in_stock_sku_days COMMENT 'Component: ranged SKUs with closing on hand > 0';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN sku_trading_hours COMMENT 'Component: SKU x trading hours';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN sku_hours_on_shelf COMMENT 'Component: SKU x trading hours with on hand > 0';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN online_units_requested COMMENT 'Component: online units requested';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN online_units_shipped COMMENT 'Component: online units shipped';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN perishable_units_received COMMENT 'Component: perishable units received';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN perishable_units_expired COMMENT 'Component: perishable units expired';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN units_sold COMMENT 'Units sold in store + shipped online';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN gross_amount COMMENT 'Component: units x unit_price before discount';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN discount_amount COMMENT 'Component: promotion discounts';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN delivery_fees COMMENT 'Component: online delivery fees';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN total_orders COMMENT 'Distinct POS baskets + online orders that day (not additive across days for distinct counts; use serving.sales_kpis)';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN unique_buyers COMMENT 'Distinct identified buyers that day (not additive across days; use serving.sales_kpis)';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN items_returned COMMENT 'Units returned from sales made that day';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN returned_orders COMMENT 'Orders from that day with at least one return';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN item_revenue COMMENT 'gross_amount - discount_amount';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN total_revenue COMMENT 'item_revenue + delivery_fees';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN avg_order_value COMMENT 'total_revenue / total_orders';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN avg_discount COMMENT 'discount_amount / gross_amount';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN item_return_rate COMMENT 'items_returned / units_sold';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN return_rate COMMENT 'returned_orders / total_orders';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN in_stock_pct COMMENT 'in_stock_sku_days / ranged_sku_days';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN on_shelf_availability COMMENT 'sku_hours_on_shelf / sku_trading_hours';
ALTER MATERIALIZED VIEW ${catalog}.gold.kpi_store_daily ALTER COLUMN online_fill_rate COMMENT 'online_units_shipped / online_units_requested';

-- ---------- gold.inventory_position ----------
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN store_id COMMENT 'Store id';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN sku_id COMMENT 'Product SKU';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN region COMMENT 'Store region (row filter column)';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN on_hand COMMENT 'Latest hourly on hand';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN as_of_ts COMMENT 'Timestamp of that snapshot';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN on_order_units COMMENT 'Units on open purchase orders (no receipt yet)';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN next_due_date COMMENT 'Earliest due date among open purchase orders';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN avg_daily_units_28d COMMENT 'Mean daily units sold over the trailing 28 days (censored by stockouts)';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN days_of_supply COMMENT 'on_hand / avg_daily_units_28d';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN category COMMENT 'Product category';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN case_pack COMMENT 'Units per supplier case';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN lead_time_days COMMENT 'Supplier lead time, days';
ALTER MATERIALIZED VIEW ${catalog}.gold.inventory_position ALTER COLUMN perishable COMMENT 'Product has a shelf life';

-- ---------- gold.online_fill ----------
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN store_id COMMENT 'Fulfilling store';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN date COMMENT 'Order date';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN lines COMMENT 'Valid online order lines';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN units_requested COMMENT 'Units requested';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN units_shipped COMMENT 'Units shipped';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN short_lines COMMENT 'Lines shipped short (shipped < requested)';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN unfilled_lines COMMENT 'Lines with nothing shipped';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN fill_rate COMMENT 'units_shipped / units_requested';
ALTER MATERIALIZED VIEW ${catalog}.gold.online_fill ALTER COLUMN lines UNSET TAGS ('kpi');

-- ---------- gold.replenishment_fill ----------
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN po_line_id COMMENT 'Purchase-order line id';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN po_id COMMENT 'Purchase order (one per store per night)';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN store_id COMMENT 'Ordering store';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN sku_id COMMENT 'Product SKU';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN supplier_id COMMENT 'Supplier';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN order_ts COMMENT 'When the incumbent nightly policy raised the order';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN ordered_qty COMMENT 'Units ordered (eaches)';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN due_date COMMENT 'Due date (order date + lead time)';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN received_qty_ea COMMENT 'Units received, normalised to eaches';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN first_received_ts COMMENT 'First receipt for this line';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN fill_rate COMMENT 'received_qty_ea / ordered_qty (replenishment fill rate)';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN days_late COMMENT 'Receipt date - due date (negative = early)';
ALTER MATERIALIZED VIEW ${catalog}.gold.replenishment_fill ALTER COLUMN status COMMENT 'OPEN, RECEIVED_FULL or RECEIVED_SHORT';
