-- Postgres (Lakebase project bigbox-ops, database bigbox_ops): the app's OLTP table. Applied by
-- scripts/setup_lakebase.py; idempotent. The app's service principal is granted USAGE + SELECT +
-- INSERT here in stage F (least privilege: it never owns the schema or updates a decision).
-- Decisions are insert-only, one row per planner action; the write-back MERGEs new ids into
-- Delta bigbox_fe_bar.gold.reorder_decisions.

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.reorder_decisions (
  decision_id      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id         text        NOT NULL,
  sku_id           text        NOT NULL,
  rec_as_of_ts     timestamptz NOT NULL,   -- as_of_ts of the recommendation decided on
  recommended_qty  integer     NOT NULL CHECK (recommended_qty >= 0),
  final_qty        integer     NOT NULL CHECK (final_qty >= 0),
  action           text        NOT NULL CHECK (action IN ('approve', 'override', 'reject')),
  reason           text,
  decided_by       text        NOT NULL,
  decided_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (action <> 'approve' OR final_qty = recommended_qty),
  CHECK (action <> 'reject' OR final_qty = 0),
  CHECK (action = 'approve' OR coalesce(reason, '') <> '')
);

CREATE INDEX IF NOT EXISTS reorder_decisions_store_sku ON app.reorder_decisions (store_id, sku_id);
CREATE INDEX IF NOT EXISTS reorder_decisions_decided_at ON app.reorder_decisions (decided_at);

COMMENT ON TABLE app.reorder_decisions IS
  'Planner decisions on the at-risk queue (approve / override / reject), written by bigbox-ops-app; insert-only.';
