# 01 Lakeflow (ingest): bronze / silver / gold with expectations
- Command: `databricks bundle run bigbox_refresh (backfill); databricks bundle run bigbox_live_drip; databricks bundle run bigbox_refresh; uv run python scripts/evidence_lakeflow.py`
- Run at: updates 2026-11-24T05:25:41.554Z → 2026-11-24T05:43:07.801Z (UTC); queried 2026-11-24T05:47:22Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: pipeline `bigbox_osa_pipeline` (`d84b1f86-3828-4676-87bb-43c03022e65e`); `bigbox_fe_bar.bronze.*`, `bigbox_fe_bar.silver.*`, `bigbox_fe_bar.gold.*`; event log via `event_log('d84b1f86-3828-4676-87bb-43c03022e65e')`
- Git commit: none yet (first commit pending); source in `src/pipeline/`

## Pipeline updates

| update_id | state | cause | started | finished |
|---|---|---|---|---|
| `6600ee08-9479-44a1-a27b-5cb288eced6f` | COMPLETED | JOB_TASK | 2026-11-24T05:25:41.554Z | 2026-11-24T05:30:19.177Z |
| `232d9ca3-90db-49d5-b1b5-d833edb056be` | COMPLETED | JOB_TASK | 2026-11-24T05:40:09.448Z | 2026-11-24T05:43:07.801Z |

## Expectations vs injected defects (event log, latest update `232d9ca3-90db-49d5-b1b5-d833edb056be`)

Silver POS / online lines are materialized views, fully recomputed each update, so the latest update's counts cover every delivered file.

| injected defect | injected (all files) | injected (delivered files) | dataset.expectation | failed (event log) | match |
|---|---|---|---|---|---|
| pos_null_sku | 52,100 | 48,372 | silver.pos_order_lines.sku_id_not_null | 48,372 | yes |
| pos_null_store | 52,632 | 48,904 | silver.pos_order_lines.store_id_not_null | 48,904 | yes |
| pos_null_price | 69,735 | 64,792 | silver.pos_order_lines.unit_price_not_null | 64,792 | yes |
| pos_orphan_sku | 35,044 | 32,528 | silver.pos_order_lines.sku_in_products | 32,528 | yes |
| pos_test_store | 17,580 | 16,363 | silver.pos_order_lines.store_in_stores | 16,363 | yes |
| pos_negative_qty | 17,415 | 16,229 | silver.pos_order_lines.quantity_positive | 16,229 | yes |
| pos_future_ts | 6,985 | 6,523 | silver.pos_order_lines.event_not_after_extract | 6,523 | yes |
| online_overship | 1,495 | 1,394 | silver.online_order_lines.shipped_not_above_requested | 1,394 | yes |

## Other defects, caught in silver / bronze (table queries)

| injected defect | injected (all files) | injected (delivered files) | caught by | caught | match |
|---|---|---|---|---|---|
| pos_duplicate | 170,668 | 158,462 | silver keeps the earliest copy per line_id; sum(_copies - 1) | 158,462 | yes |
| pos_late | 690,429 | 640,889 | is_late = extract_ts after the row's normal batch | 640,889 | yes |
| pos_cents_price | 3,662 | 3,662 | unit_price > 50 x list price, divided by 100 | 3,662 | yes |
| online_late | 31,484 | 29,212 | is_late (silver + quarantine) | 29,212 | yes |
| receipts_uom_cases | 80,137 | 80,137 | uom = CS converted with case_pack | 80,137 | yes |
| online_schema_drift_rows | 1,677,333 | 1,441,555 | new column fulfilment_method populated (schema evolution) | 1,441,555 | yes |

## All expectations with failures (latest update)

