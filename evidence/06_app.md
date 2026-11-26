# 06 App: bigbox-ops-app deployed, its bindings, a real session and an HTTP smoke test
- Command: `./scripts/deploy.sh` (bundle resource `resources/bigbox_ops_app.app.yml`), `databricks bundle run bigbox_ops_app`, `./scripts/smoke_test_app.sh`, then `uv run python scripts/evidence_app.py`
- Run at: deployment 2026-11-25T05:47:56Z (UTC); smoke test 2026-11-25T05:15:07Z → 2026-11-25T05:16:08Z; evidence queried 2026-11-25T05:50:42Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.serving.availability_kpis`, `bigbox_fe_bar.serving.sales_kpis`, `bigbox_fe_bar.serving.recommendations_synced`, `bigbox_ops_pg.app.reorder_decisions`, `bigbox_fe_bar.gold.reorder_decisions`
- Git commit: none yet (first commit pending); source sha256 `98b87a03c274` over src/app/server, src/app/client/src, src/app/config, src/app/app.yaml, src/app/package.json

## Deployment

App `bigbox-ops-app` at https://bigbox-ops-app-7474657773731312.aws.databricksapps.com: app status RUNNING, compute ACTIVE. Active deployment `01f1e893c38c1ee8a6f392feaa5e882e`: SUCCEEDED (App started successfully), mode SNAPSHOT. Runs as its service principal `app-2pidc0 bigbox-ops-app` (`3bb6052f-81da-45ab-9170-e84a4eef772e`). User API scopes requested in the bundle: ['dashboards.genie'] (Genie runs as the signed-in user, with their own grants); effective, with the platform's defaults: ['dashboards.genie', 'iam.access-control:read', 'iam.current-user:read'].

Deployments (`databricks apps list-deployments`); the session and the smoke test below ran on the one active at their time:

| deployment | created (UTC) | state | source |
|---|---|---|---|
| `01f1e893c38c1ee8a6f392feaa5e882e` | 2026-11-25T05:47:56Z | SUCCEEDED | `src/app` |
| `01f1e893aa52147281e386e7c6235774` | 2026-11-25T05:47:14Z | SUCCEEDED | `src/app` |
| `01f1e88ea44818f3bb030b4b21ab7e58` | 2026-11-25T05:11:16Z | SUCCEEDED | `app` |
| `01f1e88e17cb1349ad83dd7f3929eafc` | 2026-11-25T05:07:20Z | SUCCEEDED | `app` |
| `01f1e88d47211ed69546427978f4452e` | 2026-11-25T05:01:30Z | FAILED | `app` |

The first build failed by construction (the new service principal had no grants yet, HANDOFF trap 50); the last two redeploy the same source from `src/app` after the repository move.

Resource bindings as the Apps API stores them (declared in the bundle):

| name | type | target | permission |
|---|---|---|---|
| sql-warehouse | sql_warehouse | `d5b43df809d40fcf` | CAN_USE |
| postgres | postgres | `projects/bigbox-ops/branches/production/databases/bigbox-ops` | CAN_CONNECT_AND_CREATE |
| serving-endpoint | serving_endpoint | `bigbox-demand-forecast` | CAN_QUERY |
| genie-space | genie_space | `01f1e884bece1d39994e9ba5a98ab5f1` | CAN_RUN |

`src/app/app.yaml`:

```yaml
command: ['npm', 'run', 'start']
health_check:
  path: /health
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: DATABRICKS_GENIE_SPACE_ID
    valueFrom: genie-space
  - name: LAKEBASE_ENDPOINT
    valueFrom: postgres
  - name: DATABRICKS_SERVING_ENDPOINT_NAME
    valueFrom: serving-endpoint
