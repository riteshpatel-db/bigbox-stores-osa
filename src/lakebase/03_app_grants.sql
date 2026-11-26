-- Postgres grants for the app's service principal (role = its application id, created by the
-- platform when the app's `postgres` resource is bound). Least privilege: read the synced queue,
-- read and insert decisions. No UPDATE or DELETE (decisions are insert-only), no ownership, no other
-- schema. Applied by scripts/setup_lakebase.py once the app exists; idempotent.

GRANT USAGE ON SCHEMA serving TO "${sp_app}";
GRANT SELECT ON serving.recommendations_synced TO "${sp_app}";
GRANT USAGE ON SCHEMA app TO "${sp_app}";
GRANT SELECT, INSERT ON app.reorder_decisions TO "${sp_app}";