| dataset | expectation | passed | failed |
|---|---|---|---|
| online_order_lines | shipped_not_above_requested | 2,940,963 | 1,394 |
| pos_order_lines | event_not_after_extract | 32,429,983 | 6,523 |
| pos_order_lines | quantity_positive | 32,420,277 | 16,229 |
| pos_order_lines | sku_id_not_null | 32,388,134 | 48,372 |
| pos_order_lines | sku_in_products | 32,403,978 | 32,528 |
| pos_order_lines | store_id_not_null | 32,387,602 | 48,904 |
| pos_order_lines | store_in_stores | 32,420,143 | 16,363 |
| pos_order_lines | unit_price_not_null | 32,371,714 | 64,792 |

Expectations with zero failures: inventory_snapshots.keys_not_null, inventory_snapshots.on_hand_not_negative, online_order_lines.order_id_not_null, online_order_lines.order_not_after_extract, online_order_lines.requested_positive, online_order_lines.shipped_not_negative, online_order_lines.sku_id_not_null, online_order_lines.sku_in_products, online_order_lines.store_id_not_null, online_order_lines.store_in_stores.

## Quarantine tables

| table | failed rule | rows |
|---|---|---|
| silver.quarantine_pos_order_lines | event_not_after_extract | 6,523 |
| silver.quarantine_pos_order_lines | quantity_positive | 16,229 |
| silver.quarantine_pos_order_lines | sku_id_not_null | 48,372 |
| silver.quarantine_pos_order_lines | sku_in_products | 32,528 |
| silver.quarantine_pos_order_lines | store_id_not_null | 48,904 |
| silver.quarantine_pos_order_lines | store_in_stores | 16,363 |
| silver.quarantine_pos_order_lines | unit_price_not_null | 64,792 |
| silver.quarantine_online_order_lines | shipped_not_above_requested | 1,394 |

## Bronze rows, parse errors and schema drift

| bronze table | rows | rows with _rescued_data |
|---|---|---|
| pos_order_lines | 32,594,968 | 0 |
| online_order_lines | 2,942,357 | 0 |
| inventory_snapshots | 141,300,924 | 0 |
| replenishment_orders | 2,668,198 | 0 |
| replenishment_receipts | 2,639,976 | 0 |
| write_offs | 601,792 | 0 |
| returns | 441,675 | 0 |

Schema drift: `fulfilment_method` first populated on 2026-04-01, in 1,441,555 rows; earlier rows are NULL (Auto Loader `addNewColumns`).

## Incremental ingestion: rows written per bronze flow, per update

| bronze table | update `6600ee08` | update `232d9ca3` |
|---|---|---|
| assortment | 30,000 | - |
| buyers | 150,000 | - |
| inventory_snapshots | 141,188,904 | 112,020 |
| online_order_lines | 2,940,027 | 2,330 |
| pos_order_lines | 32,569,219 | 25,749 |
| products | 300 | - |
| promotions | 984 | - |
| replenishment_orders | 2,668,198 | - |
| replenishment_receipts | 2,639,976 | - |
| returns | 441,675 | - |
| stores | 100 | - |
| write_offs | 601,792 | - |

## Gold tables

| table | rows |
|---|---|
| gold.store_sku_daily | 10,108,926 |
| gold.inventory_position | 28,005 |
| gold.kpi_store_daily | 36,600 |
| gold.online_fill | 36,600 |
| gold.replenishment_fill | 2,668,198 |

## Gold vs ground truth (history 2025-10-01 → 2026-09-30)

| measure | gold (pipeline) | ground truth (generator) |
|---|---|---|
| in-stock at close | 92.7577% | 92.7577% |
| on-shelf availability (hours) | 94.3144% | 94.3144% |
| online fill rate | 94.2688% | 94.2715% |
| perishable shrink | 9.4055% | 9.4055% |

Online fill differs only because overshipped lines (shipped > requested) are in quarantine, so gold excludes their requested and shipped units.

| units sold (sold in store + shipped online) | units |
|---|---|
| ground truth | 37,630,559 |
| gold.kpi_store_daily | 37,393,671 |
| quarantined POS lines (real sales, excl. test store) | 232,729 |
| quarantined online lines (overship: true shipped = requested) | 1,451 |
| history-dated POS units in live files not yet released (_staging) | 2,708 |
| **unexplained difference** | **0** |
