-- Tables written by the stage-C notebooks (src/ml/). Their schema, comments, row filter and change
-- data feed are declared once here; the notebooks only write rows (INSERT OVERWRITE / MERGE).
-- CREATE ... IF NOT EXISTS keeps the data on a re-run; a schema change means dropping the table.

CREATE TABLE IF NOT EXISTS ${catalog}.gold.forecast (
  store_id STRING NOT NULL COMMENT 'Store id',
  sku_id STRING NOT NULL COMMENT 'Product SKU',
  date DATE NOT NULL COMMENT 'Day forecast; the forecast uses only what was known at the start of the day',
  region STRING COMMENT 'Store region; rows are filtered to the regions the current user may see',
  forecast_units DOUBLE COMMENT 'Forecast demand (units, in store + online requested) from the model version below',
  uncensored_actual DOUBLE COMMENT 'Units sold when the day is complete and never stocked out (sales = demand); NULL otherwise. The actual for forecast_wape',
  stockout_demand_share DOUBLE COMMENT 'Share of the day''s demand profile in trading hours that ended with zero on hand',
  lost_sales_units DOUBLE COMMENT 'forecast_units x stockout_demand_share: estimated demand lost to stockouts',
  lost_sales DOUBLE COMMENT 'lost_sales_units x list unit_price',
  model_version STRING COMMENT 'Version of bigbox_fe_bar.ml.demand_lgbm that scored the row',
  scored_at TIMESTAMP COMMENT 'When the row was scored'
)
CLUSTER BY (date, store_id)
COMMENT 'Daily demand forecast per ranged store x SKU from the @champion model, with the lost sales it implies on stocked-out hours. Region-filtered via serving.region_allowed.'
WITH ROW FILTER ${catalog}.serving.region_allowed ON (region);

CREATE TABLE IF NOT EXISTS ${catalog}.gold.recommendations (
  store_id STRING NOT NULL COMMENT 'Store id',
  sku_id STRING NOT NULL COMMENT 'Product SKU',
  region STRING COMMENT 'Store region (no row filter on this table, see the table comment)',
  format STRING COMMENT 'Store format',
  category STRING COMMENT 'Product category',
  perishable BOOLEAN COMMENT 'Product has a shelf life',
  as_of_ts TIMESTAMP COMMENT 'Latest on-hand snapshot the recommendation is based on',
  forecast_date DATE COMMENT 'First forecast day (the day of as_of_ts)',
  on_hand BIGINT COMMENT 'On hand at as_of_ts',
  on_order_units BIGINT COMMENT 'Units on open purchase orders',
  lead_time_days INT COMMENT 'Supplier lead time in days',
  case_pack INT COMMENT 'Units per case; orders are whole cases',
  shelf_life_days INT COMMENT 'Shelf life in days (0 for non-perishables)',
  unit_price DOUBLE COMMENT 'List price',
  unit_cost DOUBLE COMMENT 'Unit cost',
  forecast_today DOUBLE COMMENT 'Forecast demand for forecast_date (whole day)',
  forecast_next_7d DOUBLE COMMENT 'Forecast demand over the 7 days after forecast_date',
  demand_until_delivery DOUBLE COMMENT 'Forecast demand for the rest of today plus the lead time (an order placed tonight arrives after it)',
  sigma_daily DOUBLE COMMENT 'Daily demand standard deviation used for safety stock and risk',
  stockout_risk DOUBLE COMMENT 'P(demand until delivery > on hand + on order), normal approximation',
  expected_lost_units DOUBLE COMMENT 'Expected units short before the next delivery (normal loss function)',
  expected_lost_sales DOUBLE COMMENT 'expected_lost_units x unit_price; the queue is ranked by it',
  days_of_supply DOUBLE COMMENT 'on_hand / mean forecast daily demand over the next 7 days; NULL if nothing is expected to sell',
  overstock_flag BOOLEAN COMMENT 'days_of_supply above the threshold (perishables: shelf life; others: policy.yaml)',
  reorder_point DOUBLE COMMENT 'Order tonight when projected on hand + on order at close falls below this',
  order_up_to DOUBLE COMMENT 'Target position after tonight''s order',
  recommended_order_qty BIGINT COMMENT 'Units to order tonight, whole cases (0 = no order)',
  recommended_order_value DOUBLE COMMENT 'recommended_order_qty x unit_cost',
  queue_reason STRING COMMENT 'STOCKOUT_RISK, OVERSTOCK or NULL (not in the queue)',
  priority INT COMMENT 'Queue rank within the run, 1 = highest expected lost sales',
  features_json STRING COMMENT 'Feature row for forecast_date (JSON) that the app edits for a what-if call to the endpoint',
  model_version STRING COMMENT 'Version of bigbox_fe_bar.ml.demand_lgbm used',
  scored_at TIMESTAMP COMMENT 'When the recommendation was computed'
)
COMMENT 'Tonight''s reorder recommendation per ranged store x SKU, with stockout risk and overstock flags. No PII and no row filter: it is synced to Lakebase, where Unity Catalog row filters and masks would not apply; the East persona is therefore not granted it.'
TBLPROPERTIES (delta.enableChangeDataFeed = true);
-- Re-applied on every deploy: CREATE ... IF NOT EXISTS leaves an existing table's comment as it was.
COMMENT ON TABLE ${catalog}.gold.recommendations IS 'Tonight''s reorder recommendation per ranged store x SKU, with stockout risk and overstock flags. No PII and no row filter: it is synced to Lakebase, where Unity Catalog row filters and masks would not apply; the East persona is therefore not granted it.';