```

## Least privilege of the app's service principal

Unity Catalog (`SHOW GRANTS`): READ METADATA on metastore `metastore_aws_us_east_1`; SELECT on table `bigbox_fe_bar.serving.availability_kpis`; SELECT on table `bigbox_fe_bar.serving.sales_kpis`; USE CATALOG on catalog `bigbox_fe_bar`; USE SCHEMA on schema `bigbox_fe_bar.serving`. Row filter mapping: region *, PII cleartext false. Postgres (`information_schema.role_table_grants`): `app.reorder_decisions` INSERT, SELECT; `serving.recommendations_synced` SELECT. No other table, schema or ownership.

## A real session (`databricks apps logs`, user ritesh.patel@databricks.com)

Structured events the app logs for each request (`server/routes/ops.ts`), browser session after the smoke test: 23 events, 7 queue, 6 item, 5 whatif, 5 decision. Excerpt (first item opened, what-if, override, queue refreshed; then the last decisions):

```text
{"event":"item","ts":"2026-11-25T05:19:50.648Z","store_id":"S073","sku_id":"SKU0263"}
{"event":"item","ts":"2026-11-25T05:20:32.732Z","store_id":"S073","sku_id":"SKU0263"}
{"event":"whatif","ts":"2026-11-25T05:20:37.591Z","store_id":"S073","sku_id":"SKU0263","promo_discount":0.1,"unit_price":15.99,"baseline":10.359772374490197,"whatif":13.87847710936905,"ms":102}
{"event":"decision","ts":"2026-11-25T05:22:06.025Z","store_id":"S073","sku_id":"SKU0263","action":"override","recommended":144,"final":145,"decision_id":"63af55bf-7209-4f0e-924f-88c65be93ace"}
{"event":"queue","ts":"2026-11-25T05:22:06.215Z","offset":0,"rows":25,"ms":86}
{"event":"decision","ts":"2026-11-25T05:23:26.677Z","store_id":"S065","sku_id":"SKU0263","action":"reject","recommended":162,"final":0,"decision_id":"147406e3-c264-4a41-8419-8d547da497a6"}
{"event":"decision","ts":"2026-11-25T05:24:03.296Z","store_id":"S021","sku_id":"SKU0263","action":"override","recommended":120,"final":145,"decision_id":"ff2a3ecb-9e21-4f6d-ad39-4fb56ef07a28"}
{"event":"decision","ts":"2026-11-25T05:25:01.467Z","store_id":"S094","sku_id":"SKU0263","action":"override","recommended":90,"final":103,"decision_id":"b97af256-16b5-4b41-b624-ae4ad6222f2d"}
{"event":"decision","ts":"2026-11-25T05:25:36.838Z","store_id":"S061","sku_id":"SKU0238","action":"override","recommended":8,"final":8,"decision_id":"6c6ae5a6-1904-47d4-92b1-953f51b43e6a"}
```

Decisions of this session: 5 (override, reject); in Postgres 5, in Delta `gold.reorder_decisions` after the next write-back 5.

Genie in the same session (runs as the user): 4 questions posted to `/api/genie/default/messages`, 4 answered HTTP 200. The conversation, read back through the Genie API:

| question | status | Genie SQL (start) |
|---|---|---|
| how much revenue from all stores have been lost due to stockouts | COMPLETED | `SELECT MEASURE(`lost_sales`) AS `lost_sales` FROM `bigbox_fe_bar`.`ser` |
| break this down by region | COMPLETED | `SELECT `region`, MEASURE(`lost_sales`) AS `lost_sales` FROM `bigbox_fe` |
| show me top 5 items that lost revenue due to stockout | COMPLETED | `SELECT `sku_id`, MEASURE(`lost_sales`) AS `lost_sales` FROM `bigbox_fe` |
| show me their category | COMPLETED | `SELECT `sku_id`, `category`, MEASURE(`lost_sales`) AS `lost_sales` FRO` |

## HTTP smoke test of the deployed URL (`scripts/smoke_test_app.sh`, token generated at runtime)

| step | request | result |
|---|---|---|
| health | GET /api/health | 200: 28005 synced rows, 5133 in the queue, Lakebase 74 ms |
| identity | GET /api/whoami | 200 |
| queue | GET /api/queue?open=true&limit=5 | 200: 5112 open items in 67 ms; first S075/SKU0263 |
| what-if | POST /api/whatif (15 % off) | 200: batch 15.8182, endpoint same row 15.8182, what-if 19.6198 units, 106 ms |
| decision | POST /api/decisions (reject, labelled smoke test) | 201: `cbbe8f4d-75e8-4e3d-b22d-67db1d35adf3` |
| Postgres rows | `bigbox_ops_pg.app.reorder_decisions` | 21 → 22 |
| write-back | `bigbox_refresh` task write_back only, run 497481628286940 | SUCCESS |
| Delta rows | `bigbox_fe_bar.gold.reorder_decisions` | 21 → 22; the new id found 1 time(s) |

Verdict: PASS.
