# 02b Unity Catalog: comments, tags and lineage
- Command: `uv run python scripts/evidence_governance.py` (SQL statements on warehouse `d5b43df809d40fcf`, each persona authenticated with its own CLI profile)
- Run at: 2026-11-25T03:53:15Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.serving.region_access`, `bigbox_fe_bar.serving.region_allowed`, `bigbox_fe_bar.serving.mask_pii`, `bigbox_fe_bar.serving.sales_lines`, `bigbox_fe_bar.serving.sales_kpis`, `bigbox_fe_bar.serving.availability_kpis`, `bigbox_fe_bar.gold.*`, `bigbox_fe_bar.silver.buyers`
- Git commit: none yet (first commit pending); source in `src/governance/`, `src/pipeline/`

## Comment coverage, gold and serving (information_schema)

| object | columns | columns with comment | table comment |
|---|---|---|---|
| gold.forecast | 11 | 11 | true |
| gold.inventory_position | 13 | 13 | true |
| gold.kpi_store_daily | 29 | 29 | true |
| gold.online_fill | 8 | 8 | true |
| gold.recommendations | 33 | 33 | true |
| gold.reorder_decisions | 12 | 12 | true |
| gold.replenishment_fill | 13 | 13 | true |
| gold.store_sku_daily | 30 | 30 | true |
| serving.availability_kpis | 22 | 22 | true |
| serving.recommendations_synced | 33 | 0 | true |
| serving.region_access | 4 | 4 | true |
| serving.sales_kpis | 21 | 21 | true |
| serving.sales_lines | 17 | 17 | true |

`serving.recommendations_synced` is a Lakebase synced table: UC rejects comments on it (`UPDATE_OR_DELETE_FORBIDDEN_FOR_FOREIGN_SECURABLE`, only the owner can change); its source `gold.recommendations` is fully commented. Omitted: 1 pipeline event-log table(s) in serving (system-managed).

## Tags (table and column)

Tag values follow the account's governed tag policies: `layer` allows only bronze / silver / gold, so raw, ml and serving carry no layer tag; PII types use the governed `pii_type` key and table classification the governed `sensitivity` key.

| object | tags |
|---|---|
| gold.forecast | domain=supply_chain, kpi=true, layer=gold, sensitivity=internal |
| gold.inventory_position | domain=supply_chain, kpi=true, layer=gold, sensitivity=internal |
| gold.kpi_store_daily | domain=sales, kpi=true, layer=gold, sensitivity=internal |
| gold.online_fill | domain=sales, kpi=true, layer=gold, sensitivity=internal |
| gold.recommendations | domain=supply_chain, layer=gold, sensitivity=internal |
| gold.reorder_decisions | domain=supply_chain, layer=gold, sensitivity=internal |
| gold.replenishment_fill | domain=supply_chain, kpi=true, layer=gold, sensitivity=internal |
| gold.store_sku_daily | domain=supply_chain, kpi=true, layer=gold, sensitivity=internal |
| ml.backtest_daily | domain=supply_chain, sensitivity=internal |
| ml.store_sku_features | domain=supply_chain, sensitivity=internal |
| ml.sweep_results | domain=supply_chain, sensitivity=internal |
| serving.availability_kpis | domain=supply_chain, kpi=true, sensitivity=internal |
| serving.region_access | domain=operations, sensitivity=internal |
| serving.sales_kpis | domain=sales, kpi=true, sensitivity=internal |
| serving.sales_lines | domain=sales, sensitivity=internal |
| silver.buyers | domain=sales, layer=silver, sensitivity=pii |
| silver.buyers.email | pii_type=email |
| silver.buyers.first_name | pii_type=name |
| silver.buyers.last_name | pii_type=name |
| silver.buyers.phone | pii_type=phone |

## Table lineage (system.access.table_lineage)

| source | target | via | last seen (UTC date) |
|---|---|---|---|
| gold.store_sku_daily | gold.forecast | JOB | 2026-11-25 |
| ml.store_sku_features | gold.forecast | JOB | 2026-11-25 |
| silver.inventory_snapshots | gold.forecast | JOB | 2026-11-25 |
| gold.replenishment_fill | gold.inventory_position | PIPELINE | 2026-11-25 |
| gold.store_sku_daily | gold.inventory_position | PIPELINE | 2026-11-25 |
| silver.inventory_snapshots | gold.inventory_position | PIPELINE | 2026-11-25 |
| silver.products | gold.inventory_position | PIPELINE | 2026-11-25 |
| silver.stores | gold.inventory_position | PIPELINE | 2026-11-25 |
| gold.store_sku_daily | gold.kpi_store_daily | PIPELINE | 2026-11-25 |
| silver.online_order_lines | gold.kpi_store_daily | PIPELINE | 2026-11-25 |
| silver.pos_order_lines | gold.kpi_store_daily | PIPELINE | 2026-11-25 |
| silver.returns | gold.kpi_store_daily | PIPELINE | 2026-11-25 |
| silver.stores | gold.kpi_store_daily | PIPELINE | 2026-11-25 |
| silver.online_order_lines | gold.online_fill | PIPELINE | 2026-11-25 |
| silver.stores | gold.reorder_decisions | JOB | 2026-11-25 |
| bigbox_ops_pg.app.reorder_decisions | gold.reorder_decisions | JOB | 2026-11-25 |
| silver.replenishment_orders | gold.replenishment_fill | PIPELINE | 2026-11-25 |
| silver.replenishment_receipts | gold.replenishment_fill | PIPELINE | 2026-11-25 |
| silver.inventory_snapshots | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.online_order_lines | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.pos_order_lines | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.products | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.promotions | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.replenishment_receipts | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.returns | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.stores | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| silver.write_offs | gold.store_sku_daily | PIPELINE | 2026-11-25 |
| gold.store_sku_daily | ml.store_sku_features | JOB | 2026-11-25 |
| silver.products | ml.store_sku_features | JOB | 2026-11-25 |
| gold.forecast | serving.availability_kpis | query | 2026-11-25 |
| gold.store_sku_daily | serving.availability_kpis | query | 2026-11-25 |
| gold.recommendations | serving.recommendations_synced | PIPELINE | 2026-11-25 |
| serving.sales_lines | serving.sales_kpis | query | 2026-11-25 |
| silver.online_order_lines | serving.sales_lines | query | 2026-11-25 |
| silver.pos_order_lines | serving.sales_lines | query | 2026-11-25 |
| silver.products | serving.sales_lines | query | 2026-11-25 |
| silver.returns | serving.sales_lines | query | 2026-11-25 |
| silver.stores | serving.sales_lines | query | 2026-11-25 |
| bronze.assortment | silver.assortment | PIPELINE | 2026-11-25 |
| bronze.buyers | silver.buyers | PIPELINE | 2026-11-25 |
| bronze.inventory_snapshots | silver.inventory_snapshots | PIPELINE | 2026-11-25 |
| bronze.online_order_lines | silver.online_order_lines | PIPELINE | 2026-11-25 |
| silver.products | silver.online_order_lines | PIPELINE | 2026-11-25 |
| silver.stores | silver.online_order_lines | PIPELINE | 2026-11-25 |
| bronze.pos_order_lines | silver.pos_order_lines | PIPELINE | 2026-11-25 |
| silver.products | silver.pos_order_lines | PIPELINE | 2026-11-25 |
| silver.stores | silver.pos_order_lines | PIPELINE | 2026-11-25 |
| bronze.products | silver.products | PIPELINE | 2026-11-25 |
| bronze.promotions | silver.promotions | PIPELINE | 2026-11-25 |
| bronze.online_order_lines | silver.quarantine_online_order_lines | PIPELINE | 2026-11-25 |
| silver.products | silver.quarantine_online_order_lines | PIPELINE | 2026-11-25 |
| silver.stores | silver.quarantine_online_order_lines | PIPELINE | 2026-11-25 |
| bronze.pos_order_lines | silver.quarantine_pos_order_lines | PIPELINE | 2026-11-25 |
| silver.products | silver.quarantine_pos_order_lines | PIPELINE | 2026-11-25 |
| silver.stores | silver.quarantine_pos_order_lines | PIPELINE | 2026-11-25 |
| bronze.replenishment_orders | silver.replenishment_orders | PIPELINE | 2026-11-25 |
| bronze.replenishment_receipts | silver.replenishment_receipts | PIPELINE | 2026-11-25 |
| silver.products | silver.replenishment_receipts | PIPELINE | 2026-11-25 |
| bronze.returns | silver.returns | PIPELINE | 2026-11-25 |
| bronze.stores | silver.stores | PIPELINE | 2026-11-25 |
| bronze.write_offs | silver.write_offs | PIPELINE | 2026-11-25 |

Raw volume → bronze: 104 lineage rows target a bronze table, with 0 source tables and 0 source paths recorded. The Auto Loader reads of `/Volumes/bigbox_fe_bar/raw/landing/<entity>/` are not captured as path lineage; that hop is documented by `_source_file` on every bronze row instead.

## Column lineage sample (system.access.column_lineage)

| source column | target column |
|---|---|
| gold.store_sku_daily.in_stock_at_close | gold.kpi_store_daily.in_stock_pct |
| gold.store_sku_daily.stockout_hours | gold.kpi_store_daily.on_shelf_availability |
| gold.store_sku_daily.trading_hours | gold.kpi_store_daily.on_shelf_availability |
| gold.store_sku_daily.units_requested_online | gold.kpi_store_daily.online_fill_rate |
| gold.store_sku_daily.units_shipped_online | gold.kpi_store_daily.online_fill_rate |
