-- Delta table written by the Lakebase write-back (stage D, src/lakebase/run_write_back.py): the
-- planner decisions from Postgres app.reorder_decisions, read through the UC catalog bigbox_ops_pg.
-- Declared here once (schema, comments, row filter); the write-back only MERGEs new decision ids.

CREATE TABLE IF NOT EXISTS ${catalog}.gold.reorder_decisions (
  decision_id STRING NOT NULL COMMENT 'Decision id (uuid from Postgres app.reorder_decisions)',
  store_id STRING NOT NULL COMMENT 'Store id',
  sku_id STRING NOT NULL COMMENT 'Product SKU',
  region STRING COMMENT 'Store region (from silver.stores); rows are filtered to the regions the current user may see',
  rec_as_of_ts TIMESTAMP COMMENT 'as_of_ts of the gold.recommendations row the planner decided on',
  recommended_qty INT COMMENT 'Order quantity the policy recommended (units)',
  final_qty INT COMMENT 'Order quantity the planner committed (units; 0 when rejected)',
  action STRING COMMENT 'approve (final = recommended), override (planner changed the quantity) or reject (no order)',
  reason STRING COMMENT 'Planner reason, required for override and reject',
  decided_by STRING COMMENT 'Who decided: the app user, or stage-d-evidence for the decisions the stage-D check inserted',
  decided_at TIMESTAMP COMMENT 'When the decision was recorded in Postgres',
  written_back_at TIMESTAMP COMMENT 'When the write-back copied the decision into Delta'
)
CLUSTER BY (decided_at)
COMMENT 'Planner decisions on the at-risk queue, written back from Lakebase (bigbox_ops_pg.app.reorder_decisions) by the bigbox_refresh write_back task. Insert-only; region-filtered via serving.region_allowed.'
WITH ROW FILTER ${catalog}.serving.region_allowed ON (region);