CREATE TABLE IF NOT EXISTS ${catalog}.ml.sweep_results (
  candidate STRING COMMENT 'Candidate name',
  algorithm STRING COMMENT 'Model family',
  run_id STRING COMMENT 'MLflow run id',
  tuned BOOLEAN COMMENT 'Hyperparameters chosen by the Optuna search on the validation window',
  val_wape DOUBLE COMMENT 'WAPE on the validation window (uncensored days), used for tuning only',
  holdout_wape DOUBLE COMMENT 'WAPE on the shared 8-week holdout, uncensored store-SKU-days',
  holdout_bias DOUBLE COMMENT '(sum forecast - sum actual) / sum actual on the same rows',
  holdout_rows BIGINT COMMENT 'Holdout rows scored',
  train_rows BIGINT COMMENT 'Training rows (0 for rules without fitting)',
  fit_seconds DOUBLE COMMENT 'Final fit time',
  params STRING COMMENT 'Hyperparameters (JSON)',
  model_version STRING COMMENT 'Registered version of ml.demand_lgbm, if registered',
  alias STRING COMMENT 'champion / challenger, if any',
  run_at TIMESTAMP COMMENT 'When the sweep ran'
)
COMMENT 'One row per demand-model candidate on the shared holdout (2026-08-06 .. 2026-09-30).';

CREATE TABLE IF NOT EXISTS ${catalog}.ml.backtest_daily (
  policy STRING COMMENT 'history (the generator''s own run), incumbent (replayed) or ml (policy b)',
  service_level DOUBLE COMMENT 'Target service level for policy ml; NULL otherwise',
  date DATE COMMENT 'Replayed day',
  segment STRING COMMENT 'slow (mean daily units sold below policy.yaml threshold over the 8 weeks before the holdout) or other',
  perishable BOOLEAN COMMENT 'Product has a shelf life',
  cell_days DOUBLE COMMENT 'Ranged store-SKU-days',
  trading_hours DOUBLE COMMENT 'Store-SKU trading hours',
  stockout_hours DOUBLE COMMENT 'Store-SKU trading hours that ended with zero on hand',
  in_stock_at_close DOUBLE COMMENT 'Store-SKU-days with on hand > 0 at close',
  demand_units DOUBLE COMMENT 'True demand (ground truth, identical for every policy)',
  sold_units DOUBLE COMMENT 'Units sold in store + shipped online',
  lost_units DOUBLE COMMENT 'demand_units - sold_units',
  lost_sales DOUBLE COMMENT 'lost_units x list price',
  lost_margin DOUBLE COMMENT 'lost_units x (list price - unit cost)',
  received_units DOUBLE COMMENT 'Units received from suppliers',
  expired_units DOUBLE COMMENT 'Units written off as expired',
  damaged_units DOUBLE COMMENT 'Units written off as damaged',
  waste_cost DOUBLE COMMENT '(expired + damaged) x unit cost',
  closing_units DOUBLE COMMENT 'Units on hand at close',
  closing_cost DOUBLE COMMENT 'On hand at close x unit cost',
  sold_cost DOUBLE COMMENT 'Units sold x unit cost',
  order_lines DOUBLE COMMENT 'Purchase-order lines raised that night',
  run_id STRING COMMENT 'Job run that produced the row'
)
COMMENT 'Backtest: the 8 held-out weeks of true demand replayed under each policy with identical supply and damage draws, summed per day x segment x perishable.';
