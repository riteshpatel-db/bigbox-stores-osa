# 04 Lakebase: synced recommendations, decisions table, write-back to Delta
- Command: `./scripts/deploy.sh` (bundle project + `scripts/setup_lakebase.py`), `databricks bundle run bigbox_refresh` (run `387755722703731`), `databricks bundle run bigbox_lakebase_check` (run `909089715190901`), then `uv run python scripts/evidence_lakebase.py`
- Run at: refresh 2026-11-25T03:06:32Z → 2026-11-25T03:14:37Z; check 2026-11-25T03:14:51Z → 2026-11-25T03:19:33Z (UTC); evidence queried 2026-11-25T03:21:49Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.serving.recommendations_synced`, `bigbox_fe_bar.gold.recommendations`, `bigbox_fe_bar.gold.reorder_decisions`, `bigbox_ops_pg.app.reorder_decisions`
- Git commit: none yet (first commit pending); source sha256 `7e2bd237dba9` over src/lakebase, src/governance/02b_lakebase_tables.sql, scripts/setup_lakebase.py

## Lakebase resources

| object | state / settings |
|---|---|
| project `bigbox-ops` (bundle resource) | Autoscaling, Postgres 17, owner = deployer, tag project=bigbox-stores-osa |
| endpoint `production/primary` | ACTIVE, 0.5–2 CU, suspends after 300s idle |
| UC catalog `bigbox_ops_pg` | database `bigbox_ops` on branch production |
| synced table `bigbox_fe_bar.serving.recommendations_synced` | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE, TRIGGERED, PK store_id + sku_id, source `bigbox_fe_bar.gold.recommendations` (CDF on) |

Last sync: 2026-11-25T03:14:23.608697Z → 2026-11-25T03:14:26.523071Z, caught up to source version 4 (latest source version 4).

## Triggered sync after each refresh (`bigbox_refresh`)

| task | result | minutes |
|---|---|---|
| pipeline | SUCCESS | 2.2 |
| write_back | SUCCESS | 0.9 |
| features | SUCCESS | 2.2 |
| score | SUCCESS | 2.5 |
| sync | SUCCESS | 1.1 |

`sync` started update `3f709f1e-aaa6-4ab1-b4ee-f605b2e57b4b` of the synced table's pipeline: COMPLETED in 42.3 s, source version 3 → 4 (the `score` task rewrote `gold.recommendations`), state after: SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE. `write_back` in the same run: 0 new decisions (Postgres 0, Delta 0).

## Source vs synced, row by row (task `seed`)

| measure | `gold.recommendations` | Postgres `serving.recommendations_synced` |
|---|---|---|
| rows | 28,005 | 28,005 |
| queue rows (queue_reason not null) | 5,133 | 5,133 |
| keys only on this side | 0 | 0 |

Rows that differ, per column (doubles within 1e-9): on_hand 0, on_order_units 0, forecast_today 0, demand_until_delivery 0, stockout_risk 0, expected_lost_sales 0, recommended_order_qty 0, queue_reason 0, priority 0, as_of_ts 0, features_json 0, model_version 0.

## Lookup latency from a serverless task in the workspace (one connection, after 10 warm-up queries)

| query | n | p50 ms | p95 ms | p99 ms | max ms |
|---|---|---|---|---|---|
| point lookup (PK) | 500 | 2.2 | 3.88 | 4.91 | 20.37 |
| store queue, top 25 | 200 | 2.31 | 4.23 | 5.95 | 10.16 |

## Decisions: Postgres → write-back → Delta

`seed` inserted 20 decisions for the top-priority queue rows of snapshot 2026-10-01 14:00:00+00:00 with the app's INSERT (`decided_by = 'stage-d-evidence'`; approve 7, override 7, reject 6): `app.reorder_decisions` 0 → 20 rows.

| step | inserted into Delta | Postgres rows | Delta rows |
|---|---|---|---|
| `write_back` | 20 | 20 | 20 |
| `write_back_again` (idempotence) | 0 | 20 | 20 |

`verify`: 20 of 20 ids in both Postgres and Delta; column mismatches store_id 0, sku_id 0, recommended_qty 0, final_qty 0, action 0, reason 0, decided_by 0; region missing 0; decided → written back at most 87.4 s.

Now, from the SQL warehouse (owner):

| source | decided_by | action | rows |
|---|---|---|---|
| Delta gold.reorder_decisions | stage-d-evidence | approve | 7 |
| Delta gold.reorder_decisions | stage-d-evidence | override | 7 |
| Delta gold.reorder_decisions | stage-d-evidence | reject | 6 |
| bigbox_ops_pg.app.reorder_decisions | stage-d-evidence | approve | 7 |
| bigbox_ops_pg.app.reorder_decisions | stage-d-evidence | override | 7 |
| bigbox_ops_pg.app.reorder_decisions | stage-d-evidence | reject | 6 |

Row filter on the written-back table: owner sees CENTRAL 2, EAST 10, SOUTH 1, WEST 7; `bigbox-sp-region-east` sees EAST 10. The East persona reading Postgres through the catalog: denied (INSUFFICIENT_PERMISSIONS).

## Lineage (system.access.table_lineage)

| source | target | last seen |
|---|---|---|
| bigbox_fe_bar.silver.stores | bigbox_fe_bar.gold.reorder_decisions | 2026-11-25T03:07:19.514Z |
| bigbox_ops_pg.app.reorder_decisions | bigbox_fe_bar.gold.reorder_decisions | 2026-11-25T03:07:19.514Z |

## Trade-offs

- The synced table holds all of tonight's store × SKUs, not only the queue: TRIGGERED sync needs a Delta source with change data feed (a filtered view would force snapshot mode), and the app's what-if needs any store × SKU's feature row. The app reads the queue through a partial index (`queue_reason IS NOT NULL`).
- Unity Catalog row filters do not reach Postgres. `gold.recommendations` carries no filter and no PII (it is granted to the all-region personas only), and the app's service principal will get SELECT on schema `serving` and INSERT/SELECT on `app` only (stage F).
- The evidence decisions are labelled `decided_by = 'stage-d-evidence'` and kept; real app decisions are told apart by that column.
