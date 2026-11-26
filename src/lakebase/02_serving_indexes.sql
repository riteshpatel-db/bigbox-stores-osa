-- Postgres indexes on the synced table for the app's queue reads. CREATE INDEX is one of the few
-- statements allowed on a synced table (no writes). Applied by scripts/setup_lakebase.py once the
-- table is online; idempotent. Point lookups use the primary key (store_id, sku_id) from the sync.

-- A store's at-risk queue, in priority order.
CREATE INDEX IF NOT EXISTS recommendations_synced_store_queue
  ON serving.recommendations_synced (store_id, priority) WHERE queue_reason IS NOT NULL;

-- The all-stores queue for the Director of Operations.
CREATE INDEX IF NOT EXISTS recommendations_synced_queue
  ON serving.recommendations_synced (priority) WHERE queue_reason IS NOT NULL;
