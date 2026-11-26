#!/usr/bin/env bash
# One-command deploy: loads .env, validates strictly, creates the personas, deploys the bundle and
# applies the Unity Catalog governance in src/governance/.
# Catalog resources require the bundle's direct deployment engine.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
source .env
set +a
export DATABRICKS_BUNDLE_ENGINE=direct

: "${DATABRICKS_CONFIG_PROFILE:?set DATABRICKS_CONFIG_PROFILE in .env}"
# CLI >= 1.27 is required (bundle `postgres` app resources). DATABRICKS_CLI in .env may point at a
# specific binary; it goes first on PATH so every command, including the Python helpers, uses it.
if [[ -n "${DATABRICKS_CLI:-}" ]]; then
  export PATH="$(dirname "$DATABRICKS_CLI"):$PATH"
fi
cli_version="$(databricks --version | sed -E 's/.*v([0-9]+)\.([0-9]+).*/\1 \2/')"
read -r cli_major cli_minor <<<"$cli_version"
if (( cli_major < 1 || (cli_major == 1 && cli_minor < 27) )); then
  echo "Databricks CLI >= 1.27 required, found $(databricks --version); set DATABRICKS_CLI in .env" >&2
  exit 1
fi
: "${BUNDLE_VAR_catalog_storage_root:?set BUNDLE_VAR_catalog_storage_root in .env}"

databricks bundle validate --strict
WAREHOUSE_ID="$(databricks bundle validate -o json | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["variables"]["warehouse_id"]["value"])')"

# Persona service principals (idempotent) and the access model must exist before any pipeline
# update: the pipeline's row filter and column masks reference serving.region_allowed / mask_pii.
uv run python scripts/create_personas.py --warehouse-id "$WAREHOUSE_ID"
# The app's build generates query types as the app's service principal, which needs its UC grants;
# the SP only exists once the app does. So on the very first deploy the app build fails once: grant
# the new SP (06 + Postgres) and deploy again.
if ! databricks bundle deploy "$@"; then
  databricks apps get bigbox-ops-app >/dev/null 2>&1 || exit 1
  echo "bundle deploy failed with the app present: granting its service principal and retrying once"
  uv run python scripts/apply_governance.py --warehouse-id "$WAREHOUSE_ID" --files 06_app_access.sql
  uv run --with 'psycopg[binary]>=3.2' python scripts/setup_lakebase.py \
    --catalog "${BUNDLE_VAR_catalog:-bigbox_fe_bar}"
  databricks bundle deploy "$@"
fi
# The ML (02) and write-back (02b) tables are declared before the code that writes them.
uv run python scripts/apply_governance.py --warehouse-id "$WAREHOUSE_ID" \
  --files 01_access_model.sql 02_ml_tables.sql 02b_lakebase_tables.sql
# Lakebase objects the bundle cannot declare: database, UC catalog, synced table, app schema.
uv run --with 'psycopg[binary]>=3.2' python scripts/setup_lakebase.py \
  --catalog "${BUNDLE_VAR_catalog:-bigbox_fe_bar}"

# Serving views, comments, tags and grants need the pipeline's tables. They are applied here once
# gold exists (skipped on the very first deploy; re-run this script after the first refresh).
if databricks tables get "${BUNDLE_VAR_catalog:-bigbox_fe_bar}.gold.store_sku_daily" >/dev/null 2>&1; then
  uv run python scripts/apply_governance.py --warehouse-id "$WAREHOUSE_ID" \
    --files 03_serving.sql 04_comments_tags.sql 05_grants.sql
  # Genie space "Bigbox Stores - Store Ops" (not a bundle resource): created, or updated only when
  # space.yaml changed; space.json is the exported configuration.
  uv run python src/genie/space.py deploy --catalog "${BUNDLE_VAR_catalog:-bigbox_fe_bar}"
  # The app's service principal exists once the bundle has created the app.
  if databricks apps get bigbox-ops-app >/dev/null 2>&1; then
    uv run python scripts/apply_governance.py --warehouse-id "$WAREHOUSE_ID" --files 06_app_access.sql
  fi
else
  echo "gold not built yet: run bigbox_refresh, then ./scripts/deploy.sh again for 03-06"
fi
