# Provenance

Where this build ran, who ran it, what it creates, and what it must not touch.

## Session

| Item | Value |
|---|---|
| Built with | Claude Code (Opus 5.5), pairing with the repo owner |
| Session / conversation id | `bf191158-6010-4280-a63c-eedf77cd5b33` |
| Preflight run | 2026-10-30, 22:40–22:42 UTC |
| Git author | `riteshpatel-db <ritesh.patel@databricks.com>` (personal GitHub account; repo https://github.com/riteshpatel-db/bigbox-stores-osa, public; pushed over SSH host alias `github-personal`). The EMU account `ritesh-patel_data` cannot own public repos. |

## Workspace

| Item | Value |
|---|---|
| Host | `https://fevm-serverless-stable-ritesh.cloud.databricks.com` |
| Workspace id | `7474657773731312` |
| Metastore | `c0da88f1-c020-4992-b8c9-c828e556889d` (AWS `us-east-1`; no metastore storage root) |
| CLI profile | `fe-vm-serverless-stable-ritesh` (OAuth U2M, `databricks-cli` auth type) |
| Type | FE Vending Machine serverless-stable workspace (shared with other teams) |
| Workspace expiry | 2027-01-13 (FEVM; verified manually by the owner on 2026-10-30, because the FEVM MCP was unreachable from the build session) |

## Preflight results (2026-10-30)

| Check | Result |
|---|---|
| Auth | `current-user me` → `ritesh.patel@databricks.com`, active, workspace admin |
| CREATE CATALOG | granted directly on the metastore; `bigbox_fe_bar` owned by the builder, so schemas can be created in it |
| Identities for personas | only 3 workspace-local groups, no account groups → personas are service principals |
| SQL warehouse | `FE_BAR_Ritesh` `d5b43df809d40fcf`, serverless PRO Large; `SELECT` succeeded (DBSQL 2026.42) |
| Serverless jobs | one-time run `390170343766971` SUCCESS in 26 s: Python 3.12.3, Spark 4.2.0 (environment 4), read `bigbox_fe_bar.information_schema`, listed `/Volumes/bigbox_fe_bar/raw/landing` |
| Serverless pipelines | API available; first proof is the stage-A pipeline run |
| Model Serving | available; 55 Foundation Model endpoints (51 chat, 3 embedding), no custom endpoints. The LLM is chosen at runtime from this list, never hard-coded |
| Lakebase Autoscaling | projects API available (Postgres 18). Synced-table support on autoscaling projects is checked at the start of stage D |
| Genie | spaces API available |
| Databricks Apps | available (existing apps running) |

## Resources this build creates

Only these names. Anything else needs the owner's approval first.

| Resource | Name | Status at preflight |
|---|---|---|
| Catalog | `bigbox_fe_bar` (`prevent_destroy`) | created by the bundle |
| Schemas | `raw`, `bronze`, `silver`, `gold`, `ml`, `serving` | created by the bundle |
| Volume | `bigbox_fe_bar.raw.landing` | created by the bundle |
| Bundle | `bigbox-stores-osa` (target `dev`) | deployed |
| Pipeline | `bigbox_osa_pipeline` (`d84b1f86-3828-4676-87bb-43c03022e65e`) | created 2026-11-23 (stage A) |
| Jobs | `bigbox_generate_data` (`779275887426580`), `bigbox_live_drip` (`995706476776113`, schedule paused) | created 2026-11-23 (stage 0) |
| Job | `bigbox_refresh` (`253060125385282`, schedule paused; pipeline → features → score → sync, plus write_back) | created 2026-11-23 (stage A), ML tasks added 2026-11-24, Lakebase tasks 2026-11-25 UTC |
| Job | `bigbox_lakebase_check` (`224787984707293`, no schedule; seed → write_back → verify → write_back_again) | created 2026-11-25 UTC (stage D, approved that session) |
| Job | `bigbox_ml_train` (`486211536028653`) | created 2026-11-24 (stage C, approved that day) |
| MLflow experiment | `/Users/ritesh.patel@databricks.com/bigbox_demand_forecast` (`3164772271447205`) | created 2026-11-24 (stage C, approved that day) |
| Tables | `bigbox_fe_bar.gold.forecast`, `gold.recommendations`; helper tables `ml.sweep_results`, `ml.backtest_daily` (approved 2026-11-24) | created 2026-11-24 (stage C, `src/governance/02_ml_tables.sql`) |
| Feature table | `bigbox_fe_bar.ml.store_sku_features` | created 2026-11-24 (stage C) |
| UC model | `bigbox_fe_bar.ml.demand_lgbm` (`@champion` v1, `@challenger` v2) | created 2026-11-24 (stage C) |
| Serving endpoints | `bigbox-demand-forecast` (`703553fdc99c4070a041b589c913e522`); `bigbox-reorder-agent` (P1, not created) | created 2026-11-24 (stage C) |
| Lakebase | project `bigbox-ops` (Autoscaling, Postgres 17, uid `6802ba52-d611-4608-94c2-aaa97a9ae416`; branch `production`, endpoint `primary` 0.5–2 CU), database `bigbox_ops` (resource id `bigbox-ops`), UC catalog `bigbox_ops_pg` | created 2026-11-25 UTC (stage D) |
| Synced / OLTP tables | `bigbox_fe_bar.serving.recommendations_synced` (TRIGGERED; its sync pipeline `e1d1b737-4300-4602-80c8-dabb0e38df80` is created by the synced table, storage schema `bigbox_fe_bar.serving`); Postgres `app.reorder_decisions` → Delta `bigbox_fe_bar.gold.reorder_decisions` | created 2026-11-25 UTC (stage D) |
| Service principals | `bigbox-sp-ops-director` (`bca34f6d-2c4f-44de-a3fd-9dbcd50d3de2`), `bigbox-sp-region-east` (`3c86153e-fa92-42a9-8954-3fd9fba0af46`), `bigbox-sp-analyst` (`7043dc63-81b4-4245-82e2-29a7cf6c0da5`); CAN_USE on `FE_BAR_Ritesh` | created 2026-11-24 (stage B) |
| Governance objects | `bigbox_fe_bar.serving.region_access` (table), `serving.region_allowed`, `serving.mask_pii` (functions), `serving.sales_lines` (view), `serving.sales_kpis`, `serving.availability_kpis` (metric views) | created 2026-11-24 (stage B) |
| Genie space | "Bigbox Stores - Store Ops" (`01f1e884bece1d39994e9ba5a98ab5f1`, warehouse `FE_BAR_Ritesh`; config `src/genie/space.json`) | created 2026-11-25 UTC (stage E) |
| App | `bigbox-ops-app` (bundle resource; URL https://bigbox-ops-app-7474657773731312.aws.databricksapps.com; its service principal `app-2pidc0 bigbox-ops-app`, `3bb6052f-81da-45ab-9170-e84a4eef772e`, created by the platform with the app) | created 2026-11-25 UTC (stage F) |

Shared resource used but not owned: the warehouse `FE_BAR_Ritesh` (don't resize it). Its ACL was extended with CAN_USE for the three personas (owner and admins entries unchanged).

## Do not touch

This is a shared workspace, and other teams create resources in it daily. The rule: **create or modify only the
resources listed above.** Never alter, grant on, or delete anything else. Counts listed at 2026-10-30T22:42:16Z:

| Kind | Count | Notes |
|---|---|---|
| Catalogs (other than `bigbox_fe_bar`) | 44 | including the owner's `rp_demo` and `serverless_stable_ritesh_catalog` |
| SQL warehouses | 3 | `Serverless Starter Warehouse`, `MyWarehouse`, `validation_Warehouse` |
| Lakebase projects | 1 | `ritesh-test` |
| Apps | 3 | the owner's other apps |
| Pipelines / jobs | 4 / 3 | none belong to this build |
| Genie spaces | 3 | none belong to this build |
| Serving endpoints | 55 | all Foundation Model API |
| Service principals | 5 | none belong to this build |
| External locations | 103 | the catalog's storage root lives under one; never modify it |

Other teams' resource names are kept out of this public repo (some of them name real organisations). The full,
dated inventory is kept privately outside the repo, and it is re-listed and diffed at the start and end of each session.
